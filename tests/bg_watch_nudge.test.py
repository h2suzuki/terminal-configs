#!/usr/bin/env python3
"""Acceptance tests for the bg_watch_nudge PreToolUse hook (Claude Code only), written before the implementation.

Contract (each claim maps to one test):
  N1  Bash with run_in_background=true and no bg_watch in the command gets the guidance
  N2  a lone trailing "&" (end of command, or just before ";" / newline) or a whole-word nohup / setsid /
      disown gets the guidance; "&&", "2>&1", "&>", a query-string "&" and words that merely contain those
      names do not
  N3  a command that mentions bg_watch gets nothing, whatever else it contains
  N4  only the Bash tool counts
  N6  the output is exactly {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ...}}
      and exit 0: the hook guides, never blocks
  N7  broken JSON, empty input, a non-object payload or a malformed tool_input exit 0 with no output
  N8  --exclusions <managed settings> silences commands matching a sandbox.excludedCommands glob as a whole,
      since bg_watch in front would pull them into the sandbox; a missing or unreadable file silences nothing
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "files",
    "claude_managed-hooks",
    "bg_watch_nudge.py",
)
MSG = (
    "bg-watch: 長時間の処理は `bg_watch -- <コマンド>` で包んで run_in_background で起動してください。"
    "15 分ごとと終了時に、あなたへ状況の知らせが届きます。"
    "& / nohup / setsid での切り離しは使わないでください（追跡されず放置されます）。"
)
DETACHED = (
    "sleep 100 &",
    "sleep 100 &\n",
    "sleep 100 &   ",
    "sleep 100 &\necho started",
    "sleep 100 & ; echo started",
    "sleep 100 &;echo started",
    "make >out.log 2>&1 &",
    "make &>out.log &",
    "nohup make",
    "cd x && nohup make",
    "setsid make",
    "/usr/bin/setsid make",
    "make; disown",
    "(sleep 1; echo hi) & disown",
)
NOT_DETACHED = (
    "ls",
    "make && make install",
    "make &&\nmake install",
    "make 2>&1",
    "make 2>&1 | tail -5",
    "make >&2",
    "make &>out.log",
    "make |& tee out.log",
    "curl 'http://host/path?a=1&b=2'",
    "echo 'a &'",
    "cat nohup.out",
    "ls setsid.txt",
    "echo xsetsid disowned my-nohup",
)


def run_hook(payload: object, *args: str, raw: str | None = None):
    stdin = raw if raw is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK, *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def bash(command: object, tool: str = "Bash", **tool_input) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command, **tool_input},
    }


def message(result: subprocess.CompletedProcess) -> str | None:
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


class GuidanceTest(unittest.TestCase):
    def test_n1_run_in_background_is_guided(self):
        result = run_hook(bash("sleep 100", run_in_background=True))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(message(result), MSG)

    def test_n1_foreground_plain_command_is_silent(self):
        for extra in ({}, {"run_in_background": False}, {"run_in_background": "true"}):
            with self.subTest(extra=extra):
                payload = bash("sleep 100")
                payload["tool_input"].update(extra)
                self.assertIsNone(message(run_hook(payload)))

    def test_n2_detaching_is_guided(self):
        for command in DETACHED:
            with self.subTest(command=command):
                self.assertEqual(message(run_hook(bash(command))), MSG)

    def test_n2_other_shell_syntax_is_silent(self):
        for command in NOT_DETACHED:
            with self.subTest(command=command):
                self.assertIsNone(message(run_hook(bash(command))))

    def test_n3_bg_watch_in_command_is_silent(self):
        for command in (
            "bg_watch -- make",
            "bg_watch --interval 60 -- sleep 100",
            "bg_watch -- make &",
            "nohup bg_watch -- make",
        ):
            with self.subTest(command=command):
                payload = bash(command, run_in_background=True)
                self.assertIsNone(message(run_hook(payload)))

    def test_n4_only_bash_counts(self):
        for tool in ("Read", "Task", "Agent", "Edit"):
            with self.subTest(tool=tool):
                payload = bash("sleep 100 &", tool=tool, run_in_background=True)
                self.assertIsNone(message(run_hook(payload)))


class ShapeTest(unittest.TestCase):
    def test_n6_output_shape_never_blocks(self):
        result = run_hook(bash("sleep 100 &"))
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(set(output), {"hookSpecificOutput"})
        self.assertEqual(
            set(output["hookSpecificOutput"]), {"hookEventName", "additionalContext"}
        )
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(result.stdout.count("\n"), 1)

    def test_n6_script_is_executable_python3(self):
        self.assertTrue(os.access(HOOK, os.X_OK))
        with open(HOOK, encoding="utf-8") as fh:
            self.assertEqual(fh.readline().strip(), "#!/usr/bin/env python3")

    def test_n7_bad_input_is_silent_exit_0(self):
        for raw in ("", "{not json", "[]", '"text"', "null", "42"):
            with self.subTest(raw=raw):
                result = run_hook(None, raw=raw)
                self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_n7_malformed_tool_input_is_silent_exit_0(self):
        for tool_input in (
            None,
            "sleep 100 &",
            ["sleep 100 &"],
            {},
            {"command": None},
            {"command": 5},
            {"command": ["sleep", "100", "&"]},
        ):
            with self.subTest(tool_input=tool_input):
                payload = {"tool_name": "Bash", "tool_input": tool_input}
                result = run_hook(payload)
                self.assertEqual((result.returncode, result.stdout), (0, ""))


class ExclusionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_n8_excluded_command_globs_match_the_whole_command(self):
        settings = self.write(
            "managed-settings.json",
            json.dumps(
                {"sandbox": {"excludedCommands": ["docker *", "claude --bg *"]}}
            ),
        )
        for command, expected in (
            ("docker compose up", None),
            ("claude --bg run", None),
            ("make", MSG),
            ("cd x && docker compose up", MSG),
            ("dockerd-rootless", MSG),
        ):
            with self.subTest(command=command):
                payload = bash(command, run_in_background=True)
                result = run_hook(payload, "--exclusions", settings)
                self.assertEqual(message(result), expected)

    def test_n8_missing_or_broken_file_silences_nothing(self):
        broken = self.write("broken.json", "{not json")
        for path in (os.path.join(self.dir.name, "absent.json"), broken):
            with self.subTest(path=path):
                payload = bash("docker compose up", run_in_background=True)
                result = run_hook(payload, "--exclusions", path)
                self.assertEqual((result.returncode, message(result)), (0, MSG))

    def test_n8_dangling_exclusions_flag_exits_0(self):
        result = run_hook(bash("make", run_in_background=True), "--exclusions")
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
