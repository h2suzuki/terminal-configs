#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: deny `git add` invocations combined with
shell operators (`&&`, `||`, `;`, `|`).

Sibling to deny_compound_git_commit.py. Forces `git add` to run as
a standalone Bash call so the staged state is settled before the
subsequent `git commit` PreToolUse hooks fire.

Legacy: derived from genai-development-process/.claude/hooks/
deny-compound-git-add.py.
"""

import json
import re
import sys

COMPOUND_OPS = ("&&", "||", ";", "|")
GIT_ADD = re.compile(r"\bgit(?:\s+(?:-\S+|--\S+))*\s+add\b")
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[\s\S]*?^\1\b", re.MULTILINE)


def main() -> int:
    payload = json.load(sys.stdin)
    cmd = payload.get("tool_input", {}).get("command", "")
    stripped = HEREDOC.sub("", cmd)
    stripped = QUOTED.sub("", stripped)
    if any(op in stripped for op in COMPOUND_OPS) and GIT_ADD.search(cmd):
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


if __name__ == "__main__":
    sys.exit(main())
