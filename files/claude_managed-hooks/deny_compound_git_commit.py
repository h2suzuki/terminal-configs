#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: deny `git commit` combined with shell operators
(`&&`, `||`, `;`, `|`).

Forces `git commit` standalone so the sibling check_commit_format /
check_commit_author hooks can parse the single-command form
unambiguously; compound forms expose bypass surfaces the per-command
regexes cannot reason about.

Exit:
  0: not a compound git-commit invocation (allow)
  2: compound `git commit` detected (deny)

Always exits 0 on any parse / matcher error (fail-open).
"""

import json
import re
import sys

COMPOUND_OPS = ("&&", "||", ";", "|")

# Match `git ... commit` past intervening flags; the flag-arg swallow keeps
# the substring `commit` inside `-c commit.X=Y` from reading as the subcommand.
GIT_COMMIT = re.compile(r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+commit\b(?![\w.])")

# Strip quoted strings to a single `_` placeholder (not empty) so downstream
# regex still sees the flag taking an arg, e.g. `-c "x"` becomes `-c _`.
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# Heredoc body strip: closing delimiter may be tab-indented under `<<-`, and
# trailing shell code on the opener line must survive (`<<EOF && git commit`).
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)


def _strip_heredoc(m: re.Match) -> str:
    """Replace heredoc body with `_`, keeping trailing shell code on the opener line."""
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
    if any(op in stripped for op in COMPOUND_OPS) and GIT_COMMIT.search(stripped):
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
