#!/usr/bin/env python3
"""Exercise Codex's validated stdin writer against an isolated Git clone."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "files" / "claude_memory_sync"
GATE = ROOT / "files" / "claude_managed-hooks" / "memory_routing_gate.py"
CONTENT = """---
name: test_feature_value
description: Test a concrete feature benefit before retaining it
metadata:
  type: feedback
reminder: 機能を残す前に利用者にとっての利益を示せ
keywords: 利用者利益, feature benefit, agent_coord, 機能の価値
models: gpt-6-astra
check: 回答に具体的な利用者利益があるか確認せよ
when: prompt
---

## 理由

利益の説明が無いと不要機能を残す。

## 事例

- 2026-09-22: 実装の説明に終始した。
"""


class WriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clone = Path(self.tmp.name) / "clone"
        subprocess.run(["git", "init", "-q", str(self.clone)], check=True)
        for key, value in (("user.name", "Test"), ("user.email", "test@example.org")):
            subprocess.run(
                ["git", "-C", str(self.clone), "config", key, value], check=True
            )
        self.log = Path(self.tmp.name) / "index.log"
        self.surface = Path(self.tmp.name) / "surface.py"
        self.surface.write_text(
            "import os, sys\n"
            "with open(os.environ['INDEX_LOG'], 'a') as f:\n"
            "    f.write(' '.join(sys.argv[1:]) + '\\n')\n",
            encoding="utf-8",
        )
        env = {"CLAUDE_MEMORY_REPO": str(self.clone), "INDEX_LOG": str(self.log)}
        with mock.patch.dict(os.environ, env):
            loader = importlib.machinery.SourceFileLoader(
                "memory_sync_write_test", str(SOURCE)
            )
            spec = importlib.util.spec_from_loader(loader.name, loader)
            self.sync = importlib.util.module_from_spec(spec)
            loader.exec_module(self.sync)
        self.sync.GATE_PATH = str(GATE)
        self.sync.SURFACE_CLI = str(self.surface)
        self.target = self.clone / "org" / "feedback_test_feature_value.md"

    def write(self, path, content):
        with (
            mock.patch.dict(os.environ, {"INDEX_LOG": str(self.log)}),
            mock.patch.object(sys, "stdin", io.StringIO(content)),
            mock.patch.object(self.sync, "spawn_push"),
        ):
            return self.sync.main_write(str(path))

    def write_from(self, path, content):
        draft = Path(self.tmp.name) / "entry-draft.md"
        draft.write_text(content, encoding="utf-8")
        with (
            mock.patch.dict(os.environ, {"INDEX_LOG": str(self.log)}),
            mock.patch.object(self.sync, "spawn_push"),
            mock.patch.object(sys, "argv", ["claude_memory_sync", "--write-from", str(draft), str(path)]),
        ):
            return self.sync.main()

    def test_valid_entry_is_indexed_and_committed(self):
        self.assertEqual(self.write(self.target, CONTENT), 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), CONTENT)
        committed = subprocess.run(
            [
                "git",
                "-C",
                str(self.clone),
                "show",
                "HEAD:org/feedback_test_feature_value.md",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(committed.stdout, CONTENT)
        self.assertIn("--upsert", self.log.read_text(encoding="utf-8"))

    def test_invalid_or_outside_entry_does_not_write(self):
        self.assertEqual(self.write(self.target, "bad entry"), 1)
        self.assertFalse(self.target.exists())
        outside = Path(self.tmp.name) / "feedback_outside.md"
        self.assertEqual(self.write(outside, CONTENT), 1)
        self.assertFalse(outside.exists())

    def test_draft_creates_and_updates_one_entry(self):
        self.assertEqual(self.write_from(self.target, CONTENT), 0)
        updated = CONTENT.replace("利益の説明が無い", "具体的な利益の説明が無い")
        self.assertEqual(self.write_from(self.target, updated), 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), updated)
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(self.clone), "show", "HEAD:org/feedback_test_feature_value.md"],
                check=True, capture_output=True, text=True,
            ).stdout,
            updated,
        )
        self.assertEqual(self.write_from(self.target, "bad entry"), 1)
        self.assertEqual(self.target.read_text(encoding="utf-8"), updated)


if __name__ == "__main__":
    unittest.main()
