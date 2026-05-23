#!/usr/bin/env python3
"""
detect_cwd_pollution hook for Claude Code.

Legacy: user CLAUDE.md「Bash 運用」 § cwd 汚染を疑うエラーパターン より

PostToolUseFailure hook on Bash (official tool-failure-only
event; PostToolUse does not fire on failures by design). When the
failed Bash command's output contains cwd-pollution error
patterns, emits a brief advisory via
hookSpecificOutput.additionalContext naming payload.cwd. The
advisory is a reminder for Claude to compare cwd against its
mental expectation, not an independent verification.

Patterns matched:
  - "no such file or directory"
  - "cannot open directory"
  - "pathspec ... did not match"

The hook only sees failed tool calls (PostToolUseFailure
guarantee), so there is no exit-code filter — every fire is by
definition a failed Bash invocation. Skip only if payload.cwd is
missing.

The hook deliberately does not call `pwd` in a subprocess: with
cwd= set on subprocess.run, `pwd` just echoes back the same path,
giving no independent diagnostic. The advisory references
payload.cwd so Claude can compare against its own mental model.

Always exits 0 (advisory; the tool has already failed by the time
PostToolUseFailure fires).
"""

from __future__ import annotations

import json
import re
import sys

POLLUTION_PATTERNS = [
    re.compile(r"no such file or directory", re.IGNORECASE),
    re.compile(r"cannot open directory", re.IGNORECASE),
    re.compile(r"pathspec .* did not match", re.IGNORECASE),
]


def _emit(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUseFailure",
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


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    response = payload.get("tool_response") or {}
    if not isinstance(response, dict):
        return 0
    output = _collect_output(response)
    if not output:
        return 0
    if not any(p.search(output) for p in POLLUTION_PATTERNS):
        return 0
    cwd = payload.get("cwd")
    if not cwd:
        return 0
    _emit(
        "cwd-pollution パターンの error が Bash 出力に出ました。 "
        f"payload.cwd: {cwd}\n"
        "想定 cwd と一致するか確認してから、 推測 retry の前に "
        "`cd` でなく絶対パス / `git -C <repo>` 等で書き直すのを優先。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
