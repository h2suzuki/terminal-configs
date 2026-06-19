#!/usr/bin/env python3
r"""
codex delegation surface for org-managed Claude Code.

Purpose
=======
tool-role-delegation (実装は codex へ委譲・Claude は仕様/レビュー) は self-judgment
依存で発火率が低い。 本 hook は委譲判断の自然な 2 つの境界で nudge を inject する。
deny せず additionalContext のみ (実装を止めない・誘導のみ)。

発火点 (payload の hook_event_name / tool_name で判定):

  PreToolUse ExitPlanMode : plan -> 実装の境界。 実装を /codex:rescue へ委譲せよと案内

ExitPlanMode は plan 退出 1 回 / plan で自然に低頻度ゆえ advise-once は不要。

委譲は plugin 経路 `/codex:rescue` 一本 (raw mcp-server は非登録)。 rescue 完了時の
review-nudge は todo (SubagentStop / Agent PostToolUse + subagent_type 判定で再導入)。

emit / fail-open
================
additionalContext のみ (permissionDecision を出さず tool は通常進行)。 全例外を握り
潰し exit 0 (fail-open)。

canonical source: files/claude_managed-hooks/codex_delegation_surface.py
deploy: /etc/claude-code/hooks/ (copy_dir で自動)。 両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import json
import sys
import unittest

# nudge 文面は意図的に冗長 (委譲先 + 役割境界 + degrade 条件を内面化させる)。 trim 禁止。
DELEGATE_MSG = (
    "[codex-delegation] plan を終え実装に入ります。 tool-role-delegation: 実装そのもの"
    "は codex に委譲してください — `/codex:rescue <spec>` に達成条件・制約・対象 file・"
    "受入基準を渡す (長時間は --background、 進捗 /codex:status、 結果 /codex:result、"
    " 中断 /codex:cancel)。 前回 codex run の継続 (apply top fix / 深掘り) は "
    "`/codex:rescue --resume`、 仕切り直しは --fresh、 model / 負荷調整は --model spark / "
    "--effort。 Claude は仕様明文化・レビュー・バグ出しを担い、 codex が返したコードを"
    "敵対的/受入レビューします (auth / data-loss / race 等の高リスクは "
    "/codex:adversarial-review で独立 cross-model 第二レビュー)。 trivial な変更・doc "
    "編集・codex 利用不可時は self-implement で構いません。"
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


def cmd(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return
    if event == "PreToolUse" and tool == "ExitPlanMode":
        _emit("PreToolUse", DELEGATE_MSG)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        cmd(payload)
    except Exception:
        pass  # fail-open
    return 0


class SurfaceTest(unittest.TestCase):
    """emit-vs-comply。 Run: python3 -m unittest codex_delegation_surface"""

    @staticmethod
    def _run(payload):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd(payload)
        out = buf.getvalue().strip()
        return json.loads(out)["hookSpecificOutput"] if out else None

    def test_exitplanmode_delegate_nudge(self):
        out = self._run({"hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode"})
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("/codex:rescue", out["additionalContext"])
        self.assertIn("--resume", out["additionalContext"])
        self.assertIn("[codex-delegation]", out["additionalContext"])

    def test_no_fire_on_other_tools(self):
        self.assertIsNone(
            self._run({"hook_event_name": "PreToolUse", "tool_name": "Edit"})
        )
        self.assertIsNone(
            self._run(
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "mcp__codegraph__codegraph_search",
                }
            )
        )

    def test_exitplanmode_only_on_pretooluse(self):
        # PostToolUse の ExitPlanMode (理論上) には委譲 nudge を出さない。
        self.assertIsNone(
            self._run({"hook_event_name": "PostToolUse", "tool_name": "ExitPlanMode"})
        )

    def test_non_dict_and_missing_fields(self):
        self.assertIsNone(self._run({}))
        self.assertIsNone(self._run({"tool_name": "ExitPlanMode"}))  # event 欠落


if __name__ == "__main__":
    sys.exit(main())
