#!/usr/bin/env python3
"""Keeps the codex-delegation skill's exit table in step with the watcher's own and with the CLI it documents, since the skill is what a caller reads before choosing flags."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SENTINEL = os.path.join(HERE, "codex_task_sentinel")
SKILL = os.path.join(HERE, "claude_managed-skills", "codex-delegation", "SKILL.md")

# "  4  stall             --trust-log only: log and tree quiet — ..."
MODULE_ROW = re.compile(r"^ {2}(\d+)\s+\S+\s{2,}(.+)$")
# "  | 4 | stall (`--trust-log` 時のみ) | log を読み、... |"
SKILL_ROW = re.compile(r"^\s*\|\s*(\d+)\s*\|([^|]*)\|")

TRUST_FLAG = "--trust-log"

SPEC = importlib.util.spec_from_loader(
    "codex_task_sentinel",
    importlib.machinery.SourceFileLoader("codex_task_sentinel", SENTINEL),
)
assert SPEC is not None and SPEC.loader is not None
sentinel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sentinel
SPEC.loader.exec_module(sentinel)


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

    @staticmethod
    def _runtime_codes() -> set[str]:
        """実装が実際に返す exit 値 — 表どうしの比較だけでは定数の書き換えを見逃す。"""
        return {
            str(v)
            for n, v in vars(sentinel).items()
            if n.startswith("EXIT_") and isinstance(v, int)
        }

    def test_both_tables_are_populated(self):
        """空の parse は差分ゼロに見えてしまうので、まず両表が読めていることを確かめる。"""
        self.assertGreaterEqual(len(self.module), 10)
        self.assertGreaterEqual(len(self.skill), 10)
        self.assertGreaterEqual(len(self._runtime_codes()), 10)

    def test_the_skill_lists_every_exit_code(self):
        self.assertEqual(sorted(self.module, key=int), sorted(self.skill, key=int))

    def test_both_tables_match_the_values_the_code_returns(self):
        """docstring と skill が揃っていても、 定数を変えれば実 exit だけがずれる。"""
        runtime = self._runtime_codes()
        self.assertEqual(set(self.module), runtime)
        self.assertEqual(set(self.skill), runtime)

    def test_the_two_tables_agree_on_which_codes_are_opt_in(self):
        """片方向の含意だと、 module 側だけを既定へ書き換える drift が green のまま通る。"""
        self.assertEqual(
            {c for c, t in self.module.items() if TRUST_FLAG in t},
            {c for c, t in self.skill.items() if TRUST_FLAG in t},
        )

    def test_the_skill_states_the_default_hands_over(self):
        body = "\n".join(_read(SKILL))
        self.assertIn("既定は cancel を指示しない", body)


class DocumentedDefaultTest(unittest.TestCase):
    """両表が同じ誤記で揃えば docs 同士の比較は通る — 実 CLI の既定そのものを pin する。"""

    def test_the_parser_defaults_to_not_trusting_the_log(self):
        parser = sentinel.build_parser()
        self.assertIs(parser.parse_args(["task-x"]).trust_log, False)
        self.assertIs(parser.parse_args(["task-x", TRUST_FLAG]).trust_log, True)

    def _quiet_job(self) -> str:
        """静穏な log とツリーを持つ running job 一式を作り、 state root を返す。"""
        root = tempfile.mkdtemp()
        jobs = os.path.join(root, "ws", "jobs")
        tree = os.path.join(root, "tree")
        os.makedirs(jobs)
        os.makedirs(tree)
        with open(os.path.join(jobs, "task-q.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "task-q", "status": "running", "workspaceRoot": tree}, f)
        log = os.path.join(jobs, "task-q.log")
        with open(log, "w", encoding="utf-8") as f:
            f.write("[2026-08-08T22:00:00.000Z] quiet\n")
        written = os.path.join(tree, "f")  # 空ツリーは 「読めない」 側に落ちる
        with open(written, "w", encoding="utf-8") as f:
            f.write("x")
        stale = time.time() - 600
        for path in (log, written, tree):
            os.utime(path, (stale, stale))
        return root

    def _run(self, root: str, *extra: str) -> int:
        return subprocess.run(
            [
                sys.executable,
                SENTINEL,
                "task-q",
                "--state-root",
                root,
                "--once",
                "--stall-seconds",
                "1",
                "--hang-seconds",
                "1",
                *extra,
            ],
            capture_output=True,
            check=False,
        ).returncode

    def test_a_quiet_job_is_handed_over_by_default_and_asserted_only_on_opt_in(self):
        root = self._quiet_job()
        self.assertEqual(self._run(root), sentinel.EXIT_UNVERIFIABLE)
        self.assertEqual(self._run(root, TRUST_FLAG), sentinel.EXIT_STALL)


if __name__ == "__main__":
    unittest.main()
