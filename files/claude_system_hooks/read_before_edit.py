#!/usr/bin/env python3
"""
Read-before-edit hook for Claude Code.

Legacy: org CLAUDE.md「a. コーディング」より (「編集前に git status / ls -la で mtime 確認」 bullet を hook 化)

Subcommands:
  record   PostToolUse hook for Read / Edit / Write / MultiEdit /
           NotebookEdit. Records the file's post-tool mtime keyed by
           (session_id, canonical_path).

  check    PreToolUse hook for Edit / Write / MultiEdit /
           NotebookEdit. Emits hookSpecificOutput.additionalContext
           when the target file's current mtime differs from the
           recorded value for this session, or when no record exists
           yet. Never blocks the tool call.

State lives in ~/.claude/hooks/state/read_mtime.sqlite3 (WAL mode).
Rows older than TTL_SECONDS (default 7 days) are pruned
opportunistically on each write.

Paths are canonicalised via os.path.realpath against the payload's
`cwd`, so symlink and relative/absolute path variants converge to a
single state row.

Exit code is always 0 (fail-open) so that hook bugs never block Claude.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

TTL_SECONDS = 7 * 24 * 3600
DB_PATH = Path.home() / ".claude" / "hooks" / "state" / "read_mtime.sqlite3"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
RECORD_TOOLS = EDIT_TOOLS | {"Read"}


def _open_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=2.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS read_mtime (
            session_id  TEXT NOT NULL,
            path        TEXT NOT NULL,
            mtime_ns    INTEGER NOT NULL,
            recorded_at INTEGER NOT NULL,
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
    if not raw_path:
        return ""
    if not os.path.isabs(raw_path) and cwd:
        raw_path = os.path.join(cwd, raw_path)
    return os.path.realpath(raw_path)


def _emit(event_name: str, msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "permissionDecision": "allow",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _extract(payload: dict) -> tuple[str, str, str]:
    tool = payload.get("tool_name") or ""
    sid = payload.get("session_id") or ""
    cwd = payload.get("cwd") or ""
    tool_input = payload.get("tool_input") or {}
    raw_path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or ""
    )
    path = _canonical(raw_path, cwd)
    return tool, sid, path


def cmd_record(payload: dict) -> None:
    tool, sid, path = _extract(payload)
    if tool not in RECORD_TOOLS or not sid or not path:
        return
    mtime_ns = _file_mtime_ns(path)
    if mtime_ns is None:
        return
    now = int(time.time())
    with _open_db() as conn:
        conn.execute(
            "INSERT INTO read_mtime(session_id, path, mtime_ns, recorded_at) "
            "VALUES(?, ?, ?, ?) "
            "ON CONFLICT(session_id, path) DO UPDATE SET "
            "mtime_ns=excluded.mtime_ns, recorded_at=excluded.recorded_at",
            (sid, path, mtime_ns, now),
        )
        _prune(conn)


def cmd_check(payload: dict) -> None:
    tool, sid, path = _extract(payload)
    if tool not in EDIT_TOOLS or not sid or not path:
        return
    if not os.path.exists(path):
        return  # new-file Write: nothing to compare
    current_ns = _file_mtime_ns(path)
    if current_ns is None:
        return
    with _open_db() as conn:
        row = conn.execute(
            "SELECT mtime_ns FROM read_mtime WHERE session_id=? AND path=?",
            (sid, path),
        ).fetchone()
    if row is None:
        _emit(
            "PreToolUse",
            f"{path}: 本セッションで未 Read のまま編集しようとしています。"
            "書き換え前に Read してください。",
        )
    elif current_ns != row[0]:
        delta_s = (current_ns - row[0]) / 1_000_000_000
        _emit(
            "PreToolUse",
            f"{path}: 直近 Read 後に disk 側 mtime が "
            f"{delta_s:+.3f}s 変化しています。"
            "他者変更の可能性があるため、Edit 前に再 Read してください。",
        )


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
