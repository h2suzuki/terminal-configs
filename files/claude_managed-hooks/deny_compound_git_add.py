#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: keep `git add` safe in a shared working tree.

Two denials, both protecting the staged state from cross-session damage:

1. Compound `git add` (with `&&`, `||`, `;`, `|`) — forces a standalone
   call so the index is settled before the `git commit` PreToolUse hooks
   fire. Sibling to deny_compound_git_commit.py.
2. Broad `git add` (`-A` / `--all` / `-u` / `--update` / `.` / `:/` /
   pathless) — requires explicit file paths so a parallel Claude session's
   uncommitted edits in the same working tree are never swept into this
   session's commit.

Exit:
  0: standalone `git add` naming explicit paths (allow), or not a git-add
  2: compound or broad `git add` (deny)

Always exits 0 on any parse / matcher error (fail-open).
"""

import json
import re
import sys

COMPOUND_OPS = ("&&", "||", ";", "|")

# Flags / pathspecs that stage more than the explicitly named files. In a
# shared working tree these sweep a parallel session's uncommitted edits.
BROAD_FLAGS = {"-A", "--all", "-u", "--update"}
WHOLE_TREE_PATHS = {".", "./", ":/", ":/.", "*"}

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


def _broad_add_reason(stripped: str) -> str | None:
    """Reason a (non-compound) `git add` stages beyond explicit paths, else None."""
    m = GIT_ADD.search(stripped)
    if not m:
        return None
    after_ddash = False
    has_path = False
    # Join `\`-newline continuations, then bound to the `git add` line.
    tail = stripped[m.end() :].replace("\\\n", " ")
    for tok in tail.split("\n", 1)[0].split():
        if not after_ddash and tok == "--":
            after_ddash = True
            continue
        if not after_ddash and tok.startswith("-"):
            if tok in BROAD_FLAGS:
                return f"`{tok}` stages every change"
            if not tok.startswith("--") and ("A" in tok[1:] or "u" in tok[1:]):
                return f"`{tok}` bundles -A/-u and stages every change"
            continue  # benign flag (-f / -v / -n / ...)
        if tok in WHOLE_TREE_PATHS:
            return f"pathspec `{tok}` stages the whole tree"
        has_path = True
    if not has_path:
        return "no explicit file path was given"
    return None


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
    if not GIT_ADD.search(stripped):
        return 0
    if any(op in stripped for op in COMPOUND_OPS):
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
    reason = _broad_add_reason(stripped)
    if reason:
        sys.stderr.write(
            "deny-broad-git-add: `git add` must name explicit file paths "
            f"({reason}). Staging everything (`-A` / `.` / `-u` / pathless) "
            "can sweep a parallel Claude session's uncommitted edits in this "
            "shared working tree into your commit — causing cross-session "
            "commits and lost work.\n\n"
            "Retry: list each path explicitly, e.g. "
            "`git add files/foo.py files/bar.py`. This hook never modifies "
            "files or the index.\n"
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
