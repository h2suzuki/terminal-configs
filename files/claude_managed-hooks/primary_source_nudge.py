#!/usr/bin/env python3
"""
UserPromptSubmit hook: every real prompt turn, restate the primary-source rule
before the model gets a chance to assert anything (org CLAUDE.md 「事実 vs 推論」).

Why an always-on injection (not a Stop-time check): the failure mode is a claim
written before the first tool call, so the only place a reminder can still change
the outcome is ahead of that first claim.

Time-boxed trial: the wording extends the AGENTS.md line that the
Codex CLI obeys reliably, placed in the closest always-on form that needs no
CLAUDE.md edit. The removal / keep criterion is tracked in todos.md, not here.

Contract (each claim maps to one test):
  P1  real prompt -> the line rides additionalContext
  P2  empty / whitespace-only prompt -> silence
  P3  synthetic <task-notification> re-entry -> silence (not a real prompt turn)
  P4  malformed stdin -> silence, exit 0 (fail-open)
  P5  systemMessage is never written (a model-only nudge, invisible to the user)

Stdin: UserPromptSubmit payload JSON (`prompt`).
Stdout: hookSpecificOutput additionalContext only; nothing otherwise.

Exit:
  0: always. This hook only injects context, never blocks; exits 0 on any
     parse / IO error (fail-open).
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

NUDGE = (
    "primary-source (試行 2026-09-10〜): 断定を書く前に必ず一次ソース "
    "(対象 file / command 出力 / 公式資料) にあたって裏付けをとれ。 "
    "裏付けの走査空間と出力を示せない文は断定でなく推論として書け"
)
SYNTHETIC_PREFIX = "<task-notification>"


def _nudge_wanted(payload: dict) -> bool:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    return not prompt.lstrip().startswith(SYNTHETIC_PREFIX)


def _emit_context(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict) -> int:
    if isinstance(payload, dict) and _nudge_wanted(payload):
        _emit_context(NUDGE)
    return 0


def main() -> int:
    if os.environ.get("CLAUDE_HOOK_CHILD"):
        return 0  # a one-off session spawned by another hook runs no session hooks
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


class NudgeTest(unittest.TestCase):
    """P1-P3, P5: the real-prompt gate, the silence cases, and the model-only channel."""

    def _emit(self, payload: dict) -> list[str]:
        sent: list[str] = []
        with mock.patch.object(sys.modules[__name__], "_emit_context", sent.append):
            rc = _run(payload)
        self.assertEqual(rc, 0)
        return sent

    def test_p1_real_prompt_injects_the_line(self):
        self.assertEqual(self._emit({"prompt": "hook を直してください"}), [NUDGE])

    def test_p1_wording_is_verbatim(self):
        self.assertEqual(
            NUDGE,
            "primary-source (試行 2026-09-10〜): 断定を書く前に必ず一次ソース "
            "(対象 file / command 出力 / 公式資料) にあたって裏付けをとれ。 "
            "裏付けの走査空間と出力を示せない文は断定でなく推論として書け",
        )

    def test_p2_empty_prompt_is_silent(self):
        for prompt in ("", "   \n\t", None, 42):
            with self.subTest(prompt=prompt):
                self.assertEqual(self._emit({"prompt": prompt}), [])

    def test_p2_missing_prompt_key_is_silent(self):
        self.assertEqual(self._emit({}), [])

    def test_p3_synthetic_reentry_is_silent(self):
        self.assertEqual(
            self._emit({"prompt": SYNTHETIC_PREFIX + "\n<task-id>x</task-id>"}), []
        )

    def test_p3_leading_whitespace_does_not_defeat_the_prefix(self):
        self.assertEqual(self._emit({"prompt": "\n  " + SYNTHETIC_PREFIX + " x"}), [])

    def test_p5_channel_is_additional_context_only(self):
        buf: list[str] = []
        with mock.patch.object(sys, "stdout", mock.Mock(write=buf.append)):
            _emit_context(NUDGE)
        out = json.loads("".join(buf))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], NUDGE)
        self.assertNotIn("systemMessage", out)
        self.assertNotIn("systemMessage", out["hookSpecificOutput"])


class MalformedStdinTest(unittest.TestCase):
    """P4: garbage / non-object stdin exits 0 and writes nothing."""

    def _main(self, stdin_text: str) -> tuple[int, str]:
        buf: list[str] = []
        with (
            mock.patch.object(sys, "stdin", mock.Mock(read=lambda: stdin_text)),
            mock.patch.object(sys, "stdout", mock.Mock(write=buf.append)),
        ):
            rc = main()
        return rc, "".join(buf)

    def test_p4_broken_json_is_silent(self):
        self.assertEqual(self._main("{not json"), (0, ""))

    def test_p4_empty_stdin_is_silent(self):
        self.assertEqual(self._main(""), (0, ""))

    def test_p4_non_object_payload_is_silent(self):
        self.assertEqual(self._main('["prompt"]'), (0, ""))

    def test_p4_unreadable_stdin_is_silent(self):
        def boom() -> str:
            raise OSError("stdin gone")

        with mock.patch.object(sys, "stdin", mock.Mock(read=boom)):
            self.assertEqual(main(), 0)


if __name__ == "__main__":
    sys.exit(main())
