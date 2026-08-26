#!/usr/bin/env python3
"""Acceptance tests for `claude_memory_sync --reach`, written by the ordering side first.

Contract (each claim maps to one test):
  C1  `--reach` exits 0 and prints a header line `reach[30d]: never=<n> hot=<m>`
  C2  never = indexed entries with zero kind='emit' rows in the last REACH_DAYS = 30 days, one line each
      `never: <path relative to the clone>`, sorted; emits older than the window do not count
  C3  hot = entries with at least HOT_EMITS = 20 emit rows in the window, one line each `hot: <count> <rel>`,
      highest count first; an entry below the threshold appears in neither list
  C4  kind='mismatch' rows are not emits
  C5  a missing index DB prints `index: unavailable` and exits 1
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "claude_memory_sync")
DAY = 86400.0


def seed(db: str, clone: str, now: float) -> None:
    con = sqlite3.connect(db)
    con.execute(
        "CREATE VIRTUAL TABLE entries_fts USING fts5(file_path UNINDEXED, "
        "project_id UNINDEXED, reminder UNINDEXED, keywords, body, "
        "last_modified UNINDEXED, tokenize='trigram')"
    )
    con.execute(
        "CREATE TABLE inject_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "file_path TEXT NOT NULL, project_id TEXT, session_id TEXT, ts REAL NOT NULL, "
        "score REAL, query_excerpt TEXT, model TEXT, kind TEXT)"
    )
    rows = {
        "never": [],
        "warm": [("emit", now - 5 * DAY)],
        "hot": [("emit", now - i * 3600) for i in range(20)],
        "old": [("emit", now - 40 * DAY)] * 3,
    }
    for name, log in rows.items():
        path = os.path.join(clone, "org", f"feedback_{name}.md")
        con.execute(
            "INSERT INTO entries_fts(file_path, project_id, reminder, keywords, body, "
            "last_modified) VALUES (?, NULL, 'r', 'k', 'b', 0)",
            (path,),
        )
        for kind, ts in log:
            con.execute(
                "INSERT INTO inject_log(file_path, session_id, ts, kind) VALUES (?, 's', ?, ?)",
                (path, ts, kind),
            )
    never = os.path.join(clone, "org", "feedback_never.md")
    for i in range(3):
        con.execute(
            "INSERT INTO inject_log(file_path, session_id, ts, kind) VALUES (?, 's', ?, 'mismatch')",
            (never, now - i),
        )
    con.commit()
    con.close()


class ReachTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.clone = os.path.join(self.tmp.name, "clone")
        os.makedirs(os.path.join(self.clone, "org"))
        self.db = os.path.join(self.tmp.name, "memory_index.sqlite3")
        self.env = {**os.environ, "CLAUDE_MEMORY_REPO": self.clone}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def reach(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, CLI, "--reach"],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
            timeout=60,
        )

    def test_c1_c2_c3_c4_report(self) -> None:
        seed(self.db, self.clone, time.time())
        out = self.reach()
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        self.assertEqual(lines[0], "reach[30d]: never=2 hot=1")
        self.assertEqual(
            [ln for ln in lines if ln.startswith("never: ")],
            ["never: org/feedback_never.md", "never: org/feedback_old.md"],
        )
        self.assertEqual(
            [ln for ln in lines if ln.startswith("hot: ")],
            ["hot: 20 org/feedback_hot.md"],
        )
        self.assertNotIn("feedback_warm", out.stdout)

    def test_c5_missing_db(self) -> None:
        out = self.reach()
        self.assertEqual(out.returncode, 1)
        self.assertIn("index: unavailable", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
