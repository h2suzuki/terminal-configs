#!/usr/bin/env python3
"""PreToolUse(Bash) hook: keep working-tree todos.md structurally compact.

Purpose
=======
Before a git commit naming todos.md, validate the working-tree file's block size,
checkbox item size, and required metadata keys.

Exit:
  0: command is outside scope or working-tree todos.md passes
  2: working-tree todos.md violates a structural rule

Always exits 0 on parse, git, file, or matcher errors (fail-open).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

MAX_BLOCK_LINES = 40
MAX_ITEM_LINES = 6
REQUIRED_KEYS = ("起票:", "Goal:", "Exit Criteria:")
GIT_OPTIONS_WITH_VALUES = {
    "-C",
    "-c",
    "--config-env",
    "--exec-path",
    "--git-dir",
    "--namespace",
    "--work-tree",
}


def is_todos_commit(command: str) -> bool:
    """Return whether command text names a git commit and todos.md."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if "--" not in tokens:
        return False
    separator = tokens.index("--")
    if not tokens or os.path.basename(tokens[0]) != "git":
        return False
    index = 1
    while index < separator:
        token = tokens[index]
        if token == "commit":
            return any(
                os.path.normpath(path) == "todos.md" for path in tokens[separator + 1 :]
            )
        if not token.startswith("-"):
            return False
        index += 2 if token in GIT_OPTIONS_WITH_VALUES else 1
    return False


def working_todos(cwd: str) -> str:
    """Resolve the repository, then return its working-tree todos.md file."""
    root = subprocess.check_output(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
    with open(os.path.join(root, "todos.md"), encoding="utf-8") as handle:
        return handle.read()


def lint(text: str) -> list[str]:
    """Return deterministic descriptions of todos.md structural violations."""
    lines = text.splitlines()
    violations: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("### "):
            index += 1
            continue
        name = lines[index][4:].strip()
        start = index
        index += 1
        while index < len(lines) and not (
            lines[index].startswith("### ") or lines[index].startswith("## ")
        ):
            index += 1
        block = lines[start:index]
        if len(block) > MAX_BLOCK_LINES:
            violations.append(f"block {name!r}: {len(block)} lines")
        for key in REQUIRED_KEYS:
            if not any(line.startswith(key) for line in block):
                violations.append(f"block {name!r}: missing {key}")
        item_index = 1
        while item_index < len(block):
            if not block[item_index].startswith(("- [ ]", "- [x]")):
                item_index += 1
                continue
            item = block[item_index]
            item_lines = 1
            item_index += 1
            while item_index < len(block) and block[item_index].startswith("  "):
                item_lines += 1
                item_index += 1
            if item_lines > MAX_ITEM_LINES:
                violations.append(
                    f"block {name!r}: item {item[:30]!r}: {item_lines} lines"
                )
    return violations


def _run(payload: object) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    cwd = payload.get("cwd")
    if not isinstance(command, str) or not isinstance(cwd, str):
        return 0
    if not is_todos_commit(command):
        return 0
    violations = lint(working_todos(cwd))
    if not violations:
        return 0
    sys.stderr.write("todos-structure:\n")
    sys.stderr.write("".join(f"- {violation}\n" for violation in violations))
    sys.stderr.write(
        "経緯は commit message か git 履歴へ、block は 起票 / Goal / "
        "Exit Criteria / Work file だけにする\n"
    )
    return 2


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
