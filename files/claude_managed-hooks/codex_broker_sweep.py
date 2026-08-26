#!/usr/bin/env python3
"""SessionStart / worktree-remove hook that reaps orphaned codex broker processes and logs recurrences."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import datetime

WORKTREE_RE = re.compile(r"\bgit\b(?:\s+-C\s+\S+)?\s+worktree\s+(?:remove|prune)\b")
SUMMARY_RE = re.compile(r"keep=(\d+)\s+reap=(\d+)\s+stale=(\d+)")
FREED_RE = re.compile(r"回収で解放=\s*(\d+)\s*MB")
DEFAULT_LEDGER = os.path.expanduser(
    "~/.claude/hooks/state/codex_broker_sweep/ledger.jsonl"
)
DEFAULT_TIMEOUT = 20.0


def ledger_path() -> str:
    return os.environ.get("CODEX_BROKER_SWEEP_LEDGER") or DEFAULT_LEDGER


def should_sweep(payload: dict) -> tuple[bool, str | None]:
    """Return (trigger, command) — command is set only for a matched PostToolUse worktree call."""
    event = payload.get("hook_event_name")
    if event == "SessionStart":
        return True, None
    if event == "PostToolUse" and payload.get("tool_name") == "Bash":
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if isinstance(command, str) and WORKTREE_RE.search(command):
            return True, command
    return False, None


def acquire_lock(lock_path: str):
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return None
        raise
    return handle


def run_reaper(timeout: float) -> subprocess.CompletedProcess | None:
    binary = os.environ.get("CODEX_BROKER_SWEEP_BIN") or "codex_broker_reap"
    try:
        return subprocess.run(
            [binary, "--apply"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(
            f"codex_broker_sweep: reaper unavailable ({exc.__class__.__name__})\n"
        )
        return None


def excerpt(text: str) -> str:
    return text.strip()[:200]


def parse_summary(stdout: str) -> tuple[int, int, int, int] | None:
    summary = SUMMARY_RE.search(stdout)
    freed = FREED_RE.search(stdout)
    if not summary or not freed:
        return None
    keep, reap, stale = (int(group) for group in summary.groups())
    return keep, reap, stale, int(freed.group(1))


def append_ledger(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def sweep(payload: dict, command: str | None) -> None:
    timeout = float(os.environ.get("CODEX_BROKER_SWEEP_TIMEOUT") or DEFAULT_TIMEOUT)
    proc = run_reaper(timeout)
    if proc is None:
        return
    if proc.returncode != 0:
        detail = f" ({excerpt(proc.stderr)})" if proc.stderr else ""
        sys.stderr.write(
            f"codex_broker_sweep: reaper exited {proc.returncode}{detail}\n"
        )
        return
    parsed = parse_summary(proc.stdout)
    if parsed is None:
        detail = f" ({excerpt(proc.stderr)})" if proc.stderr else ""
        sys.stderr.write(
            f"codex_broker_sweep: unparsable reaper output (exit 0){detail}\n"
        )
        return
    keep, reap, stale, freed = parsed
    if reap + stale <= 0:
        return
    path = ledger_path()
    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": payload.get("hook_event_name"),
        "session_id": payload.get("session_id"),
        "cwd": payload.get("cwd"),
        "keep": keep,
        "reap": reap,
        "stale": stale,
        "freed_mb": freed,
    }
    if command is not None:
        record["command"] = command
    append_ledger(path, record)
    print(
        f"codex broker 掃引: reap {reap} / stale {stale} / 解放 {freed} MB (台帳 {path})"
    )


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return
    if not isinstance(payload, dict):
        return
    trigger, command = should_sweep(payload)
    if not trigger:
        return
    lock_path = os.path.join(os.path.dirname(ledger_path()), "lock")
    handle = acquire_lock(lock_path)
    if handle is None:
        return
    try:
        sweep(payload, command)
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"codex_broker_sweep: {exc!r}\n")
    sys.exit(0)
