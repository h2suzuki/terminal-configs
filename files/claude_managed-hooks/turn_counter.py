#!/usr/bin/env python3
# /etc/claude-code/hooks/turn_counter.py
#
# UserPromptSubmit hook: shows a per-session turn marker to the USER —
# turn count, wall-clock time, elapsed since the previous turn — without
# ever entering the model context. It emits the line via the JSON
# `systemMessage` field ("A systemMessage field is shown to you, not to
# Claude" — code.claude.com/docs/en/hooks), NOT via stdout/additionalContext
# (which on UserPromptSubmit WOULD be fed to the model).
#
# State lives in a per-session counter file next to the transcript
# (`<transcript>.turns`, two ints: count + last-turn epoch), guarded by
# flock for the read-modify-write. Fail-open everywhere: any error emits
# nothing and exits 0, so a counter glitch never blocks prompt submission.

import fcntl
import json
import os
import sys
import time


def _counter_path(payload):
    transcript = payload.get("transcript_path") or ""
    if transcript:
        base = transcript[:-6] if transcript.endswith(".jsonl") else transcript
        return base + ".turns"
    session_id = payload.get("session_id") or ""
    if not session_id:
        return None
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    d = os.path.join(cache, "claude-turn-counter")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, session_id + ".turns")


def _bump(path, now):
    # Locked read-modify-write; returns (count, last_epoch_before_bump).
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    with os.fdopen(fd, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        parts = f.read().split()
        count = last = 0
        if len(parts) >= 2:
            try:
                count, last = int(parts[0]), int(parts[1])
            except ValueError:
                count = last = 0
        count += 1
        f.seek(0)
        f.truncate()
        f.write("%d %d\n" % (count, now))
    return count, last


def _gap(elapsed):
    if elapsed >= 3600:
        return "+%dh%02dm" % (elapsed // 3600, (elapsed % 3600) // 60)
    if elapsed >= 60:
        return "+%dm%02ds" % (elapsed // 60, elapsed % 60)
    return "+%ds" % elapsed


def main():
    payload = json.load(sys.stdin)
    path = _counter_path(payload)
    if not path:
        return
    now = int(time.time())
    count, last = _bump(path, now)
    clock = time.strftime("%H:%M:%S", time.localtime(now))
    gap = _gap(now - last) if last > 0 else "start"
    print(json.dumps({"systemMessage": "⟳%d · %s · %s" % (count, clock, gap)}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block prompt submission
    sys.exit(0)
