#!/usr/bin/env python3
"""Keeps the codex-delegation skill's exit table in step with the watcher's own and with the CLI it documents, since the skill is what a caller reads before choosing flags."""

from __future__ import annotations

import ast
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
RULINGS = os.path.join(HERE, "..", "docs", "sentinel-rulings.md")

# "  4  stall             --trust-log only: log and tree quiet — ..."
MODULE_ROW = re.compile(r"^ {2}(\d+)\s+(\S+)\s{2,}(.+)$")
# "  | 4 | stall (`--trust-log` 時のみ) | log を読み、... |"
SKILL_ROW = re.compile(r"^\s*\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|")
RULING_ROW = re.compile(r"^\|\s*(\d+)\s*\|.*\|\s*[A-D]\s*\|\s*(.*?)\s*\|$")
RULING_TEST = re.compile(r"`(test_[A-Za-z0-9_]+)`")
LAST_RULING = 62

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


def _rows(lines: list[str], pattern: re.Pattern[str]) -> dict[str, tuple[str, ...]]:
    """code -> 以降の列。 重複 code は dict の後勝ちで隠れるので _row_codes と併用する。"""
    return {
        m.group(1): tuple(g.strip() for g in m.groups()[1:])
        for m in map(pattern.match, lines)
        if m
    }


def _row_codes(lines: list[str], pattern: re.Pattern[str]) -> list[str]:
    return [m.group(1) for m in map(pattern.match, lines) if m]


class ExitTableSyncTest(unittest.TestCase):
    """The skill teaches the operating rule; a stale table sends callers to the wrong branch."""

    def setUp(self):
        self.module = _rows(_read(SENTINEL), MODULE_ROW)
        self.skill = _rows(_read(SKILL), SKILL_ROW)

    @staticmethod
    def _runtime_codes() -> set[str]:
        """実装が実際に返す exit 値 — 表どうしの比較だけでは定数の書き換えを見逃す。"""
        return {str(row[0]) for row in sentinel.EXIT_CONTRACT}

    def test_the_contract_covers_every_constant_exactly_once(self):
        """値の集合だけを見ると、 名前の入れ替えも値の重複も同じ集合のまま通る。"""
        declared = {
            n: v
            for n, v in vars(sentinel).items()
            if n.startswith("EXIT_") and isinstance(v, int)
        }
        self.assertEqual(
            declared, {n: code for code, n, _s, _m, _a in sentinel.EXIT_CONTRACT}
        )
        codes = [code for code, _n, _s, _m, _a in sentinel.EXIT_CONTRACT]
        self.assertEqual(len(codes), len(set(codes)))

    def test_neither_table_repeats_a_code(self):
        """重複行は dict の後勝ちで消える — 誤った行を正しい行の前に足す変異が隠れる。"""
        for lines, pattern in (
            (_read(SENTINEL), MODULE_ROW),
            (_read(SKILL), SKILL_ROW),
        ):
            codes = _row_codes(lines, pattern)
            self.assertEqual(len(codes), len(set(codes)), codes)

    def test_the_docstring_row_carries_the_contract_slug(self):
        for code, _n, slug, _m, _a in sentinel.EXIT_CONTRACT:
            self.assertEqual(self.module[str(code)][0], slug, f"exit {code}")

    def test_the_skill_row_carries_the_contract_meaning_and_action(self):
        """意味も呼び手の行動も契約と揃える — 数値集合が同じ変異は集合比較では捕まらない。"""
        for code, _n, _s, meaning, action in sentinel.EXIT_CONTRACT:
            self.assertEqual(self.skill[str(code)], (meaning, action), f"exit {code}")

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
                # 成果物は不存在のまま指定する — quiet-job の oracle を保つ
                "--artifact",
                os.path.join(root, "report.md"),
                "--token",
                "REPORT_COMPLETE",
                *extra,
            ],
            capture_output=True,
            check=False,
        ).returncode

    def test_a_quiet_job_is_handed_over_by_default_and_asserted_only_on_opt_in(self):
        root = self._quiet_job()
        self.assertEqual(self._run(root), sentinel.EXIT_UNVERIFIABLE)
        self.assertEqual(self._run(root, TRUST_FLAG), sentinel.EXIT_STALL)


class RulingsSyncTest(unittest.TestCase):
    """The canonical rulings stay ordered and name tests that exist in the source."""

    def test_rulings_are_contiguous_and_reference_existing_test_methods(self):
        rows = [
            (int(match.group(1)), match.group(2))
            for match in map(RULING_ROW.match, _read(RULINGS))
            if match
        ]
        numbers = [number for number, _assurance in rows]
        self.assertEqual(numbers, list(range(1, LAST_RULING + 1)))

        source = "\n".join(_read(SENTINEL))
        methods = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }
        referenced = {
            name
            for _number, assurance in rows
            for name in RULING_TEST.findall(assurance)
        }
        self.assertTrue(referenced)
        self.assertEqual(referenced - methods, set())


class RunnerConfigurationTest(unittest.TestCase):
    """The external suite must keep its own terminal output behind the sink."""

    def test_the_runner_uses_the_oserror_stream(self):
        tree = ast.parse("\n".join(_read(__file__)))
        main_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "unittest"
            and node.func.attr == "main"
        ]
        self.assertEqual(len(main_calls), 1)
        runners = [
            keyword.value
            for keyword in main_calls[0].keywords
            if keyword.arg == "testRunner"
        ]
        self.assertEqual(len(runners), 1)
        runner = ast.dump(runners[0])
        self.assertIn("TextTestRunner", runner)
        self.assertIn("OSErrorStream", runner)


if __name__ == "__main__":
    unittest.main(
        testRunner=unittest.TextTestRunner(
            verbosity=2,
            stream=sentinel.Observation.OSErrorStream(sys.stderr),
        )
    )
