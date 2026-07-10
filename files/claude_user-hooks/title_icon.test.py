#!/usr/bin/env python3
"""Unit tests for title_icon.py via subprocess (stdin JSON -> stdout JSON), HOME redirected to tmpdir."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK_PATH = os.path.join(os.path.dirname(__file__), "title_icon.py")
SID = "sess-1"


class TitleIconTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = dict(os.environ, HOME=self.tmp.name)

    def run_hook(self, data):
        p = subprocess.run(
            [sys.executable, HOOK_PATH],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout.strip()
        return json.loads(out)["terminalSequence"] if out else ""

    def state_file(self):
        return os.path.join(self.tmp.name, ".claude", "title-icon-state", SID)

    def state(self):
        with open(self.state_file()) as f:
            return json.load(f)

    def emit(self, event, **extra):
        data = {"hook_event_name": event, "session_id": SID, "cwd": "/tmp"}
        data.update(extra)
        return self.run_hook(data)

    def test_stop_with_workflow_bg_task_is_bg_icon(self):
        out = self.emit("Stop", background_tasks=[{"type": "workflow"}])
        self.assertIn("🔄💬", out)
        self.assertIn("]0;", out)
        self.assertEqual(self.state()["state"], "bg")

    def test_bg_then_idle_stop_returns_to_wait(self):
        self.emit("Stop", background_tasks=[{"type": "subagent"}])
        out = self.emit("Stop")
        self.assertNotIn("🔄", out)
        self.assertIn("💬", out)

    def test_stop_without_bg_tasks_is_wait(self):
        out = self.emit("Stop")
        self.assertIn("💬", out)

    def test_stop_with_shell_only_is_wait(self):
        out = self.emit("Stop", background_tasks=[{"type": "shell"}])
        self.assertIn("💬", out)

    def test_stop_with_non_list_bg_tasks_does_not_crash(self):
        out = self.emit("Stop", background_tasks="not-a-list")
        self.assertIn("💬", out)

    def test_stop_with_non_dict_bg_task_entries_does_not_crash(self):
        out = self.emit("Stop", background_tasks=["workflow", 42, None])
        self.assertIn("💬", out)

    def test_session_end_restores_default_title_and_clears_state(self):
        self.emit("SessionStart", source="startup")
        self.assertTrue(os.path.exists(self.state_file()))
        out = self.emit("SessionEnd", reason="prompt_input_exit")
        self.assertNotIn("\x1b[", out.replace("\x1b]0;", ""))
        self.assertRegex(out, r"\]0;.*@.*: /tmp\x07")
        self.assertFalse(os.path.exists(self.state_file()))

    def test_session_end_with_none_cwd_emits_osc0(self):
        self.emit("SessionStart", source="startup")
        out = self.run_hook(
            {
                "hook_event_name": "SessionEnd",
                "session_id": SID,
                "cwd": None,
                "reason": "prompt_input_exit",
            }
        )
        self.assertIn("]0;", out)

    def test_session_end_clear_reason_is_noop(self):
        self.emit("SessionStart", source="startup")
        out = self.emit("SessionEnd", reason="clear")
        self.assertEqual(out, "")
        self.assertTrue(os.path.exists(self.state_file()))

    def test_session_start_startup_has_no_csi(self):
        out = self.emit("SessionStart", source="startup")
        self.assertIn("💬", out)
        self.assertNotIn("\x1b[", out)

    def test_home_cwd_is_shortened_to_tilde(self):
        home = self.tmp.name
        out = self.emit(
            "SessionEnd", cwd=os.path.join(home, "proj"), reason="prompt_input_exit"
        )
        self.assertIn("~/proj", out)

    def test_home_sibling_prefix_cwd_is_not_shortened(self):
        home = self.tmp.name
        sibling = home + "2"
        out = self.emit(
            "SessionEnd", cwd=os.path.join(sibling, "x"), reason="prompt_input_exit"
        )
        self.assertNotIn("~", out)
        self.assertIn(sibling, out)

    def test_unchanged_state_emits_nothing(self):
        self.emit("Stop")
        out = self.emit("Stop")
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
