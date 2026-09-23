#!/usr/bin/env python3
"""Acceptance tests for deny_drafts_commit.py, written by the ordering side before the implementation.

dangling-ref-check: allow (fixtures name drafts/ paths on purpose)

Contract (each claim maps to one test):
  D1  the hook is a PreToolUse(Bash) gate: payload JSON on stdin, exit 0 = allow, exit 2 = deny with the
      reason on stderr starting with "deny-drafts-commit:" and naming the offending path
  D2  `git add` whose pathspec (quoted or not, relative or absolute) has a `drafts` path component is
      denied, with or without `-f` / `--force`
  D3  `git commit` (including `--amend`) is denied when it would record an added / copied / modified /
      renamed path with a `drafts` component: the staged diff vs HEAD, plus for `-- PATH` commits the
      working-tree diff vs HEAD of those paths. Deletions (untracking a leaked file) are allowed
  D4  `git commit` is denied when a line it would add to a non-exempt file holds a concrete drafts
      reference: a `drafts` path component (preceded by start of text, `/`, or a character outside
      `[A-Za-z0-9_.-]`) followed by `/` and a name starting with `[A-Za-z0-9_]`. Lines come from the same
      two diffs as D3; unchanged and deleted lines do not count
  D5  exempt from D4: paths with a `drafts` component, and, line-scoped like shellcheck,
      `dangling-ref-check: allow` on the same added line or alone (as a comment) on the line
      immediately before it (an added line or unchanged context, from the same diff). A name alone
      (test file, `tests` component, `todos.md`) exempts nothing, nor does a marker elsewhere in the
      file
  D6  `git -C DIR` selects the repo, otherwise the payload cwd; pathspecs resolve against it
  D7  commit message text (`-m` values, heredoc bodies) is never read as a path or a reference
  D8  fail-open and scope: non-Bash tool, unreadable payload, or a cwd outside any git repo → exit 0;
      other git subcommands and non-git commands are allowed
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
    "deny_drafts_commit.py",
)
ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
COMMIT_A = "git commit -m 'docs: Update' -- docs/a.md"
BASE_A = "intro\nsee `drafts/old.md`\n"  # dangling-ref-check: allow


def git(repo: str, *args: str) -> None:
    subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        check=True,
        env=ENV,
        timeout=60,
    )


def run_hook(
    command: str, cwd: str, tool: str = "Bash", body: str | None = None
) -> subprocess.CompletedProcess:
    payload = (
        body
        if body is not None
        else json.dumps(
            {"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}
        )
    )
    return subprocess.run(
        [sys.executable, HOOK],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=ENV,
    )


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(self.repo)
        os.makedirs(self.plain)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        self.write(".gitignore", "drafts/\n")
        self.write("docs/a.md", BASE_A)
        git(self.repo, "add", ".gitignore", "docs/a.md")
        git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def deny(self, command: str, *needles: str, cwd: str | None = None) -> None:
        out = run_hook(command, cwd or self.repo)
        self.assertEqual(out.returncode, 2, f"{command!r}: {out.stderr}")
        self.assertTrue(out.stderr.startswith("deny-drafts-commit:"), out.stderr)
        for needle in needles:
            self.assertIn(needle, out.stderr)

    def allow(self, command: str, cwd: str | None = None) -> None:
        out = run_hook(command, cwd or self.repo)
        self.assertEqual(out.returncode, 0, f"{command!r}: {out.stderr}")

    def test_d1_d8_contract_and_fail_open(self) -> None:
        """D1 / D8: only Bash payloads are gated; broken input and non-repo cwd never block."""
        self.assertEqual(
            run_hook("git add drafts/x.md", self.repo, tool="Write").returncode,
            0,  # dangling-ref-check: allow
        )
        self.assertEqual(run_hook("", self.repo, body="{not json").returncode, 0)
        self.allow("git add drafts/x.md", cwd=self.plain)  # dangling-ref-check: allow
        self.allow(COMMIT_A, cwd=self.plain)
        for command in (
            "git status",
            "git log -p -- drafts/x.md",  # dangling-ref-check: allow
            "git diff -- drafts/x.md",  # dangling-ref-check: allow
            "git stash",
            "ls drafts",
            "cat drafts/x.md",  # dangling-ref-check: allow
        ):
            self.allow(command)

    def test_d2_git_add_of_drafts_paths(self) -> None:
        """D2: staging anything under a drafts/ component is the first step of a leak."""
        self.deny("git add drafts/x.md", "drafts/x.md")  # dangling-ref-check: allow
        self.deny("git add -f drafts/x.md", "drafts/x.md")  # dangling-ref-check: allow
        self.deny(
            "git add --force -- sub/drafts/y.md", "sub/drafts/y.md"
        )  # dangling-ref-check: allow
        self.deny('git add "drafts/x.md"', "drafts/x.md")  # dangling-ref-check: allow
        self.deny("git add ./drafts")
        self.deny("git add drafts")
        self.deny(
            "git add docs/a.md drafts/x.md", "drafts/x.md"
        )  # dangling-ref-check: allow
        self.deny(
            f"git add {self.repo}/drafts/x.md", "drafts/x.md"
        )  # dangling-ref-check: allow
        for command in (
            "git add docs/a.md",
            "git add docs/drafts-notes.md",
            "git add mydrafts/x.md",
            "git add .drafts/x.md",
            "git rm --cached drafts/x.md",  # dangling-ref-check: allow
        ):
            self.allow(command)

    def test_d3_staged_drafts_file_blocks_any_commit(self) -> None:
        """D3: a force-staged drafts file leaks through a pathspec or an amend commit."""
        self.write("drafts/x.md", "scratch\n")  # dangling-ref-check: allow
        git(self.repo, "add", "-f", "drafts/x.md")  # dangling-ref-check: allow
        self.deny(COMMIT_A, "drafts/x.md")  # dangling-ref-check: allow
        self.deny(
            "git commit --amend --no-edit", "drafts/x.md"
        )  # dangling-ref-check: allow

    def test_d3_nested_drafts_component(self) -> None:
        """D3: the drafts component may sit below the repo root."""
        self.write("sub/drafts/y.md", "scratch\n")  # dangling-ref-check: allow
        git(self.repo, "add", "-f", "sub/drafts/y.md")  # dangling-ref-check: allow
        self.deny(
            "git commit -m 'sub: Add' -- sub/drafts/y.md", "sub/drafts/y.md"
        )  # dangling-ref-check: allow

    def test_d3_untracking_a_leaked_file_is_allowed(self) -> None:
        """D3: removing a leaked file from the index is the fix and must stay committable."""
        self.write("drafts/x.md", "scratch\n")  # dangling-ref-check: allow
        git(self.repo, "add", "-f", "drafts/x.md")  # dangling-ref-check: allow
        git(self.repo, "commit", "-q", "-m", "leak")
        git(
            self.repo, "rm", "-q", "--cached", "drafts/x.md"
        )  # dangling-ref-check: allow
        self.allow(
            "git commit -m 'drafts: Untrack scratch' -- drafts/x.md"
        )  # dangling-ref-check: allow

    def test_d4_reference_added_in_working_tree_of_pathspec(self) -> None:
        """D4: a `-- PATH` commit records working-tree content that was never staged."""
        self.write(
            "docs/a.md", BASE_A + "details in `drafts/plan.md`\n"
        )  # dangling-ref-check: allow
        self.deny(COMMIT_A, "docs/a.md", "drafts/plan.md")  # dangling-ref-check: allow

    def test_d4_reference_added_in_staged_file(self) -> None:
        """D4: staged content is checked even when the pathspec names another file."""
        self.write(
            "docs/b.md", "see /home/u/repo/drafts/notes/n.md\n"
        )  # dangling-ref-check: allow
        git(self.repo, "add", "docs/b.md")
        self.deny(
            "git commit -m 'docs: Add b' -- docs/b.md",
            "docs/b.md",
            "drafts/notes/n.md",  # dangling-ref-check: allow
        )
        self.deny(COMMIT_A, "docs/b.md")

    def test_d4_concrete_reference_forms(self) -> None:
        """D4: any concrete file or dir name under a drafts component is a reference."""
        for line in (
            "`drafts/corpus-tools/extract.py`",  # dangling-ref-check: allow
            "(spec: drafts/plan.md)",  # dangling-ref-check: allow
            '"drafts/a"',  # dangling-ref-check: allow
            "./drafts/a.md",  # dangling-ref-check: allow
            "sub/drafts/_x.md",  # dangling-ref-check: allow
            "/abs/repo/drafts/9.md",  # dangling-ref-check: allow
        ):
            with self.subTest(line=line):
                self.write("docs/a.md", BASE_A + line + "\n")
                self.deny(COMMIT_A, "docs/a.md")

    def test_d4_placeholders_and_bare_mentions_are_not_references(self) -> None:
        """D4: convention text that names no concrete drafts file stays allowed."""
        for line in (
            "handoff lives at drafts/<task-slug>-handoff.md",
            "drafts/*",
            "drafts/...",
            "session-spanning files go to drafts/",
            "mydrafts/a.md",
            ".drafts/a.md",
            "drafts/$NAME",
            "drafts/{a,b}.md",
        ):
            with self.subTest(line=line):
                self.write("docs/a.md", BASE_A + line + "\n")
                self.allow(COMMIT_A)

    def test_d4_only_added_lines_count(self) -> None:
        """D4: an untouched old reference or a deleted one does not block an unrelated edit."""
        self.write(
            "docs/a.md", "intro changed\nsee `drafts/old.md`\n"
        )  # dangling-ref-check: allow
        self.allow(COMMIT_A)
        self.write("docs/a.md", "intro\n")
        self.allow(COMMIT_A)

    def test_d5_name_alone_no_longer_exempts(self) -> None:
        """D5: a test-like name or todos.md is no longer a free pass for a drafts reference."""
        for rel in (
            "todos.md",
            "files/x.test.py",
            "files/x.mutants.py",
            "files/test_x.py",
            "files/x_test.py",
            "tests/helper.py",
        ):
            with self.subTest(rel=rel):
                self.write(rel, "see drafts/plan.md\n")  # dangling-ref-check: allow
                git(self.repo, "add", rel)
                self.deny(
                    f"git commit -m 'x: Update' -- {rel}", "drafts/plan.md"
                )  # dangling-ref-check: allow

    def test_d5_preceding_line_marker_allows(self) -> None:
        """D5: a marker alone on the line immediately before an added reference exempts it."""
        self.write(
            "docs/c.md", "<!-- dangling-ref-check: allow -->\nsee drafts/plan.md\n"
        )
        git(self.repo, "add", "docs/c.md")
        self.allow("git commit -m 'docs: Add c' -- docs/c.md")

    def test_d5_same_line_marker_allows(self) -> None:
        """D5: a marker on the same added line as the reference exempts it."""
        self.write("docs/c.md", "see drafts/plan.md (dangling-ref-check: allow)\n")
        git(self.repo, "add", "docs/c.md")
        self.allow("git commit -m 'docs: Add c' -- docs/c.md")

    def test_d5_marker_elsewhere_in_file_exempts_nothing(self) -> None:
        """D5: a marker at the top of the file does not exempt a reference added further down."""
        self.write("docs/c.md", "# dangling-ref-check: allow\nintro\n")
        git(self.repo, "add", "docs/c.md")
        git(self.repo, "commit", "-q", "-m", "c: Add")
        self.write(
            "docs/c.md", "# dangling-ref-check: allow\nintro\nsee drafts/plan.md\n"
        )
        self.deny(
            "git commit -m 'c: Update' -- docs/c.md", "drafts/plan.md"
        )  # dangling-ref-check: allow

    def test_d5_preceding_unchanged_context_line_marker_allows(self) -> None:
        """D5: the preceding line may be pre-existing, unchanged context from the same diff."""
        self.write("docs/e.md", "keep\n# dangling-ref-check: allow\n")
        git(self.repo, "add", "docs/e.md")
        git(self.repo, "commit", "-q", "-m", "e: Add")
        self.write(
            "docs/e.md", "keep\n# dangling-ref-check: allow\nsee drafts/plan.md\n"
        )
        git(self.repo, "add", "docs/e.md")
        self.allow("git commit -m 'e: Update' -- docs/e.md")

    def test_d6_git_dash_c_selects_the_repo(self) -> None:
        """D6: `git -C` overrides a cwd that is not the repo."""
        self.write(
            "docs/a.md", BASE_A + "see drafts/plan.md\n"
        )  # dangling-ref-check: allow
        self.deny(
            f"git -C {self.repo} commit -m 'docs: Update' -- docs/a.md",
            "drafts/plan.md",  # dangling-ref-check: allow
            cwd=self.plain,
        )
        self.deny(
            f"git -C {self.repo} add drafts/x.md", "drafts/x.md", cwd=self.plain
        )  # dangling-ref-check: allow

    def test_d7_commit_message_is_not_a_path(self) -> None:
        """D7: messages may mention drafts paths; only recorded content matters."""
        self.write("docs/a.md", BASE_A + "plain line\n")
        self.allow(
            "git commit -m 'docs: Mention drafts/x.md' -- docs/a.md"
        )  # dangling-ref-check: allow
        self.allow(
            "git commit -m \"$(cat <<'EOF'\ndocs: Update\n\nsee drafts/x.md\nEOF\n)\" -- docs/a.md"  # dangling-ref-check: allow
        )


if __name__ == "__main__":
    unittest.main()
