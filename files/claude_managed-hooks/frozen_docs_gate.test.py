#!/usr/bin/env python3
"""Acceptance tests for frozen_docs_gate.py, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  the hook is a PreToolUse(Bash) gate: payload JSON on stdin, exit 0 = allow, exit 2 = deny with the
      reason on stderr starting with "frozen-doc:"
  C2  it acts only on a `git commit` whose pathspec (tokens after `--`) names a file; `git -C <dir>`
      (repeatable, relative to the payload cwd) moves the repository the paths resolve against; a path
      mentioned only in the message, or any other command, exits 0
  C3  a named file is frozen iff its HEAD blob contains a line matching ^凍結 (YYYY-MM-DD); neither the
      index nor the working tree decides (adding the marker in the same commit is no freeze, removing it
      in the working tree is no thaw)
  C4  a frozen file whose working-tree line count exceeds its HEAD line count is denied; equal or fewer
      lines is allowed
  C5  the deny reason names the path, both line counts, and the outlet drafts/journal/
  C6  fail-open: not a git repo, path not in HEAD, path missing from the working tree, or unreadable
      payload → exit 0
  C7  the repository's own frozen docs (docs/*.md two directories above this file whose text carries the
      marker; exactly two today) are denied when one line is appended and allowed when unchanged
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "frozen_docs_gate.py")
REPO_DOCS = os.path.join(HERE, "..", "..", "docs")
MARKER = re.compile(r"^凍結 \(\d{4}-\d{2}-\d{2}\)", re.MULTILINE)
DOC = "docs/ledger.md"
COMMIT = f'git commit -m "docs: x" -- {DOC}'

FROZEN = "# Ledger\n\n凍結 (2026-08-26): 追記しない。\n\n- entry one\n- entry two\n"
PLAIN = "# Ledger\n\n- entry one\n- entry two\n"


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
        base = [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
        ]
        subprocess.run([*base, "init", "-q", root], check=True)
        self.git = [*base, "-C", root]

    def write(self, rel: str, text: str) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def stage(self, rel: str) -> None:
        subprocess.run([*self.git, "add", rel], check=True)

    def commit(self, rel: str, text: str) -> None:
        self.write(rel, text)
        self.stage(rel)
        subprocess.run([*self.git, "commit", "-q", "-m", "c", "--", rel], check=True)


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_c1_c4_unchanged_or_shrunk_frozen_file_is_allowed(self) -> None:
        self.repo.commit(DOC, FROZEN)
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.repo.write(DOC, FROZEN.replace("- entry two\n", ""))
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)

    def test_c4_c5_grown_frozen_file_is_denied_with_counts_and_outlet(self) -> None:
        self.repo.commit(DOC, FROZEN)
        self.repo.write(DOC, FROZEN + "- entry three\n")
        out = run_hook(self.repo.root, COMMIT)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertTrue(out.stderr.startswith("frozen-doc:"), out.stderr)
        self.assertIn(DOC, out.stderr)
        self.assertRegex(out.stderr, r"\b6\b.*\b7\b")
        self.assertIn("drafts/journal/", out.stderr)

    def test_c3_head_decides_the_freeze(self) -> None:
        self.repo.commit(DOC, PLAIN)
        self.repo.write(DOC, FROZEN)
        self.repo.stage(DOC)
        self.repo.write(DOC, FROZEN + "- entry three\n")
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)
        self.repo.commit(DOC, FROZEN)
        self.repo.write(DOC, PLAIN + "- three\n- four\n- five\n")
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 2)

    def test_c2_only_a_commit_naming_the_file_triggers(self) -> None:
        self.repo.commit(DOC, FROZEN)
        self.repo.write(DOC, FROZEN + "- entry three\n")
        for command in (
            f"git add {DOC}",
            "git status",
            f'git commit -m "{DOC}" -- README.md',
            f"cat {DOC}",
        ):
            self.assertEqual(run_hook(self.repo.root, command).returncode, 0, command)
        for command in (
            f'git commit -m "x" -- ./{DOC}',
            f'git commit -q -m "x" -- README.md {DOC}',
            f'git -c user.name=t commit -m "x" -- {DOC}',
        ):
            self.assertEqual(run_hook(self.repo.root, command).returncode, 2, command)

    def test_c2_dash_c_moves_the_repository(self) -> None:
        self.repo.commit(DOC, FROZEN)
        self.repo.write(DOC, FROZEN + "- entry three\n")
        with tempfile.TemporaryDirectory() as plain:
            command = f'git -C {self.repo.root} commit -m "x" -- {DOC}'
            self.assertEqual(run_hook(plain, command).returncode, 2, command)
        parent, name = os.path.split(self.repo.root)
        command = f'git -C {name} commit -m "x" -- {DOC}'
        self.assertEqual(run_hook(parent, command).returncode, 2, command)

    def test_c6_fail_open(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            os.makedirs(os.path.join(plain, "docs"))
            with open(os.path.join(plain, DOC), "w", encoding="utf-8") as fh:
                fh.write(FROZEN + "- x\n")
            self.assertEqual(run_hook(plain, COMMIT).returncode, 0)
        self.repo.commit("README.md", "# r\n")
        self.repo.write(DOC, FROZEN + "- x\n")
        self.repo.stage(DOC)
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)
        self.repo.commit(DOC, FROZEN)
        os.remove(os.path.join(self.repo.root, DOC))
        self.assertEqual(run_hook(self.repo.root, COMMIT).returncode, 0)
        self.repo.write(DOC, FROZEN + "- x\n")
        self.assertEqual(
            run_hook(self.repo.root, COMMIT, payload="{not json").returncode, 0
        )
        self.assertEqual(run_hook(self.repo.root, COMMIT, payload="[]").returncode, 0)

    def test_c7_repository_frozen_docs(self) -> None:
        frozen: dict[str, str] = {}
        for path in glob.glob(os.path.join(REPO_DOCS, "*.md")):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if MARKER.search(text):
                frozen[os.path.basename(path)] = text
        self.assertEqual(
            sorted(frozen),
            [
                "adversarial-review-methodology.md",
                "methodology-case-ledger.md",
            ],
        )
        for name, text in frozen.items():
            rel = f"docs/{name}"
            command = f'git commit -m "x" -- {rel}'
            self.repo.commit(rel, text)
            self.assertEqual(run_hook(self.repo.root, command).returncode, 0, name)
            self.repo.write(rel, text + "追記\n")
            out = run_hook(self.repo.root, command)
            self.assertEqual(out.returncode, 2, name)
            self.assertIn(rel, out.stderr)


if __name__ == "__main__":
    unittest.main()
