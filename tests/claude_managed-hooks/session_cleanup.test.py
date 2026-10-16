#!/usr/bin/env python3
"""Black-box tests for session_cleanup.py's session scratch removal at SessionEnd.

Contract (each claim maps to one test):
  C1  the ending session's harness scratchpad (<tmp root>/<project>/<session id>/scratchpad) is
      removed; its sibling harness files (tasks/) and another session's scratchpad stay
  C2  a session id that is not UUID-shaped removes nothing (no path tricks)
  C3  a hook-spawned one-off session (CLAUDE_HOOK_CHILD) removes nothing
  C4  the ending session's turn counters (<transcript>.turns and the cache-keyed
      <cache>/claude-turn-counter/<session id>.turns) stay for every SessionEnd reason, /clear
      included, so a resumed session keeps counting (/clear resets by starting a new transcript)
  C5  an orphan <transcript dir>/*.turns (no sibling .jsonl, mtime older than 7 days) is removed
  C6  an orphan .turns with a recent mtime stays (its transcript may not exist yet)
  C7  an old .turns whose .jsonl exists stays, and a .turns.waste file is left alone
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
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
OLD = 8 * 86400  # older than the hook's 7-day orphan TTL


class SessionCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
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

    def _end(
        self,
        session_id: str,
        transcript_path: str | None = None,
        reason: str | None = None,
        **env: str,
    ) -> None:
        payload = {"hook_event_name": "SessionEnd", "session_id": session_id}
        if transcript_path:
            payload["transcript_path"] = transcript_path
        if reason:
            payload["reason"] = reason
        subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            env={
                **os.environ,
                "HOME": self.home,
                "XDG_CACHE_HOME": os.path.join(self.home, "cache"),
                "SESSION_CLEANUP_TMP_ROOT": self.root,
                **env,
            },
        )

    def _touch(self, path: str, age: float = 0) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        if age:
            old = time.time() - age
            os.utime(path, (old, old))
        return path

    def _transcript(self, session: str) -> str:
        return self._touch(
            os.path.join(
                self.home, ".claude", "projects", "-home-u-repo", session + ".jsonl"
            )
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

    def test_c4_keeps_the_ending_sessions_turn_counters(self):
        transcript = self._transcript(SESSION)
        for reason in (None, "prompt_input_exit", "clear", "resume", "other"):
            with self.subTest(reason=reason):
                beside = self._touch(transcript[: -len(".jsonl")] + ".turns")
                cache_keyed = self._touch(
                    os.path.join(
                        self.home, "cache", "claude-turn-counter", SESSION + ".turns"
                    )
                )
                self._end(SESSION, transcript, reason)
                self.assertTrue(os.path.exists(beside))
                self.assertTrue(os.path.exists(cache_keyed))

    def test_c5_removes_old_orphan_turns_beside_the_transcript(self):
        transcript = self._transcript(SESSION)
        orphan = self._touch(
            os.path.join(os.path.dirname(transcript), OTHER + ".turns"), OLD
        )
        self._end(SESSION, transcript)
        self.assertFalse(os.path.exists(orphan))

    def test_c6_keeps_recent_orphan_turns(self):
        transcript = self._transcript(SESSION)
        fresh = self._touch(os.path.join(os.path.dirname(transcript), OTHER + ".turns"))
        self._end(SESSION, transcript)
        self.assertTrue(os.path.exists(fresh))

    def test_c7_keeps_old_turns_with_a_transcript_and_other_suffixes(self):
        transcript = self._transcript(SESSION)
        directory = os.path.dirname(transcript)
        self._transcript(OTHER)
        resumable = self._touch(os.path.join(directory, OTHER + ".turns"), OLD)
        waste = self._touch(os.path.join(directory, "gone.turns.waste"), OLD)
        self._end(SESSION, transcript)
        self.assertTrue(os.path.exists(resumable))
        self.assertTrue(os.path.exists(waste))


if __name__ == "__main__":
    unittest.main()
