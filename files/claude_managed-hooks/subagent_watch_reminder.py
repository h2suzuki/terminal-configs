#!/usr/bin/env python3
"""PreToolUse:^(Task|Agent)$ hook — remind the parent to schedule its own check on a long-running subagent.

Once the spawning turn ends, only the completion notice wakes the parent; a scheduled
prompt is the one thing that brings it back while the subagent still runs.
Fail-open on unreadable input.
"""

from __future__ import annotations

import json
import sys

# Deliberately concrete: a rule without a wake-up action is forgotten when the turn ends.
CONTEXT = (
    "subagent-watch: この subagent が長時間 (目安 15 分超) かかりそうなら、起動した turn のうちに "
    "CronCreate で 15 分おきの確認 (例: cron `*/15 * * * *`、prompt は「agent_coord の sessions と peek で "
    "子の状態を確かめ、止まっていれば原因を調べる」) を登録してください。turn が終わると、完了通知か "
    "この cron 以外にあなたを起こすものはありません。完了通知を受けたら CronDelete で消してください。"
)


def _run(payload: object) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") not in (
        "Task",
        "Agent",
    ):
        return 0
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": CONTEXT,
        }
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    return 0


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
