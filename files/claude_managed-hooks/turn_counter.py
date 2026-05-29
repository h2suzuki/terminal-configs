#!/usr/bin/env python3
# /etc/claude-code/hooks/turn_counter.py
#
# UserPromptSubmit hook: shows a per-session turn marker to the USER —
# wall-clock time, turn count, context size, elapsed since the previous
# turn — without ever entering the model context. Emitted via the JSON
# `systemMessage` field ("A systemMessage field is shown to you, not to
# Claude" — code.claude.com/docs/en/hooks), NOT stdout/additionalContext
# (which on UserPromptSubmit WOULD be fed to the model).
#
# Turn count + last-turn epoch live in `<transcript>.turns`, flock-guarded
# for the RMW. Context size and the session-start epoch both come from the
# per-session statusline cache that statusline.sh writes
# (.../claude-tui-statusline/<session_id>.json: .stdin.context_window
# .total_input_tokens and .session_started_epoch). The context field is
# omitted if that file is absent; the first prompt shows time since the
# session start (falling back to "(first prompt)" if unknown). Output is
# pure ASCII — earlier "⟳N · …" glyphs garbled in some terminals. Fail-open
# everywhere: any error drops the field or emits nothing and exits 0, so a
# glitch never blocks prompt submission.

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


def _statusline(session_id):
    # Parsed per-session statusline cache, or {} if absent/unreadable.
    if not session_id:
        return {}
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(cache, "claude-tui-statusline", session_id + ".json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _context_size(sl):
    # Context window size = total input tokens, from the statusline cache.
    cw = (sl.get("stdin") or {}).get("context_window") or {}
    n = cw.get("total_input_tokens")
    if n is None:
        cu = cw.get("current_usage") or {}
        n = (cu.get("input_tokens", 0) + cu.get("cache_read_input_tokens", 0)
             + cu.get("cache_creation_input_tokens", 0)) or None
    return n


def _gap(elapsed):
    if elapsed >= 3600:
        return "%d hr %d min" % (elapsed // 3600, (elapsed % 3600) // 60)
    if elapsed >= 60:
        return "%d min" % (elapsed // 60)
    return "%d sec" % elapsed


def main():
    payload = json.load(sys.stdin)
    path = _counter_path(payload)
    if not path:
        return
    now = int(time.time())
    count, last = _bump(path, now)
    sl = _statusline(payload.get("session_id"))
    parts = [time.strftime("%H:%M:%S", time.localtime(now)), "Turn #%d" % count]
    ctx = _context_size(sl)
    if ctx is not None:
        parts.append("Context %dK" % round(ctx / 1000.0))
    if last > 0:
        parts.append("(%s passed since the last prompt)" % _gap(now - last))
    else:
        started = sl.get("session_started_epoch")
        if isinstance(started, (int, float)) and 0 < started <= now:
            parts.append("(%s passed since the session start)" % _gap(now - int(started)))
        else:
            parts.append("(first prompt)")
    print(json.dumps({"systemMessage": " ".join(parts)}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block prompt submission
    sys.exit(0)
