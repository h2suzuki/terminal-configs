#!/usr/bin/env python3
"""SessionStart hook: freshen the shared memory clone in the background.

clone ok  -> at most once per PULL_THROTTLE, spawn a detached
             `claude_memory_sync --pull` and return immediately, so the
             session never waits on the network (pull lands ~1-3s later).
clone gone -> once per WARN_THROTTLE, tell the user + model that memory is
             closed until install_claude_extensions is re-run.
Always exits 0 (fail-open): a hook bug must never break session start.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

REPO_DIR = "/var/lib/claude-rag-memory/claude-lessons-learned"
SYNC_CLI = "/usr/local/bin/claude_memory_sync"
ATTEMPT_STAMP = REPO_DIR + ".pull-attempt"
WARN_STAMP = REPO_DIR + ".missing-warned"
SYNC_LOG = REPO_DIR + ".sync.log"
PULL_THROTTLE = 900
WARN_THROTTLE = 86400
CLOSED_MSG = (
    "memory-sync: 共有 memory clone が不在/破損です。 install_claude_extensions "
    "を再実行すると復旧します (それまで surface は既存 index のみ・entry 書込は閉塞)。"
)


def _fresh(path: str, window: int) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) < window
    except OSError:
        return False


def _touch(path: str) -> None:
    # Best-effort: a foreign-owned stamp may be unwritable; the throttle then
    # just re-fires, which only costs a redundant background pull/warning.
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("%d\n" % int(time.time()))
    except OSError:
        pass


def main() -> int:
    os.umask(0o002)
    try:
        sys.stdin.read()
    except Exception:
        pass
    if os.path.isdir(os.path.join(REPO_DIR, ".git")) and os.path.exists(SYNC_CLI):
        if not _fresh(ATTEMPT_STAMP, PULL_THROTTLE):
            _touch(ATTEMPT_STAMP)
            try:
                with open(SYNC_LOG, "a", encoding="utf-8") as log:
                    subprocess.Popen(
                        [sys.executable, SYNC_CLI, "--pull"],
                        stdout=log,
                        stderr=log,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True,
                    )
            except OSError:
                pass
        return 0
    if not _fresh(WARN_STAMP, WARN_THROTTLE):
        _touch(WARN_STAMP)
        out = {
            "systemMessage": CLOSED_MSG,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": CLOSED_MSG,
            },
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
