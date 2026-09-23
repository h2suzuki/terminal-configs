#!/usr/bin/env python3
"""Black-box tests for subagent_watch_reminder.py: stdin payload in, exit code / stdout JSON out."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "files",
    "claude_managed-hooks",
    "subagent_watch_reminder.py",
)


def run_hook(payload: object) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK], input=body, capture_output=True, text=True, check=False
    )


class WatchReminderTest(unittest.TestCase):
    def test_spawn_gets_a_wake_up_rule_without_a_decision(self):
        """Claim 1: every subagent spawn tells the parent to schedule its own 15-minute check; the spawn is not judged."""
        for tool in ("Agent", "Task"):
            proc = run_hook(
                {"tool_name": tool, "tool_input": {"prompt": "x", "model": "sonnet"}}
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)["hookSpecificOutput"]
            self.assertEqual(out["hookEventName"], "PreToolUse")
            self.assertNotIn("permissionDecision", out)
            context = out["additionalContext"]
            self.assertIn("15", context)
            self.assertIn("agent_coord", context)
            # A sentence alone wakes nobody; the cron does.
            self.assertIn("CronCreate", context)
            self.assertIn("CronDelete", context)

    def test_other_tools_and_bad_input_are_silent(self):
        """Claim 2: other tools and unreadable payloads produce nothing (fail-open)."""
        for payload in ({"tool_name": "Bash", "tool_input": {}}, "{not json", "[]"):
            proc = run_hook(payload)
            self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)


if __name__ == "__main__":
    unittest.main()
