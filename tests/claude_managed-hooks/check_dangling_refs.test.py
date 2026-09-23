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
  R3  exempt targets for R2: a `drafts` path component, git-ignored files, files outside any git work
      tree, and payloads without `file_path`. A name alone (test file, `tests` component, `todos.md`)
      exempts nothing
  R4  opt-out for R2 is line-scoped, like shellcheck: `dangling-ref-check: allow` exempts a reference
      only when it appears on the same line as that reference, or alone (as a comment) on the line
      immediately before it in the resulting text — Edit/MultiEdit reconstruct that line from the
      target's on-disk content when the edit itself supplies no context. A marker elsewhere in the
      file (e.g. at the top) exempts nothing else
  R5  placeholders and bare mentions are not references
  R6  the pre-existing patterns keep their behavior: denied whatever the target path, skipped only by the
      marker anywhere in the new content (unlike R4, this opt-out is not line-scoped)
  R7  fail-open: unreadable payload or another tool → exit 0
  R8  a `.refignore` file at the repo root exempts specific (repo-relative path, reference) pairs for
      formats that cannot carry a line marker: each non-blank, non-`#` line is `<path> <reference>`
      (whitespace-separated); a listed pair is allowed, an unlisted reference in the same file is still
      denied, a pair listed for another file exempts nothing here, comment/blank/malformed (not exactly
      two fields) lines are ignored, and a missing/unreadable `.refignore` behaves as before its existence
  R9  in the root `.refignore` itself, a well-formed entry line is the exemption, not a reference: it
      may be written; a drafts reference on any other line of it (e.g. a comment) is still denied
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
REF = "see `drafts/plan.md` for details"  # dangling-ref-check: allow


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

    def refignore(self, content: str) -> None:
        with open(os.path.join(self.repo, ".refignore"), "w", encoding="utf-8") as fh:
            fh.write(content)

    def deny(self, payload: dict, needle: str) -> str:
        out = run_hook(payload)
        self.assertEqual(out.returncode, 2, f"{payload}: {out.stderr}")
        self.assertTrue(out.stderr.startswith("dangling-ref-check:"), out.stderr)
        self.assertIn(needle, out.stderr)
        return out.stderr

    def allow(self, payload: dict) -> None:
        out = run_hook(payload)
        self.assertEqual(out.returncode, 0, f"{payload}: {out.stderr}")

    def test_r1_r2_each_tool_shape(self) -> None:
        """R1 / R2: every content slot of Write, Edit, and MultiEdit is scanned."""
        target = self.path("docs/a.md")
        self.deny(
            write_payload(target, REF),
            "drafts/plan.md",  # dangling-ref-check: allow
        )
        self.deny(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": target,
                    "old_string": "x",
                    "new_string": REF,
                },
            },
            "drafts/plan.md",  # dangling-ref-check: allow
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
            "drafts/plan.md",  # dangling-ref-check: allow
        )
        self.deny(
            write_payload(self.path("docs/new/deep/x.md"), REF),
            "drafts/plan.md",  # dangling-ref-check: allow
        )

    def test_r2_concrete_reference_forms(self) -> None:
        """R2: any concrete file or dir name under a drafts component is a reference."""
        for text, needle in (
            (
                "`drafts/corpus-tools/extract.py`",  # dangling-ref-check: allow
                "drafts/corpus-tools/extract.py",  # dangling-ref-check: allow
            ),
            ("(spec: drafts/plan.md)", "drafts/plan.md"),  # dangling-ref-check: allow
            ('"drafts/a"', "drafts/a"),  # dangling-ref-check: allow
            ("./drafts/a.md", "drafts/a.md"),  # dangling-ref-check: allow
            ("sub/drafts/_x.md", "drafts/_x.md"),  # dangling-ref-check: allow
            ("/home/u/repo/drafts/9.md", "drafts/9.md"),  # dangling-ref-check: allow
        ):
            with self.subTest(text=text):
                self.deny(write_payload(self.path("docs/a.md"), text), needle)

    def test_r3_exempt_targets(self) -> None:
        """R3: scratch, ignored files, and files outside git may name drafts paths."""
        for target in (
            self.path("drafts/notes.md"),  # dangling-ref-check: allow
            self.path("sub/drafts/notes.md"),  # dangling-ref-check: allow
            self.path("ignored.md"),
            os.path.join(self.plain, "note.md"),
        ):
            with self.subTest(target=target):
                self.allow(write_payload(target, REF))
        self.allow({"tool_name": "Write", "tool_input": {"content": REF}})

    def test_r3_name_alone_no_longer_exempts(self) -> None:
        """R3: a test-like name or todos.md is no longer a free pass for a drafts reference."""
        for target in (
            self.path("todos.md"),
            self.path("files/x.test.py"),
            self.path("files/x.mutants.py"),
            self.path("files/test_x.py"),
            self.path("files/x_test.py"),
            self.path("tests/helper.py"),
        ):
            with self.subTest(target=target):
                self.deny(
                    write_payload(target, REF),
                    "drafts/plan.md",  # dangling-ref-check: allow
                )

    def test_r4_same_line_marker_allows(self) -> None:
        """R4: a marker on the very line that holds the reference exempts it."""
        target = self.path("docs/a.md")
        self.allow(write_payload(target, REF + " (dangling-ref-check: allow)"))

    def test_r4_preceding_line_marker_allows_only_the_next_line(self) -> None:
        """R4: a marker alone on the line before exempts that line only, not a later one."""
        target = self.path("docs/a.md")
        content = (
            "<!-- dangling-ref-check: allow -->\n"
            + REF
            + "\nnotes\n"
            + "also see drafts/other.md\n"  # dangling-ref-check: allow
        )
        out = self.deny(
            write_payload(target, content),
            "drafts/other.md",  # dangling-ref-check: allow
        )
        self.assertNotIn("drafts/plan.md", out)  # dangling-ref-check: allow

    def test_r4_marker_elsewhere_in_file_exempts_nothing(self) -> None:
        """R4: a marker at the top of the file no longer exempts a reference further down."""
        target = self.path("docs/a.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("# dangling-ref-check: allow\nfiller\nunrelated\n")
        self.deny(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": target,
                    "old_string": "unrelated",
                    "new_string": REF,
                },
            },
            "drafts/plan.md",  # dangling-ref-check: allow
        )

    def test_r4_edit_reconstructs_the_preceding_on_disk_line(self) -> None:
        """R4: Edit supplies no context of its own, so the preceding line comes from disk."""
        target = self.path("docs/a.md")
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

    def test_r8_refignore_pair_exempts_listed_reference(self) -> None:
        """R8: a (file, reference) pair listed in .refignore is exempt."""
        self.refignore("docs/a.md drafts/plan.md\n")  # dangling-ref-check: allow
        self.allow(write_payload(self.path("docs/a.md"), REF))

    def test_r8_unlisted_reference_in_same_file_still_denied(self) -> None:
        """R8: listing one reference for a file does not exempt another reference in it."""
        self.refignore("docs/a.md drafts/plan.md\n")  # dangling-ref-check: allow
        self.deny(
            write_payload(
                self.path("docs/a.md"),
                "see drafts/other.md",  # dangling-ref-check: allow
            ),
            "drafts/other.md",  # dangling-ref-check: allow
        )

    def test_r8_pair_listed_for_another_file_does_not_exempt(self) -> None:
        """R8: the same reference listed for a different file does not exempt this file."""
        self.refignore("docs/b.md drafts/plan.md\n")  # dangling-ref-check: allow
        self.deny(
            write_payload(self.path("docs/a.md"), REF),
            "drafts/plan.md",  # dangling-ref-check: allow
        )

    def test_r8_comment_blank_and_malformed_lines_ignored(self) -> None:
        """R8: comment, blank, and malformed (not exactly two fields) lines add no exemption."""
        self.refignore(
            "# header\n\ndocs/a.md\ndocs/a.md drafts/plan.md extra\n"  # dangling-ref-check: allow
        )
        self.deny(
            write_payload(self.path("docs/a.md"), REF),
            "drafts/plan.md",  # dangling-ref-check: allow
        )

    def test_r8_no_refignore_behaves_as_before(self) -> None:
        """R8: a missing .refignore denies exactly as it did before the file existed."""
        self.deny(
            write_payload(self.path("docs/a.md"), REF),
            "drafts/plan.md",  # dangling-ref-check: allow
        )

    def test_r9_refignore_entry_lines_are_not_references(self) -> None:
        """R9: a well-formed .refignore entry may be written; a drafts reference in its comment may not."""
        target = self.path(".refignore")
        self.allow(
            write_payload(
                target,
                "docs/a.md drafts/plan.md\n",  # dangling-ref-check: allow
            )
        )
        self.deny(
            write_payload(
                target,
                "# see drafts/plan.md\n",  # dangling-ref-check: allow
            ),
            "drafts/plan.md",  # dangling-ref-check: allow
        )

    def test_r7_fail_open(self) -> None:
        """R7: broken input or an unrelated tool never blocks."""
        self.assertEqual(run_hook("{not json").returncode, 0)
        self.allow(
            {"tool_name": "Read", "tool_input": {"file_path": self.path("docs/a.md")}}
        )


if __name__ == "__main__":
    unittest.main()
