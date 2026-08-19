#!/usr/bin/env python3
"""SessionStart hook: freshen the shared memory clone in the background.

clone ok  -> unless git's own FETCH_HEAD is fresher than PULL_THROTTLE, spawn
             a detached `claude_memory_sync --pull` and return immediately, so
             the session never waits on the network (pull lands ~1-3s later).
clone gone -> tell the user + model that memory is closed until
             install_claude_extensions is re-run.
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
FETCH_STAMP = os.path.join(REPO_DIR, ".git", "FETCH_HEAD")
SYNC_LOG = REPO_DIR + ".sync.log"
PULL_THROTTLE = 900
CLOSED_MSG = (
    "memory-sync: 共有 memory clone が不在/破損です。 install_claude_extensions "
    "を再実行すると復旧します (それまで surface は既存 index のみ・entry 書込は閉塞)。"
)


def _fresh(path: str, window: int) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) < window
    except OSError:
        return False


def main() -> int:
    os.umask(0o002)
    try:
        sys.stdin.read()
    except Exception:
        pass
    if os.path.isdir(os.path.join(REPO_DIR, ".git")) and os.path.exists(SYNC_CLI):
        # A failed attempt leaves FETCH_HEAD stale, so it simply retries next start.
        if not _fresh(FETCH_STAMP, PULL_THROTTLE):
            try:
                log = open(SYNC_LOG, "a", encoding="utf-8")
            except OSError:
                log = None  # an unwritable foreign log must not veto the pull itself
            try:
                subprocess.Popen(
                    [sys.executable, SYNC_CLI, "--pull"],
                    stdout=log if log else subprocess.DEVNULL,
                    stderr=log if log else subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                pass
            finally:
                if log:
                    log.close()
        return 0
    # No throttle on purpose: a broken clone deserves a nag at every session start.
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
