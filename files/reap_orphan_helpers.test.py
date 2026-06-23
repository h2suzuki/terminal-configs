#!/usr/bin/env python3
"""Unit tests for the Claude Code orphan helper reaper using synthetic process tables and registry state only."""

from __future__ import annotations

import importlib.util
import os
import signal
import sys
import tempfile
import unittest
from unittest import mock

MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "claude_managed-hooks", "reap_orphan_helpers.py"
)
SPEC = importlib.util.spec_from_file_location("reap_orphan_helpers", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
reaper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reaper
SPEC.loader.exec_module(reaper)


class FakeProc:
    def __init__(self, ppid, cmdline, euid=1000, env=None, starttime="1"):
        self.ppid = ppid
        self.cmdline = cmdline
        self.euid = euid
        self.env = env
        self.starttime = starttime


class ReaperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reg_dir = os.path.join(self.tmp.name, "sessions")
        os.makedirs(self.reg_dir)
        self.proc = {}
        self.kills = []
        self.patches = [
            mock.patch.object(reaper, "REG_DIR", self.reg_dir),
            mock.patch.object(reaper, "iter_proc_pids", lambda: sorted(self.proc)),
            mock.patch.object(
                reaper,
                "read_ppid",
                lambda pid: self.proc[pid].ppid if pid in self.proc else None,
            ),
            mock.patch.object(
                reaper,
                "read_cmdline",
                lambda pid: self.proc[pid].cmdline if pid in self.proc else None,
            ),
            mock.patch.object(
                reaper,
                "read_euid",
                lambda pid: self.proc[pid].euid if pid in self.proc else None,
            ),
            mock.patch.object(
                reaper,
                "read_starttime",
                lambda pid: self.proc[pid].starttime if pid in self.proc else None,
            ),
            mock.patch.object(reaper, "read_env_value", self.fake_read_env_value),
            mock.patch.object(reaper.os, "geteuid", lambda: 1000),
            mock.patch.object(reaper.os, "getpid", lambda: 9999),
            mock.patch.object(reaper.os, "getpgrp", lambda: 9999),
            mock.patch.object(reaper.os, "getpgid", lambda pid: pid),
            mock.patch.object(reaper.os, "kill", self.fake_kill),
            mock.patch.object(reaper.time, "sleep", lambda seconds: None),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_read_env_value(self, pid, key):
        if pid not in self.proc:
            return None
        env = self.proc[pid].env
        if env is None:
            return None
        return env.get(key, "")

    def fake_kill(self, pid, sig):
        if sig == 0:
            raise ProcessLookupError()
        self.kills.append((pid, sig))

    def write_registry(self, session_id, pid, starttime):
        with open(
            os.path.join(self.reg_dir, session_id), "w", encoding="utf-8"
        ) as handle:
            handle.write(f"{pid} {starttime}")

    def add_class_a(self, pid, owner, ppid=1):
        self.proc[pid] = FakeProc(
            ppid,
            "/x/.claude/plugins/cache/openai-codex/bin/codex",
            env={"CLAUDE_CODE_SESSION_ID": owner},
        )

    def test_class_a_with_dead_owner_is_reaped(self):
        self.proc[10] = FakeProc(1, "claude", starttime="new")
        self.write_registry("dead-session", 10, "old")
        self.add_class_a(20, "dead-session")
        reaper.reap()
        self.assertIn((20, signal.SIGTERM), self.kills)

    def test_class_a_with_alive_owner_is_spared(self):
        self.proc[10] = FakeProc(1, "claude", starttime="same")
        self.write_registry("alive-session", 10, "same")
        self.add_class_a(20, "alive-session")
        reaper.reap()
        self.assertNotIn((20, signal.SIGTERM), self.kills)

    def test_class_a_with_unknown_owner_is_spared(self):
        self.add_class_a(20, "missing-session")
        reaper.reap()
        self.assertEqual([], self.kills)

    def test_class_a_with_unreadable_environ_is_spared(self):
        self.proc[10] = FakeProc(1, "claude", starttime="new")
        self.write_registry("dead-session", 10, "old")
        self.proc[20] = FakeProc(
            1, "/x/.claude/plugins/cache/openai-codex/bin/codex", env=None
        )
        reaper.reap()
        self.assertEqual([], self.kills)

    def test_class_b_with_ppid_one_is_reaped(self):
        self.proc[30] = FakeProc(1, "node agent-browser")
        reaper.reap()
        self.assertIn((30, signal.SIGTERM), self.kills)

    def test_class_b_with_non_one_ppid_is_not_candidate(self):
        self.proc[30] = FakeProc(44, "node agent-browser")
        reaper.reap()
        self.assertEqual([], self.kills)

    def test_session_state_dead_on_starttime_mismatch(self):
        self.proc[10] = FakeProc(1, "claude", starttime="new")
        self.write_registry("reused", 10, "old")
        self.assertEqual("dead", reaper.session_state("reused"))

    def test_subtree_kill_orders_children_before_parent(self):
        self.proc[40] = FakeProc(1, "node agent-browser")
        self.proc[41] = FakeProc(40, "child")
        self.proc[42] = FakeProc(41, "grandchild")
        reaper.reap_subtree(40)
        terms = [pid for pid, sig in self.kills if sig == signal.SIGTERM]
        self.assertEqual([42, 41, 40], terms)

    def test_own_process_group_is_never_killed(self):
        # safety invariant: a candidate sharing our process group must be spared (never kill our own session tree)
        self.proc[30] = FakeProc(1, "node agent-browser")
        with mock.patch.object(reaper.os, "getpgid", lambda pid: 9999):
            reaper.reap()
        self.assertEqual([], self.kills)


if __name__ == "__main__":
    unittest.main()
