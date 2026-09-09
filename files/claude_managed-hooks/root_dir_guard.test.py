#!/usr/bin/env python3
"""Acceptance tests for root_dir_guard.py, written before the implementation.

Contract (each claim maps to one test):
  C1  host-run detection mirrors Claude Code's excludedCommands match: a top-level statement (split on
      `&&` / `||` / `;` / `|` / `&` / newline, redirections ignored) matches a pattern once its leading
      assignments and wrappers (timeout N / time / nice / stdbuf / nohup / command / builtin / noglob)
      are stripped and a quoted head is unquoted; compound statements (if / while / for / case /
      subshell / brace group / `!`), command substitution, quoted text, comment lines, path-prefixed and
      `sudo` / `env` forms, and a `PATH=` / `LD_*` / `DYLD_*` assignment prefix do not match; over 10000
      chars only the leading form counts
  C2  PreToolUse(Bash): a host-run command that expands $TMPDIR / ${TMPDIR} / $TMP / $TEMP / $TEMPDIR in
      any form (default-valued expansion and a preceding assignment included) is denied — exit 2, stderr
      names the excluded command, the variable and `$CLAUDE_TMPDIR`
  C3  a single-quoted mention, a quoted-delimiter heredoc body, $CLAUDE_TMPDIR while it is set, and a
      command without any reference are allowed; while CLAUDE_TMPDIR is unset in the hook's environment a
      $CLAUDE_TMPDIR reference is denied and an absolute path is recommended instead
  C4  a sandbox-run command referencing $TMPDIR is allowed
  C5  `dangerouslyDisableSandbox: true` counts as host-run; when the sandbox does not restrict commands
      every command is host-run, but the deny applies only while TMPDIR is empty in the hook's environment
  C6  PreToolUse(Bash) snapshots the root directory listing per tool_use_id (session_id fallback) for every
      allowed call and purges snapshots older than one hour
  C7  PostToolUse / PostToolUseFailure (Bash): entries in the root directory absent from the snapshot are
      reported (exit 0, JSON with decision block + reason + systemMessage naming each entry) and left in
      place; nothing is created outside the state dir; the snapshot is removed
  C8  PostToolUse with nothing new, or with no snapshot, exits 0 silently (snapshot removed if present)
  C9  fail-open: non-Bash tool, non-dict payload, unwritable state dir → exit 0 silent
  C10 the hook file is executable and works end to end through stdin / exit code
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HOOK_DIR, "root_dir_guard.py")
sys.path.insert(0, HOOK_DIR)
import root_dir_guard as guard  # noqa: E402

PATTERNS = [
    "git *",
    "gh *",
    "cargo test *",
    "node *codex-companion.mjs*",
    "codex_broker_reap*",
    "claude --bg *",
]
HOST = (
    "git push",
    "git",
    "cd x && git push",
    "FOO=1 git push",
    "FOO=1 BAR=2 gh pr view",
    "timeout 5 git push",
    "timeout -k 3 5s git push",
    "time git push",
    "nice -n 10 git push",
    "nohup git push",
    "stdbuf -oL git log",
    "command git push",
    "FOO=1 timeout 5 git push",
    "git log | head",
    "x=1; git push",
    "echo a\ngit push",
    "git log > out.txt",
    "cat msg | git commit -F -",
    "if true; then :; fi && git push",
    "case x in a) echo a;; esac; git push",
    "cargo test foo",
    "node ./codex-companion.mjs run",
    "codex_broker_reap --all",
    "claude --bg -p x",
    "echo hi; gh pr view; echo done",
    "git push &",
    "git push || echo fail",
    "git commit -F $TMPDIR/msg",
    '"git" push',
)
SANDBOX = (
    "",
    "if git diff --quiet; then echo clean; fi",
    "while git fetch; do sleep 1; done",
    "for f in a b; do git add $f; done",
    "case x in a) git push;; esac",
    "(git push)",
    "{ git push; }",
    "! git diff --quiet",
    "VERSION=$(git describe)",
    "echo $(git rev-parse HEAD)",
    "echo `git status`",
    "/usr/bin/git push",
    "sudo git push",
    "env git push",
    "npx gh pr view",
    'echo "git push"',
    "echo 'git push'",
    "# git push",
    "PATH=/x git push",
    "LD_PRELOAD=x git push",
    "ghost run",
    "gitk",
    "git-lfs pull",
    "cargo build",
    "node app.js",
    "which git",
    "echo done",
    "cat <<EOF\ngit push\nEOF",
)
DENY = (
    "cat > $TMPDIR/body.md <<'EOF'\nhi\nEOF\ngh issue create --body-file $TMPDIR/body.md",
    'cp x "$TMPDIR/x.bak" && git commit -F "${TMPDIR}/msg"',
    "git commit -F $TMP/msg",
    "git commit -F $TEMP/msg",
    "git commit -F $TEMPDIR/msg",
    'git commit -m "use $TMPDIR"',
    "git commit -F ${TMPDIR:-/tmp}/msg",
    "git commit -F ${TMPDIR-/tmp}/msg",
    "git commit -F ${TMPDIR:=/tmp}/msg",
    "git commit -F ${TMPDIR:?}/msg",
    "TMPDIR=$CLAUDE_TMPDIR git commit -F $TMPDIR/msg",
    "export TMPDIR=/var/tmp; git commit -F $TMPDIR/msg",
    "git commit -F - <<EOF\nuse $TMPDIR\nEOF",
)
ALLOW = (
    "git commit -m 'use $TMPDIR'",
    "git commit -F - <<'EOF'\nuse $TMPDIR\nEOF",
    "git commit -F $CLAUDE_TMPDIR/msg",
    "git status",
    "git commit -m TMPDIR",
    "git commit -F $TMPDIRX/msg",
)


def pre(cmd: str, **extra) -> dict:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
        "tool_use_id": "toolu_1",
    }
    payload.update(extra)
    return payload


def post(event: str = "PostToolUse", **extra) -> dict:
    payload = {
        "hook_event_name": event,
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "tool_response": {"stdout": ""},
        "tool_use_id": "toolu_1",
    }
    payload.update(extra)
    return payload


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "root")
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(os.path.join(self.root, "etc"))
        with open(os.path.join(self.root, "init"), "w") as f:
            f.write("x")
        for name, value in (("ROOT_DIR", self.root), ("STATE_DIR", self.state)):
            patch = mock.patch.object(guard, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        env = mock.patch.dict(os.environ, {"CLAUDE_TMPDIR": "/tmp/claude-1000"})
        env.start()
        self.addCleanup(env.stop)

    @staticmethod
    def run_hook(payload, restricted=True, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False):
            with redirect_stdout(out), redirect_stderr(err):
                rc = guard._run(payload, PATTERNS, restricted)
        return rc, out.getvalue(), err.getvalue()

    def snapshot(self, key="toolu_1"):
        return os.path.join(self.state, f"snap-{key}.json")

    def test_c1_host_run_mirrors_claude_code_matching(self):
        for cmd in HOST:
            self.assertTrue(guard.host_run(cmd, PATTERNS), cmd)
        for cmd in SANDBOX:
            self.assertEqual(guard.host_run(cmd, PATTERNS), "", cmd)
        filler = "echo x; " * 1300
        self.assertEqual(guard.host_run(filler + "git push", PATTERNS), "")
        self.assertTrue(guard.host_run("git push; " + filler, PATTERNS))

    def test_c2_denies_every_host_run_tmpdir_expansion(self):
        for cmd in DENY:
            rc, out, err = self.run_hook(pre(cmd))
            self.assertEqual((rc, out), (2, ""), cmd)
            self.assertIn("$CLAUDE_TMPDIR", err, cmd)
            self.assertIn("host", err, cmd)
            self.assertIn("例外はありません", err, cmd)
        rc, _, err = self.run_hook(pre(DENY[0]))
        self.assertIn("gh issue create", err)
        self.assertIn("$TMPDIR", err)
        self.assertFalse(os.path.exists(self.snapshot()))

    def test_c3_allows_non_expanding_forms_and_guards_an_unset_claude_tmpdir(self):
        for cmd in ALLOW:
            self.assertEqual(self.run_hook(pre(cmd)), (0, "", ""), cmd)
        unset = {"CLAUDE_TMPDIR": ""}
        rc, out, err = self.run_hook(pre("git commit -F $CLAUDE_TMPDIR/msg"), env=unset)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("設定されていない", err)
        self.assertIn("絶対 path", err)
        self.assertNotIn("`$CLAUDE_TMPDIR` (host", err)

    def test_c4_allows_sandbox_run_reference(self):
        self.assertEqual(self.run_hook(pre("cp x $TMPDIR/x.bak")), (0, "", ""))
        self.assertEqual(
            self.run_hook(pre("for f in a; do git add $f; done; cp x $TMPDIR/y")),
            (0, "", ""),
        )

    def test_c5_disabled_sandbox_paths(self):
        payload = pre("cp x $TMPDIR/x.bak")
        payload["tool_input"]["dangerouslyDisableSandbox"] = True
        self.assertEqual(self.run_hook(payload)[0], 2)
        empty = {"TMPDIR": ""}
        rc, _, err = self.run_hook(
            pre("cp x $TMPDIR/x.bak"), restricted=False, env=empty
        )
        self.assertEqual(rc, 2)
        self.assertIn("$CLAUDE_TMPDIR", err)
        result = self.run_hook(
            pre("cp x $TMPDIR/x.bak"), restricted=False, env={"TMPDIR": "/tmp/x"}
        )
        self.assertEqual(result, (0, "", ""))

    def test_c6_snapshots_every_allowed_call_and_purges_stale_ones(self):
        os.makedirs(self.state)
        stale = self.snapshot("old")
        with open(stale, "w") as f:
            f.write("[]")
        old = time.time() - 2 * 3600
        os.utime(stale, (old, old))
        self.assertEqual(self.run_hook(pre("cp x $TMPDIR/x.bak")), (0, "", ""))
        with open(self.snapshot()) as f:
            self.assertEqual(sorted(json.load(f)), ["etc", "init"])
        self.assertFalse(os.path.exists(stale))
        payload = pre("git status", session_id="sess")
        del payload["tool_use_id"]
        self.assertEqual(self.run_hook(payload), (0, "", ""))
        self.assertTrue(os.path.exists(self.snapshot("sess")))

    def _litter(self):
        with open(os.path.join(self.root, "AG.bak"), "w") as f:
            f.write("backup")
        os.makedirs(os.path.join(self.root, "relocate"))

    def _tree(self, top):
        return sorted(
            os.path.relpath(os.path.join(d, n), top)
            for d, dirs, files in os.walk(top)
            for n in dirs + files
        )

    def test_c7_reports_new_root_entries_without_touching_them(self):
        for event in ("PostToolUse", "PostToolUseFailure"):
            with self.subTest(event=event):
                self.assertEqual(self.run_hook(pre("git status")), (0, "", ""))
                self._litter()
                before = self._tree(self.tmp.name)
                rc, out, err = self.run_hook(post(event))
                self.assertEqual((rc, err), (0, ""))
                report = json.loads(out)
                self.assertEqual(report["decision"], "block")
                for name in ("AG.bak", "relocate"):
                    path = os.path.join(self.root, name)
                    self.assertIn(path, report["reason"])
                    self.assertIn(path, report["systemMessage"])
                    self.assertTrue(os.path.exists(path))
                self.assertIn("ユーザーへ報告", report["reason"])
                self.assertIn("$CLAUDE_TMPDIR", report["reason"])
                self.assertIn("移動も削除もしていません", report["reason"])
                after = self._tree(self.tmp.name)
                self.assertEqual(
                    sorted(set(before) - set(after)), ["state/snap-toolu_1.json"]
                )
                self.assertEqual(set(after) - set(before), set())
                for name in ("AG.bak", "relocate"):
                    path = os.path.join(self.root, name)
                    (os.rmdir if os.path.isdir(path) else os.remove)(path)

    def test_c8_silent_when_nothing_new_or_no_snapshot(self):
        self.assertEqual(self.run_hook(post()), (0, "", ""))
        self.assertEqual(self.run_hook(pre("git status")), (0, "", ""))
        self.assertEqual(self.run_hook(post()), (0, "", ""))
        self.assertFalse(os.path.exists(self.snapshot()))

    def test_c9_fails_open(self):
        for payload in (
            "x",
            3,
            None,
            {"tool_name": "Read", "hook_event_name": "PreToolUse"},
        ):
            self.assertEqual(self.run_hook(payload), (0, "", ""), payload)
        read = post()
        read["tool_name"] = "Read"
        self._litter()
        self.assertEqual(self.run_hook(read), (0, "", ""))
        with mock.patch.object(guard, "STATE_DIR", os.path.join(self.root, "init")):
            self.assertEqual(self.run_hook(pre("git status")), (0, "", ""))
            self.assertEqual(self.run_hook(pre(DENY[0]))[0], 2)

    def test_c10_executable_end_to_end(self):
        self.assertTrue(os.access(HOOK, os.X_OK))
        project = os.path.join(self.tmp.name, "project", ".claude")
        os.makedirs(project)
        with open(os.path.join(project, "settings.json"), "w") as f:
            json.dump({"sandbox": {"enabled": True, "excludedCommands": ["git *"]}}, f)
        env = {
            **os.environ,
            "CLAUDE_PROJECT_DIR": os.path.dirname(project),
            "ROOT_DIR_GUARD_ROOT": self.root,
            "ROOT_DIR_GUARD_STATE_DIR": self.state,
        }

        def call(payload):
            return subprocess.run(
                [HOOK],
                input=json.dumps(payload),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        denied = call(pre("git commit -F $TMPDIR/msg"))
        self.assertEqual(denied.returncode, 2, denied.stderr)
        self.assertIn("$CLAUDE_TMPDIR", denied.stderr)
        allowed = call(pre("git status"))
        self.assertEqual(
            (allowed.returncode, allowed.stdout, allowed.stderr), (0, "", "")
        )
        self.assertTrue(os.path.exists(self.snapshot()))
        self._litter()
        found = call(post())
        self.assertEqual((found.returncode, found.stderr), (0, ""), found.stderr)
        self.assertIn(
            os.path.join(self.root, "AG.bak"), json.loads(found.stdout)["systemMessage"]
        )
        self.assertTrue(os.path.exists(os.path.join(self.root, "AG.bak")))


if __name__ == "__main__":
    unittest.main()
