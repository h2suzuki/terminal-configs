#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: deny `git add` combined with shell operators
(`&&`, `||`, `;`, `|`). Forces `git add` standalone so the staged state
is settled before the subsequent `git commit` PreToolUse hooks fire.
Sibling to deny_compound_git_commit.py.

Exit:
  0: not a compound git-add invocation (allow)
  2: compound `git add` detected (deny)

Always exits 0 on any parse / matcher error (fail-open).
"""

import json
import re
import sys

COMPOUND_OPS = ("&&", "||", ";", "|")

# Detect `add` after `git` past intervening flags (`git -C /repo add` etc).
# Run against the stripped command so `echo "git add foo"` won't false-trigger.
GIT_ADD = re.compile(r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+add\b(?![\w.])")

# Strip quoted strings, substituting `_` (not empty) so `-c "x=y"` becomes
# `-c _` and the flag-arg regex still sees `-c` taking an arg.
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# Strip heredoc body but keep trailing shell code on the opener line
# (e.g. `... <<EOF && git add foo`); `<<-` allows a tab-indented delimiter.
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)


def _strip_heredoc(m: re.Match) -> str:
    """Replace a heredoc with `_` plus the opener line's trailing shell code."""
    return "_" + m.group(2)


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return 0
    stripped = HEREDOC.sub(_strip_heredoc, cmd)
    stripped = QUOTED.sub("_", stripped)
    if any(op in stripped for op in COMPOUND_OPS) and GIT_ADD.search(stripped):
        sys.stderr.write(
            "deny-compound-git-add: `git add` must run as a standalone Bash "
            "call. Compound forms with shell operators (`&&`, `||`, `;`, `|`) "
            "are not allowed.\n\n"
            "Reason: the subsequent `git commit` PreToolUse gates need a "
            "settled staged state; compound forms fire PreToolUse before bash "
            "runs and the index is still empty at that point.\n\n"
            "Retry: send `git add ...` as a single Bash invocation.\n"
        )
        return 2
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        return _run(payload)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
