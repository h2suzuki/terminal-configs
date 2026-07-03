#!/usr/bin/env python3
r"""
codex delegation surface for org-managed Claude Code.

Purpose
=======
tool-role-delegation (routing: 実装は codex へ委譲) と codex-delegation (委譲後の
lifecycle 規律) は self-judgment 依存で発火率が低い。 本 hook は委譲判断の自然な 2 つの
境界で両 skill を surface する nudge を inject する。 deny せず additionalContext のみ
(実装を止めない・誘導のみ)。

発火点 (payload の hook_event_name / tool_name / agent_type で判定):

  PreToolUse ExitPlanMode : plan -> 実装の境界。 実装を /codex:rescue へ委譲せよと案内
  SubagentStop codex-rescue : Claude Code >= 2.1.179 は asyncRewake で REVIEW_MSG + exit 2
  SubagentStop codex-rescue : それ以外は session-keyed review flag を arm
  PreToolUse / UserPromptSubmit : review flag が fresh なら敵対的/受入レビュー nudge を deliver-and-clear

asyncRewake capable では SubagentStop hook が plain text を出し exit 2 で main agent を
re-wake する。fallback では SubagentStop の additionalContext が main agent に surface しない
ため、次の surface-capable event (PreToolUse / UserPromptSubmit) で 1 回だけ配送する。
clearing rule: deferred deliver path だけが flag を clear し、asyncRewake path は arm/clear しない。

委譲は plugin 経路 `/codex:rescue` 一本 (raw mcp-server は非登録)。

emit / fail-open
================
additionalContext のみ (permissionDecision を出さず tool は通常進行)。 全例外を握り
潰し exit 0 (fail-open)。

canonical source: files/claude_managed-hooks/codex_delegation_surface.py
deploy: /etc/claude-code/hooks/  両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "hooks", "state", "codex_review_pending")
TTL_SECONDS = 1800
PRUNE_SECONDS = 24 * 3600

# nudge 文面は意図的に冗長 (委譲先 + 役割境界 + degrade 条件を内面化させる)。 trim 禁止。
DELEGATE_MSG = (
    "[codex-delegation] plan を終え実装に入ります。 tool-role-delegation: 実装そのもの"
    "は codex に委譲してください — `/codex:rescue <spec>` に達成条件・制約・対象 file・"
    "受入基準を渡す (長時間は --background、 進捗 /codex:status、 結果 /codex:result、"
    " 中断 /codex:cancel)。 前回 codex run の継続 (apply top fix / 深掘り) は "
    "`/codex:rescue --resume`、 仕切り直しは --fresh、 model / 負荷調整は --model spark / "
    "--effort。 Claude は仕様明文化・レビュー・バグ出しを担い、 codex が返したコードを"
    "敵対的/受入レビューします (auth / data-loss / race 等の高リスクは "
    "/codex:adversarial-review で独立 cross-model 第二レビュー)。 発注書の書き方・"
    "走行監視・完了判定 (ツリー静穏 + companion status)・fix round の lifecycle 規律は "
    "`codex-delegation` skill を invoke。 trivial な変更・doc "
    "編集・codex 利用不可時は self-implement で構いません。"
)
REVIEW_MSG = (
    "[codex-review] codex-rescue が停止しました (SubagentStop は codex 本体の完了を"
    "保証しません — ツリー静穏 + companion status running[] 空を先に確認し moving-target "
    "レビューを回避)。 tool-role-delegation step4: コードを"
    "敵対的/受入レビューし、 バグ・仕様逸脱・副作用を検査してください (patch 反映も"
    "レビューの一部)。 auth / data-loss / race / rollback 等の高リスク変更は "
    "`/codex:adversarial-review` で codex の独立 cross-model 第二レビューを追加して"
    "ください。 完了判定〜受入レビュー〜fix round の規律は `codex-delegation` skill を invoke。"
)


def _emit(event: str, context: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def _cc_version() -> tuple[int, int, int] | None:
    try:
        # SubagentStop env lacks CLAUDE_CODE_VERSION/EXECPATH; AI_AGENT (claude-code_2-1-183_harness) carries it.
        for raw in (
            os.environ.get("CLAUDE_CODE_VERSION"),
            os.path.basename(os.environ.get("CLAUDE_CODE_EXECPATH", "")),
            os.environ.get("AI_AGENT"),
        ):
            if not raw:
                continue
            m = re.search(r"(\d+)[.\-_](\d+)[.\-_](\d+)", raw)
            if m:
                return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None
    except Exception:
        return None


def _async_rewake_active() -> bool:
    version = _cc_version()
    return version is not None and version >= (2, 1, 179)


def _sid(payload: dict) -> str:
    sid = payload.get("session_id")
    if not isinstance(sid, str) or not sid:
        sid = "_"
    return sid


def _marker(payload: dict) -> str:
    return os.path.join(STATE_DIR, _sid(payload), "pending")


def _fresh(path: str, now: float) -> bool:
    try:
        return now - os.path.getmtime(path) < TTL_SECONDS
    except OSError:
        return False


def _prune(now: float) -> None:
    cutoff = now - PRUNE_SECONDS
    try:
        sids = os.listdir(STATE_DIR)
    except OSError:
        return
    for sid in sids:
        d = os.path.join(STATE_DIR, sid)
        try:
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
            os.rmdir(d)  # only succeeds if now empty
        except OSError:
            pass


def _arm(payload: dict, now: float) -> None:
    marker = _marker(payload)
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(str(now))
    except OSError:
        return
    _prune(now)


def _pop_review(payload: dict, now: float) -> str | None:
    marker = _marker(payload)
    try:
        exists = os.path.exists(marker)
    except OSError:
        return None
    if not exists:
        return None
    fresh = _fresh(marker, now)
    try:
        os.remove(marker)
    except OSError:
        pass
    return REVIEW_MSG if fresh else None


def cmd(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    event = payload.get("hook_event_name")
    now = time.time()
    if event == "SubagentStop":
        if "codex-rescue" in str(payload.get("agent_type", "")).lower():
            if _async_rewake_active():
                sys.stdout.write(REVIEW_MSG + "\n")
                return 2
            _arm(payload, now)
        return 0
    if event == "PreToolUse":
        messages = []
        if payload.get("tool_name") == "ExitPlanMode":
            messages.append(DELEGATE_MSG)
        review = _pop_review(payload, now)
        if review:
            messages.append(review)
        if messages:
            _emit("PreToolUse", "\n\n".join(messages))
    elif event == "UserPromptSubmit":
        review = _pop_review(payload, now)
        if review:
            _emit("UserPromptSubmit", review)
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        return cmd(payload)
    except Exception:
        pass  # fail-open
    return 0


class SurfaceTest(unittest.TestCase):
    """emit-vs-comply。 Run: python3 -m unittest codex_delegation_surface"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_state_dir = globals()["STATE_DIR"]
        self.old_version = os.environ.pop("CLAUDE_CODE_VERSION", None)
        self.old_execpath = os.environ.pop("CLAUDE_CODE_EXECPATH", None)
        self.old_ai_agent = os.environ.pop("AI_AGENT", None)
        globals()["STATE_DIR"] = self.tmp

    def tearDown(self):
        globals()["STATE_DIR"] = self.old_state_dir
        if self.old_version is None:
            os.environ.pop("CLAUDE_CODE_VERSION", None)
        else:
            os.environ["CLAUDE_CODE_VERSION"] = self.old_version
        if self.old_execpath is None:
            os.environ.pop("CLAUDE_CODE_EXECPATH", None)
        else:
            os.environ["CLAUDE_CODE_EXECPATH"] = self.old_execpath
        if self.old_ai_agent is None:
            os.environ.pop("AI_AGENT", None)
        else:
            os.environ["AI_AGENT"] = self.old_ai_agent
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _run(payload):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cmd(payload)
        out = buf.getvalue().strip()
        parsed = json.loads(out)["hookSpecificOutput"] if out.startswith("{") else None
        return (parsed, code, out)

    def _marker_path(self, sid="s1"):
        return os.path.join(self.tmp, sid, "pending")

    def _arm_marker(self, sid="s1"):
        path = self._marker_path(sid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        return path

    def _arm_stale_marker(self, sid="s1"):
        path = self._arm_marker(sid)
        stale = time.time() - TTL_SECONDS - 10
        os.utime(path, (stale, stale))
        return path

    def _output(self, payload):
        out, code, _ = self._run(payload)
        self.assertEqual(code, 0)
        self.assertIsNotNone(out)
        assert out is not None
        return out

    def _no_output(self, payload):
        out, code, text = self._run(payload)
        self.assertEqual(code, 0)
        self.assertEqual(text, "")
        self.assertIsNone(out)

    def test_subagentstop_codex_rescue_arms_marker_emits_nothing(self):
        for at in ("codex:codex-rescue", "codex-rescue", "Codex-Rescue"):
            sid = at.replace(":", "_")
            out, code, text = self._run(
                {"hook_event_name": "SubagentStop", "agent_type": at, "session_id": sid}
            )
            self.assertEqual(code, 0)
            self.assertEqual(text, "")
            self.assertIsNone(out)
            self.assertTrue(os.path.exists(self._marker_path(sid)))

    def test_subagentstop_other_agent_arms_nothing_emits_nothing(self):
        for at in ("general-purpose", ""):
            out, code, text = self._run(
                {"hook_event_name": "SubagentStop", "agent_type": at, "session_id": at}
            )
            self.assertEqual(code, 0)
            self.assertEqual(text, "")
            self.assertIsNone(out)
            self.assertFalse(os.path.exists(self._marker_path(at or "_")))

    def test_pretooluse_any_tool_with_fresh_marker_delivers_and_removes(self):
        path = self._arm_marker()
        out = self._output(
            {"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s1"}
        )
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("[codex-review]", out["additionalContext"])
        self.assertIn("companion status", out["additionalContext"])
        self.assertIn("`codex-delegation` skill", out["additionalContext"])
        self.assertFalse(os.path.exists(path))

    def test_pretooluse_second_call_after_delivery_emits_nothing(self):
        self._arm_marker()
        first = self._output(
            {"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s1"}
        )
        second, code, text = self._run(
            {"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s1"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(text, "")
        self.assertIn("[codex-review]", first["additionalContext"])
        self.assertIsNone(second)

    def test_userpromptsubmit_with_fresh_marker_delivers_and_removes(self):
        path = self._arm_marker()
        out = self._output({"hook_event_name": "UserPromptSubmit", "session_id": "s1"})
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("[codex-review]", out["additionalContext"])
        self.assertFalse(os.path.exists(path))

    def test_pretooluse_stale_marker_removed_not_emitted(self):
        path = self._arm_stale_marker()
        out, code, text = self._run(
            {"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s1"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(text, "")
        self.assertIsNone(out)
        self.assertFalse(os.path.exists(path))

    def test_userpromptsubmit_stale_marker_removed_not_emitted(self):
        path = self._arm_stale_marker()
        out, code, text = self._run(
            {"hook_event_name": "UserPromptSubmit", "session_id": "s1"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(text, "")
        self.assertIsNone(out)
        self.assertFalse(os.path.exists(path))

    def test_exitplanmode_delegate_nudge_no_marker_side_effects(self):
        out = self._output(
            {"hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode"}
        )
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("/codex:rescue", out["additionalContext"])
        self.assertIn("--resume", out["additionalContext"])
        self.assertIn("[codex-delegation]", out["additionalContext"])
        self.assertIn("`codex-delegation` skill", out["additionalContext"])
        self.assertFalse(os.path.exists(self._marker_path("_")))

    def test_exitplanmode_with_fresh_marker_delivers_both_and_removes(self):
        path = self._arm_marker()
        out = self._output(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "ExitPlanMode",
                "session_id": "s1",
            }
        )
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("[codex-delegation]", out["additionalContext"])
        self.assertIn("[codex-review]", out["additionalContext"])
        self.assertLess(
            out["additionalContext"].index("[codex-delegation]"),
            out["additionalContext"].index("[codex-review]"),
        )
        self.assertFalse(os.path.exists(path))

    def test_no_fire_on_other_tools(self):
        self._no_output({"hook_event_name": "PreToolUse", "tool_name": "Edit"})
        self._no_output(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "mcp__codegraph__codegraph_search",
            }
        )

    def test_exitplanmode_only_on_pretooluse(self):
        # PostToolUse の ExitPlanMode (理論上) には委譲 nudge を出さない。
        self._no_output({"hook_event_name": "PostToolUse", "tool_name": "ExitPlanMode"})

    def test_non_dict_and_missing_fields(self):
        self._no_output(None)
        self._no_output([])
        self._no_output({})
        self._no_output({"tool_name": "ExitPlanMode"})  # event 欠落

    def test_cc_version_parsing(self):
        os.environ["CLAUDE_CODE_VERSION"] = "2.1.183"
        self.assertEqual(_cc_version(), (2, 1, 183))
        os.environ["CLAUDE_CODE_VERSION"] = ""
        os.environ["CLAUDE_CODE_EXECPATH"] = "/x/versions/2.1.183"
        self.assertEqual(_cc_version(), (2, 1, 183))
        os.environ["CLAUDE_CODE_EXECPATH"] = "/x/versions/garbage"
        self.assertIsNone(_cc_version())
        os.environ["CLAUDE_CODE_VERSION"] = "garbage"
        self.assertIsNone(_cc_version())
        os.environ.pop("CLAUDE_CODE_VERSION", None)
        os.environ.pop("CLAUDE_CODE_EXECPATH", None)
        os.environ["AI_AGENT"] = "claude-code_2-1-183_harness"
        self.assertEqual(_cc_version(), (2, 1, 183))

    def test_async_rewake_active_version_gate(self):
        for version in ("2.1.179", "2.1.183"):
            os.environ["CLAUDE_CODE_VERSION"] = version
            self.assertTrue(_async_rewake_active())
        for version in ("2.1.178", "2.0.999"):
            os.environ["CLAUDE_CODE_VERSION"] = version
            self.assertFalse(_async_rewake_active())
        os.environ.pop("CLAUDE_CODE_VERSION", None)
        os.environ.pop("CLAUDE_CODE_EXECPATH", None)
        self.assertFalse(_async_rewake_active())

    def test_subagentstop_codex_rescue_async_rewake_returns_2_without_marker(self):
        os.environ["CLAUDE_CODE_VERSION"] = "2.1.183"
        out, code, text = self._run(
            {
                "hook_event_name": "SubagentStop",
                "agent_type": "codex-rescue",
                "session_id": "s1",
            }
        )
        self.assertIsNone(out)
        self.assertEqual(code, 2)
        self.assertIn("[codex-review]", text)
        self.assertFalse(text.startswith("{"))
        self.assertFalse(os.path.exists(self._marker_path()))

    def test_subagentstop_codex_rescue_inactive_arms_marker(self):
        os.environ["CLAUDE_CODE_VERSION"] = "2.1.178"
        out, code, text = self._run(
            {
                "hook_event_name": "SubagentStop",
                "agent_type": "codex-rescue",
                "session_id": "s1",
            }
        )
        self.assertIsNone(out)
        self.assertEqual(code, 0)
        self.assertEqual(text, "")
        self.assertTrue(os.path.exists(self._marker_path()))

    def test_main_fail_open_when_cmd_raises(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("{}")
            buf = io.StringIO()
            with patch(__name__ + ".cmd", side_effect=RuntimeError("boom")):
                with redirect_stdout(buf):
                    self.assertEqual(main(), 0)
            self.assertEqual(buf.getvalue(), "")
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    sys.exit(main())
