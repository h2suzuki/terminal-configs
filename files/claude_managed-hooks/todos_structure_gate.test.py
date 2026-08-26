#!/usr/bin/env python3
"""Acceptance tests for todos_structure_gate.py, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  the hook is a PreToolUse(Bash) gate: payload JSON on stdin, exit 0 = allow, exit 2 = deny with the
      reason on stderr starting with "todos-structure:"
  C2  it acts only on a `git commit` whose command text names todos.md; any other command exits 0
  C3  it lints the STAGED todos.md (`git show :todos.md` from the payload cwd's repo), not the working tree
  C4  a `### ` block (heading line through the line before the next `### ` / `## ` / EOF) may span at most
      MAX_BLOCK_LINES = 40 lines; a longer block is denied and named with its line count
  C5  a checkbox item (`- [ ]` / `- [x]` line plus its indented continuation lines) may span at most
      MAX_ITEM_LINES = 6 lines; a longer item is denied and quoted by its first 30 characters
  C6  every block must contain the lines `起票:`, `Goal:` and `Exit Criteria:`; a missing key is denied
  C7  the repository's own todos.md (two directories above this file) passes
  C8  fail-open: not a git repo, todos.md not staged, or unreadable payload → exit 0
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "todos_structure_gate.py"
)
REPO_TODOS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "todos.md"
)
COMMIT = 'git commit -m "todos: x" -- todos.md'

HEAD = "# Todos\n\n## Critical\n\n## High\n\n"


def block(
    name: str, *, extra_lines: int = 0, item_lines: int = 1, drop: str = ""
) -> str:
    lines = [
        f"### {name}",
        "",
        "起票: user 2026-08-26",
        "",
        "Goal: one line.",
        "",
        "Exit Criteria:",
        "",
    ]
    item = ["- [ ] first item"] + ["  continuation"] * (item_lines - 1)
    lines += (
        item + ["- [x] second item — 2026-08-26", ""] + ["- [ ] padding"] * extra_lines
    )
    lines += ["Work file: なし", ""]
    text = "\n".join(lines) + "\n"
    if drop:
        text = (
            "\n".join(line for line in text.splitlines() if not line.startswith(drop))
            + "\n"
        )
    return text


def run_hook(
    cwd: str, command: str, payload: str | None = None
) -> subprocess.CompletedProcess:
    body = (
        payload
        if payload is not None
        else json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
        )
    )
    return subprocess.run(
        [sys.executable, HOOK],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


class Repo:
    def __init__(self, root: str) -> None:
        self.root = root
        git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
        subprocess.run([*git, "init", "-q", root], check=True)
        self.git = [*git, "-C", root]

    def stage_todos(self, text: str) -> None:
        with open(os.path.join(self.root, "todos.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        subprocess.run([*self.git, "add", "todos.md"], check=True)

    def overwrite_worktree(self, text: str) -> None:
        with open(os.path.join(self.root, "todos.md"), "w", encoding="utf-8") as fh:
            fh.write(text)


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_c1_c4_conforming_file_is_allowed(self) -> None:
        self.repo.stage_todos(HEAD + block("A") + block("B"))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_c4_block_over_forty_lines_is_denied_by_name_and_count(self) -> None:
        text = HEAD + block("Long block", extra_lines=30)
        self.assertGreater(len(block("Long block", extra_lines=30).splitlines()), 40)
        self.repo.stage_todos(text)
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertTrue(out.stderr.startswith("todos-structure:"), out.stderr)
        self.assertIn("Long block", out.stderr)
        self.assertRegex(out.stderr, r"\b4[1-9]\b|\b[5-9]\d\b")

    def test_c4_exactly_forty_lines_is_allowed(self) -> None:
        body = block("Edge")
        pad = 40 - len(body.splitlines())
        self.repo.stage_todos(HEAD + block("Edge", extra_lines=pad))
        self.assertEqual(len(block("Edge", extra_lines=pad).splitlines()), 40)
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)

    def test_c5_item_over_six_lines_is_denied_and_quoted(self) -> None:
        self.repo.stage_todos(HEAD + block("Items", item_lines=7))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("first item", out.stderr)
        self.repo.stage_todos(HEAD + block("Items", item_lines=6))
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)

    def test_c6_missing_required_key_is_denied(self) -> None:
        for key in ("起票:", "Goal:", "Exit Criteria:"):
            self.repo.stage_todos(HEAD + block("Keys", drop=key))
            out = run_hook(self.repo.root, COMMIT)
            self.assertEqual(out.returncode, 2, key)
            self.assertIn(key, out.stderr)

    def test_c2_other_commands_are_ignored_even_with_a_bad_file(self) -> None:
        self.repo.stage_todos(HEAD + block("Long block", extra_lines=30))
        for command in (
            "git add todos.md",
            "git status",
            'git commit -m "x" -- README.md',
            "cat todos.md",
        ):
            self.assertEqual(run_hook(self.repo.root, command).returncode, 0, command)

    def test_c3_staged_content_is_what_gets_linted(self) -> None:
        self.repo.stage_todos(HEAD + block("A"))
        self.repo.overwrite_worktree(HEAD + block("Long block", extra_lines=30))
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)
        self.repo.stage_todos(HEAD + block("Long block", extra_lines=30))
        self.repo.overwrite_worktree(HEAD + block("A"))
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 2)

    def test_c7_repository_todos_passes(self) -> None:
        with open(REPO_TODOS, encoding="utf-8") as fh:
            self.repo.stage_todos(fh.read())
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_c8_fail_open(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(run_hook(plain, COMMIT).returncode, 0)
        self.assertEqual(
            run_hook(self.repo.root, COMMIT).returncode, 0
        )  # nothing staged
        self.assertEqual(
            run_hook(self.repo.root, COMMIT, payload="{not json").returncode, 0
        )
        self.assertEqual(run_hook(self.repo.root, COMMIT, payload="[]").returncode, 0)


if __name__ == "__main__":
    unittest.main()
