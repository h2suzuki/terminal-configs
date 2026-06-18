#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: keep `git commit` safe in a shared git index.

Two denials, both protecting the staged state from cross-session damage:

1. Compound `git commit` (with `&&`, `||`, `;`, `|`) — forces a
   standalone call so the sibling check_commit_format / check_commit_author
   hooks can parse the single-command form unambiguously.
2. Broad `git commit` (`-a` / `--all` / `-i` / `--include` / pathless /
   whole-tree pathspec) — requires explicit file paths so a parallel Claude
   session's staged files in the same shared index are never swept into this
   session's commit.

Exit:
  0: standalone `git commit` naming explicit paths (allow), or not git-commit
  2: compound or broad `git commit` (deny)

Always exits 0 on any parse / matcher error (fail-open).
"""

import json
import re
import sys

COMPOUND_OPS = ("&&", "||", ";", "|")
WHOLE_TREE_PATHS = {".", "./", ":/", ":/.", "*"}

# Match `git ... commit` past intervening flags so `-c commit.X=Y` is not the subcommand.
GIT_COMMIT = re.compile(r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+commit\b(?![\w.])")

# Strip quoted strings to `_` so downstream regex still sees flag arguments.
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# Strip heredoc body while keeping trailing shell code on the opener line.
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)


def _strip_heredoc(m: re.Match) -> str:
    """Replace heredoc body with `_`, keeping trailing shell code on the opener line."""
    return "_" + m.group(2)


def _broad_commit_reason(stripped: str) -> str | None:
    """Reason a (non-compound) `git commit` commits beyond explicit paths, else None."""
    m = GIT_COMMIT.search(stripped)
    if not m:
        return None
    # Join `\`-newline continuations so a multi-line command's paths aren't truncated.
    tail = stripped[m.end() :].replace("\\\n", " ")
    tokens = tail.split("\n", 1)[0].split()
    if "--" in tokens:
        sep = tokens.index("--")
        opts = tokens[:sep]
        paths = tokens[sep + 1 :]
        has_sep = True
    else:
        opts = tokens
        paths = []
        has_sep = False

    amend_like = False
    has_all = False
    has_include = False
    for tok in opts:
        if tok.startswith("--"):
            name = tok.split("=", 1)[0]
            if name in {"--amend", "--fixup", "--squash"}:
                amend_like = True
            elif name == "--all":
                has_all = True
            elif name == "--include":
                has_include = True
            continue
        if tok.startswith("-"):
            for char in tok[1:]:
                if char in {"m", "F", "C", "c", "t", "S", "u"}:
                    break
                if char == "a":
                    has_all = True
                elif char == "i":
                    has_include = True

    if amend_like:
        return None
    if has_include:
        return "`-i` / `--include` also commits the whole staged index"
    if has_all:
        return "`-a` / `--all` stages every tracked change"
    if not has_sep:
        return "no `-- PATH` separator (a pathless commit takes the whole shared index)"
    if not paths:
        return "`--` names no path"
    for path in paths:
        if path in WHOLE_TREE_PATHS:
            return f"pathspec `{path}` stages the whole tree"
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
    if any(op in stripped for op in COMPOUND_OPS) and GIT_COMMIT.search(stripped):
        sys.stderr.write(
            "deny-compound-git-commit: `git commit` must run as a standalone "
            "Bash call. Compound forms with shell operators (`&&`, `||`, `;`, "
            "`|`) are not allowed.\n\n"
            "Reason: check_commit_format and check_commit_author parse the "
            "single-command form; compound forms tangle multi-heredoc and "
            "multi-quoting cases and create bypass surfaces.\n\n"
            "Retry: split into separate Bash invocations — first `git add ...`, "
            'then `git commit -m "..."` (or heredoc form) as another call.\n'
        )
        return 2
    reason = _broad_commit_reason(stripped)
    if reason:
        sys.stderr.write(
            "deny-broad-git-commit: `git commit` must name explicit file "
            f"paths ({reason}). A pathless git commit commits the entire "
            "shared index and can sweep a parallel Claude session's staged "
            "files into your commit.\n\n"
            'Retry: `git commit -m "..." -- files/a.py files/b.py`. '
            "`--amend` / `--fixup` / `--squash` remain allowed. This hook "
            "never modifies files or the index.\n"
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
