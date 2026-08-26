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

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
