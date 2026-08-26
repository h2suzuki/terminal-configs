#!/usr/bin/env python3
"""Contract for the auth-failure marker: only credential errors leave it, any success clears it.

A1  transport failure whose stderr names an auth problem -> marker holds the first 300 chars
A2  transport failure with any other stderr (e.g. non-fast-forward) -> no marker
A3  a later success removes an existing marker
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "claude_memory_sync")


def load_cli(repo: str):
    os.environ["CLAUDE_MEMORY_REPO"] = repo
    loader = importlib.machinery.SourceFileLoader("claude_memory_sync", CLI)
    spec = importlib.util.spec_from_loader("claude_memory_sync", loader)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AuthMarkerTest(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.repo = os.path.join(holder.name, "clone")
        os.makedirs(os.path.join(self.repo, ".git"))
        self.cli = load_cli(self.repo)
        self.marker = os.path.join(self.repo, ".git", "auth-failure")

    def test_a1_auth_failure_leaves_marker(self) -> None:
        self.cli.record_transport(
            False, "fatal: Authentication failed for 'https://x/y.git'\n"
        )
        with open(self.marker, encoding="utf-8") as fh:
            self.assertIn("Authentication failed", fh.read())

    def test_a2_other_failure_leaves_no_marker(self) -> None:
        self.cli.record_transport(False, "! [rejected] main -> main (fetch first)\n")
        self.assertFalse(os.path.exists(self.marker))

    def test_a3_success_clears_marker(self) -> None:
        self.cli.record_transport(False, "remote: Permission denied (publickey).\n")
        self.assertTrue(os.path.exists(self.marker))
        self.cli.record_transport(True, "")
        self.assertFalse(os.path.exists(self.marker))


if __name__ == "__main__":
    unittest.main()
