#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: deny `git add` invocations combined with
shell operators (`&&`, `||`, `;`, `|`).

Sibling to deny_compound_git_commit.py. Forces `git add` to run as
a standalone Bash call so the staged state is settled before the
subsequent `git commit` PreToolUse hooks fire.

Legacy: derived from genai-development-process/.claude/hooks/
deny-compound-git-add.py.

Exit:
  0: not a compound git-add invocation (allow)
  2: compound `git add` detected (deny)

Always exits 0 on any parse / matcher error (fail-open).
"""

import json
import re
import sys

COMPOUND_OPS = ("&&", "||", ";", "|")

# Match `git ... add` allowing intervening flags with optional space- or
# `=`-separated args, so `git -C /repo add`, `git -c key=val add`, and
# `git --git-dir /x add` are detected. Matches GIT_ADD against the
# stripped command so `echo "git add foo"` doesn't false-trigger.
GIT_ADD = re.compile(r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+add\b(?![\w.])")

# Strip quoted strings first (single and double; backslash escapes inside
# double quotes). Substitutes a single `_` placeholder rather than empty
# string, so `-c "user.email=x"` becomes `-c _` and downstream regex still
# sees `-c` taking an arg.
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# Heredoc body strip: closing delimiter may be tab-indented under `<<-`,
# and the line containing the `<<DELIM` opener may carry trailing shell
# code that must be preserved (e.g. `... <<EOF && git add foo`).
# Pattern: opener up to end-of-its-line, then body until a line whose
# only whitespace-leading content is the delimiter word.
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)


def _strip_heredoc(m: re.Match) -> str:
    """Keep `_` placeholder + any trailing shell code on the opener line.

    `cat <<EOF && git add foo\\ncontent\\nEOF` reduces to
    `cat _ && git add foo\\n` — the body is stripped but the real
    compound operator and the real `git add` survive.
    """
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
