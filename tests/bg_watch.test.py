#!/usr/bin/env python3
"""Acceptance tests for bg_watch, written before the implementation.

Contract (each claim maps to one test):
  C1  the child's exit code is the wrapper's exit code; arguments after "--" reach the child verbatim
  C2  a child killed by a signal exits the wrapper with 128 + the signal number
  C3  child stdout and stderr go to the wrapper's stdout and to <run dir>/log, as they are produced; a closed
      wrapper stdout stops neither the log nor the exit code
  C4  the run dir holds cmd, log, meta.json (label, pid, started_at, interval, sid) and exit; without
      --log-dir it is ${TMPDIR:-/tmp}/bg_watch/<YYYYmmdd-HHMMSS>-<wrapper pid>/; stderr says log=<path>
  C5  nothing is sent at start; while the child runs one "running" message per interval, then exactly one
      "finished" message when it exits
  C6  messages name the label, the log path and the last 5 log lines cut to 200 chars; "running" reports the
      log growth since the previous message; each ends by asking for an ack, without which no later message wakes
  C7  the agent_coord token never reaches the log, meta, exit file, stdout, stderr or any sent text
  C8  agent_coord failing (whoami or send) never stops the child or changes its exit code; stderr says so
  C9  --no-notify calls agent_coord not at all
  C10 --to <sid> sends to that sid and does not call whoami
  C11 SIGINT / SIGTERM / SIGHUP to the wrapper kill the child's whole process group; exit is 128 + number
  C12 no command after "--", or a bad option, exits 2
  C13 a command that cannot be started exits 127 with one stderr line and no traceback
  C14 whoami runs as the caller; sends run as client "bg_watch" under one per-run sid without the caller's
      token, because agent_coord never wakes a session for its own messages; a final leave closes that sid
"""

from __future__ import annotations

import itertools
import json
import os
import re
import select
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

BG_WATCH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "files", "bg_watch"
)
SECRET = "SECRET"
SID = "cc-test"

# Records every call (with a timestamp) and answers like agent_coord; FAKE_AC_FAIL picks what fails.
FAKE_AGENT_COORD = """#!__PYTHON__
import json, os, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_AC_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"t": time.time(), "args": args, "env": {
        k: os.environ.get(k) for k in ("AGENT_COORD_CLIENT", "AGENT_COORD_SID", "AGENT_COORD_TOKEN")
    }}) + "\\n")
mode = os.environ.get("FAKE_AC_FAIL", "")
if args[:2] == ["--json", "whoami"]:
    if mode in ("all", "whoami"):
        sys.stderr.write("whoami failed\\n")
        sys.exit(1)
    print(json.dumps({"session": {"sid": "cc-test", "token": "SECRET"}}))
elif args[:1] == ["send"] and mode in ("all", "send"):
    sys.stderr.write("send failed\\n")
    sys.exit(1)
"""


def py(code: str, *args: str) -> list[str]:
    return [sys.executable, "-c", code, *args]


class Result:
    def __init__(self, proc: subprocess.Popen, out: bytes, err: bytes, t0: float):
        self.pid = proc.pid
        self.code = proc.returncode
        self.out = out.decode("utf-8", "replace")
        self.err = err.decode("utf-8", "replace")
        self.t0 = t0

    @property
    def run_dir(self) -> str:
        match = re.search(r"^bg_watch: log=(.+)/log$", self.err, re.MULTILINE)
        assert match, self.err
        return match.group(1)

    def read(self, name: str) -> str:
        with open(os.path.join(self.run_dir, name), encoding="utf-8") as fh:
            return fh.read()


class BgWatchCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.tmp = tmp
        self.bin = os.path.join(tmp, "bin")
        os.makedirs(self.bin)
        fake = os.path.join(self.bin, "agent_coord")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(FAKE_AGENT_COORD.replace("__PYTHON__", sys.executable))
        os.chmod(fake, 0o755)
        self.calls_path = os.path.join(tmp, "calls.jsonl")
        self.tmpdir = os.path.join(tmp, "tmpdir")
        os.makedirs(self.tmpdir)

    def env(self, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        env["FAKE_AC_LOG"] = self.calls_path
        env["TMPDIR"] = self.tmpdir
        env.pop("FAKE_AC_FAIL", None)
        env.update(extra)
        return env

    def start(self, *args: str, fail: str = "", **popen) -> subprocess.Popen:
        env = self.env(**({"FAKE_AC_FAIL": fail} if fail else {}))
        return subprocess.Popen(
            [sys.executable, BG_WATCH, *args],
            stdout=popen.pop("stdout", subprocess.PIPE),
            stderr=subprocess.PIPE,
            env=env,
            **popen,
        )

    def invoke(self, *args: str, fail: str = "", timeout: float = 30) -> Result:
        t0 = time.time()
        proc = self.start(*args, fail=fail)
        out, err = proc.communicate(timeout=timeout)
        return Result(proc, out, err, t0)

    def calls(self) -> list[dict]:
        try:
            with open(self.calls_path, encoding="utf-8") as fh:
                return [json.loads(line) for line in fh]
        except FileNotFoundError:
            return []

    def sends(self) -> list[dict]:
        return [c for c in self.calls() if c["args"][:1] == ["send"]]

    @staticmethod
    def text_of(send: dict) -> str:
        return send["args"][3]


class ExitCodeTest(BgWatchCase):
    def test_c1_exit_code_passes_through(self):
        for code in (0, 7):
            with self.subTest(code=code):
                result = self.invoke(
                    "--no-notify", "--", *py(f"raise SystemExit({code})")
                )
                self.assertEqual(result.code, code)

    def test_c1_arguments_after_double_dash_reach_the_child(self):
        child = py("import sys; print(sys.argv[1:])", "--interval", "9", "--to", "x")
        result = self.invoke("--no-notify", "--interval", "3", "--", *child)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out.strip(), "['--interval', '9', '--to', 'x']")

    def test_c2_signal_death_is_128_plus_number(self):
        code = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
        result = self.invoke("--no-notify", "--", *py(code))
        self.assertEqual(result.code, 128 + signal.SIGTERM)


class OutputTest(BgWatchCase):
    def test_c3_stdout_and_stderr_reach_wrapper_stdout_and_log(self):
        code = "import sys; print('to-out'); print('to-err', file=sys.stderr)"
        result = self.invoke("--no-notify", "--", *py(code))
        for text in (result.out, result.read("log")):
            self.assertIn("to-out", text)
            self.assertIn("to-err", text)
        self.assertNotIn("to-err", result.err)

    def test_c3_output_streams_before_the_child_exits(self):
        code = "import time; print('first', flush=True); time.sleep(3); print('last')"
        proc = self.start("--no-notify", "--", *py(code))
        assert proc.stdout is not None
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 2.0)
            self.assertTrue(ready, "no output within 2s of a 3s child")
            self.assertEqual(proc.stdout.readline(), b"first\n")
            self.assertIsNone(proc.poll())
        finally:
            proc.communicate(timeout=30)

    def test_c3_closed_stdout_does_not_stop_the_log_or_the_exit_code(self):
        code = "import time; time.sleep(0.5); print('after-close' * 1000); raise SystemExit(6)"
        proc = self.start("--no-notify", "--", *py(code))
        assert proc.stdout is not None
        proc.stdout.close()
        _, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 6, err)
        self.assertNotIn(b"Traceback", err)
        self.assertNotIn(b"Exception ignored", err)
        log_dir = re.search(rb"log=(.+)/log", err)
        assert log_dir
        with open(os.path.join(log_dir.group(1).decode(), "log"), "rb") as fh:
            self.assertIn(b"after-close", fh.read())

    def test_c4_run_dir_in_tmpdir_by_default(self):
        result = self.invoke(
            "--label", "mine", "--interval", "7", "--", *py("print(1)")
        )
        run_dir = result.run_dir
        self.assertEqual(
            os.path.dirname(run_dir), os.path.join(self.tmpdir, "bg_watch")
        )
        match = re.fullmatch(r"\d{8}-\d{6}-(\d+)", os.path.basename(run_dir))
        assert match, run_dir
        self.assertEqual(int(match.group(1)), result.pid)
        self.assertEqual(result.read("log"), "1\n")
        self.assertEqual(result.read("exit"), "0\n")
        meta = json.loads(result.read("meta.json"))
        self.assertEqual(
            set(meta), {"label", "pid", "started_at", "interval", "sid"}, meta
        )
        self.assertEqual(
            (meta["label"], meta["pid"], meta["interval"], meta["sid"]),
            ("mine", result.pid, 7, SID),
        )

    def test_c4_log_dir_option_and_cmd_file(self):
        target = os.path.join(self.tmp, "chosen")
        child = py("raise SystemExit(3)", "a b")
        result = self.invoke("--no-notify", "--log-dir", target, "--", *child)
        self.assertEqual(result.code, 3)
        self.assertIn(f"bg_watch: log={target}/log", result.err)
        self.assertEqual(shlex.split(result.read("cmd")), child)
        self.assertEqual(result.read("exit"), "3\n")
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "bg_watch")))

    def test_c4_default_label_is_the_command_cut_to_80_chars(self):
        result = self.invoke("--no-notify", "--", "echo", "x" * 100)
        self.assertEqual(
            json.loads(result.read("meta.json"))["label"], ("echo " + "x" * 100)[:80]
        )

    def test_c4_script_is_executable_python3(self):
        self.assertTrue(os.access(BG_WATCH, os.X_OK))
        with open(BG_WATCH, encoding="utf-8") as fh:
            self.assertEqual(fh.readline().strip(), "#!/usr/bin/env python3")


class NotifyTest(BgWatchCase):
    def test_c5_running_every_interval_then_one_finished(self):
        code = (
            "import time; print('a', flush=True); time.sleep(1.5);"
            "print('bbb', flush=True); time.sleep(1.0)"
        )
        result = self.invoke("--interval", "1", "--label", "job", "--", *py(code))
        self.assertEqual(result.code, 0)
        sends = self.sends()
        texts = [self.text_of(s) for s in sends]
        running = [t for t in texts if t.startswith("[bg_watch] 実行中: ")]
        finished = [t for t in texts if t.startswith("[bg_watch] 終了: ")]
        self.assertIn(len(running), (1, 2, 3), texts)
        self.assertEqual(len(finished), 1, texts)
        self.assertEqual(texts[-1], finished[0])
        self.assertEqual(len(texts), len(running) + len(finished))
        self.assertGreaterEqual(sends[0]["t"] - result.t0, 0.9, "sent at start")
        gaps = [b["t"] - a["t"] for a, b in itertools.pairwise(sends)]
        self.assertTrue(all(gap >= 0.8 for gap in gaps[: len(running) - 1]), gaps)

    def test_c5_sent_through_the_resolved_sid(self):
        self.invoke("--interval", "1", "--", *py("import time; time.sleep(1.5)"))
        calls = [c["args"] for c in self.calls()]
        self.assertEqual(calls[0], ["--json", "whoami"])
        self.assertEqual(calls[-1], ["leave"])
        for args in calls[1:-1]:
            self.assertEqual(args[:3], ["send", "--to", SID])
            self.assertEqual(len(args), 4)

    def test_c14_sends_under_a_per_run_identity_then_leave(self):
        env = self.env(AGENT_COORD_TOKEN="caller-token")
        subprocess.run(
            [
                sys.executable,
                BG_WATCH,
                "--interval",
                "1",
                "--",
                *py("import time; time.sleep(1.5)"),
            ],
            env=env,
            capture_output=True,
            timeout=30,
            check=False,
        )
        calls = self.calls()
        self.assertEqual(calls[0]["env"]["AGENT_COORD_CLIENT"], None)
        self.assertEqual(calls[0]["env"]["AGENT_COORD_TOKEN"], "caller-token")
        rest = calls[1:]
        self.assertGreaterEqual(len(rest), 3, calls)
        self.assertEqual(rest[-1]["args"], ["leave"])
        sids = {c["env"]["AGENT_COORD_SID"] for c in rest}
        self.assertEqual(len(sids), 1, sids)
        self.assertTrue(next(iter(sids)).startswith("bg_watch-"), sids)
        for call in rest:
            self.assertEqual(call["env"]["AGENT_COORD_CLIENT"], "bg_watch")
            self.assertIsNone(call["env"]["AGENT_COORD_TOKEN"])

    def test_c14_each_run_gets_its_own_sid(self):
        for _ in range(2):
            self.invoke("--", *py("print(1)"))
        sids = {
            c["env"]["AGENT_COORD_SID"] for c in self.calls() if c["args"] == ["leave"]
        }
        self.assertEqual(len(sids), 2, self.calls())

    def test_c6_running_text_reports_growth_and_log_location(self):
        code = (
            "import time; print('a', flush=True); time.sleep(1.5);"
            "print('bbb', flush=True); time.sleep(1.0)"
        )
        result = self.invoke("--interval", "1", "--label", "job", "--", *py(code))
        running = [
            self.text_of(s)
            for s in self.sends()
            if self.text_of(s).startswith("[bg_watch] 実行中: ")
        ]
        log_path = os.path.join(result.run_dir, "log")
        self.assertGreaterEqual(len(running), 2, running)
        first = running[0].splitlines()
        self.assertRegex(
            first[0],
            r"^\[bg_watch\] 実行中: job / 経過 0分 / ログ \+2 bytes（最終更新 \d+秒前）"
            + re.escape(f"/ log: {log_path}")
            + "$",
        )
        self.assertIn("ログ +4 bytes", running[1].splitlines()[0])
        self.assertEqual(first[1:-1], ["a"])
        self.assertEqual(
            first[-1],
            "様子を確かめ、止まっている・異常なら原因を調べて対処すること。"
            "読んだら agent_coord で ack すること（しないと次の知らせで起こされない）。",
        )

    def test_c6_finished_text_has_exit_code_and_last_five_lines(self):
        code = (
            "for i in range(1, 8): print(f'line{i}')\n"
            "print('L' + 'y' * 299)\n"
            "raise SystemExit(3)"
        )
        result = self.invoke("--label", "job", "--", *py(code))
        self.assertEqual(result.code, 3)
        (send,) = self.sends()
        lines = self.text_of(send).splitlines()
        log_path = os.path.join(result.run_dir, "log")
        self.assertEqual(
            lines[0], f"[bg_watch] 終了: job / exit=3 / 経過 0分 / log: {log_path}"
        )
        self.assertEqual(
            lines[1:-1],
            ["line4", "line5", "line6", "line7", "L" + "y" * 199],
        )
        self.assertEqual(
            lines[-1],
            "結果を確かめ、次の作業に進むこと。"
            "読んだら agent_coord で ack すること（しないと次の知らせで起こされない）。",
        )

    def test_c7_token_never_leaks(self):
        code = "import time; print('x'); time.sleep(1.5)"
        result = self.invoke("--interval", "1", "--", *py(code))
        self.assertGreaterEqual(len(self.sends()), 2)
        haystacks = [result.out, result.err]
        for name in os.listdir(result.run_dir):
            haystacks.append(result.read(name))
        haystacks += [self.text_of(s) for s in self.sends()]
        haystacks += [" ".join(c["args"]) for c in self.calls()]
        for text in haystacks:
            self.assertNotIn(SECRET, text)

    def test_c8_whoami_failure_disables_notifications_only(self):
        result = self.invoke(
            "--", *py("print('done'); raise SystemExit(4)"), fail="all"
        )
        self.assertEqual(result.code, 4)
        self.assertIn("done", result.out)
        self.assertEqual(self.sends(), [])
        warnings = [ln for ln in result.err.splitlines() if "agent_coord" in ln]
        self.assertEqual(len(warnings), 1, result.err)
        self.assertTrue(warnings[0].startswith("bg_watch: "))

    def test_c8_send_failure_does_not_stop_the_child(self):
        code = "import time; time.sleep(1.5); print('done'); raise SystemExit(4)"
        result = self.invoke("--interval", "1", "--", *py(code), fail="send")
        self.assertEqual(result.code, 4)
        self.assertIn("done", result.out)
        self.assertEqual(result.read("exit"), "4\n")
        self.assertGreaterEqual(len(self.sends()), 2)
        failures = [ln for ln in result.err.splitlines() if "send" in ln]
        self.assertGreaterEqual(len(failures), 2, result.err)
        self.assertTrue(all(ln.startswith("bg_watch: ") for ln in failures))

    def test_c9_no_notify_calls_agent_coord_not_at_all(self):
        result = self.invoke(
            "--no-notify", "--interval", "1", "--", *py("import time; time.sleep(1.5)")
        )
        self.assertEqual(result.code, 0)
        self.assertEqual(self.calls(), [])
        self.assertEqual(result.err.strip().splitlines()[0][:14], "bg_watch: log=")
        self.assertEqual(len(result.err.strip().splitlines()), 1, result.err)

    def test_c10_to_option_skips_whoami(self):
        self.invoke("--to", "cc-other", "--", *py("print(1)"))
        calls = [c["args"] for c in self.calls()]
        self.assertEqual(len(calls), 2, calls)
        self.assertEqual(calls[0][:3], ["send", "--to", "cc-other"])
        self.assertEqual(calls[1], ["leave"])


class SignalTest(BgWatchCase):
    CHILD = (
        "import os, signal, subprocess, sys, time\n"
        "for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):\n"
        "    signal.signal(s, signal.SIG_DFL)\n"
        "grandchild = subprocess.Popen(['sleep', '60'])\n"
        "with open(sys.argv[1], 'w') as fh:\n"
        "    fh.write(f'{os.getpid()} {grandchild.pid}')\n"
        "time.sleep(60)\n"
    )

    @staticmethod
    def alive(pid: int) -> bool:
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
                return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return False

    def wait_for(self, predicate, what: str, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(f"timed out waiting for {what}")

    def pids(self, path: str) -> list[int]:
        try:
            with open(path, encoding="utf-8") as fh:
                return [int(p) for p in fh.read().split()]
        except (OSError, ValueError):
            return []

    def launch(self, name: str) -> tuple[subprocess.Popen, int, int]:
        pidfile = os.path.join(self.tmp, name)
        proc = self.start("--", *py(self.CHILD, pidfile))
        self.wait_for(lambda: len(self.pids(pidfile)) == 2, "child pids")
        child, grandchild = self.pids(pidfile)
        return proc, child, grandchild

    def check_signal(self, sig: signal.Signals) -> None:
        proc, child, grandchild = self.launch(f"pids-{sig.name}")
        try:
            self.assertNotEqual(os.getpgid(child), os.getpgid(proc.pid))
            proc.send_signal(sig)
            _, err = proc.communicate(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 128 + sig.value, err)
        self.wait_for(
            lambda: not (self.alive(child) or self.alive(grandchild)),
            "child group to die",
        )

    def test_c11_signal_kills_the_child_group(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(sig=sig.name):
                self.check_signal(sig)

    def test_c11_finished_message_reports_the_signal_exit(self):
        proc, _, _ = self.launch("pids")
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=10)
        (send,) = self.sends()
        self.assertIn(f"exit={128 + signal.SIGTERM}", self.text_of(send))


class UsageTest(BgWatchCase):
    def test_c12_bad_invocations_exit_2(self):
        for args in (
            (),
            ("--interval", "5"),
            ("--",),
            ("--interval", "5", "--"),
            ("--bogus", "--", "true"),
            ("--interval", "soon", "--", "true"),
        ):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.code, 2, result.err)
                self.assertIn("usage:", result.err)
                self.assertEqual(self.calls(), [])

    def test_c13_unstartable_command_exits_127(self):
        result = self.invoke("--no-notify", "--", "/nonexistent/bg_watch_test_cmd")
        self.assertEqual(result.code, 127)
        self.assertNotIn("Traceback", result.err)
        errors = [
            ln for ln in result.err.splitlines() if not ln.startswith("bg_watch: log=")
        ]
        self.assertEqual(len(errors), 1, result.err)
        self.assertTrue(errors[0].startswith("bg_watch: "))


if __name__ == "__main__":
    unittest.main()
