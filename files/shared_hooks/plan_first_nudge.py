#!/usr/bin/env python3
"""Point real user prompts to the shared mytask skill; never block a turn.

Only model-facing UserPromptSubmit additionalContext is emitted. Empty prompts
and synthetic task notifications stay silent. Claude's native-task feature gate
does not disable the reminder: the skill also covers the mytask MCP fallback.
"""

from __future__ import annotations

import json
import sys
import unittest
from unittest import mock

PURPOSE = "依頼を記録し、大きな作業を分解し、自分の計画を依頼に照らして見直すため、"
NUDGE = (
    "mytask: "
    + PURPOSE
    + "未読なら mytask Skill（~/.claude/skills/mytask/SKILL.md）を読み、その手順に従う。"
    "読込済みなら今回の依頼・追加・訂正を反映する。"
)
CODEX_NUDGE = (
    "mytask: "
    + PURPOSE
    + "未読なら /etc/codex/skills/mytask/SKILL.md を読み、その手順に従う。"
    "読込済みなら今回の依頼・追加・訂正を反映する。"
)
SYNTHETIC_PREFIX = "<task-notification>"


def _emit_context(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict, *, codex: bool = False) -> int:
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if (
        isinstance(prompt, str)
        and prompt.strip()
        and not prompt.lstrip().startswith(SYNTHETIC_PREFIX)
    ):
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
    def test_client_specific_skill_reference(self):
        for codex, expected in ((False, NUDGE), (True, CODEX_NUDGE)):
            with (
                self.subTest(codex=codex),
                mock.patch.object(sys.modules[__name__], "_emit_context") as emit,
            ):
                self.assertEqual(_run({"prompt": "追加の依頼です"}, codex=codex), 0)
                emit.assert_called_once_with(expected)

    def test_empty_and_synthetic_prompts_are_silent(self):
        with mock.patch.object(sys.modules[__name__], "_emit_context") as emit:
            for codex in (False, True):
                for prompt in (None, "", "  ", SYNTHETIC_PREFIX + "done"):
                    _run({"prompt": prompt}, codex=codex)
                _run([], codex=codex)
            emit.assert_not_called()

    def test_only_model_context_is_emitted(self):
        for codex in (False, True):
            output = []
            with mock.patch.object(sys, "stdout", mock.Mock(write=output.append)):
                _run({"prompt": "作業を再開して"}, codex=codex)
            result = json.loads("".join(output))
            self.assertEqual(set(result), {"hookSpecificOutput"})
            self.assertEqual(
                result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
            )
            self.assertNotIn("ToolSearch", CODEX_NUDGE)


if __name__ == "__main__":
    sys.exit(main())
