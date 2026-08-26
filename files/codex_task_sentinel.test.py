#!/usr/bin/env python3
"""Acceptance tests for codex_task_sentinel, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  records are searched as <root>/*/jobs/<job-id>.json in every --state-root; zero or several → exit 6
  C2  an unreadable or non-object record → exit 6
  C3  status "queued" / "running" is alive; any other status is terminal
  C4  deliverable ready ⇔ regular file, UTF-8, last non-blank line equals --token exactly
  C5  terminal "completed" + ready → exit 0
  C6  terminal "completed" + not ready → exit 3
  C7  terminal but not "completed" (cancelled / failed / other) → exit 5
  C8  alive with heartbeat age ≤ --stall-seconds → --once exits 1; watch mode keeps polling
  C9  alive with heartbeat age > --stall-seconds → exit 4
  C10 watch mode with no verdict by --timeout-seconds, or past 2×--estimate-seconds → exit 4
  C11 every exit prints verdict= and record= lines; non-zero exits add status=, heartbeat_age=, deliverable=, log_tail
  C12 missing --artifact or --token → exit 2 (argparse usage)
Heartbeat = newest mtime among the record, its log (<id>.log beside it), and the artifact.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

SENTINEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "codex_task_sentinel"
)
JOB = "task-abc123-def456"
TOKEN = "REPORT_COMPLETE"


def run(*extra: str, root: str, once: bool = True) -> subprocess.CompletedProcess:
    cmd = [sys.executable, SENTINEL, JOB, "--state-root", root, *extra]
    if once:
        cmd.append("--once")
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)


class Fixture:
    def __init__(self, root: str, workspace: str = "ws-1") -> None:
        self.root = root
        self.jobs = os.path.join(root, workspace, "jobs")
        os.makedirs(self.jobs, exist_ok=True)
        self.record = os.path.join(self.jobs, f"{JOB}.json")
        self.log = os.path.join(self.jobs, f"{JOB}.log")
        self.artifact = os.path.join(root, "report.md")

    def write_record(self, status: str, raw: str | None = None) -> None:
        with open(self.record, "w", encoding="utf-8") as fh:
            fh.write(
                raw if raw is not None else json.dumps({"id": JOB, "status": status})
            )

    def write_log(self, *lines: str) -> None:
        with open(self.log, "w", encoding="utf-8") as fh:
            fh.write("".join(f"[2026-08-26T00:00:00.000Z] {line}\n" for line in lines))

    def write_artifact(self, text: str) -> None:
        with open(self.artifact, "w", encoding="utf-8") as fh:
            fh.write(text)

    def age_everything(self, seconds: float) -> None:
        stamp = time.time() - seconds
        for path in (self.record, self.log, self.artifact):
            if os.path.exists(path):
                os.utime(path, (stamp, stamp))

    def args(self) -> list[str]:
        return ["--artifact", self.artifact, "--token", TOKEN]


class VerdictTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_c5_completed_and_ready_is_done(self) -> None:
        self.fx.write_record("completed")
        self.fx.write_artifact("body\n\n" + TOKEN + "\n")
        done = run(*self.fx.args(), root=self.fx.root)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("verdict=done", done.stdout)
        self.assertIn(f"record={self.fx.record}", done.stdout)

    def test_c4_token_must_be_the_last_nonblank_line(self) -> None:
        self.fx.write_record("completed")
        for text in (
            TOKEN + "\ntrailing\n",
            "prefix " + TOKEN + "\n",
            TOKEN + " \n",
            "no token\n",
        ):
            self.fx.write_artifact(text)
            self.assertEqual(
                run(*self.fx.args(), root=self.fx.root).returncode, 3, repr(text)
            )
        self.fx.write_artifact(TOKEN)
        self.assertEqual(run(*self.fx.args(), root=self.fx.root).returncode, 0)

    def test_c4_non_utf8_or_missing_artifact_is_not_ready(self) -> None:
        self.fx.write_record("completed")
        self.assertEqual(run(*self.fx.args(), root=self.fx.root).returncode, 3)
        with open(self.fx.artifact, "wb") as fh:
            fh.write(b"\xff\xfe\n" + TOKEN.encode() + b"\n")
        self.assertEqual(run(*self.fx.args(), root=self.fx.root).returncode, 3)

    def test_c6_completed_without_deliverable_says_so(self) -> None:
        self.fx.write_record("completed")
        self.fx.write_log("Starting Codex Task.", "Turn started.")
        out = run(*self.fx.args(), root=self.fx.root)
        self.assertEqual(out.returncode, 3)
        self.assertIn("verdict=no-deliverable", out.stdout)
        self.assertIn("deliverable=", out.stdout)
        self.assertIn("Turn started.", out.stdout)

    def test_c7_cancelled_or_failed_is_never_a_result(self) -> None:
        self.fx.write_artifact(TOKEN + "\n")
        for status in ("cancelled", "failed", "exploded"):
            self.fx.write_record(status)
            out = run(*self.fx.args(), root=self.fx.root)
            self.assertEqual(out.returncode, 5, status)
            self.assertIn("verdict=failed", out.stdout)
            self.assertIn(f"status={status}", out.stdout)

    def test_c3_c8_alive_and_fresh_reports_alive_under_once(self) -> None:
        for status in ("queued", "running"):
            self.fx.write_record(status)
            out = run(*self.fx.args(), "--stall-seconds", "420", root=self.fx.root)
            self.assertEqual(out.returncode, 1, status)
            self.assertIn("verdict=alive", out.stdout)
            self.assertIn("heartbeat_age=", out.stdout)

    def test_c9_alive_but_quiet_past_stall_is_undecided(self) -> None:
        self.fx.write_record("running")
        self.fx.write_log("Starting Codex Task.")
        self.fx.age_everything(1000)
        out = run(*self.fx.args(), "--stall-seconds", "420", root=self.fx.root)
        self.assertEqual(out.returncode, 4)
        self.assertIn("verdict=undecided", out.stdout)
        self.assertIn("Starting Codex Task.", out.stdout)

    def test_c8_artifact_activity_counts_as_heartbeat(self) -> None:
        self.fx.write_record("running")
        self.fx.age_everything(1000)
        self.fx.write_artifact("partial\n")
        self.assertEqual(
            run(
                *self.fx.args(), "--stall-seconds", "420", root=self.fx.root
            ).returncode,
            1,
        )

    def test_c8_watch_mode_polls_until_the_record_turns_terminal(self) -> None:
        self.fx.write_record("running")
        self.fx.write_artifact(TOKEN + "\n")
        proc = subprocess.Popen(
            [
                sys.executable,
                SENTINEL,
                JOB,
                "--state-root",
                self.fx.root,
                *self.fx.args(),
                "--poll-seconds",
                "0.2",
                "--timeout-seconds",
                "30",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(1.0)
        self.assertIsNone(
            proc.poll(), "watch mode must not exit while the job is alive"
        )
        self.fx.write_record("completed")
        stdout, _ = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, stdout)

    def test_c10_watch_mode_timeout_is_undecided(self) -> None:
        self.fx.write_record("running")
        out = run(
            *self.fx.args(),
            "--poll-seconds",
            "0.2",
            "--timeout-seconds",
            "1",
            root=self.fx.root,
            once=False,
        )
        self.assertEqual(out.returncode, 4)
        self.assertIn("verdict=undecided", out.stdout)

    def test_c10_over_estimate_is_undecided(self) -> None:
        self.fx.write_record("running")
        out = run(
            *self.fx.args(),
            "--poll-seconds",
            "0.2",
            "--estimate-seconds",
            "1",
            "--timeout-seconds",
            "30",
            root=self.fx.root,
            once=False,
        )
        self.assertEqual(out.returncode, 4)
        self.assertIn("estimate", out.stdout)

    def test_c1_no_record_anywhere(self) -> None:
        out = run(*self.fx.args(), root=self.fx.root)
        self.assertEqual(out.returncode, 6)
        self.assertIn("verdict=unresolved", out.stdout)

    def test_c1_several_records_are_listed_not_chosen(self) -> None:
        self.fx.write_record("completed")
        other = Fixture(self.fx.root, workspace="ws-2")
        other.write_record("running")
        self.fx.write_artifact(TOKEN + "\n")
        out = run(*self.fx.args(), root=self.fx.root)
        self.assertEqual(out.returncode, 6)
        self.assertIn(self.fx.record, out.stdout)
        self.assertIn(other.record, out.stdout)

    def test_c1_second_state_root_is_searched(self) -> None:
        with tempfile.TemporaryDirectory() as second:
            fx2 = Fixture(second)
            fx2.write_record("completed")
            fx2.write_artifact(TOKEN + "\n")
            cmd = [
                sys.executable,
                SENTINEL,
                JOB,
                "--state-root",
                self.fx.root,
                "--state-root",
                second,
                *fx2.args(),
                "--once",
            ]
            out = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=60
            )
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_c2_unreadable_record_is_unresolved(self) -> None:
        for raw in ("{not json", "[]", '"string"'):
            self.fx.write_record("x", raw=raw)
            out = run(*self.fx.args(), root=self.fx.root)
            self.assertEqual(out.returncode, 6, raw)

    def test_c11_log_tail_is_bounded(self) -> None:
        self.fx.write_record("completed")
        self.fx.write_log(*[f"line {i}" for i in range(50)], "x" * 5000)
        out = run(*self.fx.args(), root=self.fx.root)
        self.assertEqual(out.returncode, 3)
        self.assertNotIn("line 0\n", out.stdout)
        self.assertIn("line 4", out.stdout)
        self.assertLess(max(len(line) for line in out.stdout.splitlines()), 400)

    def test_c12_usage_errors(self) -> None:
        for cmd in (
            [
                sys.executable,
                SENTINEL,
                JOB,
                "--state-root",
                self.fx.root,
                "--token",
                TOKEN,
            ],
            [
                sys.executable,
                SENTINEL,
                JOB,
                "--state-root",
                self.fx.root,
                "--artifact",
                self.fx.artifact,
            ],
        ):
            out = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=60
            )
            self.assertEqual(out.returncode, 2, cmd)


if __name__ == "__main__":
    unittest.main()
