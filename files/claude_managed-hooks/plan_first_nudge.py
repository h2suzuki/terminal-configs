#!/usr/bin/env python3
"""
UserPromptSubmit hook: while the session tracks no open work item, remind the
model to upsert a Task before its first working tool call (org CLAUDE.md
「計画と遂行」).

Why UserPromptSubmit (not Stop): stop_checks.py's task-plan-first family is a
Stop-time block, so an ordering miss is only ever reported after the tools have
already run — the rework it costs is exactly what this nudge prevents.

Contract (each claim maps to one test):
  N1  no open task -> the nudge rides additionalContext
  N2  an open task -> silence (a session already tracking work is not nagged)
  N3  every task closed -> the nudge returns (closed == none for this purpose)
  N4  synthetic <task-notification> re-entry -> silence (not a real prompt turn)
  N5  Task tools gated off for the session -> silence (nothing to upsert with)
  N6  systemMessage is never written (a model-only nudge, invisible to the user)

Stdin: UserPromptSubmit payload JSON (`prompt`, `cwd`, `session_id`).
Stdout: hookSpecificOutput additionalContext only; nothing otherwise.

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

# open-task reader は sibling UserPromptSubmit hook が単一 source
# (same deployed dir; absent/broken hook → 本 hook は沈黙 = fail-open)。
try:
    import check_uncommitted_at_handoff as _tasks_mod
except Exception:
    _tasks_mod = None  # fail-open sentinel, guarded by `is not None`

NUDGE = (
    "task-plan-first: この turn で作業 tool を使うなら、最初の tool より前に Task を "
    "upsert せよ (Stop 側の gate は事後 block ゆえ手戻りになる)"
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


def _nudge_wanted(payload: dict) -> bool:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    if prompt.lstrip().startswith(SYNTHETIC_PREFIX):
        return False
    if _tasks_mod is None or _tasks_gated_off():
        return False
    session = payload.get("session_id")
    cwd = payload.get("cwd")
    if not isinstance(session, str) or not session:
        return False
    return not _tasks_mod.open_tasks(session, cwd if isinstance(cwd, str) else "")


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
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


class NudgeTest(unittest.TestCase):
    """N1-N6: the open-task gate, the silence cases, and the model-only channel."""

    SID = "s1"

    def _emit(self, prompt: str, tasks: list[str], *, gated: bool = False) -> list[str]:
        sent: list[str] = []
        module = sys.modules[__name__]
        with (
            mock.patch.object(
                module, "_tasks_mod", mock.Mock(open_tasks=lambda *_: tasks)
            ),
            mock.patch.object(module, "_tasks_gated_off", lambda: gated),
            mock.patch.object(module, "_emit_context", sent.append),
        ):
            _run({"prompt": prompt, "cwd": "/tmp", "session_id": self.SID})
        return sent

    def test_n1_no_open_task_nudges(self):
        self.assertEqual(self._emit("hook を直してください", []), [NUDGE])

    def test_n2_open_task_is_silent(self):
        self.assertEqual(self._emit("hook を直してください", ["#1 作業"]), [])

    def test_n4_synthetic_reentry_is_silent(self):
        self.assertEqual(
            self._emit(SYNTHETIC_PREFIX + "\n<task-id>x</task-id>", []), []
        )

    def test_n5_gated_off_session_is_silent(self):
        self.assertEqual(self._emit("hook を直してください", [], gated=True), [])

    def test_n6_channel_is_additional_context_only(self):
        buf = []
        with mock.patch.object(sys, "stdout", mock.Mock(write=buf.append)):
            _emit_context(NUDGE)
        out = json.loads("".join(buf))
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], NUDGE)
        self.assertNotIn("systemMessage", out)


class StoreTest(unittest.TestCase):
    """N2 / N3 を sibling の実 store reader 越しに固定する (status 判定は sibling が単一 source)。"""

    SID = "s1"

    def _emit(self, tasks: list[dict]) -> list[str]:
        if _tasks_mod is None:
            self.skipTest("sibling hook not importable")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = os.path.join(tmp.name, "drafts", "tasks")
        os.makedirs(store)
        with open(os.path.join(store, self.SID + ".json"), "w", encoding="utf-8") as f:
            json.dump(tasks, f)
        sent: list[str] = []
        module = sys.modules[__name__]
        with (
            mock.patch.object(module, "_tasks_gated_off", lambda: False),
            mock.patch.object(module, "_emit_context", sent.append),
            mock.patch.object(_tasks_mod, "NATIVE_TASKS_DIR", tmp.name),
        ):
            _run({"prompt": "hook を直して", "cwd": tmp.name, "session_id": self.SID})
        return sent

    def test_n2_pending_task_in_the_store_is_silent(self):
        self.assertEqual(
            self._emit([{"id": 1, "content": "作業", "status": "pending"}]), []
        )

    def test_n3_closed_tasks_nudge_again(self):
        for status in ("completed", "cancelled"):
            with self.subTest(status=status):
                self.assertEqual(
                    self._emit([{"id": 1, "content": "作業", "status": status}]),
                    [NUDGE],
                )


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
