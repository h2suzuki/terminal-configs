#!/usr/bin/env python3
"""
detect_cwd_pollution hook for Claude Code.

Legacy: user CLAUDE.md「Bash 運用」 § cwd 汚染を疑うエラーパターン より

PostToolUseFailure hook on Bash (official tool-failure-only
event; PostToolUse does not fire on failures by design). When a
failed Bash command's output contains cwd-pollution error
patterns, emits a brief advisory via
hookSpecificOutput.additionalContext naming payload.cwd. The
advisory is a reminder for Claude to compare cwd against its
mental expectation, not an independent verification.

Pattern scope:
  - "pathspec ... did not match" — git complaint about a path arg
    that didn't resolve in the current repo / cwd
  - relative-path "no such file or directory" — leading char is NOT
    "/", "~", or "." followed by "/", suggesting the path was
    resolved against cwd
  - relative-path "cannot open directory" — same as above

Absolute-path errors (e.g. `ls: cannot access '/nonexistent'`) are
NOT flagged: those are unrelated to cwd. The originating CLAUDE.md
rule explicitly targets "routine commands that suddenly fail" due
to cwd drift, not generic missing-file errors.

The hook deliberately does not call `pwd` in a subprocess: with
cwd= set on subprocess.run, `pwd` just echoes back the same path,
giving no independent diagnostic. The advisory references
payload.cwd so Claude can compare against its own mental model.

Always exits 0 (advisory; the tool has already failed by the time
PostToolUseFailure fires).
"""

from __future__ import annotations

import io
import json
import re
import sys

PATHSPEC_RE = re.compile(r"pathspec\s+'?[^'\s]+'?\s+did not match", re.IGNORECASE)
NOSUCHFILE_TEXT_RE = re.compile(
    r"no such file or directory|cannot open directory", re.IGNORECASE
)
# Capture paths quoted in the error line (most common format:
# `cmd: cannot access '<path>': No such file or directory`).
QUOTED_PATH_RE = re.compile(r"'([^']+)'" r'|"([^"]+)"')


def _looks_relative(p: str) -> bool:
    """True iff path looks resolved against cwd (not absolute / home / explicit ./)."""
    if not p:
        return False
    if p.startswith(("/", "~")):
        return False
    # `./foo` is technically cwd-relative but Claude explicitly typed it,
    # so cwd drift isn't surprising — skip it.
    if p.startswith("./") or p == ".":
        return False
    return True


def _emit(event_name: str, msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _collect_output(response: dict) -> str:
    chunks: list[str] = []
    for key in ("output", "stdout", "stderr", "error", "message", "tool_result"):
        v = response.get(key)
        if isinstance(v, str):
            chunks.append(v)
    return "\n".join(chunks)


def _is_pollution(output: str) -> bool:
    # pathspec is always cwd-relative inside its repo, so flag unconditionally
    if PATHSPEC_RE.search(output):
        return True
    # no-such-file / cannot-open-directory: scan line-by-line. In each line
    # that contains the error text, examine quoted path tokens — if any one
    # is cwd-relative, flag. If only absolute paths are quoted, don't flag.
    # If no path is quoted at all, conservative: don't flag.
    for line in output.splitlines():
        if not NOSUCHFILE_TEXT_RE.search(line):
            continue
        quoted_paths = [
            (m.group(1) or m.group(2)) for m in QUOTED_PATH_RE.finditer(line)
        ]
        for p in quoted_paths:
            if _looks_relative(p):
                return True
    return False


def _run(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("tool_name") != "Bash":
        return
    response = payload.get("tool_response") or {}
    if not isinstance(response, dict):
        return
    output = _collect_output(response)
    if not output:
        return
    if not _is_pollution(output):
        return
    cwd = payload.get("cwd")
    if not cwd or not isinstance(cwd, str):
        return
    event_name = payload.get("hook_event_name") or "PostToolUseFailure"
    _emit(
        event_name,
        "cwd-pollution パターンの error が Bash 出力に出ました。 "
        f"payload.cwd: {cwd}\n"
        "想定 cwd と一致するか確認してから、 推測 retry の前に "
        "`cd` でなく絶対パス / `git -C <repo>` 等で書き直すのを優先。",
    )


def main() -> int:
    # Force UTF-8 stdin so non-ASCII paths in error output don't blow up
    # under a non-UTF-8 locale (e.g. LANG=C).
    try:
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer, encoding="utf-8", errors="replace"
        )
    except Exception:
        pass
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        _run(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
