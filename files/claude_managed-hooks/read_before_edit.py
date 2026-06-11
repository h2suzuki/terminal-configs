#!/usr/bin/env python3
"""
Read-before-edit hook for Claude Code.

Use-case scenarios
==================

PostToolUse — fix knowledge state
---------------------------------
On Read / Write / Edit / MultiEdit: INSERT record {tool, agent_id, mtime_ns}
(Read adds offset+limit). Edit / MultiEdit record the post-edit mtime so the
editing agent's own next Edit passes without a re-Read.
On NotebookEdit: no action (not routed; its PreToolUse is unconditional allow).

PreToolUse — gate or prompt the tool call
-----------------------------------------
A record is "own" when session_id + agent_id match the caller (main loop
agent_id = null). An own record at the file's current mtime means the caller
produced or already saw the current content.
On Read:
  Own record(s) at current mtime -> advise duplicate range already in context.
  Otherwise -> allow silently.
On Write / NotebookEdit: unconditional allow.
On Edit / MultiEdit:
  Own record at current mtime -> allow silently (prior Read, own Write, or
  own successful Edit).
  Sibling-agent Write / Edit / MultiEdit at current mtime -> DENY (content
  unseen here).
  Otherwise -> DENY: never read by this agent, or changed since its Read.

Subcommands
===========

  record  PostToolUse for Read / Write / Edit / MultiEdit. Appends an access entry.
  check   PreToolUse for Read / Edit / MultiEdit. Emits hookSpecificOutput per above.

  Write / NotebookEdit PreToolUse and NotebookEdit PostToolUse must not route
  here (excluded at the settings.json matcher — anchored `^(Read|Edit|MultiEdit)$`
  and `^(Read|Write|Edit|MultiEdit)$`). The hook is defensive and early-returns
  on unexpected tools.

State lives in ~/.claude/hooks/state/read_mtime.sqlite3 (WAL). Rows older than
TTL_SECONDS (default 7 days) are pruned opportunistically on each write;
accesses_json is capped to the last ACCESS_HISTORY_CAP entries per row.

Paths are canonicalised via `~`-expansion -> realpath against the payload's `cwd`,
so symlink and relative/absolute variants converge to one state row. Non-string
`file_path` is rejected early.

cmd_record wraps SELECT-then-UPSERT in one `BEGIN IMMEDIATE` transaction so two
concurrent PostToolUse hooks for the same (session_id, path) cannot lose an append.

`record` always exits 0. `check` exits 0 even when denying — the deny rides JSON
`permissionDecision: "deny"`, not the exit code, so hook bugs cannot block Claude.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

TTL_SECONDS = 7 * 24 * 3600
ACCESS_HISTORY_CAP = 50
DB_PATH = Path.home() / ".claude" / "hooks" / "state" / "read_mtime.sqlite3"
RECORD_TOOLS = {"Read", "Write", "Edit", "MultiEdit"}
CHECK_TOOLS = {"Read", "Edit", "MultiEdit"}
MUTATING_TOOLS = {"Write", "Edit", "MultiEdit"}
EXPECTED_COLUMNS = {"session_id", "path", "recorded_at", "accesses_json"}


def _open_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None gives us manual control over transactions so
    # cmd_record can use BEGIN IMMEDIATE to serialize concurrent appends.
    conn = sqlite3.connect(DB_PATH, timeout=2.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(read_mtime)").fetchall()}
    if cols and cols != EXPECTED_COLUMNS:
        conn.execute("DROP TABLE IF EXISTS read_mtime")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS read_mtime (
            session_id    TEXT NOT NULL,
            path          TEXT NOT NULL,
            recorded_at   INTEGER NOT NULL,
            accesses_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (session_id, path)
        )
        """
    )
    return conn


def _prune(conn: sqlite3.Connection) -> None:
    cutoff = int(time.time()) - TTL_SECONDS
    conn.execute("DELETE FROM read_mtime WHERE recorded_at < ?", (cutoff,))


def _file_mtime_ns(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _canonical(raw_path: str, cwd: str) -> str:
    if not isinstance(raw_path, str) or not raw_path:
        return ""
    expanded = os.path.expanduser(raw_path)
    if not os.path.isabs(expanded):
        base = cwd if cwd else os.getcwd()
        expanded = os.path.join(base, expanded)
    return os.path.realpath(expanded)


def _emit_allow(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _agent_of(obj: dict) -> str | None:
    agent = obj.get("agent_id")
    return agent if isinstance(agent, str) and agent else None


def _extract(payload: dict) -> tuple[str, str, str | None, str, dict]:
    if not isinstance(payload, dict):
        return "", "", None, "", {}
    tool = payload.get("tool_name") or ""
    sid = payload.get("session_id") or ""
    agent = _agent_of(payload)
    cwd = payload.get("cwd") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return tool, sid, agent, "", {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    path = _canonical(raw_path, cwd)
    return tool, sid, agent, path, tool_input


def _build_entry(tool: str, tool_input: dict, mtime_ns: int, agent: str | None) -> dict:
    entry: dict = {"tool": tool, "mtime_ns": mtime_ns, "agent_id": agent}
    if tool == "Read":
        entry["offset"] = tool_input.get("offset")
        entry["limit"] = tool_input.get("limit")
    return entry


def _load_accesses(blob: str | None) -> list[dict]:
    try:
        data = json.loads(blob or "[]")
        if isinstance(data, list):
            return [a for a in data if isinstance(a, dict)]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _format_entry(a: dict) -> str:
    tool = a.get("tool") or "?"
    if tool == "Read":
        return f"Read(offset={a.get('offset')}, limit={a.get('limit')})"
    if tool == "Write":
        return "Write()"
    return f"{tool}()"


def cmd_record(payload: dict) -> None:
    tool, sid, agent, path, tool_input = _extract(payload)
    if tool not in RECORD_TOOLS or not sid or not path:
        return
    mtime_ns = _file_mtime_ns(path)
    if mtime_ns is None:
        return
    now = int(time.time())
    entry = _build_entry(tool, tool_input, mtime_ns, agent)

    conn = _open_db()
    try:
        # RESERVED lock up front so concurrent same-(session_id, path) hooks
        # cannot interleave SELECT-then-UPSERT and clobber each other's append.
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT accesses_json FROM read_mtime WHERE session_id=? AND path=?",
                (sid, path),
            ).fetchone()
            accesses = _load_accesses(row[0]) if row else []
            accesses.append(entry)
            if len(accesses) > ACCESS_HISTORY_CAP:
                accesses = accesses[-ACCESS_HISTORY_CAP:]
            conn.execute(
                "INSERT INTO read_mtime(session_id, path, recorded_at, accesses_json) "
                "VALUES(?, ?, ?, ?) "
                "ON CONFLICT(session_id, path) DO UPDATE SET "
                "recorded_at=excluded.recorded_at, "
                "accesses_json=excluded.accesses_json",
                (sid, path, now, json.dumps(accesses)),
            )
            _prune(conn)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def cmd_check(payload: dict) -> None:
    tool, sid, agent, path, _ = _extract(payload)
    if tool not in CHECK_TOOLS or not sid or not path:
        return
    if not os.path.exists(path):
        return
    current_ns = _file_mtime_ns(path)
    if current_ns is None:
        return

    conn = _open_db()
    try:
        row = conn.execute(
            "SELECT accesses_json FROM read_mtime WHERE session_id=? AND path=?",
            (sid, path),
        ).fetchone()
    finally:
        conn.close()

    accesses = _load_accesses(row[0]) if row else []
    own = [a for a in accesses if _agent_of(a) == agent]
    own_now = [a for a in own if a.get("mtime_ns") == current_ns]

    if tool == "Read":
        if own_now:
            formatted = ", ".join(_format_entry(a) for a in own_now)
            _emit_allow(
                f"{path}: current mtime に対し既に "
                f"{len(own_now)} 件 Read/Write/Edit 済 [{formatted}]。 "
                "重複 scope の Read は context に既保持。 "
                "新 scope (異なる offset/limit) の Read は問題ありません。"
            )
        return

    # Edit / MultiEdit: own record at current mtime = content already known.
    if own_now:
        return

    sibling_mut = [
        a
        for a in accesses
        if a.get("mtime_ns") == current_ns
        and _agent_of(a) != agent
        and a.get("tool") in MUTATING_TOOLS
    ]
    # 文面は意図的に冗長 (hook 誤読防止 + corrective 行動の書き下し)。 trim せず維持。
    if sibling_mut:
        reason = (
            "同じ session の別 agent がこのファイルを更新しているため、現在の内容は"
            "この agent からまだ見えていません。お手数ですが、該当範囲を Read してから"
            "編集してください。Read 後はこの hook は deny しません (内容差分により "
            "Edit の old_string 調整が必要な場合があります。hook 自身はファイルを"
            "変更していません)。"
        )
    elif own:
        reason = (
            "前回内容を確認した時点からファイルが更新されています。お手数ですが、"
            "該当範囲を Read し直してから編集してください。Read 後はこの hook は "
            "deny しません (内容差分により Edit の old_string 調整が必要な場合が"
            "あります。hook 自身はファイルを変更していません)。"
        )
    else:
        reason = (
            "このファイルはまだ Read していません。お手数ですが、編集の前に Read で"
            "内容を確認してください。Read 後はこの hook は deny しません。"
        )
    _emit_deny(reason)


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    sub = sys.argv[1]
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        if sub == "record":
            cmd_record(payload)
        elif sub == "check":
            cmd_check(payload)
    except sqlite3.Error:
        pass
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
