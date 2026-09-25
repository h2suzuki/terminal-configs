#!/usr/bin/env python3
"""Black-box tests for sandbox_shadow_nudge.py: stdin payload in, exit code / stdout JSON out.

Contract (each claim maps to one test):
  S1  an assistant text block with a shadow name (unprefixed) AND a cue word -> additionalContext
      fires, names the hook, and includes the lessons-learned path
  S2  a block with a shadow name but no cue word -> silent
  S3  a shadow name prefixed by `~/` or an absolute `/home/<user>/` path -> silent even with a cue
      word (that names a real HOME file, not the repo-root shadow)
  S4  a block with a cue word but no shadow name -> silent
  A1  a hit block separated from the tail only by a tool_result-only user entry still fires (the
      transcript is often not yet updated with fresh assistant text at PreToolUse time, so a
      tool_result-only entry must not be treated as a scan boundary)
  A2  a hit block that sits before a REAL user prompt (a fresh human turn) does not fire; the scan
      stops there
  A3  a block already nudged in this session stays silent on a later call with the same text; a
      distinct new block in the same session fires again
  B1  tool_name=="Bash" whose tool_input.command contains a shadow name (no cue word needed) fires;
      a second Bash-hit command in the same session is silent (dedupe is one marker per session)
  B2  `cat ~/.bashrc` (home-prefixed) does not fire from the command scan
  B3  tool_name=="Read" targeting `.claude/settings.json` never triggers the command scan (only Bash
      tool_input is scanned)
  C1  when both the transcript scan and the command scan hit in the same call, MSG is emitted once
      (a single JSON line), not twice
  S7  missing transcript file -> exit 0, empty stdout (fail-open)
  S8  malformed stdin / non-object JSON -> exit 0, empty stdout (fail-open)
  S9  the tail read tolerates a transcript far larger than the read window without crashing and still
      finds the trailing block (partial first line is dropped, not parsed as JSON)
  S10 the hook file is executable
  L1  `config.lock` with lock-holder framing ("ロックされている", "stale lock") -> config-lock fires
      with the lessons-learned path
  L2  `config.lock` text that already names the sandbox mask -> silent
  L3  lock-holder framing without `config.lock`, or an English cue only inside another word
      ("blocked") -> silent
  P1  a sandboxed tool call that looks at a covered file or the sandbox itself (Bash naming
      config.lock in any form, /proc/self/mountinfo; Read of a credential path) gets masked-probe
      and still runs
  P2  a second such look in the same turn, by another method, is denied
  P3  a new real prompt starts a new turn: the next look is nudged again, not denied
  P4  a Bash call taken out of the sandbox by an excluded command, one that names no covered file,
      or one that only mentions it as text (a grep pattern, a heredoc body) is silent
  X1  --codex PreToolUse: a sandboxed look at a covered file (Codex `cmd` or `command`) gets
      masked-probe as context and is never denied; a combined call is sandboxed even when it
      starts with an excluded command, and only a standalone excluded call is host-bound
  X2  --codex PostToolUse: git's `could not lock config file` gets config-lock context once per
      session; other output is silent
  X3  --codex Stop: a config.lock lock-holder final message gets {"decision": "block"} once;
      stop_hook_active and correct readings are silent
  T1  Stop with a config.lock lock-holder final message -> exit 2, stderr carries the rule and the
      restate instruction; the same message on the next Stop ends the turn (exit 0)
  T2  Stop with only a shadow hit -> exit 0 (the shadow rule nudges at PreToolUse only)
  T3  Stop reads last_assistant_message when the transcript lacks the final text
  T4  Stop is silent when CLAUDE_HOOK_CHILD is set (a hook-spawned one-off session)
  C2  one text hitting two rules -> a single JSON line naming both
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
    "..",
    "files",
    "claude_managed-hooks",
    "sandbox_shadow_nudge.py",
)
LESSON_PATH = (
    "/var/lib/claude-rag-memory/claude-lessons-learned/org/"
    "feedback_sandbox_dotfile_shadow.md"
)


def _assistant_text(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _assistant_tool_use(name: str = "Bash", tool_input: dict | None = None) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": name, "input": tool_input or {}}]
        },
    }


def _user_prompt(text: str = "do it") -> dict:
    return {"type": "user", "message": {"content": text}}


def _user_tool_result() -> dict:
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "ok"}]},
    }


def _write_transcript(
    tmp_dir: str, entries: list[dict], name: str = "transcript.jsonl"
) -> str:
    path = os.path.join(tmp_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


def run_hook(
    payload: object, env: dict, args: tuple[str, ...] = ()
) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, HOOK, *args],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        env=full_env,
    )


class SandboxShadowNudgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_dir = os.path.join(self.tmp.name, "state")
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        sandbox = {
            "excludedCommands": ["git *"],
            "credentials": {"files": [{"path": "~/.ssh", "mode": "deny"}]},
        }
        with open(
            os.path.join(self.home, ".claude", "settings.json"), "w", encoding="utf-8"
        ) as f:
            json.dump({"sandbox": sandbox}, f)

    def _env(self) -> dict:
        return {
            "SANDBOX_SHADOW_NUDGE_STATE_DIR": self.state_dir,
            "HOME": self.home,
            "CLAUDE_PROJECT_DIR": "",
        }

    def _look(
        self, entries: list[dict], tool: str, tool_input: dict, session_id: str = "p"
    ) -> dict:
        proc = self._call(entries, session_id, tool, tool_input)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["hookSpecificOutput"] if proc.stdout else {}

    def _stop(
        self, entries: list[dict], session_id: str = "stop", final: str | None = None
    ) -> subprocess.CompletedProcess:
        payload = {
            "hook_event_name": "Stop",
            "session_id": session_id,
            "transcript_path": _write_transcript(self.tmp.name, entries),
        }
        if final is not None:
            payload["last_assistant_message"] = final
        return run_hook(payload, self._env())

    def _context(self, proc: subprocess.CompletedProcess) -> str:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]

    def _call(
        self,
        entries: list[dict],
        session_id: str = "sess1",
        tool_name: str = "Bash",
        tool_input: dict | None = None,
    ) -> subprocess.CompletedProcess:
        transcript = _write_transcript(self.tmp.name, entries)
        payload = {
            "session_id": session_id,
            "transcript_path": transcript,
            "tool_name": tool_name,
            "tool_input": tool_input if tool_input is not None else {"command": "ls"},
        }
        return run_hook(payload, self._env())

    def test_s1_fires_on_name_and_cue(self):
        proc = self._call(
            [_user_prompt(), _assistant_text("repo 直下に .bashrc が未追跡で出ている")]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("sandbox-shadow", out["additionalContext"])
        self.assertIn(LESSON_PATH, out["additionalContext"])

    def test_s2_silent_without_cue_word(self):
        proc = self._call(
            [
                _user_prompt(),
                _assistant_text("edit .claude/settings.json to add a hook"),
            ]
        )
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_s3_silent_for_real_home_paths(self):
        for i, mention in enumerate(("~/.bashrc", "/home/scorer/.bashrc")):
            with self.subTest(mention=mention):
                proc = self._call(
                    [
                        _user_prompt(),
                        _assistant_text(f"{mention} が untracked と出ている"),
                    ],
                    session_id=f"s3-{i}",
                )
                self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_s4_silent_without_shadow_name(self):
        proc = self._call(
            [_user_prompt(), _assistant_text("これは未追跡ファイルの話です")]
        )
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_a1_hit_block_behind_a_tool_result_still_fires(self):
        proc = self._call(
            [
                _user_prompt(),
                _assistant_text(".bashrc が未追跡です"),  # hit, but not the tail
                _user_tool_result(),  # must not be treated as a scan boundary
                _assistant_tool_use(),  # this call's own trigger, carries no text
            ]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertIn("sandbox-shadow", out["additionalContext"])

    def test_a2_hit_block_behind_a_real_prompt_does_not_fire(self):
        proc = self._call(
            [
                _assistant_text(".bashrc が未追跡です"),  # older turn, hit
                _user_prompt("次はこれをやって"),  # a real prompt: scan stops here
                _assistant_tool_use(),
            ]
        )
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_a3_dedup_per_block_then_new_block_refires(self):
        entries = [_user_prompt(), _assistant_text(".bashrc が未追跡です")]
        first = self._call(entries, session_id="dedup")
        self.assertNotEqual(first.stdout.strip(), "")
        second = self._call(entries, session_id="dedup")
        self.assertEqual((second.returncode, second.stdout), (0, ""), second.stderr)
        different = [_user_prompt(), _assistant_text(".zshrc が未追跡です")]
        third = self._call(different, session_id="dedup")
        self.assertNotEqual(third.stdout.strip(), "")

    def test_b1_bash_command_hit_fires_once_per_session(self):
        payload = {
            "session_id": "cmd-session",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la .bashrc"},
        }
        first = run_hook(payload, self._env())
        self.assertEqual(first.returncode, 0, first.stderr)
        out = json.loads(first.stdout)["hookSpecificOutput"]
        self.assertIn("sandbox-shadow", out["additionalContext"])
        # a second, different Bash-hit command in the same session stays silent (one marker/session)
        payload2 = {
            "session_id": "cmd-session",
            "tool_name": "Bash",
            "tool_input": {"command": "stat .claude/settings.json"},
        }
        second = run_hook(payload2, self._env())
        self.assertEqual((second.returncode, second.stdout), (0, ""), second.stderr)

    def test_b2_home_prefixed_command_does_not_fire(self):
        payload = {
            "session_id": "cmd-home",
            "tool_name": "Bash",
            "tool_input": {"command": "cat ~/.bashrc"},
        }
        proc = run_hook(payload, self._env())
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_b3_read_tool_input_is_never_scanned(self):
        payload = {
            "session_id": "cmd-read",
            "tool_name": "Read",
            "tool_input": {"file_path": ".claude/settings.json"},
        }
        proc = run_hook(payload, self._env())
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_c1_both_scans_hitting_emit_a_single_message(self):
        proc = self._call(
            [_user_prompt(), _assistant_text("repo 直下に .bashrc が未追跡です")],
            session_id="both",
            tool_name="Bash",
            tool_input={"command": "ls -la .bashrc"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, proc.stdout)
        out = json.loads(lines[0])["hookSpecificOutput"]
        self.assertIn("sandbox-shadow", out["additionalContext"])

    def test_s7_missing_transcript_is_silent(self):
        payload = {
            "session_id": "sess1",
            "transcript_path": os.path.join(self.tmp.name, "nope.jsonl"),
            "tool_name": "Bash",
        }
        proc = run_hook(payload, self._env())
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_s8_malformed_stdin_is_silent(self):
        for body in ("{not json", "[]", "", '"just a string"'):
            with self.subTest(body=body):
                proc = run_hook(body, self._env())
                self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_s9_large_transcript_tail_read_finds_trailing_block(self):
        filler = [
            _assistant_tool_use(tool_input={"junk": "x" * 2000}) for _ in range(200)
        ]
        entries = filler + [_user_prompt(), _assistant_text(".zshrc が未追跡です")]
        proc = self._call(entries, session_id="s9")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertIn("sandbox-shadow", out["additionalContext"])

    def test_s10_hook_is_executable(self):
        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_l1_config_lock_with_lock_holder_framing_fires(self):
        for i, text in enumerate(
            (
                "`.git/config.lock` がロックされているので git config が書けません",
                "a stale lock: .git/config.lock was left by a crashed git",
                ".git/config.lock で失敗しました。この lock を持っている session は居ますか",
            )
        ):
            with self.subTest(text=text):
                context = self._context(
                    self._call([_user_prompt(), _assistant_text(text)], f"l1-{i}")
                )
                self.assertIn("config-lock", context)
                self.assertIn("feedback_sandbox_mask_leaks_git_config_lock.md", context)

    def test_l2_config_lock_named_as_mask_is_silent(self):
        text = "config.lock は sandbox の mask で、ロックされているわけではない"
        proc = self._call([_user_prompt(), _assistant_text(text)])
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_l3_lock_framing_without_config_lock_is_silent(self):
        for i, text in enumerate(
            (
                "index.lock がロックされている",
                "label the PR draft/blocked; deletion of .git/config.lock is listed",
            )
        ):
            with self.subTest(text=text):
                proc = self._call([_user_prompt(), _assistant_text(text)], f"l3-{i}")
                self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_p1_looking_at_a_covered_file_is_nudged_and_still_runs(self):
        looks = (
            ("Bash", {"command": "ls -la .git/config.lock"}, ".git/config.lock"),
            (
                "Bash",
                {"command": "cd .git && stat -c %F config.lock"},
                ".git/config.lock",
            ),
            ("Bash", {"command": "cat /proc/self/mountinfo"}, "/proc/self/mountinfo"),
            (
                "Bash",
                {"command": "findmnt -T /root/repo/.git/config.lock"},
                ".git/config.lock",
            ),
            (
                "Bash",
                {
                    "command": "grep -n 'excluded\\|git \\*' notes.md; ls .git/config.lock"
                },
                ".git/config.lock",
            ),
            ("Read", {"file_path": self.home + "/.ssh/id_ed25519"}, "~/.ssh"),
        )
        for i, (tool, tool_input, what) in enumerate(looks):
            with self.subTest(tool=tool, tool_input=tool_input):
                out = self._look([_user_prompt()], tool, tool_input, f"p1-{i}")
                self.assertNotIn("permissionDecision", out)
                self.assertIn("masked-probe", out["additionalContext"])
                self.assertIn(what, out["additionalContext"])

    def test_p2_another_method_in_the_same_turn_is_denied(self):
        entries = [_user_prompt(), _assistant_text("確かめます")]
        self._look(entries, "Bash", {"command": "ls .git/config.lock"})
        code = "import os; os.stat(os.path.join('.git', 'config.lock'))"
        out = self._look(entries, "Bash", {"command": f'python3 -c "{code}"'})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("確かめ直さず", out["permissionDecisionReason"])

    def test_p3_a_new_prompt_starts_a_new_turn(self):
        first = [_user_prompt("調べて")]
        self._look(first, "Bash", {"command": "ls .git/config.lock"})
        out = self._look(
            [*first, _user_prompt("次へ")], "Bash", {"command": "stat .git/config.lock"}
        )
        self.assertNotIn("permissionDecision", out)
        self.assertIn("masked-probe", out["additionalContext"])

    def test_p4_host_bound_or_unrelated_calls_are_silent(self):
        for i, command in enumerate(
            (
                "git status && ls .git/config.lock",
                "grep -rn TODO src/",
                'grep -n "config.lock\\|stale lock" docs/workflow.md',
                "cat >> /var/tmp/note.md <<'EOF'\nthe .git/config.lock is a mask\nEOF",
                "ps aux | grep -v bwrap",
            )
        ):
            with self.subTest(command=command):
                out = self._look(
                    [_user_prompt()], "Bash", {"command": command}, f"p4-{i}"
                )
                self.assertEqual(out, {})

    def _codex(self, payload: dict) -> subprocess.CompletedProcess:
        proc = run_hook({"session_id": "codex", **payload}, self._env(), ("--codex",))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def test_x1_codex_looks_are_nudged_never_denied(self):
        looks = (
            ("exec_command", {"cmd": "ls -la .git/config.lock"}),
            ("Bash", {"command": "stat .git/config.lock"}),
            ("Bash", {"command": "git status && ls .git/config.lock"}),
        )
        for tool, tool_input in looks:
            with self.subTest(tool_input=tool_input):
                proc = self._codex(
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": tool,
                        "tool_input": tool_input,
                    }
                )
                out = json.loads(proc.stdout)["hookSpecificOutput"]
                self.assertNotIn("permissionDecision", out)
                self.assertIn("masked-probe", out["additionalContext"])
                self.assertIn("workdir", out["additionalContext"])
        host = self._codex(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git config --get core.bare"},
            }
        )
        self.assertEqual(host.stdout, "")

    def test_x2_codex_config_lock_error_is_explained_once(self):
        def after(output: str) -> str:
            return self._codex(
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git config x.y 1"},
                    "tool_response": output,
                }
            ).stdout

        self.assertEqual(after("On branch main"), "")
        error = "error: could not lock config file .git/config: Read-only file system"
        context = json.loads(after(error))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("config-lock", context)
        self.assertIn("証拠にならない", context)
        self.assertEqual(after(error), "")

    def test_x3_codex_stop_restates_a_lock_claim_once(self):
        claim = ".git/config.lock がロックされているので待ちます"
        stop = {"hook_event_name": "Stop", "last_assistant_message": claim}
        out = json.loads(self._codex(stop).stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("config-lock", out["reason"])
        self.assertEqual(self._codex({**stop, "stop_hook_active": True}).stdout, "")
        correct = {
            **stop,
            "last_assistant_message": "config.lock は sandbox の mask です",
        }
        self.assertEqual(self._codex(correct).stdout, "")

    def test_t1_stop_blocks_once_then_lets_the_restated_turn_end(self):
        entries = [
            _user_prompt(),
            _assistant_text(".git/config.lock がロック中のため待ちます"),
        ]
        first = self._stop(entries, session_id="t1")
        self.assertEqual(first.returncode, 2, first.stderr)
        self.assertIn("config-lock", first.stderr)
        self.assertIn("書き直して", first.stderr)
        second = self._stop(entries, session_id="t1")
        self.assertEqual(second.returncode, 0, second.stderr)

    def test_t4_stop_is_silent_in_a_hook_child(self):
        payload = {
            "hook_event_name": "Stop",
            "session_id": "t4",
            "last_assistant_message": ".git/config.lock がロック中のため待ちます",
        }
        proc = run_hook(payload, {**self._env(), "CLAUDE_HOOK_CHILD": "1"})
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def test_t2_stop_ignores_shadow_only_text(self):
        proc = self._stop([_user_prompt(), _assistant_text(".bashrc が未追跡です")])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_t3_stop_reads_last_assistant_message(self):
        proc = self._stop(
            [_user_prompt()], final="stale lock の .git/config.lock を消しました"
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("config-lock", proc.stderr)

    def test_c2_one_text_hitting_two_rules_emits_one_line(self):
        text = ".bashrc が未追跡で、.git/config.lock もロックされている"
        proc = self._call([_user_prompt(), _assistant_text(text)], session_id="c2")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, proc.stdout)
        context = json.loads(lines[0])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("config-lock", context)
        self.assertIn("sandbox-shadow", context)


if __name__ == "__main__":
    unittest.main()
