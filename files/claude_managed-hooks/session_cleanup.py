#!/usr/bin/env python3
# /etc/claude-code/hooks/session_cleanup.py
#
# SessionEnd hook: removes this session's per-session temp files — the
# statusline cache (<cache>/claude-tui-statusline/<session_id>.json,
# written by statusline.sh) and the turn counter (<transcript>.turns,
# written by turn_counter.py). Best-effort: SessionEnd does not fire on
# crash/kill, and every error is swallowed (exit 0) — leftover files are
# harmless and overwritten next session.

import json
import os
import sys


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def main():
    payload = json.load(sys.stdin)
    session_id = payload.get("session_id") or ""
    if session_id:
        cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        _rm(os.path.join(cache, "claude-tui-statusline", session_id + ".json"))
    transcript = payload.get("transcript_path") or ""
    if transcript:
        base = transcript[:-6] if transcript.endswith(".jsonl") else transcript
        _rm(base + ".turns")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # best-effort cleanup: never fail the session teardown
    sys.exit(0)
