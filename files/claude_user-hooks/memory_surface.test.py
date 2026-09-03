#!/usr/bin/env python3
"""Acceptance tests for the per-session emit cap in memory_surface.py, written by the ordering side first.

Contract (each claim maps to one test):
  C1  SESSION_EMIT_CAP = 2: once an entry has two kind='emit' rows in the session, _surface_core skips it
      even after THROTTLE_SECONDS has passed, and the next-best pick surfaces instead
  C2  the cap is per session: another session_id starts from zero for the same entry
  C3  kind='mismatch' rows do not count toward the cap
  C4  when every pick is capped, _surface_core returns [] and records nothing
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "memory_surface_under_test", os.path.join(HERE, "memory_surface.py")
)
assert SPEC is not None and SPEC.loader is not None
ms = importlib.util.module_from_spec(SPEC)
sys.modules["memory_surface_under_test"] = ms
SPEC.loader.exec_module(ms)

PICKS = [("/m/a.md", "reminder A", 0.9), ("/m/b.md", "reminder B", 0.8)]
PROJECT = "proj"


class CapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(
                ms, "DB_PATH", os.path.join(self.tmp.name, "idx.sqlite3")
            ),
            mock.patch.object(ms, "_build_query", lambda text: "q"),
            mock.patch.object(ms, "_bm_candidates", lambda con, q, p: [("row",)]),
            mock.patch.object(ms, "_hybrid_picks", lambda *a, **k: list(PICKS)),
        ]
        for p in self.patches:
            p.start()
        con = ms._connect()
        assert con is not None
        self.con: sqlite3.Connection = con

    def tearDown(self) -> None:
        self.con.close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def surface(self, session: str, now: float) -> list[str]:
        out = ms._surface_core(self.con, "text", session, PROJECT, now, 1, None)
        return [path for path, _reminder, _score in out]

    def test_c1_third_surface_in_a_session_rotates_to_the_next_pick(self) -> None:
        step = ms.THROTTLE_SECONDS + 100
        self.assertEqual(self.surface("s1", 1000), ["/m/a.md"])
        self.assertEqual(self.surface("s1", 1000 + step), ["/m/a.md"])
        self.assertEqual(self.surface("s1", 1000 + 2 * step), ["/m/b.md"])

    def test_c2_cap_is_per_session(self) -> None:
        step = ms.THROTTLE_SECONDS + 100
        for i in range(2):
            self.surface("s1", 1000 + i * step)
        self.assertEqual(self.surface("s1", 1000 + 2 * step), ["/m/b.md"])
        self.assertEqual(self.surface("s2", 1000 + 3 * step), ["/m/a.md"])

    def test_c3_mismatch_rows_do_not_count(self) -> None:
        for i in range(3):
            ms._record_inject(
                self.con,
                "/m/a.md",
                PROJECT,
                "s1",
                100 + i,
                0.5,
                "text",
                "x",
                "mismatch",
            )
        self.assertEqual(self.surface("s1", 10_000), ["/m/a.md"])

    def test_c4_all_capped_returns_nothing_and_records_nothing(self) -> None:
        step = ms.THROTTLE_SECONDS + 100
        for i in range(4):
            self.surface("s1", 1000 + i * step)
        before = self.con.execute("SELECT COUNT(*) FROM inject_log").fetchone()[0]
        self.assertEqual(self.surface("s1", 1000 + 4 * step), [])
        after = self.con.execute("SELECT COUNT(*) FROM inject_log").fetchone()[0]
        self.assertEqual(before, after)


class WhenDispatchTest(unittest.TestCase):
    """`when:` dispatch, written by the ordering side first.

    Contract (each claim maps to one test):
      W1  when: absent -> default prompt: the entry surfaces on the prompt route
      W2  when: stop alone -> the entry never surfaces on the prompt route
      W3  when: listing two values -> the entry surfaces on both of its routes
      W4  the dense route is filtered by the same predicate (passed into _hybrid_picks)
      W5  the BM25 fallback route is filtered by the same predicate
      W6  SubagentStop queries with last_assistant_message on the after-subagent
          route and re-wakes the main agent (exit 2) with the reminder
      W7  SubagentStop with no matching entry writes nothing and exits 0
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.entries = {
            "plain": self._entry("plain", None),
            "stoponly": self._entry("stoponly", "stop"),
            "both": self._entry("both", "prompt after-subagent"),
        }
        self.patches = [
            mock.patch.object(
                ms, "DB_PATH", os.path.join(self.tmp.name, "idx.sqlite3")
            ),
            mock.patch.object(ms, "_build_query", lambda text: "q"),
            mock.patch.object(ms, "_bm_candidates", lambda con, q, p: self.rows()),
        ]
        for p in self.patches:
            p.start()
        con = ms._connect()
        assert con is not None
        self.con: sqlite3.Connection = con

    def tearDown(self) -> None:
        self.con.close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _entry(self, name: str, when: str | None) -> str:
        path = os.path.join(self.tmp.name, name + ".md")
        head = "---\nkeywords: x\n" + (f"when: {when}\n" if when else "") + "---\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(head + "body\n")
        return path

    def rows(self) -> list[tuple[str, str, float]]:
        return [
            (self.entries["stoponly"], "reminder stop", -7.0),
            (self.entries["plain"], "reminder plain", -6.0),
            (self.entries["both"], "reminder both", -5.0),
        ]

    def surface(self, when: str, dense: bool) -> list[str]:
        def hybrid(con, prompt, project_id, bm_rows, ok=None):
            if not dense:
                return None
            universe = [(path, "r", 0.9) for path in self.entries.values()]
            return [t for t in universe if ok is None or ok(t[0])]

        with mock.patch.object(ms, "_hybrid_picks", hybrid):
            out = ms._surface_core(
                self.con, "text", "s1", PROJECT, 1000.0, 3, None, when
            )
        return sorted(path for path, _reminder, _score in out)

    def test_w1_w2_w3_prompt_route_selects_by_when_set(self) -> None:
        self.assertEqual(
            self.surface("prompt", dense=True),
            sorted([self.entries["plain"], self.entries["both"]]),
        )

    def test_w3_after_subagent_route_selects_only_its_entries(self) -> None:
        self.assertEqual(
            self.surface("after-subagent", dense=True), [self.entries["both"]]
        )

    def test_w5_bm25_fallback_route_is_filtered_too(self) -> None:
        self.assertNotIn(self.entries["stoponly"], self.surface("prompt", dense=False))

    def _subagent(self, picks: list) -> tuple[int, str]:
        seen: dict = {}

        def fake_surface(text, session_id, project_id, max_emit=1, model=None, when=""):
            seen.update(text=text, when=when)
            return picks

        buf = io.StringIO()
        with (
            mock.patch.object(ms, "surface_for_text", fake_surface),
            contextlib.redirect_stdout(buf),
        ):
            code = ms._main_subagent(
                {
                    "hook_event_name": "SubagentStop",
                    "last_assistant_message": "review findings",
                    "session_id": "s1",
                    "cwd": self.tmp.name,
                }
            )
        self.seen = seen
        return code, buf.getvalue()

    def test_w6_subagentstop_rewakes_with_the_reminder(self) -> None:
        code, out = self._subagent([("/m/x.md", "reminder X", 0.9)])
        self.assertEqual(code, 2)
        self.assertEqual(self.seen["when"], "after-subagent")
        self.assertEqual(self.seen["text"], "review findings")
        self.assertIn("reminder X", out)

    def test_w7_subagentstop_without_a_match_is_silent(self) -> None:
        code, out = self._subagent([])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class PlanFirstNudgeTest(unittest.TestCase):
    """model 限定の task-plan-first nudge, written by the ordering side first.

    Contract (each claim maps to one test):
      P1  Task store が空の prompt turn -> nudge が additionalContext に乗る
      P2  nudge は systemMessage に乗らない (user の画面を汚さない model 限定 channel)
      P3  未クローズ Task が 1 件でもあれば nudge は出ない (追跡中の session を nag しない)
      P6  Task が全て completed / cancelled なら nudge は再び出る (0 件と同義)
      P4  synthetic <task-notification> re-entry -> turn marker も nudge も無し
      P5  drafts/tasks (mytask MCP) と ~/.claude/tasks (native) の両 store を数える
    """

    def _query(self, prompt: str, *, tasks=None, native=None) -> dict:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        session = "s1"
        if tasks is not None:
            store = os.path.join(tmp.name, "drafts", "tasks")
            os.makedirs(store)
            with open(os.path.join(store, session + ".json"), "w") as f:
                json.dump(tasks, f)
        home = os.path.join(tmp.name, "home")
        if native is not None:
            store = os.path.join(home, ".claude", "tasks", session)
            os.makedirs(store)
            with open(os.path.join(store, "1.json"), "w") as f:
                json.dump(native, f)
        payload = {
            "prompt": prompt,
            "session_id": session,
            "cwd": tmp.name,
            "transcript_path": os.path.join(tmp.name, "t.jsonl"),
        }
        buf = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"HOME": home}, clear=False),
            mock.patch.object(ms, "DB_PATH", os.path.join(tmp.name, "idx.sqlite3")),
            mock.patch.object(ms, "_memory_surface", lambda *a, **k: None),
            mock.patch.object(ms, "_concern_inject", lambda *a, **k: None),
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))),
            contextlib.redirect_stdout(buf),
        ):
            self.assertEqual(ms._main_query(), 0)
        out = buf.getvalue().strip()
        return json.loads(out) if out else {}

    def test_p1_nudge_rides_additional_context_when_no_task_exists(self) -> None:
        out = self._query("hook を直してください")
        self.assertIn(
            ms.PLAN_FIRST_NUDGE, out["hookSpecificOutput"]["additionalContext"]
        )

    def test_p2_nudge_stays_out_of_system_message(self) -> None:
        out = self._query("hook を直してください")
        self.assertNotIn(ms.PLAN_FIRST_NUDGE, out.get("systemMessage", ""))

    def test_p3_open_task_silences_the_nudge(self) -> None:
        out = self._query(
            "hook を直してください",
            tasks=[{"content": "作業", "status": "in_progress"}],
        )
        self.assertNotIn(ms.PLAN_FIRST_NUDGE, json.dumps(out, ensure_ascii=False))

    def test_p6_closed_tasks_do_not_silence_the_nudge(self) -> None:
        for status in ("completed", "cancelled"):
            with self.subTest(status=status):
                out = self._query(
                    "hook を直してください",
                    tasks=[{"content": "作業", "status": status}],
                )
                self.assertIn(
                    ms.PLAN_FIRST_NUDGE,
                    out["hookSpecificOutput"]["additionalContext"],
                )

    def test_p4_synthetic_reentry_gets_no_nudge(self) -> None:
        out = self._query("<task-notification>\n<task-id>x</task-id>")
        self.assertNotIn(ms.PLAN_FIRST_NUDGE, json.dumps(out, ensure_ascii=False))

    def test_p5_native_store_counts_too(self) -> None:
        out = self._query(
            "hook を直してください", native={"content": "作業", "status": "pending"}
        )
        self.assertNotIn(ms.PLAN_FIRST_NUDGE, json.dumps(out, ensure_ascii=False))
        empty = self._query("hook を直してください", tasks=[])
        self.assertIn(
            ms.PLAN_FIRST_NUDGE, empty["hookSpecificOutput"]["additionalContext"]
        )


if __name__ == "__main__":
    unittest.main()
