#!/usr/bin/env python3
"""Acceptance tests for playwright_listener_gate.py, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  the hook is a PreToolUse gate for the tool `mcp__playwright__browser_run_code_unsafe`: payload JSON
      on stdin, exit 0 = allow, exit 2 = deny with the reason on stderr starting with "playwright-listener:"
  C2  a snippet (tool_input.code) that registers a listener with `page.on(` and never removes one with
      `page.off(` is denied; a snippet with both, with `page.once(` only, or with no listener is allowed
  C3  fail-open: other tools, unreadable payload, or a non-string code → exit 0
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "playwright_listener_gate.py"
)
TOOL = "mcp__playwright__browser_run_code_unsafe"


def run_hook(tool: str, tool_input: object, payload: str | None = None):
    body = (
        payload
        if payload is not None
        else json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": "/tmp"})
    )
    return subprocess.run(
        [sys.executable, HOOK],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


class GateTest(unittest.TestCase):
    def test_c1_c2_listener_without_off_is_denied(self) -> None:
        out = run_hook(
            TOOL, {"code": "page.on('console', h);\nawait page.click('#x');"}
        )
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertTrue(out.stderr.startswith("playwright-listener:"), out.stderr)
        for code in (
            "page.on('console', h);\nawait page.click('#x');\npage.off('console', h);",
            "page.once('dialog', d => d.accept());\nawait page.click('#x');",
            "await page.goto(url);\nreturn await page.title();",
        ):
            self.assertEqual(run_hook(TOOL, {"code": code}).returncode, 0, code)

    def test_c3_fail_open(self) -> None:
        self.assertEqual(run_hook("Bash", {"command": "page.on("}).returncode, 0)
        self.assertEqual(run_hook(TOOL, {"code": 123}).returncode, 0)
        self.assertEqual(run_hook(TOOL, {}).returncode, 0)
        self.assertEqual(run_hook(TOOL, None, payload="{not json").returncode, 0)
        self.assertEqual(run_hook(TOOL, None, payload="[]").returncode, 0)


if __name__ == "__main__":
    unittest.main()
