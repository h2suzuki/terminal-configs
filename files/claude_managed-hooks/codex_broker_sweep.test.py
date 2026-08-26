#!/usr/bin/env python3
"""Acceptance tests for codex_broker_sweep.py, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  Payload with hook_event_name == "SessionStart" -> the hook invokes the reaper exactly once with
      argv ["codex_broker_reap", "--apply"]. The binary is resolved via PATH, or via env
      CODEX_BROKER_SWEEP_BIN when set.
  C2  Payload with hook_event_name == "PostToolUse", tool_name == "Bash" and tool_input.command matching
      \\bgit\\b(?:\\s+(?:-C\\s+(?:"[^"]*"|'[^']*'|\\S+)|-c\\s+\\S+|--git-dir=\\S+|--work-tree=\\S+))*
      \\s+worktree\\s+(?:remove|prune)\\b -> invokes the reaper once, including quoted/spaced -C paths and
      repeated -c/--git-dir/--work-tree options. Non-matching forms (worktree list/add, git status, ls) do
      not invoke it. A mention inside quotes still triggers.
  C3  Any other event name or tool name (SessionEnd, PostToolUse with tool_name Read) -> exit 0, no
      invocation, empty stdout.
  C4  When the reaper exits 0, parse keep/reap/stale and freed MB from its stdout. If reap + stale > 0:
      append one JSON ledger line (path = env CODEX_BROKER_SWEEP_LEDGER, else the documented default under
      ~/.claude/hooks/state/codex_broker_sweep/ledger.jsonl) and print exactly one stdout line:
      {"hookSpecificOutput": {"hookEventName": <event>, "additionalContext": <summary text>}}. If
      reap + stale == 0: no ledger line, empty stdout.
  C5  Fail-open: missing binary, non-zero exit, timeout, or unparsable stdout -> exit 0, empty stdout, no
      ledger line, and exactly one stderr line (newlines collapsed) naming the reason, with exit code /
      stderr excerpt when available.
  C6  A non-blocking flock (LOCK_EX) on <ledger dir>/lock; if another sweep holds it (shared or exclusive),
      skip silently apart from one stderr trace line, exit 0, no invocation.
  C7  Exit code is always 0; empty or malformed stdin (non-JSON, or JSON that is not an object) -> exit 0,
      no invocation, empty stdout.
  C8  Lock or ledger directory failures (e.g. an unwritable directory) do not cancel the sweep: the reaper
      still runs and one stderr line names the degraded step; a relative ledger path resolves against cwd.
"""

from __future__ import annotations

import contextlib
import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex_broker_sweep.py")
REAL_REAPER = os.path.join(os.path.dirname(HOOK), "..", "codex_broker_reap")
PY_DIR = os.path.dirname(sys.executable) or "/usr/bin"

FAKE_REAPER = """#!/usr/bin/env python3
import json
import os
import sys
import time

argv_file = os.environ.get("FAKE_REAP_ARGV_FILE")
if argv_file:
    with open(argv_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(sys.argv) + "\\n")
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
        self.argv_file = os.path.join(tmp_dir, "argv.jsonl")
        self.tmp_dir = tmp_dir
        self.env = {
            "PATH": self.bindir + os.pathsep + PY_DIR,
            "CODEX_BROKER_SWEEP_LEDGER": self.ledger,
            "FAKE_REAP_ARGV_FILE": self.argv_file,
            "FAKE_REAP_STDOUT": ZERO_SUMMARY,
            "FAKE_REAP_EXIT": "0",
        }

    def run_hook(
        self,
        payload,
        env_overrides: dict | None = None,
        raw: str | None = None,
        cwd: str | None = None,
    ):
        env = dict(self.env)
        for key, value in (env_overrides or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        body = raw if raw is not None else json.dumps(payload)
        return subprocess.run(
            [sys.executable, HOOK],
            input=body,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=env,
            cwd=cwd,
        )

    def assert_not_invoked(self, case: unittest.TestCase) -> None:
        case.assertFalse(os.path.exists(self.argv_file))

    def assert_invoked_once(
        self, case: unittest.TestCase, expected_bin: str = "codex_broker_reap"
    ):
        """A shebang re-exec via PATH always yields an absolute argv[0]; compare by basename there."""
        with open(self.argv_file, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        case.assertEqual(len(lines), 1)
        argv = json.loads(lines[0])
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
            "git -C '/path with space/repo' worktree remove -- wt",
            'git -C "/p q/r" worktree remove wt',
            "git -c core.x=1 worktree remove wt",
            "git -C /repo -c core.hooksPath=/dev/null worktree remove wt",
            "git --git-dir=/r/.git --work-tree=/r worktree prune",
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

    def test_c4_ledger_and_json_summary_emitted_when_reaped(self) -> None:
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
        stdout_lines = out.stdout.splitlines()
        self.assertEqual(len(stdout_lines), 1)
        emitted = json.loads(stdout_lines[0])
        hook_output = emitted["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "PostToolUse")
        self.assertIn("reap 1 / stale 1", hook_output["additionalContext"])
        self.assertIn(fx.ledger, hook_output["additionalContext"])
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

    def test_c4_session_start_summary_names_session_start_event(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"FAKE_REAP_STDOUT": REAP_SUMMARY},
        )
        emitted = json.loads(out.stdout.splitlines()[0])
        self.assertEqual(emitted["hookSpecificOutput"]["hookEventName"], "SessionStart")
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

    def test_c5_stderr_excerpt_collapses_newlines(self) -> None:
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={
                "FAKE_REAP_EXIT": "2",
                "FAKE_REAP_STDERR": "usage: x\nerror: y",
            },
        )
        self.assertEqual(out.returncode, 0)
        lines = out.stderr.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("usage: x", lines[0])
        self.assertIn("error: y", lines[0])

    def test_c6_lock_held_exclusive_skips_with_trace(self) -> None:
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
        self.assertIn("sweep skipped (lock held)", out.stderr)

    def test_c6_lock_held_shared_also_blocks(self) -> None:
        fx = self.fixture()
        os.makedirs(fx.ledger_dir, exist_ok=True)
        lock_path = os.path.join(fx.ledger_dir, "lock")
        with open(lock_path, "a+", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_SH)
            out = fx.run_hook(
                {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"}
            )
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, "")
        fx.assert_not_invoked(self)
        self.assertIn("sweep skipped (lock held)", out.stderr)

    def test_c7_malformed_or_empty_stdin(self) -> None:
        for raw in ("", "{not json", "[]", '"a string"'):
            with self.subTest(raw=raw):
                fx = self.fixture()
                out = fx.run_hook(None, raw=raw)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(out.stdout, "")
                fx.assert_not_invoked(self)

    def test_c8_unwritable_lock_dir_still_sweeps(self) -> None:
        fx = self.fixture()
        locked_dir = os.path.join(fx.tmp_dir, "locked")
        os.makedirs(locked_dir)
        ledger = os.path.join(locked_dir, "ledger.jsonl")
        os.chmod(locked_dir, 0o500)
        try:
            out = fx.run_hook(
                {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
                env_overrides={"CODEX_BROKER_SWEEP_LEDGER": ledger},
            )
        finally:
            os.chmod(locked_dir, 0o700)
        self.assertEqual(out.returncode, 0, out.stderr)
        fx.assert_invoked_once(self, "codex_broker_reap")
        self.assertIn("lock unavailable", out.stderr)

    def test_c8_bare_relative_ledger_filename_still_sweeps(self) -> None:
        fx = self.fixture()
        work_dir = os.path.join(fx.tmp_dir, "work")
        os.makedirs(work_dir)
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"},
            env_overrides={"CODEX_BROKER_SWEEP_LEDGER": "ledger.jsonl"},
            cwd=work_dir,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        fx.assert_invoked_once(self, "codex_broker_reap")
        self.assertEqual(out.stderr, "")

    def test_default_ledger_path_under_home(self) -> None:
        """C4's documented default is exercised end-to-end when no override is set."""
        fx = self.fixture()
        home_dir = os.path.join(fx.tmp_dir, "home")
        os.makedirs(home_dir)
        out = fx.run_hook(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git worktree remove wt-x"},
                "session_id": "s1",
                "cwd": "/x",
            },
            env_overrides={
                "CODEX_BROKER_SWEEP_LEDGER": None,
                "HOME": home_dir,
                "FAKE_REAP_STDOUT": REAP_SUMMARY,
            },
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        expected_ledger = os.path.join(
            home_dir, ".claude", "hooks", "state", "codex_broker_sweep", "ledger.jsonl"
        )
        self.assertTrue(os.path.exists(expected_ledger))

    def test_double_invocation_is_observable(self) -> None:
        """F7 exactly-once guard: the fake reaper appends one record per real invocation."""
        fx = self.fixture()
        out = fx.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"}
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        with open(fx.argv_file, encoding="utf-8") as fh:
            self.assertEqual(len(fh.read().splitlines()), 1)

    def test_real_reaper_dry_run_matches_summary_regexes(self) -> None:
        """C4/C9: the hook's parsing regexes stay coupled to the real CLI's actual wording."""
        if not os.path.isfile(REAL_REAPER):
            self.skipTest(
                "real reaper not co-located (test file copied out of the repo layout)"
            )
        spec = importlib.util.spec_from_file_location(
            "codex_broker_sweep_under_test", HOOK
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with (
            tempfile.TemporaryDirectory() as state_dir,
            tempfile.TemporaryDirectory() as tmp_dir,
        ):
            proc = subprocess.run(
                [
                    sys.executable,
                    REAL_REAPER,
                    "--state",
                    state_dir,
                    "--tmpdir",
                    tmp_dir,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNotNone(module.SUMMARY_RE.search(proc.stdout))
        self.assertIsNotNone(module.FREED_RE.search(proc.stdout))


if __name__ == "__main__":
    unittest.main()
