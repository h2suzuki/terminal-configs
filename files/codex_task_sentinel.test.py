#!/usr/bin/env python3
"""Keeps the codex-delegation skill's exit table in step with the watcher's own, since the skill is what a caller reads before choosing flags."""

from __future__ import annotations

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SENTINEL = os.path.join(HERE, "codex_task_sentinel")
SKILL = os.path.join(HERE, "claude_managed-skills", "codex-delegation", "SKILL.md")

# "  4  stall             --trust-log only: log and tree quiet — ..."
MODULE_ROW = re.compile(r"^ {2}(\d+)\s+\S+\s{2,}(.+)$")
# "  | 4 | stall (`--trust-log` 時のみ) | log を読み、... |"
SKILL_ROW = re.compile(r"^\s*\|\s*(\d+)\s*\|([^|]*)\|")

TRUST_FLAG = "--trust-log"


def _read(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _rows(lines: list[str], pattern: re.Pattern[str]) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in map(pattern.match, lines) if m}


class ExitTableSyncTest(unittest.TestCase):
    """The skill teaches the operating rule; a stale table sends callers to the wrong branch."""

    def setUp(self):
        self.module = _rows(_read(SENTINEL), MODULE_ROW)
        self.skill = _rows(_read(SKILL), SKILL_ROW)

    def test_both_tables_are_populated(self):
        """空の parse は差分ゼロに見えてしまうので、まず両表が読めていることを確かめる。"""
        self.assertGreaterEqual(len(self.module), 10)
        self.assertGreaterEqual(len(self.skill), 10)

    def test_the_skill_lists_every_exit_code(self):
        self.assertEqual(sorted(self.module, key=int), sorted(self.skill, key=int))

    def test_opt_in_codes_are_marked_opt_in_in_the_skill(self):
        """既定で出ない verdict を既定の導線として教えると、呼び手が動く job を cancel する。"""
        for code, text in self.module.items():
            if TRUST_FLAG in text:
                self.assertIn(TRUST_FLAG, self.skill[code], f"exit {code}")

    def test_the_skill_states_the_default_hands_over(self):
        body = "\n".join(_read(SKILL))
        self.assertIn("既定は cancel を指示しない", body)


if __name__ == "__main__":
    unittest.main()
