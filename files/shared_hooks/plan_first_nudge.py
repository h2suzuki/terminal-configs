#!/usr/bin/env python3
"""
UserPromptSubmit hook: remind the model to upsert a Task — a new item, or the
in_progress flip of one it already tracks — before its first working tool call
(org CLAUDE.md 「計画と遂行」).

Why UserPromptSubmit (not Stop): stop_checks.py's task-plan-first family is a
Stop-time block, so an ordering miss is only ever reported after the tools have
already run — the rework it costs is exactly what this nudge prevents.

Contract (each claim maps to one test):
  N1  a real prompt -> the nudge rides additionalContext
  N2  an open task -> the nudge still rides (its status flip is the upsert the
      Stop gate asks for, so tracked work is no reason to stay silent)
  N3  N2 through the real store: an open item never reaches this hook at all
  N4  synthetic <task-notification> re-entry -> silence (not a real prompt turn)
  N5  Task tools gated off for the session -> silence (nothing to upsert with)
  N6  systemMessage is never written (a model-only nudge, invisible to the user)

Stdin: UserPromptSubmit payload JSON (`prompt`, `cwd`, `session_id`).
Stdout: hookSpecificOutput additionalContext only; nothing otherwise.

Codex (--codex): prompt multi-step work to use mytask. Does not read Claude's
feature gates or assume Claude's ToolSearch and Stop hooks exist in Codex.

Exit:
  0: always. This hook only injects context, never blocks; exits 0 on any
     parse / IO error (fail-open).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

NUDGE = (
    "task-plan-first: この turn で作業 tool を使うなら、最初の tool より前に Task を "
    "upsert せよ — 新規登録でも、既に開いている Task の in_progress 化でもよい "
    "(Stop 側の gate は事後 block ゆえ手戻りになる)。 Task tool の schema が "
    "未読込なら ToolSearch だけを単独で撃て — 同 block に作業 tool を並べると違反になる"
)
CODEX_NUDGE = (
    "mytask: 複数段階の作業を行うときは、作業開始・再開時に mytask の TaskList で "
    "現在の項目を確認し、必要な手順を TaskCreate で登録する。着手時に TaskUpdate で "
    "in_progress、外部依存待ちは blocked、成果物を検証してから completed に更新する。 "
    "状態が変わったらユーザーへ簡潔に伝える。単発の小さな編集では一覧の作成は不要。 "
    "MCP が利用できない場合は使ったと主張せず、その旨を伝えて作業を続ける。"
)
SYNTHETIC_PREFIX = "<task-notification>"


def _tasks_gated_off() -> bool:
    """True while the session's Task tools may be gated off — 判定不能な値は沈黙側に倒す。"""
    try:
        with open(
            os.path.join(os.environ.get("HOME", ""), ".claude.json"), encoding="utf-8"
        ) as f:
            config = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(config, dict):
        return False
    features = config.get("cachedGrowthBookFeatures")
    gate = features.get("tengu_vellum_ash") if isinstance(features, dict) else None
    return bool(gate)


def _nudge_wanted(payload: dict, *, codex: bool = False) -> bool:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    if prompt.lstrip().startswith(SYNTHETIC_PREFIX):
        return False
    return codex or not _tasks_gated_off()


def _emit_context(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict, *, codex: bool = False) -> int:
    if isinstance(payload, dict) and _nudge_wanted(payload, codex=codex):
        _emit_context(CODEX_NUDGE if codex else NUDGE)
    return 0


def main() -> int:
    try:
        return _run(
            json.loads(sys.stdin.read() or "{}"), codex="--codex" in sys.argv[1:]
        )
    except Exception:
        return 0


class NudgeTest(unittest.TestCase):
    """N1-N6: the open-task gate, the silence cases, and the model-only channel."""

    SID = "s1"

    def _emit(self, prompt: str, *, gated: bool = False) -> list[str]:
        sent: list[str] = []
        module = sys.modules[__name__]
        with (
            mock.patch.object(module, "_tasks_gated_off", lambda: gated),
            mock.patch.object(module, "_emit_context", sent.append),
        ):
            _run({"prompt": prompt, "cwd": "/tmp", "session_id": self.SID})
        return sent

    def test_n1_a_real_prompt_nudges(self):
        self.assertEqual(self._emit("hook を直してください"), [NUDGE])

    def test_n2_open_task_does_not_silence_the_nudge(self):
        """開いた Task を持つ turn こそ in_progress 化が要る: Stop gate は order を見る。"""
        self.assertEqual(self._emit("hook を直してください"), [NUDGE])
        self.assertIn("in_progress", NUDGE)

    def test_n4_synthetic_reentry_is_silent(self):
        self.assertEqual(self._emit(SYNTHETIC_PREFIX + "\n<task-id>x</task-id>"), [])

    def test_n5_gated_off_session_is_silent(self):
        self.assertEqual(self._emit("hook を直してください", gated=True), [])

    def test_n6_channel_is_additional_context_only(self):
        buf = []
        with mock.patch.object(sys, "stdout", mock.Mock(write=buf.append)):
            _emit_context(NUDGE)
        out = json.loads("".join(buf))
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], NUDGE)
        self.assertNotIn("systemMessage", out)


class CodexNudgeTest(unittest.TestCase):
    def test_codex_uses_mytask_without_claude_gate(self):
        sent = []
        with (
            mock.patch.object(
                sys.modules[__name__],
                "_tasks_gated_off",
                side_effect=AssertionError("Claude-only gate"),
            ),
            mock.patch.object(sys.modules[__name__], "_emit_context", sent.append),
        ):
            _run({"prompt": "MCP を移植してテストして"}, codex=True)
        self.assertEqual(sent, [CODEX_NUDGE])
        self.assertIn("TaskList", sent[0])
        self.assertIn("TaskCreate", sent[0])
        self.assertIn("TaskUpdate", sent[0])
        self.assertNotIn("ToolSearch", sent[0])

    def test_codex_empty_or_synthetic_prompt_is_silent(self):
        with mock.patch.object(sys.modules[__name__], "_emit_context") as emit:
            for prompt in (None, "", "  ", SYNTHETIC_PREFIX + "done"):
                _run({"prompt": prompt}, codex=True)
            _run([], codex=True)
        emit.assert_not_called()

    def test_codex_only_adds_model_context(self):
        output = []
        with mock.patch.object(sys, "stdout", mock.Mock(write=output.append)):
            self.assertEqual(_run({"prompt": "実装して"}, codex=True), 0)
        result = json.loads("".join(output))
        self.assertEqual(set(result), {"hookSpecificOutput"})
        self.assertEqual(
            result["hookSpecificOutput"],
            {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": CODEX_NUDGE,
            },
        )


class StoreTest(unittest.TestCase):
    """N3: 実 store に開いた item がある session でも nudge は出る (store を読まない)。"""

    SID = "s1"

    def test_n3_pending_task_in_the_store_still_nudges(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = os.path.join(tmp.name, "drafts", "tasks")
        os.makedirs(store)
        with open(os.path.join(store, self.SID + ".json"), "w", encoding="utf-8") as f:
            json.dump([{"id": 1, "content": "作業", "status": "pending"}], f)
        sent: list[str] = []
        module = sys.modules[__name__]
        with (
            mock.patch.object(module, "_tasks_gated_off", lambda: False),
            mock.patch.object(module, "_emit_context", sent.append),
        ):
            _run({"prompt": "hook を直して", "cwd": tmp.name, "session_id": self.SID})
        self.assertEqual(sent, [NUDGE])


class GateOffTest(unittest.TestCase):
    """N5 の下地: growthbook gate の値ごとの判定。"""

    def _gated(self, features) -> bool:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump({"cachedGrowthBookFeatures": features}, f)
        with mock.patch.dict(os.environ, {"HOME": tmp.name}, clear=False):
            return _tasks_gated_off()

    def test_absent_gate_is_on(self):
        self.assertFalse(self._gated({}))

    def test_true_gate_is_off(self):
        self.assertTrue(self._gated({"tengu_vellum_ash": True}))

    def test_model_list_gate_is_off(self):
        self.assertTrue(self._gated({"tengu_vellum_ash": ["claude-opus-5"]}))

    def test_empty_list_gate_is_on(self):
        self.assertFalse(self._gated({"tengu_vellum_ash": []}))

    def test_missing_config_is_on(self):
        with mock.patch.dict(os.environ, {"HOME": "/nonexistent"}, clear=False):
            self.assertFalse(_tasks_gated_off())


if __name__ == "__main__":
    sys.exit(main())
