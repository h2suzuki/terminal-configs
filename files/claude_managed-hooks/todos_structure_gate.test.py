#!/usr/bin/env python3
"""Acceptance tests for todos_structure_gate.py, written by the ordering side before the implementation.

todos.md holds only a short cross-session handoff summary; details belong in last-session-handoff.md.

Contract (each claim maps to one test):
  C1  the hook is a PreToolUse(Bash) gate: payload JSON on stdin, exit 0 = allow, exit 2 = deny with the
      reason on stderr starting with "todos-structure:"
  C2  it acts only on a `git commit` whose pathspec (tokens after `--`), resolved against the effective
      cwd, is the repository root's todos.md; `git -C <dir>` (repeatable, relative to the payload cwd)
      moves the effective cwd; a todos.md mentioned only in the message, or any other command, exits 0
  C3  it lints the WORKING-TREE todos.md at the root of the repository containing the effective cwd
      (what `git commit -- todos.md` records), not the index blob and not the payload cwd's repository
  C4  the whole file may span at most MAX_FILE_LINES = 30 lines; a longer file is denied with its line
      count and a pointer to last-session-handoff.md
  C5  an entry (a line starting with `- ` plus its indented continuation lines) may span at most
      MAX_ENTRY_LINES = 3 lines; a longer entry is denied and quoted by its first 30 characters
  C7  the repository's own todos.md (two directories above this file) passes
  C8  fail-open: not a git repo, no todos.md in the working tree, or unreadable payload → exit 0
  C9  consent: against the HEAD:todos.md baseline (git show; unreadable baseline → the consent check is
      skipped, the other checks still run), a unit holding a working-tree line absent from the baseline
      and containing 決裁 / 承認 / 合意 / 採用 is denied as "consent" unless that unit also holds a 「…」
      utterance quote or an explicit non-decision marker (提案中 / 発話証跡なし / 要確認 / 未承認 /
      無承認 / 承認不備 / 不採用). A unit is one entry, or one run of contiguous non-blank lines outside
      entries; units without a new line are untouched
  C10 the negated forms double as satisfiers: a unit whose only decision word sits inside 不採用 /
      未承認 etc. passes
  C11 CAVEAT blocks are kept in todos.md: lines from a line starting with `CAVEAT:` up to the next entry
      line, `CAVEAT:` line, or `#` heading do not count toward MAX_FILE_LINES; entry lines and other
      prose still count
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

HEAD = "# Todos\n\n"
TAIL = "\n詳細は last-session-handoff.md\n"


def entry(name: str, lines: int = 1) -> str:
    return f"- {name} — 再開点: next step\n" + "  continuation\n" * (lines - 1)


def todos(*entries: str, pad: int = 0) -> str:
    return HEAD + "".join(entries) + "- padding\n" * pad + TAIL


LONG = todos(*(entry(f"item {n}") for n in range(40)))

DECISION_ENTRY = "- 処遇を決めた — 2026-08-26 決裁: 縮小する\n"
QUOTED_ENTRY = DECISION_ENTRY + "  (発話 22:00「縮小してよい」)\n"
MARKED_ENTRY = "- 縮小を採用したい (提案中)\n"
NEGATED_ENTRY = "- 近接重複の検出は計測で不採用\n"


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


def commit_todos(repo: Repo, text: str) -> None:
    repo.stage_todos(text)
    subprocess.run([*repo.git, "commit", "-q", "-m", "seed"], check=True)


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_c1_c4_conforming_file_is_allowed(self) -> None:
        self.repo.stage_todos(todos(entry("A"), entry("B", lines=2)))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_c4_file_over_thirty_lines_is_denied_with_count(self) -> None:
        self.assertGreater(len(LONG.splitlines()), 30)
        self.repo.stage_todos(LONG)
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertTrue(out.stderr.startswith("todos-structure:"), out.stderr)
        self.assertIn(str(len(LONG.splitlines())), out.stderr)
        self.assertIn("last-session-handoff.md", out.stderr)

    def test_c4_exactly_thirty_lines_is_allowed(self) -> None:
        pad = 30 - len(todos(entry("Edge")).splitlines())
        text = todos(entry("Edge"), pad=pad)
        self.assertEqual(len(text.splitlines()), 30)
        self.repo.stage_todos(text)
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)

    def test_c5_entry_over_three_lines_is_denied_and_quoted(self) -> None:
        self.repo.stage_todos(todos(entry("first item", lines=4)))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("first item", out.stderr)
        self.repo.stage_todos(todos(entry("first item", lines=3)))
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)

    def test_c2_other_commands_are_ignored_even_with_a_bad_file(self) -> None:
        self.repo.stage_todos(LONG)
        for command in (
            "git add todos.md",
            "git status",
            'git commit -m "x" -- README.md',
            'git commit -m "docs: mention todos.md in README" -- README.md',
            "cat todos.md",
        ):
            self.assertEqual(run_hook(self.repo.root, command).returncode, 0, command)

    def test_c3_worktree_content_is_what_gets_linted(self) -> None:
        self.repo.stage_todos(todos(entry("A")))
        self.repo.overwrite_worktree(LONG)
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 2)
        self.repo.stage_todos(LONG)
        self.repo.overwrite_worktree(todos(entry("A")))
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)

    def test_c2_c3_dash_c_moves_the_repository(self) -> None:
        self.repo.stage_todos(LONG)
        with tempfile.TemporaryDirectory() as plain:
            command = f'git -C {self.repo.root} commit -m "todos: x" -- todos.md'
            self.assertEqual(run_hook(plain, command).returncode, 2, command)
            other = Repo(plain)
            other.stage_todos(todos(entry("A")))
            self.assertEqual(run_hook(plain, command).returncode, 2, command)
            mirror = f'git -C {plain} commit -m "todos: x" -- todos.md'
            self.assertEqual(run_hook(self.repo.root, mirror).returncode, 0, mirror)
        parent, name = os.path.split(self.repo.root)
        relative = f'git -C {name} commit -m "todos: x" -- todos.md'
        self.assertEqual(run_hook(parent, relative).returncode, 2, relative)
        absolute = f'git commit -m "todos: x" -- {self.repo.root}/todos.md'
        self.assertEqual(run_hook(self.repo.root, absolute).returncode, 2, absolute)

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
        )  # no todos.md in the working tree
        self.assertEqual(
            run_hook(self.repo.root, COMMIT, payload="{not json").returncode, 0
        )
        self.assertEqual(run_hook(self.repo.root, COMMIT, payload="[]").returncode, 0)

    def test_c9_added_decision_entry_needs_quote(self) -> None:
        commit_todos(self.repo, todos(entry("A")))
        self.repo.stage_todos(todos(entry("A"), DECISION_ENTRY))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("consent", out.stderr)
        self.assertIn("決裁", out.stderr)

    def test_c9_quote_or_marker_satisfies(self) -> None:
        commit_todos(self.repo, todos(entry("A")))
        for item in (QUOTED_ENTRY, MARKED_ENTRY):
            self.repo.stage_todos(todos(entry("A"), item))
            out = run_hook(self.repo.root, COMMIT)
            self.assertEqual(out.returncode, 0, f"{item!r}: {out.stderr}")

    def test_c9_unchanged_decision_entry_is_grandfathered(self) -> None:
        commit_todos(self.repo, todos(entry("A"), DECISION_ENTRY))
        self.repo.stage_todos(todos(entry("A"), DECISION_ENTRY, entry("B")))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_c9_decision_prose_outside_entries_is_a_unit(self) -> None:
        commit_todos(self.repo, todos(entry("A")))
        self.repo.stage_todos(todos(entry("A")) + "\n方針を決裁した\n")
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("consent", out.stderr)

    def test_c10_negated_decision_word_passes(self) -> None:
        commit_todos(self.repo, todos(entry("A")))
        self.repo.stage_todos(todos(entry("A"), NEGATED_ENTRY))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_c11_caveat_lines_do_not_count(self) -> None:
        """C11: important CAVEATs stay in todos.md however long they are."""
        caveat = "CAVEAT: long warning\n" + "detail\n" * 20 + "\n参考 link\n\n"
        text = HEAD + caveat + "CAVEAT: second\n" + "more\n" * 20 + "\n"
        self.repo.stage_todos(text + "".join(entry(f"e{n}") for n in range(20)) + TAIL)
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_c11_prose_and_entries_outside_caveats_still_count(self) -> None:
        """C11: only CAVEAT blocks are exempt; notes and entries keep the limit."""
        self.repo.stage_todos(HEAD + "note\n" * 40 + entry("A") + TAIL)
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 2)
        caveat = "CAVEAT: short\ndetail\n\n"
        self.repo.stage_todos(
            HEAD + caveat + "".join(entry(f"e{n}") for n in range(40))
        )
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 2)

    def test_c9_unreadable_baseline_skips_consent_only(self) -> None:
        self.repo.stage_todos(todos(entry("A"), DECISION_ENTRY))
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main()
