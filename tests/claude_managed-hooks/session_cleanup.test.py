#!/usr/bin/env python3
"""Black-box tests for session_cleanup.py's session scratch removal at SessionEnd.

Contract (each claim maps to one test):
  C1  the ending session's harness scratchpad (<tmp root>/<project>/<session id>/scratchpad) is
      removed; its sibling harness files (tasks/) and another session's scratchpad stay
  C2  a session id that is not UUID-shaped removes nothing (no path tricks)
  C3  a hook-spawned one-off session (CLAUDE_HOOK_CHILD) removes nothing
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "files",
    "claude_managed-hooks",
    "session_cleanup.py",
)
SESSION = "72fc7613-1ab7-4e51-a069-73f92245326a"
OTHER = "0f0ccaee-4c2c-4c5d-a16f-7e75b1cb4a40"


class SessionCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "claude-1000")
        for session, sub in (
            (SESSION, "scratchpad"),
            (SESSION, "tasks"),
            (OTHER, "scratchpad"),
        ):
            path = os.path.join(self.root, "-home-u-repo", session, sub)
            os.makedirs(path)
            with open(os.path.join(path, "f.txt"), "w", encoding="utf-8") as f:
                f.write("x")

    def _path(self, session: str, sub: str) -> str:
        return os.path.join(self.root, "-home-u-repo", session, sub)

    def _end(self, session_id: str, **env: str) -> None:
        home = os.path.join(self.tmp.name, "home")
        subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps(
                {"hook_event_name": "SessionEnd", "session_id": session_id}
            ),
            text=True,
            capture_output=True,
            check=True,
            env={
                **os.environ,
                "HOME": home,
                "XDG_CACHE_HOME": os.path.join(home, "cache"),
                "SESSION_CLEANUP_TMP_ROOT": self.root,
                **env,
            },
        )

    def test_c1_removes_only_the_ending_sessions_scratchpad(self):
        self._end(SESSION)
        self.assertFalse(os.path.exists(self._path(SESSION, "scratchpad")))
        self.assertTrue(os.path.exists(self._path(SESSION, "tasks")))
        self.assertTrue(os.path.exists(self._path(OTHER, "scratchpad")))

    def test_c2_non_uuid_session_id_removes_nothing(self):
        for session_id in ("*", "..", "abc"):
            with self.subTest(session_id=session_id):
                self._end(session_id)
                self.assertTrue(os.path.exists(self._path(SESSION, "scratchpad")))
                self.assertTrue(os.path.exists(self._path(OTHER, "scratchpad")))

    def test_c3_hook_child_removes_nothing(self):
        self._end(SESSION, CLAUDE_HOOK_CHILD="1")
        self.assertTrue(os.path.exists(self._path(SESSION, "scratchpad")))


if __name__ == "__main__":
    unittest.main()
