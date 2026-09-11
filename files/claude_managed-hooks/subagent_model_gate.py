#!/usr/bin/env python3
"""PreToolUse:^(Task|Agent)$ hook — deny a subagent spawn that never chose a model.

An omitted `model` silently inherits the parent (often the most expensive
model) for work a smaller one would do. Choosing the parent model is fine;
not choosing is not. Forks are exempt: they always run on the parent model.
Fail-open on unreadable input.
"""

from __future__ import annotations

import json
import sys

# Deliberately long: it tells the model what to do next, not just what went wrong.
REASON = (
    "subagent-model-gate: `model` が未指定です。 未指定は親 model の無検討継承になり、 "
    "search / review / 要約なら haiku か sonnet で足ります。 作業に必要な model を判断して "
    "`model` を明示指定してから再実行してください (検討の結果 親と同じ model を選ぶのは問題ありません。 "
    'その場合も名前を明示します)。 fork (`subagent_type: "fork"`) は親 model 固定なので対象外です。'
)


def _run(payload: object) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") not in (
        "Task",
        "Agent",
    ):
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    if str(tool_input.get("subagent_type") or "").strip() == "fork":
        return 0
    if str(tool_input.get("model") or "").strip():
        return 0
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": REASON,
                }
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
