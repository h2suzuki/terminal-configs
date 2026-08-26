#!/usr/bin/env python3
"""Acceptance tests for codex_broker_sweep.py, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  Payload with hook_event_name == "SessionStart" -> the hook invokes the reaper exactly once with
      argv ["codex_broker_reap", "--apply"]. The binary is resolved via PATH, or via env
      CODEX_BROKER_SWEEP_BIN when set.
  C2  Payload with hook_event_name == "PostToolUse", tool_name == "Bash" and tool_input.command matching
      \\bgit\\b(?:\\s+-C\\s+\\S+)?\\s+worktree\\s+(?:remove|prune)\\b -> invokes the reaper once. Non-matching
      forms (worktree list/add, git status, ls) do not invoke it. A mention inside quotes still triggers.
  C3  Any other event name or tool name (SessionEnd, PostToolUse with tool_name Read) -> exit 0, no
      invocation, empty stdout.
  C4  When the reaper exits 0, parse keep/reap/stale and freed MB from its stdout. If reap + stale > 0:
      append exactly one JSON ledger line and print exactly one summary stdout line. If reap + stale == 0:
      no ledger line, empty stdout.
  C5  Fail-open: missing binary, non-zero exit, timeout, or unparsable stdout -> exit 0, empty stdout, no
      ledger line, and exactly one stderr line naming the reason (with exit code / stderr excerpt when
      available).
  C6  A non-blocking flock on <ledger dir>/lock; if another sweep holds it, skip silently (exit 0, no
      invocation).
  C7  Exit code is always 0; empty or malformed stdin (non-JSON, or JSON that is not an object) -> exit 0,
      no invocation, empty stdout.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex_broker_sweep.py")
PY_DIR = os.path.dirname(sys.executable) or "/usr/bin"

FAKE_REAPER = """#!/usr/bin/env python3
import json
import os
import sys
import time

argv_file = os.environ.get("FAKE_REAP_ARGV_FILE")
if argv_file:
    with open(argv_file, "w", encoding="utf-8") as fh:
        json.dump(sys.argv, fh)
sleep_s = os.environ.get("FAKE_REAP_SLEEP")
if sleep_s:
    time.sleep(float(sleep_s))
sys.stdout.write(os.environ.get("FAKE_REAP_STDOUT", ""))
sys.stderr.write(os.environ.get("FAKE_REAP_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_REAP_EXIT", "0")))
"""

ZERO_SUMMARY = "keep=0  reap=0  stale=0\n回収で解放= 0 MB / 残す稼働分= 0 MB\n"
REAP_SUMMARY = "keep=2  reap=1  stale=1\n回収で解放= 128 MB / 残す稼働分= 64 MB\n"


def write_fake_reaper(path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(FAKE_REAPER)
    os.chmod(path, 0o755)


class Fixture:
    """One isolated bin/ledger/argv-file set, scoped to a single temp dir."""

    def __init__(self, tmp_dir: str) -> None:
        self.bindir = os.path.join(tmp_dir, "bin")
        os.makedirs(self.bindir)
        write_fake_reaper(os.path.join(self.bindir, "codex_broker_reap"))
        self.ledger_dir = os.path.join(tmp_dir, "ledger")
        self.ledger = os.path.join(self.ledger_dir, "ledger.jsonl")
        self.argv_file = os.path.join(tmp_dir, "argv.json")
        self.tmp_dir = tmp_dir
        self.env = {
            "PATH": self.bindir + os.pathsep + PY_DIR,
            "CODEX_BROKER_SWEEP_LEDGER": self.ledger,
            "FAKE_REAP_ARGV_FILE": self.argv_file,
            "FAKE_REAP_STDOUT": ZERO_SUMMARY,
            "FAKE_REAP_EXIT": "0",
        }

    def run_hook(
        self, payload, env_overrides: dict | None = None, raw: str | None = None
    ):
        env = dict(self.env)
        if env_overrides:
            env.update(env_overrides)
        body = raw if raw is not None else json.dumps(payload)
        return subprocess.run(
            [sys.executable, HOOK],
            input=body,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=env,
        )

    def assert_not_invoked(self, case: unittest.TestCase) -> None:
        case.assertFalse(os.path.exists(self.argv_file))

    def assert_invoked_once(
        self, case: unittest.TestCase, expected_bin: str = "codex_broker_reap"
    ):
        """A shebang re-exec via PATH always yields an absolute argv[0]; compare by basename there."""
        with open(self.argv_file, encoding="utf-8") as fh:
            argv = json.load(fh)
        case.assertEqual(len(argv), 2)
        case.assertEqual(argv[1], "--apply")
        if os.path.isabs(expected_bin):
            case.assertEqual(argv[0], expected_bin)
        else:
            case.assertEqual(os.path.basename(argv[0]), expected_bin)
        return argv


class SweepTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

    def fixture(self) -> Fixture:
        tmp_dir = self.stack.enter_context(tempfile.TemporaryDirectory())
        return Fixture(tmp_dir)

    def test_c1_session_start_invokes_reaper_once_via_path(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"}
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        fx.assert_invoked_once(self, "codex_broker_reap")

    def test_c1_session_start_uses_env_bin_override(self) -> None:
        fx = self.fixture()
        alt_bin = os.path.join(fx.tmp_dir, "alt_reaper")
        write_fake_reaper(alt_bin)
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"CODEX_BROKER_SWEEP_BIN": alt_bin, "PATH": PY_DIR},
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        fx.assert_invoked_once(self, alt_bin)

    def test_c2_worktree_remove_prune_positive_forms(self) -> None:
        for command in (
            "git worktree remove wt-x",
            "git -C /repo worktree remove --force wt-x",
            "git worktree prune",
        ):
            with self.subTest(command=command):
                fx = self.fixture()
                payload = {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "session_id": "s1",
                    "cwd": "/x",
                }
                out = fx.run_hook(payload)
                self.assertEqual(out.returncode, 0, out.stderr)
                fx.assert_invoked_once(self, "codex_broker_reap")

    def test_c2_worktree_non_matching_forms_negative(self) -> None:
        for command in (
            "git worktree list",
            "git worktree add wt-y -b wt-y main",
            "git status",
            "ls",
        ):
            with self.subTest(command=command):
                fx = self.fixture()
                payload = {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "session_id": "s1",
                    "cwd": "/x",
                }
                out = fx.run_hook(payload)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(out.stdout, "")
                fx.assert_not_invoked(self)

    def test_c3_other_events_no_invocation(self) -> None:
        for payload in (
            {"hook_event_name": "SessionEnd", "session_id": "s1", "cwd": "/x"},
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/x"},
                "session_id": "s1",
                "cwd": "/x",
            },
        ):
            with self.subTest(payload=payload):
                fx = self.fixture()
                out = fx.run_hook(payload)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(out.stdout, "")
                fx.assert_not_invoked(self)

    def test_c4_ledger_appended_when_reaped(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git worktree remove wt-x"},
                "session_id": "sess-42",
                "cwd": "/repo",
            },
            env_overrides={"FAKE_REAP_STDOUT": REAP_SUMMARY},
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        expected = (
            "codex broker 掃引: reap 1 / stale 1 / 解放 128 MB (台帳 "
            + fx.ledger
            + ")\n"
        )
        self.assertEqual(out.stdout, expected)
        with open(fx.ledger, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["event"], "PostToolUse")
        self.assertEqual(record["session_id"], "sess-42")
        self.assertEqual(record["cwd"], "/repo")
        self.assertEqual(record["command"], "git worktree remove wt-x")
        self.assertEqual(record["keep"], 2)
        self.assertEqual(record["reap"], 1)
        self.assertEqual(record["stale"], 1)
        self.assertEqual(record["freed_mb"], 128)
        self.assertIn("ts", record)

    def test_c4_session_start_ledger_has_no_command_key(self) -> None:
        fx = self.fixture()
        fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"FAKE_REAP_STDOUT": REAP_SUMMARY},
        )
        with open(fx.ledger, encoding="utf-8") as fh:
            record = json.loads(fh.read().splitlines()[0])
        self.assertNotIn("command", record)

    def test_c4_no_ledger_when_nothing_reaped(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"}
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, "")
        self.assertFalse(os.path.exists(fx.ledger))

    def test_c5_fail_open_missing_binary(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"PATH": PY_DIR},
        )
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")
        self.assertFalse(os.path.exists(fx.ledger))
        self.assertEqual(len(out.stderr.splitlines()), 1)
        self.assertIn("reaper unavailable (FileNotFoundError)", out.stderr)

    def test_c5_fail_open_nonzero_exit(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"FAKE_REAP_EXIT": "3", "FAKE_REAP_STDERR": "boom"},
        )
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")
        self.assertFalse(os.path.exists(fx.ledger))
        lines = out.stderr.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("reaper exited 3", lines[0])
        self.assertIn("boom", lines[0])

    def test_c5_fail_open_timeout(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"FAKE_REAP_SLEEP": "1", "CODEX_BROKER_SWEEP_TIMEOUT": "0.1"},
        )
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")
        self.assertFalse(os.path.exists(fx.ledger))
        self.assertEqual(len(out.stderr.splitlines()), 1)
        self.assertIn("reaper unavailable (TimeoutExpired)", out.stderr)

    def test_c5_fail_open_unparsable_summary(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"FAKE_REAP_STDOUT": "no summary here\n"},
        )
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")
        self.assertFalse(os.path.exists(fx.ledger))
        self.assertEqual(len(out.stderr.splitlines()), 1)
        self.assertIn("unparsable reaper output", out.stderr)

    def test_c6_lock_held_elsewhere_skips_silently(self) -> None:
        fx = self.fixture()
        os.makedirs(fx.ledger_dir, exist_ok=True)
        lock_path = os.path.join(fx.ledger_dir, "lock")
        with open(lock_path, "a+", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            out = fx.run_hook(
                {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"}
            )
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, "")
        fx.assert_not_invoked(self)

    def test_c7_malformed_or_empty_stdin(self) -> None:
        for raw in ("", "{not json", "[]", '"a string"'):
            with self.subTest(raw=raw):
                fx = self.fixture()
                out = fx.run_hook(None, raw=raw)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(out.stdout, "")
                fx.assert_not_invoked(self)


if __name__ == "__main__":
    unittest.main()
