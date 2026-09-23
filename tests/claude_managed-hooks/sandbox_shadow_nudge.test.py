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


def run_hook(payload: object, env: dict) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, HOOK],
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

    def _env(self) -> dict:
        return {"SANDBOX_SHADOW_NUDGE_STATE_DIR": self.state_dir}

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


if __name__ == "__main__":
    unittest.main()
