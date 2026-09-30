#!/usr/bin/env python3
"""Black-box tests for subagent_gate_suggest.py: stdin payload in, exit code / stdout JSON out."""

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
    "claude_user-hooks",
    "subagent_gate_suggest.py",
)


def run_hook(payload: object) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK], input=body, capture_output=True, text=True, check=False
    )


def advisory(prompt: str) -> str:
    proc = run_hook({"prompt": prompt})
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit"
    return out["additionalContext"]


class SubagentGateSuggestTest(unittest.TestCase):
    def test_detected_pattern_is_cited(self):
        """Claim 1: a compound pattern in the prompt yields an advisory that quotes the match."""
        self.assertIn("「全件 確認」", advisory("この repo の全件 確認 をお願いします"))

    def test_advisory_names_the_five_conditions(self):
        """Claim 2: the advisory refers to the skill's five conditions (a-e), not the old four."""
        text = advisory("全 file を scan して")
        self.assertIn("5 条件", text)
        self.assertNotIn("4 条件", text)

    def test_advisory_routes_investigation_to_investigator(self):
        """Claim 3: delegation goes to the investigator agent, not Explore / general-purpose."""
        text = advisory("codebase 全体 を grep して")
        self.assertIn('subagent_type: "investigator"', text)
        self.assertNotIn("Explore", text)
        self.assertNotIn("general-purpose", text)

    def test_advisory_keeps_the_single_query_escape(self):
        """Claim 4: the advisory still says a single-file / single-query task needs no subagent."""
        self.assertIn("subagent は不要", advisory("複数 endpoint を確認して"))

    def test_plain_prompt_is_silent(self):
        """Claim 5: prompts without a compound pattern produce no output."""
        proc = run_hook({"prompt": "この関数の名前を変えて"})
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_garbage_input_fails_open(self):
        """Claim 6: unreadable or non-dict payloads exit 0 silently."""
        for body in ("not json", [1, 2], {"prompt": 3}, {}):
            with self.subTest(body=body):
                proc = run_hook(body)
                self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)


if __name__ == "__main__":
    unittest.main()
