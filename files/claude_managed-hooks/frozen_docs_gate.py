#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: deny growth of frozen documentation.

A file is frozen when its HEAD blob has a dated freeze marker. A commit
pathspec is denied when its working-tree line count exceeds the HEAD count.

Exit:
  0: allow or ignore an unchecked command; 2: deny growth of a frozen file

Always exits 0 on parse, git, or file errors (fail-open).
"""

import json
import os
import re
import shlex
import subprocess
import sys

FROZEN_MARKER = re.compile(r"^凍結 \(\d{4}-\d{2}-\d{2}\)", re.MULTILINE)
HEAD_REF = "HEAD"
VALUE_OPTIONS = (
    "-c -C --git-dir --work-tree --exec-path --namespace --config-env".split()
)


def _commit_paths(command: str, base: str) -> tuple[str, list[str]] | None:
    tokens = shlex.split(command)
    if not tokens or tokens[0] != "git":
        return None
    cwd = os.path.abspath(base)
    index = 1
    while index < len(tokens) and tokens[index] != "commit":
        token = tokens[index]
        if token == "-C":
            index += 1
            cwd = os.path.abspath(os.path.join(cwd, tokens[index]))
        elif token in VALUE_OPTIONS:
            index += 1
        elif not token.startswith("-"):
            return None
        index += 1
    if index == len(tokens):
        return None
    tail = tokens[index + 1 :]
    if "--" not in tail:
        return None
    separator = tail.index("--")
    paths = tail[separator + 1 :]
    return (cwd, paths) if paths else None


def _git(cwd: str, *args: str) -> str:
    return subprocess.check_output(["git", "-C", cwd, *args], text=True)


def _check(payload: dict) -> int:
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    base = payload.get("cwd")
    if (
        not isinstance(tool_input, dict)
        or not isinstance(base, str)
        or not isinstance(tool_input.get("command"), str)
    ):
        return 0
    parsed = _commit_paths(tool_input["command"], base)
    if parsed is None:
        return 0
    cwd, paths = parsed
    root = os.path.abspath(_git(cwd, "rev-parse", "--show-toplevel").strip())
    denied: list[tuple[str, int, int]] = []
    for path in paths:
        target = os.path.abspath(os.path.join(cwd, path))
        try:
            if os.path.commonpath((root, target)) != root or not os.path.isfile(target):
                continue
            rel = os.path.relpath(target, root)
            head = _git(root, "show", f"{HEAD_REF}:{rel}").splitlines()
            if not FROZEN_MARKER.search("\n".join(head)):
                continue
            with open(target, encoding="utf-8") as handle:
                work = handle.read().splitlines()
            if len(work) > len(head):
                denied.append((rel, len(head), len(work)))
        except Exception:
            continue
    if not denied:
        return 0
    sys.stderr.write("frozen-doc:\n")
    for rel, head_count, work_count in denied:
        sys.stderr.write(
            f"- {rel}: HEAD {head_count} 行 → working tree {work_count} 行\n"
        )
    sys.stderr.write(
        "書き出したい経緯は drafts/journal/ (gitignore 済み・読み返さない) へ。凍結 file は削除だけ\n"
    )
    return 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        return _check(payload) if isinstance(payload, dict) else 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
