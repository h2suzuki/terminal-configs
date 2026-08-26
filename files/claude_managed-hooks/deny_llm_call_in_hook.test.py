#!/usr/bin/env python3
"""Acceptance tests for deny_llm_call_in_hook.py, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  the hook is a PreToolUse(Write|Edit|MultiEdit) gate: payload JSON on stdin, exit 0 = allow,
      exit 2 = deny with the reason on stderr starting with "hook-llm-call:"
  C2  scope: file_path whose last directory is claude_managed-hooks, claude_user-hooks, .claude/hooks,
      claude-code/hooks or skel/hooks; any other path is allowed whatever the content
  C3  the written text (Write: content; Edit: new_string; MultiEdit: every edits[].new_string) containing
      `claude -p` or `claude --bg` — as adjacent shell words, or as adjacent list items such as
      `"claude", "-p"` / `'claude', '--bg'` — is denied
  C4  exempt basenames: those starting with `claude-md-lint`, and those ending in `.test.py` or
      `.mutants.py`
  C5  fail-open: other tools, unreadable payload, missing fields → exit 0
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "deny_llm_call_in_hook.py"
)
HOOK_PATH = "/home/u/terminal-configs/files/claude_managed-hooks/some_gate.py"


def run_hook(tool: str, tool_input: dict | None, payload: str | None = None):
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


def write(path: str, content: str) -> dict:
    return {"file_path": path, "content": content}


class GateTest(unittest.TestCase):
    def deny(self, tool: str, tool_input: dict) -> None:
        out = run_hook(tool, tool_input)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertTrue(out.stderr.startswith("hook-llm-call:"), out.stderr)

    def allow(self, tool: str, tool_input: dict) -> None:
        out = run_hook(tool, tool_input)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_c1_c3_llm_calls_in_hook_text_are_denied(self) -> None:
        self.deny(
            "Write", write(HOOK_PATH, "run(['claude', '-p', prompt])\nclaude -p x")
        )
        self.deny("Write", write(HOOK_PATH, "subprocess.run('claude --bg review')"))
        self.deny("Write", write(HOOK_PATH, 'subprocess.run(["claude", "-p", prompt], check=False)'))
        self.deny("Write", write(HOOK_PATH, "run(['claude', '--bg', task])"))
        self.deny("Write", write(HOOK_PATH, 'args = ["claude",\n    "-p",\n    q]'))
        self.deny(
            "Edit",
            {
                "file_path": HOOK_PATH,
                "old_string": "pass",
                "new_string": "os.system('claude -p q')",
            },
        )
        self.deny(
            "MultiEdit",
            {
                "file_path": HOOK_PATH,
                "edits": [
                    {"old_string": "a", "new_string": "b"},
                    {"old_string": "c", "new_string": "claude --bg x"},
                ],
            },
        )
        self.allow("Write", write(HOOK_PATH, "print('deterministic check')"))
        self.allow("Write", write(HOOK_PATH, "note = 'the claude CLI'  # no -p here"))

    def test_c2_scope(self) -> None:
        text = "claude -p x"
        for path in (
            "/home/u/terminal-configs/files/claude_user-hooks/memory_surface.py",
            "/home/u/.claude/hooks/x.py",
            "/etc/claude-code/hooks/x.py",
            "/etc/claude-code/skel/hooks/x.py",
            "/home/u/proj/.claude/hooks/x.py",
        ):
            self.deny("Write", write(path, text))
        for path in (
            "/home/u/terminal-configs/docs/notes.md",
            "/home/u/terminal-configs/files/claude_memory_sync",
            "/home/u/proj/src/hooks_helper.py",
            "/home/u/terminal-configs/files/claude_managed-skills/x/SKILL.md",
        ):
            self.allow("Write", write(path, text))

    def test_c4_exempt_basenames(self) -> None:
        text = "claude -p x"
        base = "/home/u/terminal-configs/files/claude_managed-hooks/"
        self.allow("Write", write(base + "claude-md-lint", text))
        self.allow("Write", write(base + "claude-md-lint.py", text))
        self.allow("Write", write(base + "some_gate.test.py", text))
        self.allow("Write", write(base + "some_gate.mutants.py", text))
        self.deny("Write", write(base + "claude_md_lint_helper.py", text))

    def test_c5_fail_open(self) -> None:
        self.allow("Bash", {"command": "claude -p x"})
        self.allow("Read", {"file_path": HOOK_PATH})
        self.assertEqual(run_hook("Write", None, payload="{not json").returncode, 0)
        self.assertEqual(run_hook("Write", None, payload="[]").returncode, 0)
        self.allow("Write", {"content": "claude -p x"})
        self.allow("Write", {"file_path": HOOK_PATH})


if __name__ == "__main__":
    unittest.main()
