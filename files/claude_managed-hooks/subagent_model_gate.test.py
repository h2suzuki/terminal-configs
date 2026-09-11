#!/usr/bin/env python3
"""Black-box tests for subagent_model_gate.py: stdin payload in, exit code / stdout JSON out."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "subagent_model_gate.py"
)


def run_hook(payload: object) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK], input=body, capture_output=True, text=True, check=False
    )


def spawn(**tool_input: object) -> dict:
    return {"tool_name": "Agent", "tool_input": tool_input}


class ModelGateTest(unittest.TestCase):
    def assertDenied(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("model", out["permissionDecisionReason"])

    def assertSilent(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_missing_model_is_denied(self):
        """Claim 1: a spawn that never chose a model inherits the parent unconsidered, so it is refused."""
        self.assertDenied(run_hook(spawn(prompt="review this", description="review")))

    def test_explicit_model_passes(self):
        """Claim 2: any explicit choice passes, the parent's own model included."""
        for model in ("haiku", "sonnet", "opus", "fable"):
            with self.subTest(model=model):
                self.assertSilent(run_hook(spawn(prompt="x", model=model)))

    def test_fork_passes_without_model(self):
        """Claim 3: a fork always runs on the parent model, so there is no choice to make."""
        self.assertSilent(run_hook(spawn(prompt="x", subagent_type="fork")))

    def test_blank_model_counts_as_missing(self):
        """Claim 1 boundary: an empty string is not a choice."""
        self.assertDenied(run_hook(spawn(prompt="x", model="  ")))

    def test_other_tools_are_ignored(self):
        """Claim 4: only Task / Agent spawns are gated."""
        self.assertSilent(run_hook({"tool_name": "Bash", "tool_input": {}}))

    def test_garbage_input_fails_open(self):
        """Claim 5: unreadable payloads never block."""
        self.assertSilent(run_hook("not json"))
        self.assertSilent(run_hook([1, 2]))


if __name__ == "__main__":
    unittest.main()
