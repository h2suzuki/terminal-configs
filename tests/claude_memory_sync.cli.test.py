#!/usr/bin/env python3
"""Acceptance tests for the claude_memory_sync argparse surface (usage help and dispatch).

Contract (each claim maps to one test):
  C1  `--help` and `-h` exit 0; the text names every command flag and the clone layout
  C2  no arguments is `--status`: identical output and exit status
  C3  an unknown flag exits 2 with a usage line on stderr
  C4  `--commit` / `--retire` without PATH exit 2
  C5  two commands at once exit 2 (mutually exclusive)
  C6  a relative PATH is resolved against the cwd before the command sees it
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files")
CLI = os.path.join(HERE, "claude_memory_sync")
COMMANDS = (
    "--pull",
    "--commit",
    "--retire",
    "--full",
    "--status",
    "--reach",
    "--push-bg",
)


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {
            **os.environ,
            "CLAUDE_MEMORY_REPO": os.path.join(self.tmp.name, "clone"),
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, CLI, *args],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
            cwd=self.tmp.name,
            timeout=60,
        )

    def test_c1_help(self) -> None:
        for flag in ("--help", "-h"):
            out = self.run_cli(flag)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(out.stdout.startswith("usage: claude_memory_sync"))
            for cmd in COMMANDS:
                self.assertIn(cmd, out.stdout)
            self.assertIn("org/<entry>.md", out.stdout)
            self.assertIn("CLAUDE_MEMORY_REPO", out.stdout)

    def test_c2_default_is_status(self) -> None:
        bare, status = self.run_cli(), self.run_cli("--status")
        self.assertEqual(bare.returncode, status.returncode)
        self.assertEqual(bare.stdout, status.stdout)
        self.assertIn("state: MISSING", bare.stdout)

    def test_c3_unknown_flag(self) -> None:
        out = self.run_cli("--bogus")
        self.assertEqual(out.returncode, 2)
        self.assertIn("usage: claude_memory_sync", out.stderr)
        self.assertIn("--bogus", out.stderr)

    def test_c4_missing_path(self) -> None:
        for cmd in ("--commit", "--retire"):
            out = self.run_cli(cmd)
            self.assertEqual(out.returncode, 2, cmd)
            self.assertIn("expected one argument", out.stderr)

    def test_c5_mutually_exclusive(self) -> None:
        out = self.run_cli("--pull", "--status")
        self.assertEqual(out.returncode, 2)
        self.assertIn("not allowed with", out.stderr)

    def test_c6_relative_path_resolved(self) -> None:
        out = self.run_cli("--retire", "elsewhere/entry.md")
        self.assertEqual(out.returncode, 1)
        self.assertIn(os.path.join(self.tmp.name, "elsewhere/entry.md"), out.stderr)


if __name__ == "__main__":
    unittest.main()
