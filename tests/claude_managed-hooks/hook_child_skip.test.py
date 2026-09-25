#!/usr/bin/env python3
"""Black-box tests: a one-off session spawned by a hook (CLAUDE_HOOK_CHILD=1) skips session hooks.

Contract (each claim maps to one test):
  K1  no hook command in the managed settings carries a shell-side CLAUDE_HOOK_CHILD guard; the
      skip lives in the scripts
  K2  every session-level hook (SessionStart / UserPromptSubmit / Stop / SubagentStop / SessionEnd /
      MessageDisplay) in a child exits 0 without output and writes no file; a script wired only on
      session-level events returns before it even reads its hook input
  K3  a script also wired on a tool event still runs that tool gate in the child (the skip is limited
      to session-level events)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "files")
SETTINGS = os.path.join(ROOT, "claude_managed-extensions.json")
HOOKS = os.path.join(ROOT, "claude_managed-hooks")
COURT = os.path.join(ROOT, "claude_court_guard")

# (event, script, reads_input): reads_input marks scripts that must read the event name first
SESSION_HOOKS = (
    ("SubagentStop", os.path.join(HOOKS, "codex_delegation_surface.py"), True),
    ("SessionStart", os.path.join(HOOKS, "sandbox_exclusion_guard.py"), True),
    ("SessionStart", os.path.join(HOOKS, "claude_md_lint.py"), False),
    ("SessionStart", os.path.join(HOOKS, "feature_findings_build.py"), False),
    ("SessionStart", os.path.join(HOOKS, "session_resume_context.py"), False),
    ("SessionStart", os.path.join(HOOKS, "reap_orphan_helpers.py"), False),
    ("SessionStart", os.path.join(HOOKS, "codex_broker_sweep.py"), True),
    ("SessionStart", os.path.join(HOOKS, "memory_sync_pull.py"), False),
    ("UserPromptSubmit", os.path.join(HOOKS, "check_uncommitted_at_handoff.py"), False),
    ("UserPromptSubmit", os.path.join(HOOKS, "codex_delegation_surface.py"), True),
    (
        "UserPromptSubmit",
        os.path.join(ROOT, "shared_hooks", "plan_first_nudge.py"),
        False,
    ),
    ("UserPromptSubmit", os.path.join(HOOKS, "primary_source_nudge.py"), False),
    ("MessageDisplay", COURT, False),
    ("Stop", os.path.join(HOOKS, "stop_checks.py"), False),
    ("Stop", os.path.join(HOOKS, "question_research_gate.py"), True),
    ("Stop", os.path.join(HOOKS, "sandbox_shadow_nudge.py"), True),
    ("Stop", os.path.join(ROOT, "scratch_file_management.py"), True),
    ("Stop", COURT, False),
    ("SessionEnd", os.path.join(HOOKS, "session_cleanup.py"), False),
    ("SessionEnd", os.path.join(HOOKS, "reap_orphan_helpers.py"), False),
)

# loaded through PYTHONPATH: leaves a marker file when the hook reads its stdin
STDIN_PROBE = """\
import os, sys
_marker = os.environ.get("HOOK_CHILD_STDIN_MARKER")
if _marker:
    class _Probe:
        def __init__(self, inner):
            self._inner = inner
        def _hit(self):
            open(_marker, "w").close()
        def read(self, *a):
            self._hit()
            return self._inner.read(*a)
        def readline(self, *a):
            self._hit()
            return self._inner.readline(*a)
        def __iter__(self):
            self._hit()
            return iter(self._inner)
        def __getattr__(self, name):
            return getattr(self._inner, name)
    sys.stdin = _Probe(sys.stdin)
"""


def run_hook(script: str, payload: dict, env: dict) -> subprocess.CompletedProcess:
    argv = [sys.executable, script] + (["--hook"] if script == COURT else [])
    return subprocess.run(
        argv,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
        timeout=60,
    )


def _files(root: str) -> set[str]:
    return {
        os.path.relpath(os.path.join(d, f), root)
        for d, _, names in os.walk(root)
        for f in names
    }


class HookChildSkipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = os.path.join(self.tmp.name, "work")  # HOME, caches and ledgers
        probe_dir = os.path.join(self.tmp.name, "probe")
        os.makedirs(self.work)
        os.makedirs(probe_dir)
        with open(
            os.path.join(probe_dir, "sitecustomize.py"), "w", encoding="utf-8"
        ) as f:
            f.write(STDIN_PROBE)
        transcript = os.path.join(self.tmp.name, "t.jsonl")
        with open(transcript, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
        self.marker = os.path.join(self.tmp.name, "stdin-read")
        # each field makes some hook act when it is not skipped
        self.base = {
            "session_id": "hook-child-test",
            "transcript_path": transcript,
            "cwd": self.work,
            "source": "startup",
            "prompt": "handoff お疲れさま",
            "agent_type": "codex:codex-rescue",
            "last_assistant_message": ".git/config.lock がロック中です。どちらにしますか?",
        }
        self.env = {
            "HOME": self.work,
            "XDG_CACHE_HOME": os.path.join(self.work, "cache"),
            "CODEX_BROKER_SWEEP_LEDGER": os.path.join(
                self.work, "codex", "ledger.json"
            ),
            "PYTHONPATH": probe_dir,
            "HOOK_CHILD_STDIN_MARKER": self.marker,
            "CLAUDE_HOOK_CHILD": "1",
        }

    def test_k1_settings_carry_no_shell_guard(self):
        with open(SETTINGS, encoding="utf-8") as f:
            self.assertNotIn("CLAUDE_HOOK_CHILD", f.read())

    def test_k2_session_hooks_do_nothing_in_a_hook_child(self):
        for event, script, reads_input in SESSION_HOOKS:
            with self.subTest(event=event, script=os.path.basename(script)):
                shutil.rmtree(self.work)
                os.makedirs(self.work)
                if os.path.exists(self.marker):
                    os.remove(self.marker)
                proc = run_hook(
                    script, {**self.base, "hook_event_name": event}, self.env
                )
                self.assertEqual(
                    (proc.returncode, proc.stdout, proc.stderr), (0, "", "")
                )
                self.assertEqual(_files(self.work), set())
                if not reads_input:
                    self.assertFalse(os.path.exists(self.marker))

    def test_k3_tool_gate_still_runs_in_a_hook_child(self):
        payload = {
            **self.base,
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "/usr/bin/git push"},
        }
        script = os.path.join(HOOKS, "sandbox_exclusion_guard.py")
        proc = run_hook(script, payload, self.env)
        self.assertNotEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
