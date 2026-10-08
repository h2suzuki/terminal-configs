#!/usr/bin/env python3
"""Black-box tests for task_record_memory_check.py: stdin payload in, exit code / stdout JSON out.

Contract (each claim maps to one test):
  T1  a task record whose text matches a stop-time lesson's keywords gets that lesson's check as
      additionalContext; the hook never denies (no permissionDecision)
  T2  the lesson with the most keyword hits wins
  T3  matching uses the same NFKC + lowercase normalization as the Stop-time lesson check
  T4  neutral text, a lesson without `stop` in `when`, a missing memory root, other tools and a
      non-string content all stay silent
  T5  malformed stdin, or a missing sibling stop_checks.py, fails open: exit 0 and no output
  T6  the hook is registered once under PreToolUse for the TaskCreate tool only, and is executable
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "files")
HOOK = os.path.join(FILES, "claude_managed-hooks", "task_record_memory_check.py")
SETTINGS = os.path.join(FILES, "claude_managed-extensions.json")
TOOL = "mcp__mytask__TaskCreate"
DEPLOYED = "/etc/claude-code/hooks/task_record_memory_check.py"

BLAME = "deploy は sandbox で書き込み禁止のため ユーザーの実行待ち"
CHECK = "sandbox の書き込み禁止は断定せず、実際に試してから報告する"


class MemoryRoot:
    """Temp lesson store and cwd: the hook sees nothing real."""

    def __init__(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="task-record-memory-")
        self.root = os.path.join(self.tmp, "memory")
        self.cwd = os.path.join(self.tmp, "repo")
        os.makedirs(self.cwd)

    def lesson(self, name: str, check: str, keywords: str, when: str) -> str:
        path = os.path.join(self.root, "org", name + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(
                f"---\nname: {name}\ndescription: fixture\nkeywords: {keywords}\n"
                f"check: {check}\nwhen: {when}\n---\n\n## 理由\n\nfixture\n"
            )
        return path

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def run_hook(
    payload: object, root: str, hook: str = HOOK
) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "STOP_CHECKS_MEMORY_ROOT": root,
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, hook],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
    )


class TaskRecordMemoryCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = MemoryRoot()
        self.addCleanup(self.fx.cleanup)

    def record(self, content: object, tool: str = TOOL) -> dict:
        return {
            "tool_name": tool,
            "tool_input": {"content": content},
            "cwd": self.fx.cwd,
        }

    def run_record(
        self, content: object, tool: str = TOOL
    ) -> subprocess.CompletedProcess:
        return run_hook(self.record(content, tool), self.fx.root)

    def assertSilent(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")

    def sandbox_lesson(self, when: str = "prompt stop") -> str:
        return self.fx.lesson(
            "sandbox-blame",
            CHECK,
            "sandbox で書き込み禁止, の実行待ち",
            when,
        )

    def test_t1_matching_record_gets_the_check_and_is_never_denied(self) -> None:
        path = self.sandbox_lesson()
        proc = self.run_record(BLAME)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        output = json.loads(proc.stdout)
        self.assertEqual(list(output), ["hookSpecificOutput"])
        section = output["hookSpecificOutput"]
        self.assertEqual(set(section), {"hookEventName", "additionalContext"})
        self.assertEqual(section["hookEventName"], "PreToolUse")
        self.assertEqual(
            section["additionalContext"],
            f"memory-reminder (task record): {CHECK} ({path})",
        )

    def test_t2_most_keyword_hits_wins(self) -> None:
        self.fx.lesson("one-hit", "one hit check", "sandbox で書き込み禁止", "stop")
        path = self.fx.lesson(
            "two-hits", "two hits check", "sandbox で書き込み禁止, の実行待ち", "stop"
        )
        proc = self.run_record(BLAME)
        context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(
            context, f"memory-reminder (task record): two hits check ({path})"
        )

    def test_t3_matching_is_nfkc_and_case_insensitive(self) -> None:
        self.sandbox_lesson()
        proc = self.run_record("ＤＥＰＬＯＹ は SANDBOX で書き込み禁止のため待機")
        self.assertIn(CHECK, proc.stdout)

    def test_t4_neutral_text_is_silent(self) -> None:
        self.sandbox_lesson()
        self.assertSilent(self.run_record("テストは 14 件すべて通りました"))

    def test_t4_lesson_without_stop_is_silent(self) -> None:
        self.sandbox_lesson(when="prompt")
        self.assertSilent(self.run_record(BLAME))

    def test_t4_missing_memory_root_is_silent(self) -> None:
        self.assertSilent(self.run_record(BLAME))

    def test_t4_other_tool_is_silent(self) -> None:
        self.sandbox_lesson()
        self.assertSilent(self.run_record(BLAME, tool="mcp__mytask__TaskUpdate"))

    def test_t4_non_string_content_is_silent(self) -> None:
        self.sandbox_lesson()
        for content in (None, 3, ["sandbox で書き込み禁止"]):
            with self.subTest(content=content):
                self.assertSilent(self.run_record(content))

    def test_t5_malformed_stdin_fails_open(self) -> None:
        self.sandbox_lesson()
        for raw in ("{not json", "", "[]", '"text"', "null"):
            with self.subTest(raw=raw):
                self.assertSilent(run_hook(raw, self.fx.root))

    def test_t5_missing_sibling_module_fails_open(self) -> None:
        self.sandbox_lesson()
        alone = os.path.join(self.fx.tmp, "alone")
        os.makedirs(alone)
        copy = os.path.join(alone, os.path.basename(HOOK))
        shutil.copy(HOOK, copy)
        self.assertSilent(run_hook(self.record(BLAME), self.fx.root, hook=copy))

    def test_t6_registered_for_the_task_create_tool_only(self) -> None:
        with open(SETTINGS, encoding="utf-8") as stream:
            groups = json.load(stream)["hooks"]["PreToolUse"]
        found = [
            (group.get("matcher"), hook["command"])
            for group in groups
            for hook in group["hooks"]
            if hook["command"].startswith(DEPLOYED)
        ]
        self.assertEqual(found, [("^" + TOOL + "$", DEPLOYED)])
        self.assertTrue(
            os.access(HOOK, os.X_OK), "hook runs bare, so it needs an exec bit"
        )


if __name__ == "__main__":
    unittest.main()
