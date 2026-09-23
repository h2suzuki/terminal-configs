#!/usr/bin/env python3
"""Tests for the worktree_home hook against throwaway git repositories and a temporary HOME."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = (
    Path(__file__).resolve().parent.parent
    / "files"
    / "claude_managed-hooks"
    / "worktree_home.py"
)


class WorktreeHomeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.home.mkdir()
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.repo = Path(tmp.name) / "proj"
        self.run_git("init", "-q", "-b", "main", str(self.repo), cwd=Path(tmp.name))
        self.run_git("commit", "-q", "--allow-empty", "-m", "init", cwd=self.repo)

    def run_git(self, *args: str, cwd: Path) -> str:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=True,
            env=self.env,
        ).stdout.strip()

    def hook(self, payload: dict) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )

    def create(
        self, name: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self.hook(
            {
                "hook_event_name": "WorktreeCreate",
                "name": name,
                "cwd": str(cwd or self.repo),
            }
        )

    def remove(self, path: Path) -> subprocess.CompletedProcess[str]:
        return self.hook(
            {
                "hook_event_name": "WorktreeRemove",
                "worktree_path": str(path),
                "cwd": str(self.repo),
            }
        )

    def test_create_places_worktree_under_home_worktrees_on_branch_named_after_it(self):
        result = self.create("feat-a")
        target = self.home / "worktrees" / "proj" / "feat-a"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], str(target))
        self.assertEqual(self.run_git("branch", "--show-current", cwd=target), "feat-a")

    def test_create_again_reuses_the_existing_worktree(self):
        first = self.create("feat-a")
        second = self.create("feat-a")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout, first.stdout)

    def test_create_from_a_linked_worktree_uses_the_main_repository_name(self):
        inner = Path(self.create("outer").stdout.strip())
        result = self.create("inner", cwd=inner)
        self.assertEqual(
            result.stdout.strip(), str(self.home / "worktrees" / "proj" / "inner")
        )

    def test_create_reuses_an_existing_branch(self):
        self.run_git("branch", "feat-b", cwd=self.repo)
        result = self.create("feat-b")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.run_git("branch", "--show-current", cwd=Path(result.stdout.strip())),
            "feat-b",
        )

    def test_create_starts_from_origin_head_when_the_remote_default_exists(self):
        clone = self.repo.parent / "clone"
        self.run_git("clone", "-q", str(self.repo), str(clone), cwd=self.repo.parent)
        self.run_git("commit", "-q", "--allow-empty", "-m", "local only", cwd=clone)
        result = self.create("feat-c", cwd=clone)
        target = Path(result.stdout.strip())
        self.assertEqual(target, self.home / "worktrees" / "clone" / "feat-c")
        self.assertEqual(
            self.run_git("rev-parse", "HEAD", cwd=target),
            self.run_git("rev-parse", "origin/HEAD", cwd=clone),
        )

    def test_create_rejects_names_that_escape_the_worktree_root(self):
        # An existing directory skips git, so only the hook's own name check can refuse it.
        (self.home / "worktrees" / "escape").mkdir(parents=True)
        for existing in ("a", "b"):
            (self.home / "worktrees" / "proj" / existing).mkdir(parents=True)
        for name in ("../escape", "a/../b", "", "with space"):
            with self.subTest(name=name):
                result = self.create(name)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")

    def test_create_outside_a_repository_fails(self):
        result = self.create("feat-d", cwd=self.home)
        self.assertEqual(result.returncode, 1)

    def test_remove_deletes_a_clean_worktree_and_its_merged_branch(self):
        target = Path(self.create("feat-e").stdout.strip())
        result = self.remove(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(self.run_git("branch", "--list", "feat-e", cwd=self.repo), "")

    def test_remove_keeps_a_worktree_with_changes(self):
        target = Path(self.create("feat-f").stdout.strip())
        (target / "wip.txt").write_text("wip\n")
        result = self.remove(target)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((target / "wip.txt").exists())

    def test_remove_keeps_an_unmerged_branch(self):
        target = Path(self.create("feat-g").stdout.strip())
        self.run_git("commit", "-q", "--allow-empty", "-m", "work", cwd=target)
        self.assertEqual(self.remove(target).returncode, 0)
        self.assertEqual(
            self.run_git(
                "branch", "--list", "feat-g", "--format=%(refname:short)", cwd=self.repo
            ),
            "feat-g",
        )

    def test_remove_of_a_missing_directory_succeeds(self):
        self.assertEqual(
            self.remove(self.home / "worktrees" / "proj" / "gone").returncode, 0
        )


if __name__ == "__main__":
    unittest.main()
