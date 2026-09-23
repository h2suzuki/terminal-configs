#!/usr/bin/env python3
"""Tests for the backtest harness run.py. Each test names the use case (U<n>) it guards.

U1  the deployed gate is measured through the connected server: `calls` prints what to send
U2  unreleased gate code is measured in one process from a given file
U3  runs are kept apart by name, so variants can be scored side by side
U4  the best threshold is reported
U5  results break down by kind and by how the case was made (origin)
U6  a case judged several times reports the spread of its scores
U7  an interrupted run resumes without judging a case twice
U8  skips are counted apart from decisions, with their reasons
U9  with no key every case is still run and logged as a skip
U10 a run can be limited to kinds, origins or ids
U11 false denials and misses list the failing pieces
U12 two runs can be compared case by case
U13 request count, tokens and latency are summed
U15 any record in the gate log format scores the same, wherever it came from
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("backtest_run", HERE / "run.py")
assert spec and spec.loader
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def record(
    run_name, case_id, outcome, fits, styles=(), skip=None, tokens=10, latency=100
):
    return {
        "session_id": f"backtest:{run_name}:{case_id}",
        "outcome": outcome,
        "skip_reason": skip,
        "input_tokens": tokens,
        "latency_ms": latency,
        "request_latency_ms": [latency],
        "pieces": [
            {"file": "README.md", "line": 5, "place": "T > A", "added_head": "text", "fit": f, "failed": f is not None and f < 0.5}
            for f in fits
        ],
        "new_sections": [{"file": "README.md", "line": 9, "place": "T > B", "heading": "B", "style": s, "failed": s < 0.5} for s in styles],
    }  # fmt: skip


def case(case_id, label, kind="doc", origin="real"):
    return {
        "id": case_id,
        "label": label,
        "kind": kind,
        "origin": origin,
        "cwd": "/x",
        "command": "git commit -- a",
    }


class HarnessTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name, rows):
        path = self.dir / name
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path

    def test_u8_u5_counts_false_denials_misses_and_skips_by_kind_and_origin(self):
        cases = self.write("cases.jsonl", [
            case("g1", "good"), case("g2", "good"), case("b1", "bad"),
            case("b2", "bad", "code", "mutation-move"), case("b3", "bad", "code", "mutation-move"),
        ])  # fmt: skip
        log = self.write("log.jsonl", [
            record("r", "g1", "allow", [0.9, 0.8]), record("r", "g2", "deny", [0.3]),
            record("r", "b1", "deny", [0.9], styles=[0.2]), record("r", "b2", "allow", [0.7]),
            record("r", "b3", "skip", [None], skip="No API key saved."),
            {"session_id": "someone-else", "outcome": "deny", "pieces": []},
        ])  # fmt: skip
        report = run.score(cases, log, "r")
        self.assertEqual(
            report["kind"]["doc"]["good"],
            {"n": 2, "denied": 1, "skipped": 0, "unjudged": 0},
        )
        self.assertEqual(
            report["kind"]["doc"]["bad"],
            {"n": 1, "allowed": 0, "skipped": 0, "unjudged": 0},
        )
        self.assertEqual(
            report["kind"]["code"]["bad"],
            {"n": 2, "allowed": 1, "skipped": 1, "unjudged": 0},
        )
        self.assertEqual(report["origin"]["mutation-move"]["bad"]["n"], 2)
        self.assertEqual(report["all"]["skip_reasons"], {"No API key saved.": 1})
        # A case scores its weakest judged piece or section.
        self.assertEqual(report["kind"]["doc"]["min_good"], 0.3)
        self.assertEqual(report["kind"]["doc"]["max_bad"], 0.2)
        self.assertAlmostEqual(report["kind"]["doc"]["margin"], 0.1)

    def test_u3_runs_are_scored_apart(self):
        cases = self.write("cases.jsonl", [case("g1", "good")])
        log = self.write(
            "log.jsonl",
            [record("a", "g1", "deny", [0.2]), record("b", "g1", "allow", [0.9])],
        )
        self.assertEqual(run.score(cases, log, "a")["all"]["good"]["denied"], 1)
        self.assertEqual(run.score(cases, log, "b")["all"]["good"]["denied"], 0)

    def test_u4_best_threshold_separates_judged_scores(self):
        cases = self.write(
            "cases.jsonl", [case("g1", "good"), case("g2", "good"), case("b1", "bad")]
        )
        log = self.write(
            "log.jsonl",
            [
                record("r", "g1", "allow", [0.8]),
                record("r", "g2", "allow", [0.6]),
                record("r", "b1", "allow", [0.55]),
            ],
        )
        best = run.score(cases, log, "r")["all"]["best_threshold"]
        self.assertGreater(best["threshold"], 0.55)
        self.assertLessEqual(best["threshold"], 0.6)
        self.assertEqual((best["correct"], best["judged"]), (3, 3))

    def test_u6_repeated_judgments_report_the_spread(self):
        cases = self.write("cases.jsonl", [case("g1", "good")])
        log = self.write(
            "log.jsonl",
            [record("r", "g1#1", "allow", [0.6]), record("r", "g1#2", "allow", [0.7])],
        )
        report = run.score(cases, log, "r")
        self.assertAlmostEqual(report["all"]["max_spread"], 0.1)
        self.assertAlmostEqual(report["kind"]["doc"]["min_good"], 0.65)

    def test_u11_problem_cases_list_the_failing_pieces(self):
        cases = self.write("cases.jsonl", [case("g1", "good"), case("b1", "bad")])
        log = self.write(
            "log.jsonl",
            [record("r", "g1", "deny", [0.9, 0.2]), record("r", "b1", "allow", [0.8])],
        )
        report = run.score(cases, log, "r")
        (fd,) = report["false_denials"]
        self.assertEqual(fd["id"], "g1")
        self.assertEqual([p["fit"] for p in fd["failing"]], [0.2])
        self.assertEqual(report["misses"][0]["id"], "b1")

    def test_u12_diff_lists_cases_whose_decision_changed(self):
        cases = self.write("cases.jsonl", [case("g1", "good"), case("g2", "good")])
        log = self.write("log.jsonl", [
            record("a", "g1", "deny", [0.2]), record("b", "g1", "allow", [0.9]),
            record("a", "g2", "allow", [0.9]), record("b", "g2", "allow", [0.8]),
        ])  # fmt: skip
        self.assertEqual(
            run.diff(cases, log, "a", "b"),
            [{"id": "g1", "label": "good", "kind": "doc", "a": "deny", "b": "allow"}],
        )

    def test_u13_cost_is_summed(self):
        cases = self.write("cases.jsonl", [case("g1", "good"), case("b1", "bad")])
        log = self.write(
            "log.jsonl",
            [
                record("r", "g1", "allow", [0.9], tokens=30, latency=200),
                record("r", "b1", "deny", [0.1], tokens=12, latency=100),
            ],
        )
        cost = run.score(cases, log, "r")["all"]["cost"]
        self.assertEqual(cost, {"requests": 2, "input_tokens": 42, "latency_ms": 300})

    def test_u10_selection_by_kind_origin_and_id(self):
        cases = [
            case("a", "good", "doc"),
            case("b", "bad", "code", "mutation-move"),
            case("c", "bad", "code"),
        ]
        self.assertEqual(
            [c["id"] for c in run.select(cases, kinds=["code"])], ["b", "c"]
        )
        self.assertEqual(
            [c["id"] for c in run.select(cases, origins=["real"])], ["a", "c"]
        )
        self.assertEqual([c["id"] for c in run.select(cases, ids=["c"])], ["c"])

    def test_u1_calls_name_each_case_by_run(self):
        cases = self.write("cases.jsonl", [case("g1", "good")])
        (call,) = run.calls(cases, "live")
        self.assertEqual(
            call,
            {
                "cwd": "/x",
                "command": "git commit -- a",
                "session_id": "backtest:live:g1",
            },
        )


class JudgeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        run.git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "README.md").write_text("# T\n\n## A\n\nText.\n")
        run.git(self.repo, "add", "README.md")
        run.git(self.repo, "commit", "-q", "-m", "base")
        (self.repo / "README.md").write_text(
            "# T\n\n## A\n\nText.\n\nMore text here.\n"
        )
        self.cases = root / "cases.jsonl"
        self.cases.write_text(
            json.dumps(
                {
                    **case("c1", "good"),
                    "cwd": str(self.repo),
                    "command": 'git commit -m "docs: More" -- README.md',
                }
            )
            + "\n"
        )
        self.log = root / "log.jsonl"
        self.calls = 0

    async def no_key(self, state, questions):
        self.calls += 1
        raise run.load_jev().JevError(
            "No API key saved. Run jev api-key set in your terminal."
        )

    async def fits(self, state, questions):
        self.calls += 1
        return {
            "answers": {k: {"type": "noul", "noul": 0.9} for k in questions},
            "model": "stub",
            "usage": {"input_tokens": 3},
        }

    def records(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_u9_without_a_key_every_case_is_logged_as_a_skip(self):
        run.judge(self.cases, self.log, "nokey", evaluate=self.no_key)
        (rec,) = self.records()
        self.assertEqual(rec["session_id"], "backtest:nokey:c1")
        self.assertEqual(rec["outcome"], "skip")
        self.assertIn("No API key saved", rec["skip_reason"])

    def test_u2_u7_u6_judges_from_a_gate_file_resumes_and_repeats(self):
        gate = (
            Path(__file__).resolve().parent.parent.parent
            / "files"
            / "jev_context_gate.py"
        )
        run.judge(self.cases, self.log, "r", gate=gate, evaluate=self.fits)
        # Resumed: the case is already logged, so nothing is judged again.
        run.judge(self.cases, self.log, "r", gate=gate, evaluate=self.fits)
        self.assertEqual(self.calls, 1)
        run.judge(self.cases, self.log, "rep", gate=gate, evaluate=self.fits, repeat=2)
        self.assertEqual(
            [r["session_id"] for r in self.records()],
            ["backtest:r:c1", "backtest:rep:c1#1", "backtest:rep:c1#2"],
        )
        self.assertEqual(
            run.score(self.cases, self.log, "r")["all"]["good"]["denied"], 0
        )


if __name__ == "__main__":
    unittest.main()
