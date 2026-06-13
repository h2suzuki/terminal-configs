#!/usr/bin/env python3
# /etc/claude-code/hooks/session_cleanup.py
#
# SessionEnd hook: removes this session's per-session temp files — the
# statusline cache (<cache>/claude-tui-statusline/<session_id>.json, written by
# statusline.sh) and the turn counter (<transcript>.turns plus session-keyed fallback
# <cache>/claude-turn-counter/<session_id>.turns, written by stop_checks.py's turn marker).
# It also drops this session's /tmp scratch dir (/tmp/claude-scratch-<session_id>/),
# the using-tmp skill's convention area for ephemeral files.
#
# SessionEnd does NOT fire on crash/kill, so abnormally-ended sessions would
# leak their files forever. To bound these areas we ALSO sweep entries
# older than CRUFT_TTL on clean exit (active sessions keep mtime fresh, so
# only true orphans are reaped). Every error is swallowed (exit 0) — teardown
# must never fail.

import glob
import json
import os
import shutil
import sys
import time

CRUFT_TTL = 7 * 86400  # reap orphans untouched for a week


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _sweep(directory, patterns):
    cutoff = time.time() - CRUFT_TTL
    for pat in patterns:
        for path in glob.glob(os.path.join(directory, pat)):
            try:
                if os.stat(path).st_mtime < cutoff:
                    os.remove(path)
            except OSError:
                pass


def _rmtree(path):
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def _clean_tmp_scratch(session_id):
    # using-tmp skill: per-session scratch at /tmp/claude-scratch-<id>.
    if session_id:
        _rmtree("/tmp/claude-scratch-" + session_id)
    cutoff = time.time() - CRUFT_TTL
    for path in glob.glob("/tmp/claude-scratch-*"):
        try:
            if os.path.isdir(path) and os.stat(path).st_mtime < cutoff:
                _rmtree(path)
        except OSError:
            pass


def main():
    payload = json.load(sys.stdin)
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    sl_dir = os.path.join(cache, "claude-tui-statusline")
    tc_dir = os.path.join(cache, "claude-turn-counter")

    session_id = payload.get("session_id") or ""
    if session_id:
        _rm(os.path.join(sl_dir, session_id + ".json"))
        _rm(os.path.join(tc_dir, session_id + ".turns"))
    transcript = payload.get("transcript_path") or ""
    if transcript:
        base = transcript[:-6] if transcript.endswith(".jsonl") else transcript
        _rm(base + ".turns")

    # Best-effort GC of orphans from sessions that did not fire SessionEnd
    # (includes leftover atomic-write temps .<session_id>.XXXXXX.json).
    _sweep(sl_dir, ("*.json", ".*.json"))
    _sweep(tc_dir, ("*.turns",))

    _clean_tmp_scratch(session_id)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # best-effort cleanup: never fail the session teardown
    sys.exit(0)
