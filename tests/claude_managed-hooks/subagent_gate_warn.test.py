#!/usr/bin/env python3
"""Black-box tests for subagent_gate_warn.py: stdin payload in, exit code / stderr advisory out."""

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
    "subagent_gate_warn.py",
)


def run_hook(payload: object) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK], input=body, capture_output=True, text=True, check=False
    )


def short_spawn(subagent_type: str) -> dict:
    """A spawn that is short on both prompt and description: the overuse shape."""
    return {
        "tool_name": "Agent",
        "tool_input": {
            "subagent_type": subagent_type,
            "prompt": "find usages of foo",
            "description": "Find foo usages",
        },
    }


class SubagentGateWarnTest(unittest.TestCase):
    def assertSilent(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_short_general_purpose_spawn_warns(self):
        """Claim 1: a short general-purpose / unspecified spawn is the overuse candidate and gets the advisory."""
        for agent in ("general-purpose", ""):
            with self.subTest(agent=agent):
                proc = run_hook(short_spawn(agent))
                self.assertEqual(proc.returncode, 0)
                self.assertIn("subagent-gate (warn)", proc.stderr)

    def test_managed_agents_do_not_warn(self):
        """Claim 2: investigator / implementer use is itself condition (c) / (e), so a short spawn is not overuse."""
        for agent in ("investigator", "implementer", "Investigator"):
            with self.subTest(agent=agent):
                self.assertSilent(run_hook(short_spawn(agent)))

    def test_existing_specialized_agents_still_do_not_warn(self):
        """Claim 2 boundary: the previously exempt specialized agents stay exempt."""
        for agent in ("Explore", "code-reviewer", "security-review"):
            with self.subTest(agent=agent):
                self.assertSilent(run_hook(short_spawn(agent)))

    def test_warning_names_the_investigator_for_condition_c(self):
        """Claim 3: the advisory ties condition (c) to the investigator agent."""
        stderr = run_hook(short_spawn("general-purpose")).stderr
        self.assertIn("5 条件", stderr)
        self.assertIn("(c) 3+ query 探索 (investigator", stderr)

    def test_long_prompt_does_not_warn(self):
        """Claim 1 boundary: a prompt at the threshold is not short, so no warning."""
        payload = short_spawn("general-purpose")
        payload["tool_input"]["prompt"] = "x" * 200
        self.assertSilent(run_hook(payload))

    def test_other_tools_and_garbage_fail_open(self):
        """Claim 4: only Task / Agent spawns are inspected; unreadable payloads never block."""
        for body in ({"tool_name": "Bash", "tool_input": {}}, "not json", [1, 2]):
            with self.subTest(body=body):
                self.assertSilent(run_hook(body))


if __name__ == "__main__":
    unittest.main()
