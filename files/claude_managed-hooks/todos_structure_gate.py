#!/usr/bin/env python3
"""PreToolUse(Bash) hook: keep working-tree todos.md a short cross-session handoff summary.

Purpose
=======
Before a git commit naming todos.md, validate the working-tree file's total size and entry size.
Decision-bearing added units also require consent evidence or a non-decision marker.

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

MAX_FILE_LINES = 30
MAX_ENTRY_LINES = 3
DECISION_WORDS = ("決裁", "承認", "合意", "採用")
CONSENT_MARKERS = ("提案中", "発話証跡なし", "要確認", "未承認", "無承認", "承認不備", "不採用")  # fmt: skip
GIT_OPTIONS_WITH_VALUES = {
    "-C",
    "-c",
    "--config-env",
    "--exec-path",
    "--git-dir",
    "--namespace",
    "--work-tree",
}


def todos_commit_target(command: str, cwd: str) -> str | None:
    """Return the working-tree todos.md path for a matching git commit."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens or os.path.basename(tokens[0]) != "git":
        return None
    index = 1
    while index < len(tokens) and tokens[index] != "commit":
        token = tokens[index]
        if token == "--" or not token.startswith("-"):
            return None
        if token == "-C":
            if index + 1 >= len(tokens):
                return None
            cwd = os.path.join(cwd, tokens[index + 1])
            index += 2
            continue
        index += 2 if token in GIT_OPTIONS_WITH_VALUES else 1
    if index == len(tokens):
        return None
    try:
        separator = tokens.index("--", index + 1)
        root = subprocess.check_output(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    target = os.path.abspath(os.path.join(root, "todos.md"))
    paths = (
        os.path.abspath(os.path.join(cwd, path)) for path in tokens[separator + 1 :]
    )
    return target if target in paths else None


def units(lines: list[str]) -> list[list[str]]:
    """Split lines into entries (`- ` line plus indented continuation) and other non-blank runs."""
    result: list[list[str]] = []
    current: list[str] = []
    in_entry = False
    for line in [*lines, ""]:
        continues = in_entry and line.startswith("  ") and bool(line.strip())
        if current and (
            not line.strip() or line.startswith("- ") or in_entry != continues
        ):
            result.append(current)
            current = []
        if line.strip():
            current.append(line)
        in_entry = line.startswith("- ") or continues
    return result


def counted_lines(lines: list[str]) -> int:
    """Number of lines outside CAVEAT blocks, which stay in todos.md whatever their length."""
    count = 0
    in_caveat = False
    for line in lines:
        if line.startswith("CAVEAT:"):
            in_caveat = True
        elif line.startswith(("- ", "#")):
            in_caveat = False
        count += not in_caveat
    return count


def lint(text: str) -> list[str]:
    """Return deterministic descriptions of todos.md size violations."""
    lines = text.splitlines()
    violations: list[str] = []
    counted = counted_lines(lines)
    if counted > MAX_FILE_LINES:
        violations.append(
            f"file: {counted} lines outside CAVEAT blocks (max {MAX_FILE_LINES})"
        )
    for unit in units(lines):
        if unit[0].startswith("- ") and len(unit) > MAX_ENTRY_LINES:
            violations.append(
                f"entry {unit[0][:30]!r}: {len(unit)} lines (max {MAX_ENTRY_LINES})"
            )
    return violations


def _consent_satisfied(paragraph: str) -> bool:
    return "「" in paragraph or any(marker in paragraph for marker in CONSENT_MARKERS)


def _consent_violations(text: str, repo_root: str) -> list[str]:
    try:
        baseline = subprocess.run(
            ["git", "-C", repo_root, "show", "HEAD:todos.md"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if baseline.returncode != 0:
        return []

    work_lines = text.splitlines()
    head_lines = baseline.stdout.splitlines()
    added = set(work_lines) - set(head_lines)
    violations: list[str] = []
    for unit in units(work_lines):
        paragraph = "\n".join(unit)
        if (
            any(item in added for item in unit)
            and any(word in paragraph for word in DECISION_WORDS)
            and not _consent_satisfied(paragraph)
        ):
            line = next(
                line for line in unit if any(word in line for word in DECISION_WORDS)
            )
            violations.append(
                f"consent {line[:40]!r}: needs a 「…」 quote or an explicit non-decision marker"
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
    target = todos_commit_target(command, cwd)
    if target is None:
        return 0
    with open(target, encoding="utf-8") as handle:
        text = handle.read()
    violations = lint(text)
    violations.extend(_consent_violations(text, os.path.dirname(target)))
    if not violations:
        return 0
    sys.stderr.write("todos-structure:\n")
    sys.stderr.write("".join(f"- {violation}\n" for violation in violations))
    sys.stderr.write(
        "todos.md は session を跨ぐ作業の概要だけ (1 作業 1 項目 3 行まで、CAVEAT を除き全体 30 行まで)。"
        "詳細は last-session-handoff.md に書き、GitHub が使えるなら issue に起こして番号を 1 行で置いてもよい。"
        "session 内で終わる作業は Task で管理し、todos.md に書かない\n"
    )
    return 2


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
