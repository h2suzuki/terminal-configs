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


if __name__ == "__main__":
    unittest.main()
