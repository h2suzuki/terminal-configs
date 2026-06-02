#!/usr/bin/env python3
"""
Read-before-edit hook for Claude Code.

Use-case scenarios
==================

PostToolUse — fix knowledge state
---------------------------------
On Read or Write:
  Knowledge is now in Claude's context.
    Read  -> INSERT record (tool=Read, range = offset+limit, mtime_ns).
    Write -> INSERT record (tool=Write, range = whole file, mtime_ns).

On Edit, MultiEdit, or NotebookEdit:
  Exact post-edit content is uncertain — context cache is invalidated.
  No action required: the file's mtime change automatically excludes
  prior records from the current-mtime filter on the next check.

PreToolUse — gate or prompt the tool call
-----------------------------------------
On Read:
  Look up records at the file's current mtime.
    No Read/Write record  -> cache invalidated -> allow
                             (Read is justified, silent advisory).
    Read/Write record(s)  -> advise that the duplicate range is
                             already in context; allow.

On Write or NotebookEdit:
  Unconditional allow. Do nothing else.

On Edit or MultiEdit:
  Look up records at the file's current mtime.
    No Read/Write record  -> cache invalidated -> DENY with a
                             Read-before-Edit instruction.
    Read/Write record(s)  -> if any Write covers the whole file,
                             stay silent (full coverage).
                             Otherwise (Read records only), advise
                             that the Edit region may fall outside
                             the prior Read scope; allow.

Subcommands
===========

  record  PostToolUse hook for Read / Write. Appends an entry
          {tool, mtime_ns, [offset, limit | -]} to accesses_json.

  check   PreToolUse hook for Read / Edit / MultiEdit. Emits
          hookSpecificOutput per the scenarios above.

  Write and NotebookEdit PreToolUse, and Edit / MultiEdit /
  NotebookEdit PostToolUse, should not route through this hook
  (excluded at the settings.json matcher level — anchored
  `^(Read|Edit|MultiEdit)$` and `^(Read|Write)$`). The hook is
  defensive and early-returns on unexpected tools.


State lives in ~/.claude/hooks/state/read_mtime.sqlite3 (WAL mode).
Rows older than TTL_SECONDS (default 7 days) are pruned
opportunistically on each write. accesses_json is capped to the last
ACCESS_HISTORY_CAP entries per row.

Paths are canonicalised via `~`-expansion -> realpath against the
payload's `cwd`, so symlink and relative/absolute path variants
converge to a single state row. Tool inputs whose `file_path` is
non-string are rejected early.

cmd_record wraps the SELECT-then-UPSERT in a single
`BEGIN IMMEDIATE` transaction so two concurrent PostToolUse hooks
for the same (session_id, path) cannot lose an append.

`record` always exits 0. `check` exits 0 even when denying — the
deny is communicated via JSON `permissionDecision: "deny"`, not via
exit code, so hook bugs cannot accidentally block Claude.
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
RECORD_TOOLS = {"Read", "Write"}
CHECK_TOOLS = {"Read", "Edit", "MultiEdit"}
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


def _extract(payload: dict) -> tuple[str, str, str, dict]:
    if not isinstance(payload, dict):
        return "", "", "", {}
    tool = payload.get("tool_name") or ""
    sid = payload.get("session_id") or ""
    cwd = payload.get("cwd") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return tool, sid, "", {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    path = _canonical(raw_path, cwd)
    return tool, sid, path, tool_input


def _build_entry(tool: str, tool_input: dict, mtime_ns: int) -> dict:
    entry: dict = {"tool": tool, "mtime_ns": mtime_ns}
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
    tool, sid, path, tool_input = _extract(payload)
    if tool not in RECORD_TOOLS or not sid or not path:
        return
    mtime_ns = _file_mtime_ns(path)
    if mtime_ns is None:
        return
    now = int(time.time())
    entry = _build_entry(tool, tool_input, mtime_ns)

    conn = _open_db()
    try:
        # BEGIN IMMEDIATE acquires a RESERVED lock right away so concurrent
        # PostToolUse hooks for the same (session_id, path) cannot interleave
        # SELECT-then-UPSERT and clobber each other's append.
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT accesses_json FROM read_mtime "
                "WHERE session_id=? AND path=?",
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
    tool, sid, path, _ = _extract(payload)
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
            "SELECT accesses_json FROM read_mtime "
            "WHERE session_id=? AND path=?",
            (sid, path),
        ).fetchone()
    finally:
        conn.close()

    accesses = _load_accesses(row[0]) if row else []
    same_mtime = [a for a in accesses if a.get("mtime_ns") == current_ns]

    if tool == "Read":
        if same_mtime:
            formatted = ", ".join(_format_entry(a) for a in same_mtime)
            _emit_allow(
                f"{path}: current mtime に対し既に "
                f"{len(same_mtime)} 件 Read/Write 済 [{formatted}]。 "
                "重複 scope の Read は context に既保持。 "
                "新 scope (異なる offset/limit) の Read は問題ありません。"
            )
        return

    # Edit / MultiEdit
    if same_mtime:
        if any(a.get("tool") == "Write" for a in same_mtime):
            return
        formatted = ", ".join(_format_entry(a) for a in same_mtime)
        _emit_allow(
            f"{path}: current mtime に対する Read scope [{formatted}] あり。 "
            "Edit 対象 region が Read scope 外の場合は再 Read 推奨 "
            "(Write は無いため file 全件は cover されていません)。"
        )
        return

    # No Read/Write at current mtime → cache invalidated, must Read first.
    # 簡潔指示形。 path は Edit input 側で既知なので reason に含めない。
    if not accesses:
        reason = "未 Read。 編集前に、 Read で内容の確認が必要。"
    else:
        reason = "前回の Read から内容が変化。 編集前に、 再 Read で現内容の確認が必要。"
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
