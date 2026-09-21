#!/usr/bin/env python3
"""Acceptance tests for check_dangling_refs.py, written by the ordering side before the drafts/ rule.

dangling-ref-check: allow (fixtures carry dangling patterns on purpose)

Contract (each claim maps to one test):
  R1  the hook is a PreToolUse(Write|Edit|MultiEdit) gate: payload JSON on stdin, exit 0 = allow,
      exit 2 = deny with the reason on stderr starting with "dangling-ref-check:" and quoting the match
  R2  a concrete drafts reference in Write `content`, Edit `new_string`, or any MultiEdit
      `edits[].new_string` is denied when the target `file_path` lies inside a git work tree (its nearest
      existing ancestor decides) and git does not ignore it. Concrete = a `drafts` path component
      (preceded by start of text, `/`, or a character outside `[A-Za-z0-9_.-]`) followed by `/` and a
      name starting with `[A-Za-z0-9_]`
  R3  exempt targets for R2: a `drafts` path component, basename `todos.md`, test files (`*.test.*`,
      `*.mutants.*`, `test_*.py`, `*_test.py`, a `tests` component), git-ignored files, files outside any
      git work tree, and payloads without `file_path`
  R4  opt-out for R2: `dangling-ref-check: allow` in the new content or in the target's current on-disk
      content
  R5  placeholders and bare mentions are not references
  R6  the pre-existing patterns keep their behavior: denied whatever the target path, skipped only by the
      marker in the new content
  R7  fail-open: unreadable payload or another tool → exit 0
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "files",
    "claude_managed-hooks",
    "check_dangling_refs.py",
)
ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
REF = "see `drafts/plan.md` for details"


def run_hook(payload: object) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=ENV,
    )


def write_payload(path: str, content: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(os.path.join(self.repo, "docs"))
        os.makedirs(self.plain)
        subprocess.run(
            ["git", "-C", self.repo, "init", "-q"], check=True, env=ENV, timeout=60
        )
        with open(os.path.join(self.repo, ".gitignore"), "w", encoding="utf-8") as fh:
            fh.write("drafts/\nignored.md\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def path(self, rel: str) -> str:
        return os.path.join(self.repo, rel)

    def deny(self, payload: dict, needle: str) -> None:
        out = run_hook(payload)
        self.assertEqual(out.returncode, 2, f"{payload}: {out.stderr}")
        self.assertTrue(out.stderr.startswith("dangling-ref-check:"), out.stderr)
        self.assertIn(needle, out.stderr)

    def allow(self, payload: dict) -> None:
        out = run_hook(payload)
        self.assertEqual(out.returncode, 0, f"{payload}: {out.stderr}")

    def test_r1_r2_each_tool_shape(self) -> None:
        """R1 / R2: every content slot of Write, Edit, and MultiEdit is scanned."""
        target = self.path("docs/a.md")
        self.deny(write_payload(target, REF), "drafts/plan.md")
        self.deny(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": target,
                    "old_string": "x",
                    "new_string": REF,
                },
            },
            "drafts/plan.md",
        )
        self.deny(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "file_path": target,
                    "edits": [
                        {"old_string": "a", "new_string": "clean"},
                        {"old_string": "b", "new_string": REF},
                    ],
                },
            },
            "drafts/plan.md",
        )
        self.deny(write_payload(self.path("docs/new/deep/x.md"), REF), "drafts/plan.md")

    def test_r2_concrete_reference_forms(self) -> None:
        """R2: any concrete file or dir name under a drafts component is a reference."""
        for text, needle in (
            ("`drafts/corpus-tools/extract.py`", "drafts/corpus-tools/extract.py"),
            ("(spec: drafts/plan.md)", "drafts/plan.md"),
            ('"drafts/a"', "drafts/a"),
            ("./drafts/a.md", "drafts/a.md"),
            ("sub/drafts/_x.md", "drafts/_x.md"),
            ("/home/u/repo/drafts/9.md", "drafts/9.md"),
        ):
            with self.subTest(text=text):
                self.deny(write_payload(self.path("docs/a.md"), text), needle)

    def test_r3_exempt_targets(self) -> None:
        """R3: scratch, ledgers, tests, ignored files, and files outside git may name drafts paths."""
        for target in (
            self.path("drafts/notes.md"),
            self.path("sub/drafts/notes.md"),
            self.path("todos.md"),
            self.path("files/x.test.py"),
            self.path("files/x.mutants.py"),
            self.path("files/test_x.py"),
            self.path("files/x_test.py"),
            self.path("tests/helper.py"),
            self.path("ignored.md"),
            os.path.join(self.plain, "note.md"),
        ):
            with self.subTest(target=target):
                self.allow(write_payload(target, REF))
        self.allow({"tool_name": "Write", "tool_input": {"content": REF}})

    def test_r4_opt_out_marker(self) -> None:
        """R4: the marker in the new content or already on disk suppresses the drafts rule."""
        target = self.path("docs/a.md")
        self.allow(write_payload(target, "<!-- dangling-ref-check: allow -->\n" + REF))
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("# dangling-ref-check: allow\nbody\n")
        self.allow(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": target,
                    "old_string": "body",
                    "new_string": REF,
                },
            }
        )

    def test_r5_placeholders_and_bare_mentions(self) -> None:
        """R5: convention text that names no concrete drafts file stays allowed."""
        for text in (
            "handoff lives at drafts/<task-slug>-handoff.md",
            "drafts/*",
            "drafts/...",
            "session-spanning files go to drafts/",
            "mydrafts/a.md",
            ".drafts/a.md",
            "drafts/$NAME",
            "drafts/{a,b}.md",
        ):
            with self.subTest(text=text):
                self.allow(write_payload(self.path("docs/a.md"), text))

    def test_r6_existing_patterns_unchanged(self) -> None:
        """R6: the older patterns stay path-independent and content-marker-only."""
        outside = os.path.join(self.plain, "note.md")
        self.deny(write_payload(outside, "see Plan B"), "Plan B")
        self.deny(write_payload(self.path("todos.md"), "tracked as AI-12"), "AI-12")
        self.allow(write_payload(outside, "dangling-ref-check: allow\nsee Plan B"))
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("dangling-ref-check: allow\n")
        self.deny(write_payload(outside, "see Plan B"), "Plan B")

    def test_r7_fail_open(self) -> None:
        """R7: broken input or an unrelated tool never blocks."""
        self.assertEqual(run_hook("{not json").returncode, 0)
        self.allow(
            {"tool_name": "Read", "tool_input": {"file_path": self.path("docs/a.md")}}
        )


if __name__ == "__main__":
    unittest.main()
