#!/usr/bin/env python3
"""Black-box tests for `claude_hook_bundle`: argv + stdin payload in, exit code / stdout / stderr out.

Contract (each claim maps to the tests named `test_c<N>_*`, IDs are the CLI docstring's 1-9):
  1  argv: `[--timeout S] [--file PATH] CMD... ::: CMD...`, no shell; children come from argv or
     from the manifest PATH (one per line, shlex, `#` comments, `~` expanded); bad argv or
     manifest = message on stderr, exit 0
  2  every child gets the same stdin bytes, inherits env and cwd
  3  children run concurrently
  4  timeout SIGKILLs the child's process group; SIGTERM / SIGINT kill all children, exit 0
  5  exit 2 if any child exited 2, stderr = the exit-2 children's stderr
  6  stdout = one merged JSON line in child order (or nothing)
  7  failed children (spawn / timeout / invalid JSON / exit not 0,2 without JSON) add a systemMessage line
  8  internal errors fail open
  9  same inputs -> same stdout bytes
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from typing import NamedTuple

CLI = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "files", "claude_hook_bundle"
)
PY = os.path.basename(sys.executable)
CONTEXT_EVENTS = ("UserPromptSubmit", "SessionStart")


class Run(NamedTuple):
    code: int
    out: str
    err: str

    @property
    def obj(self) -> dict:
        return json.loads(self.out)


def hso(**fields: object) -> dict:
    return {"hookSpecificOutput": fields}


def is_alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def wait_for(predicate, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class BundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.count = 0

    def path(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def raw_child(self, body: str) -> list[str]:
        self.count += 1
        script = self.path(f"child{self.count}.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(body)
        return [sys.executable, script]

    def child(
        self,
        obj: object = None,
        *,
        out: str = "",
        err: str = "",
        code: int = 0,
        delay: float = 0.0,
        pre: str = "",
    ) -> list[str]:
        """A child hook: sleeps `delay`, writes `obj` as JSON (or `out`) and `err`, exits `code`."""
        stdout = json.dumps(obj, ensure_ascii=False) if obj is not None else out
        return self.raw_child(
            f"import sys, time\n{pre}\ntime.sleep({delay})\n"
            f"sys.stdout.write({stdout!r})\nsys.stderr.write({err!r})\nsys.exit({code})\n"
        )

    @staticmethod
    def argv(children: tuple[list[str], ...], timeout: float | None) -> list[str]:
        head = ["--timeout", str(timeout)] if timeout is not None else []
        tail: list[str] = []
        for i, cmd in enumerate(children):
            tail += ([":::"] if i else []) + cmd
        return head + tail

    def cli(self, *args: str, stdin: bytes = b"", **kwargs) -> Run:
        proc = subprocess.run(
            [sys.executable, CLI, *args],
            input=stdin,
            capture_output=True,
            check=False,
            timeout=30,
            **kwargs,
        )
        return Run(proc.returncode, proc.stdout.decode(), proc.stderr.decode())

    def bundle(
        self,
        *children: list[str],
        event: str | None = "Stop",
        timeout: float | None = None,
        **kwargs,
    ) -> Run:
        payload = {"prompt": "hi"} | ({"hook_event_name": event} if event else {})
        return self.cli(
            *self.argv(children, timeout), stdin=json.dumps(payload).encode(), **kwargs
        )

    # --- 1: argv ---

    def test_c1_bad_argv_prints_usage_and_exits_0(self) -> None:
        ok = [sys.executable, "-c", "pass"]
        cases = {
            "no child": [],
            "timeout only": ["--timeout", "5"],
            "lone separator": [":::"],
            "empty child in the middle": [*ok, ":::", ":::", *ok],
            "trailing separator": [*ok, ":::"],
            "leading separator": [":::", *ok],
            "timeout without value": ["--timeout"],
            "timeout not a number": ["--timeout", "abc", *ok],
            "timeout zero": ["--timeout", "0", *ok],
            "timeout not finite": ["--timeout", "nan", *ok],
            "unknown option": ["--timeout=5", *ok],
        }
        for label, argv in cases.items():
            with self.subTest(label):
                run = self.cli(*argv)
                self.assertEqual((run.code, run.out), (0, ""), run.err)
                self.assertIn("usage:", run.err)

    def test_c1_help_prints_usage_to_stdout(self) -> None:
        for flag in ("--help", "-h"):
            with self.subTest(flag):
                run = self.cli(flag)
                self.assertEqual((run.code, run.err), (0, ""))
                self.assertIn("usage:", run.out)

    def test_c1_children_run_without_a_shell(self) -> None:
        args = ["a b", "$HOME", ";echo x", "*", "~", "~/x"]
        show = self.raw_child(
            "import json, sys\n"
            "print(json.dumps({'systemMessage': json.dumps(sys.argv[1:])}))\n"
        )
        run = self.bundle(show + args)
        self.assertEqual(json.loads(run.obj["systemMessage"]), args)

    def manifest(self, *lines: str, name: str = "hooks.list") -> str:
        path = self.path(name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return path

    def test_c1_manifest_children_run_in_file_order(self) -> None:
        show = self.raw_child(
            "import json, sys\n"
            "print(json.dumps({'systemMessage': json.dumps(sys.argv[1:])}))\n"
        )
        first = self.child({"systemMessage": "first"}, delay=0.3)
        path = self.manifest(
            "# leading comment",
            "",
            "   # indented comment",
            shlex.join(first) + "  # trailing comment",
            shlex.join([*show, "a b", "$HOME", "#x"]),
        )
        run = self.cli("--file", path, stdin=b"{}")
        self.assertEqual(run.code, 0, run.err)
        first_msg, _, second = run.obj["systemMessage"].partition("\n")
        self.assertEqual(first_msg, "first")
        self.assertEqual(json.loads(second), ["a b", "$HOME", "#x"])

    def test_c1_manifest_tokens_starting_with_tilde_are_expanded(self) -> None:
        home = self.path("home")
        os.mkdir(home)
        child = self.raw_child(
            "import json, sys\n"
            "print(json.dumps({'systemMessage': json.dumps(sys.argv[1:])}))\n"
        )
        path = self.manifest(shlex.join(child) + " ~ ~/x a~b")
        run = self.cli("--file", path, stdin=b"{}", env={**os.environ, "HOME": home})
        self.assertEqual(
            json.loads(run.obj["systemMessage"]), [home, f"{home}/x", "a~b"]
        )

    def test_c1_manifest_options_work_in_either_order(self) -> None:
        path = self.manifest(shlex.join(self.child(delay=30)))
        for argv in (
            ["--timeout", "0.5", "--file", path],
            ["--file", path, "--timeout", "0.5"],
        ):
            with self.subTest(argv[0]):
                run = self.cli(*argv, stdin=b"{}")
                self.assertEqual(
                    run.obj["systemMessage"], f"hook-bundle: {PY} failed (timeout 0.5s)"
                )

    def test_c1_bad_manifest_or_option_use_prints_a_message_and_exits_0(self) -> None:
        ok = [sys.executable, "-c", "pass"]
        good = self.manifest(shlex.join(ok), name="good.list")
        cases = {
            "missing file": ["--file", self.path("absent.list")],
            "directory": ["--file", self.tmp.name],
            "unterminated quote": ["--file", self.manifest("echo 'oops")],
            "only comments and blanks": ["--file", self.manifest("# a", "", "  ")],
            "empty file": ["--file", self.manifest(name="empty.list")],
            "file plus inline command": ["--file", good, *ok],
            "file plus separator": ["--file", good, ":::"],
            "file twice": ["--file", good, "--file", good],
            "timeout twice": ["--timeout", "1", "--timeout", "2", *ok],
            "file without value": ["--file"],
        }
        for label, argv in cases.items():
            with self.subTest(label):
                run = self.cli(*argv)
                self.assertEqual((run.code, run.out), (0, ""), run.err)
                self.assertIn("hook-bundle:", run.err)
                self.assertNotIn("internal error", run.err)

    def test_c1_missing_manifest_message_names_the_file(self) -> None:
        run = self.cli("--file", self.path("absent.list"))
        self.assertIn("absent.list", run.err)

    def test_c1_manifest_is_read_before_stdin(self) -> None:
        fd = os.open(self.path("write-only"), os.O_WRONLY | os.O_CREAT)
        self.addCleanup(os.close, fd)
        proc = subprocess.run(
            [sys.executable, CLI, "--file", self.path("absent.list")],
            stdin=fd,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn(b"internal error", proc.stderr)

    # --- 2: stdin / env / cwd ---

    def test_c2_every_child_receives_the_same_stdin_bytes(self) -> None:
        payload = b'{"hook_event_name":"Stop","x":"\xe3\x81\x82"}\xff\x00tail'
        sinks = [self.path(f"stdin{i}") for i in range(3)]
        save = "import sys\nopen(sys.argv[1], 'wb').write(sys.stdin.buffer.read())\n"
        children = tuple(self.raw_child(save) + [sink] for sink in sinks)
        run = self.cli(*self.argv(children, None), stdin=payload)
        self.assertEqual((run.code, run.out), (0, ""), run.err)
        for sink in sinks:
            with open(sink, "rb") as fh:
                self.assertEqual(fh.read(), payload)

    def test_c2_large_payload_reaches_readers_and_an_unread_stdin_is_harmless(
        self,
    ) -> None:
        payload = b'{"hook_event_name":"Stop","pad":"' + b"x" * (1 << 20) + b'"}'
        sink = self.path("size")
        reader = self.raw_child(
            "import sys\nn = len(sys.stdin.buffer.read())\nopen(sys.argv[1], 'w').write(str(n))\n"
        )
        ignorer = self.child({"systemMessage": "done"})
        run = self.cli(*self.argv((reader + [sink], ignorer), None), stdin=payload)
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.obj, {"systemMessage": "done"})
        with open(sink, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), str(len(payload)))

    def test_c2_children_inherit_env_and_the_bundle_adds_none(self) -> None:
        env = {"PATH": os.environ["PATH"], "LC_ALL": "C.UTF-8", "HB_PROBE": "inherited"}
        run = self.bundle(["/usr/bin/env"], event="UserPromptSubmit", env=env)
        listing = run.obj["hookSpecificOutput"]["additionalContext"]
        seen = dict(line.split("=", 1) for line in listing.split("\n"))
        self.assertEqual(seen, env)

    def test_c2_children_inherit_cwd(self) -> None:
        cwd = self.path("work")
        os.mkdir(cwd)
        show = self.raw_child("import os\nprint(os.getcwd())\n")
        run = self.bundle(show, event="UserPromptSubmit", cwd=cwd)
        self.assertEqual(
            run.obj["hookSpecificOutput"]["additionalContext"], os.path.realpath(cwd)
        )

    # --- 3: concurrency ---

    def test_c3_children_run_concurrently(self) -> None:
        slow = [self.child({"systemMessage": f"m{i}"}, delay=1.0) for i in range(2)]
        start = time.monotonic()
        run = self.bundle(*slow)
        elapsed = time.monotonic() - start
        self.assertEqual(run.obj["systemMessage"], "m0\nm1", run.err)
        self.assertLess(elapsed, 1.8)

    # --- 4: timeout and signals ---

    def sleeping_family(self, pidfile: str) -> list[str]:
        """A child that starts a 60 s grandchild and records both pids in `pidfile`."""
        return self.raw_child(
            "import os, subprocess, sys, time\n"
            "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"open({pidfile!r}, 'w').write(f'{{os.getpid()}} {{gc.pid}}')\n"
            "time.sleep(60)\n"
        )

    def family_pids(self, pidfile: str) -> list[int]:
        def read() -> list[str]:
            try:
                with open(pidfile, encoding="utf-8") as fh:
                    return fh.read().split()
            except OSError:
                return []

        self.assertTrue(wait_for(lambda: len(read()) == 2), f"{pidfile} not written")
        return [int(pid) for pid in read()]

    def assertAllDead(self, pids: list[int]) -> None:
        for pid in pids:
            self.assertTrue(
                wait_for(lambda pid=pid: not is_alive(pid)), f"pid {pid} alive"
            )

    def test_c4_timeout_kills_the_child_group_and_reports_it(self) -> None:
        pidfile = self.path("family.pid")
        start = time.monotonic()
        run = self.bundle(
            self.sleeping_family(pidfile),
            self.child({"systemMessage": "ok"}),
            timeout=1,
        )
        elapsed = time.monotonic() - start
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(
            run.obj["systemMessage"], f"ok\nhook-bundle: {PY} failed (timeout 1s)"
        )
        self.assertLess(elapsed, 10)
        self.assertAllDead(self.family_pids(pidfile))

    def test_c4_fractional_timeout_is_reported_as_given(self) -> None:
        run = self.bundle(self.child(delay=30), timeout=0.5)
        self.assertEqual(
            run.obj["systemMessage"], f"hook-bundle: {PY} failed (timeout 0.5s)"
        )

    def test_c4_terminating_signals_kill_every_child_group_and_exit_0(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(sig.name):
                pidfiles = [self.path(f"{sig.name}{i}.pid") for i in range(2)]
                children = tuple(self.sleeping_family(p) for p in pidfiles)
                proc = subprocess.Popen(
                    [sys.executable, CLI, *self.argv(children, None)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.addCleanup(proc.kill)
                pids = [pid for p in pidfiles for pid in self.family_pids(p)]
                proc.send_signal(sig)
                out, _ = proc.communicate(timeout=10)
                self.assertEqual((proc.returncode, out), (0, b""))
                self.assertAllDead(pids)

    # --- 5: exit code and stderr ---

    def test_c5_exit_2_blocks_with_the_childs_stripped_stderr(self) -> None:
        run = self.bundle(self.child(err="  keep going \n", code=2))
        self.assertEqual((run.code, run.out, run.err), (2, "", "keep going"))

    def test_c5_exit_2_stderr_joins_in_child_order(self) -> None:
        run = self.bundle(
            self.child(err="first\n", code=2, delay=0.4),
            self.child(err="ignored: exit 0\n"),
            self.child(err="\n second  ", code=2),
        )
        self.assertEqual((run.code, run.err), (2, "first\nsecond"))

    def test_c5_exit_2_alongside_a_json_child_still_merges_the_json(self) -> None:
        run = self.bundle(
            self.child({"systemMessage": "fyi"}, err="not forwarded"),
            self.child(err="stop it", code=2),
        )
        self.assertEqual((run.code, run.err), (2, "stop it"))
        self.assertEqual(run.obj, {"systemMessage": "fyi"})

    def test_c5_exit_0_and_1_do_not_exit_2(self) -> None:
        run = self.bundle(self.child(code=1, err="x"), self.child(code=0))
        self.assertEqual(run.code, 0)

    # --- 6: stdout merge ---

    def test_c6_system_message_and_terminal_sequence_follow_child_order(self) -> None:
        run = self.bundle(
            self.child({"systemMessage": "one", "terminalSequence": "A"}, delay=0.4),
            self.child({"systemMessage": "", "terminalSequence": "B"}),
            self.child({"systemMessage": "three", "terminalSequence": "C"}),
        )
        self.assertEqual(
            run.obj, {"systemMessage": "one\nthree", "terminalSequence": "ABC"}
        )

    def test_c6_additional_context_joins_with_blank_lines_in_child_order(self) -> None:
        run = self.bundle(
            self.child(hso(additionalContext="first"), delay=0.4),
            self.child(hso(additionalContext="")),
            self.child(hso(additionalContext="second")),
        )
        self.assertEqual(
            run.obj, hso(hookEventName="Stop", additionalContext="first\n\nsecond")
        )

    def test_c6_hook_event_name_comes_from_the_payload(self) -> None:
        children = (
            self.child(hso(hookEventName="FromChild", additionalContext="c")),
            self.child(hso(hookEventName="Later")),
        )
        for label, payload, expect in (
            ("payload string", b'{"hook_event_name":"Stop"}', "Stop"),
            ("payload absent", b"{}", "FromChild"),
            ("payload not a string", b'{"hook_event_name":7}', "FromChild"),
            ("payload not JSON", b"garbage", "FromChild"),
        ):
            with self.subTest(label):
                run = self.cli(*self.argv(children, None), stdin=payload)
                self.assertEqual(run.obj["hookSpecificOutput"]["hookEventName"], expect)

    def test_c6_other_hook_specific_keys_first_child_wins(self) -> None:
        run = self.bundle(
            self.child(hso(permissionDecision="deny")),
            self.child(hso(permissionDecision="allow", updatedInput={"a": 1})),
        )
        self.assertEqual(
            run.obj,
            hso(hookEventName="Stop", permissionDecision="deny", updatedInput={"a": 1}),
        )

    def test_c6_decision_block_joins_the_blocking_reasons_only(self) -> None:
        run = self.bundle(
            self.child({"decision": "block", "reason": "r1"}, delay=0.4),
            self.child({"reason": "noise"}),
            self.child({"decision": "block", "reason": ""}),
            self.child({"decision": "block", "reason": "r2"}),
        )
        self.assertEqual(run.obj, {"decision": "block", "reason": "r1\nr2"})

    def test_c6_continue_false_wins_and_joins_stop_reasons(self) -> None:
        run = self.bundle(
            self.child({"continue": False, "stopReason": "s1"}, delay=0.4),
            self.child({"continue": True, "stopReason": "noise"}),
            self.child({"continue": False, "stopReason": "s2"}),
        )
        self.assertEqual(run.obj, {"continue": False, "stopReason": "s1\ns2"})

    def test_c6_other_top_level_keys_first_child_wins(self) -> None:
        run = self.bundle(
            self.child({"suppressOutput": False}),
            self.child({"suppressOutput": True, "custom": [1]}),
        )
        self.assertEqual(run.obj, {"suppressOutput": False, "custom": [1]})

    def test_c6_plain_stdout_is_context_for_prompt_and_session_start(self) -> None:
        for event in CONTEXT_EVENTS:
            with self.subTest(event):
                run = self.bundle(
                    self.child(out="note one\n", delay=0.3),
                    self.child(hso(additionalContext="json ctx")),
                    self.child(out="\n  note two  \n"),
                    self.child(out="   "),
                    event=event,
                )
                self.assertEqual(
                    run.obj,
                    hso(
                        hookEventName=event,
                        additionalContext="note one\n\njson ctx\n\nnote two",
                    ),
                )

    def test_c6_plain_stdout_is_ignored_for_other_events(self) -> None:
        for event in ("Stop", "PreToolUse", None):
            with self.subTest(event):
                run = self.bundle(self.child(out="just logging\n"), event=event)
                self.assertEqual((run.code, run.out, run.err), (0, "", ""))

    def test_c6_silent_children_emit_nothing(self) -> None:
        run = self.bundle(self.child(), self.child(out="\n"), self.child(obj={}))
        self.assertEqual((run.code, run.out, run.err), (0, "", ""))

    def test_c6_stdout_is_one_unescaped_json_line(self) -> None:
        run = self.bundle(self.child({"systemMessage": "日本語\nline2"}))
        self.assertTrue(run.out.endswith("}\n"))
        self.assertEqual(run.out.count("\n"), 1)
        self.assertIn("日本語", run.out)

    # --- 7: failed children ---

    def test_c7_exit_1_with_a_json_object_is_merged_not_failed(self) -> None:
        run = self.bundle(self.child({"systemMessage": "kept"}, err="oops", code=1))
        self.assertEqual((run.code, run.err), (0, ""))
        self.assertEqual(run.obj, {"systemMessage": "kept"})

    def test_c7_exit_1_without_json_is_failed_and_its_stderr_is_logged(self) -> None:
        run = self.bundle(
            self.child(out="plain text", err="boom\n", code=1), event="UserPromptSubmit"
        )
        self.assertEqual(
            run.obj, {"systemMessage": f"hook-bundle: {PY} failed (exit 1)"}
        )
        self.assertEqual((run.code, run.err), (0, "boom\n"))

    def test_c7_invalid_json_is_failed(self) -> None:
        run = self.bundle(self.child(out='{"systemMessage": '), self.child(out="[1]"))
        self.assertEqual(
            run.obj, {"systemMessage": f"hook-bundle: {PY} failed (invalid JSON)"}
        )

    def test_c7_spawn_error_is_failed(self) -> None:
        run = self.bundle(["/nonexistent/dir/some_hook", "arg"])
        self.assertEqual(run.code, 0)
        self.assertEqual(
            run.obj, {"systemMessage": "hook-bundle: some_hook failed (spawn error)"}
        )

    def test_c7_failure_line_uses_the_basename_and_follows_all_messages(self) -> None:
        tool = self.path("my_hook_tool")
        with open(tool, "w", encoding="utf-8") as fh:
            fh.write(f"#!{sys.executable}\nimport sys\nsys.exit(3)\n")
        os.chmod(tool, 0o755)
        run = self.bundle([tool, "hook"], self.child({"systemMessage": "ok"}))
        self.assertEqual(
            run.obj["systemMessage"], "ok\nhook-bundle: my_hook_tool failed (exit 3)"
        )

    def test_c7_failed_child_stderr_is_dropped_when_the_bundle_exits_2(self) -> None:
        run = self.bundle(
            self.child(err="debug noise", code=1),
            self.child(err="block reason", code=2),
        )
        self.assertEqual((run.code, run.err), (2, "block reason"))
        self.assertIn("failed (exit 1)", run.obj["systemMessage"])

    def test_c7_exit_2_with_invalid_json_still_exits_2_and_is_reported(self) -> None:
        run = self.bundle(self.child(out="{oops", err="stop", code=2))
        self.assertEqual((run.code, run.err), (2, "stop"))
        self.assertIn("failed (invalid JSON)", run.obj["systemMessage"])

    # --- 8: never crashes ---

    def test_c8_unreadable_stdin_fails_open(self) -> None:
        fd = os.open(self.path("write-only"), os.O_WRONLY | os.O_CREAT)
        self.addCleanup(os.close, fd)
        proc = subprocess.run(
            [sys.executable, CLI, sys.executable, "-c", "pass"],
            stdin=fd,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual((proc.returncode, proc.stdout), (0, b""))
        self.assertIn(b"hook-bundle: internal error", proc.stderr)

    def test_c8_unwritable_stdout_fails_open(self) -> None:
        try:
            full = open("/dev/full", "wb")  # every write fails with ENOSPC
        except OSError as exc:
            self.skipTest(f"/dev/full unavailable: {exc}")
        self.addCleanup(full.close)
        proc = subprocess.run(
            [sys.executable, CLI, *self.child({"systemMessage": "x"})],
            input=b"{}",
            stdout=full,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(b"hook-bundle: internal error", proc.stderr)

    # --- 9: determinism ---

    def test_c9_same_inputs_give_identical_stdout_bytes(self) -> None:
        jitter = "import random\ntime.sleep(random.random() * 0.4)"
        outputs = (
            {"systemMessage": "a", "terminalSequence": "1", "extra": 1},
            {**hso(additionalContext="b"), "systemMessage": "b"},
            {"decision": "block", "reason": "c", "extra": 2},
        )
        children = tuple(self.child(obj, pre=jitter) for obj in outputs)
        runs = {self.bundle(*children).out for _ in range(4)}
        self.assertEqual(len(runs), 1, runs)
        self.assertEqual(
            json.loads(runs.pop()),
            {
                "systemMessage": "a\nb",
                "terminalSequence": "1",
                "decision": "block",
                "reason": "c",
                **hso(hookEventName="Stop", additionalContext="b"),
                "extra": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
