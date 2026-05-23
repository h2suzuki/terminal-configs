#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: deny `git commit` invocations combined with
shell operators (`&&`, `||`, `;`, `|`).

Forces `git commit` to run as a standalone Bash call so the sibling
check_commit_format / check_commit_author hooks can parse the
single-command form unambiguously. Compound forms tangle multi-
heredoc / multi-quoting / cross-command env-var precedence and
expose bypass surfaces that the per-command regexes cannot reason
about.

Legacy: derived from genai-development-process/.claude/hooks/
deny-compound-git-commit.py (same logic, project-tailored rationale).
"""

import json
import re
import sys

COMPOUND_OPS = ("&&", "||", ";", "|")
GIT_COMMIT = re.compile(r"\bgit(?:\s+(?:-\S+|--\S+))*\s+commit\b")
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[\s\S]*?^\1\b", re.MULTILINE)


def main() -> int:
    payload = json.load(sys.stdin)
    cmd = payload.get("tool_input", {}).get("command", "")
    stripped = HEREDOC.sub("", cmd)
    stripped = QUOTED.sub("", stripped)
    if any(op in stripped for op in COMPOUND_OPS) and GIT_COMMIT.search(cmd):
        sys.stderr.write(
            "deny-compound-git-commit: `git commit` must run as a standalone "
            "Bash call. Compound forms with shell operators (`&&`, `||`, `;`, "
            "`|`) are not allowed.\n\n"
            "Reason: check_commit_format and check_commit_author parse the "
            "single-command form; compound forms tangle multi-heredoc and "
            "multi-quoting cases and create bypass surfaces.\n\n"
            "Retry: split into separate Bash invocations — first `git add ...`, "
            "then `git commit -m \"...\"` (or heredoc form) as another call.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
