#!/usr/bin/env python3
"""Acceptance tests for deny_command_patterns.py, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  the hook is a PreToolUse(Bash) gate: payload JSON on stdin, exit 0 = allow, exit 2 = deny with the
      reason on stderr starting with "command-pattern:" and naming the rule
  C2  kill-by-port: `fuser -k`, `pkill` or `killall` as a command word is denied
  C3  unbounded loop: a loop head `while true` / `while :` / `while [ 1 ]` / `until false` / `for ((;;))`
      is denied unless the command also contains the word `timeout`
  C4  autosquash: `git rebase ... --autosquash` is denied unless `-i` / `--interactive` or
      `GIT_SEQUENCE_EDITOR` is present
  C5  voicevox: `voicevox_paplay` without `--loopback` is denied
  C6  roster: the sandbox excludedCommands roster is read from `<dir>/managed-settings.json` and
      `<dir>/managed-settings.d/*.json` (dir = $CLAUDE_MANAGED_SETTINGS_DIR or /etc/claude-code); a head is
      the first word of a `<word> *` glob. A head invoked with a path prefix, via `$(which head)` /
      `$(command -v head)`, after an assignment prefix (`VAR=x head`), or as a command word anywhere but
      the start of the command (after `;`, `&&`, `||`, `|`, `(`, newline, `do`/`then`/`else`, `timeout N`,
      `env`, `sudo`, `exec`, `nohup`) is denied — except heads in START_EXEMPT = {"git"}, which only the
      path-prefix and $(which) forms deny
  C7  text inside quoted strings and heredoc bodies is ignored by every rule
  C8  fail-open: non-Bash tool, unreadable payload, or unreadable settings → exit 0 (the roster rule is
      skipped; the other rules still apply)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "deny_command_patterns.py"
)
ROSTER = [
    "git *",
    "gh *",
    "claude_memory_sync *",
    "codex *",
    "node *codex-companion.mjs*",
]
DROPIN = ["dsa_launcher *", "cargo test *"]


def run_hook(
    command: str, settings: str | None, payload: str | None = None, tool: str = "Bash"
) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_MANAGED_SETTINGS_DIR"}
    if settings is not None:
        env["CLAUDE_MANAGED_SETTINGS_DIR"] = settings
    body = (
        payload
        if payload is not None
        else json.dumps(
            {"tool_name": tool, "tool_input": {"command": command}, "cwd": "/tmp"}
        )
    )
    return subprocess.run(
        [sys.executable, HOOK],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
    )


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = self.tmp.name
        os.makedirs(os.path.join(self.settings, "managed-settings.d"))
        with open(os.path.join(self.settings, "managed-settings.json"), "w") as fh:
            json.dump({"sandbox": {"excludedCommands": ROSTER}}, fh)
        with open(
            os.path.join(self.settings, "managed-settings.d", "p.json"), "w"
        ) as fh:
            json.dump({"sandbox": {"excludedCommands": DROPIN}}, fh)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def deny(self, command: str, rule: str) -> None:
        out = run_hook(command, self.settings)
        self.assertEqual(out.returncode, 2, f"{command!r}: {out.stderr}")
        self.assertTrue(out.stderr.startswith("command-pattern:"), out.stderr)
        self.assertIn(rule, out.stderr)

    def allow(self, command: str) -> None:
        out = run_hook(command, self.settings)
        self.assertEqual(out.returncode, 0, f"{command!r}: {out.stderr}")

    def test_c1_c2_kill_by_port(self) -> None:
        self.deny("fuser -k 5273/tcp", "kill")
        self.deny("pkill -f vite", "kill")
        self.deny("cd /x && killall node", "kill")
        self.allow("fuser 5273/tcp")
        self.allow("kill 1234")

    def test_c3_unbounded_loop_needs_timeout(self) -> None:
        self.deny("while true; do sleep 5; done", "loop")
        self.deny("while :; do curl -s localhost; done", "loop")
        self.deny("until false; do ls; done", "loop")
        self.deny("for ((;;)); do sleep 1; done", "loop")
        self.allow("timeout 300 bash -c 'while true; do sleep 5; done'")
        self.allow("while true; do timeout 5 curl -s localhost && break; done")
        self.allow("for i in $(seq 1 30); do sleep 1; done")
        self.allow("until [ -f done.txt ]; do sleep 1; done")

    def test_c4_autosquash_needs_interactive(self) -> None:
        self.deny("git rebase --autosquash main", "autosquash")
        self.deny("git -C /r rebase --autosquash HEAD~5", "autosquash")
        self.allow("GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash main")
        self.allow("git rebase --interactive --autosquash main")
        self.allow("git rebase main")

    def test_c5_voicevox_needs_loopback(self) -> None:
        self.deny("voicevox_paplay 'done'", "loopback")
        self.deny("echo x | voicevox_paplay", "loopback")
        self.allow("voicevox_paplay --loopback 'done'")

    def test_c6_roster_forms(self) -> None:
        for command in (
            "/usr/bin/codex exec x",
            "./dsa_launcher vite status",
            "$(which codex) exec x",
            "$(command -v claude_memory_sync) --status",
            "X=1 codex exec x",
            "cd /r && codex exec x",
            "ls; claude_memory_sync --status",
            "echo a || dsa_launcher db restart",
            "cat x | gh pr view",
            "(cd /r && codex exec x)",
            "for d in a b; do codex exec $d; done",
            "timeout 30 codex exec x",
            "env FOO=1 codex exec x",
            "nohup codex exec x",
            "ls\ncodex exec x",
        ):
            self.deny(command, "sandbox")
        for command in (
            "codex exec x && echo done",
            "claude_memory_sync --reach 2>&1 | head",
            "dsa_launcher vite status",
            "gh pr view 12",
            "git -C /r status",
            "W=/r; git -C $W log -1",
            "cd /r && git status",
            "echo codex",
            "grep -n codex file.txt",
            "python3 files/codex_task_sentinel job-1",
            "node /x/other.mjs",
        ):
            self.allow(command)

    def test_c6_git_path_forms_still_denied(self) -> None:
        self.deny("/usr/bin/git status", "sandbox")
        self.deny("$(which git) status", "sandbox")

    def test_c7_quotes_and_heredocs_are_ignored(self) -> None:
        self.allow('git commit -m "retire the pkill entry" -- todos.md')
        self.allow("git commit -m 'codex exec is denied' -- a.md")
        self.allow("cat > x.md <<'EOF'\npkill and codex exec and while true\nEOF")
        self.allow("python3 - <<'EOF'\nprint('fuser -k')\nEOF\nls")
        self.deny("echo 'x' && pkill vite", "kill")

    def test_c8_fail_open(self) -> None:
        self.assertEqual(run_hook("pkill x", self.settings, tool="Write").returncode, 0)
        self.assertEqual(
            run_hook("pkill x", self.settings, payload="{not json").returncode, 0
        )
        self.assertEqual(run_hook("pkill x", self.settings, payload="[]").returncode, 0)
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(run_hook("cd /r && codex exec x", empty).returncode, 0)
            self.assertEqual(run_hook("pkill x", empty).returncode, 2)


if __name__ == "__main__":
    unittest.main()
