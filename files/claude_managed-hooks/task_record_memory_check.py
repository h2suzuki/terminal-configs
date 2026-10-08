#!/usr/bin/env python3
"""PreToolUse:mcp__mytask__TaskCreate hook — surface the Stop-route lesson matching a task record (never denies, fail-open)."""

from __future__ import annotations

import json
import sys
import unicodedata

TOOL = "mcp__mytask__TaskCreate"


def _run(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != TOOL:
        return
    tool_input = payload.get("tool_input")
    content = tool_input.get("content") if isinstance(tool_input, dict) else None
    if not isinstance(content, str):
        return
    import stop_checks  # lazy: a missing sibling must fail open, not crash at load

    text = unicodedata.normalize("NFKC", content).lower()
    project_id = stop_checks._project_id(payload.get("cwd"))
    best = None
    for root in stop_checks._memory_roots():
        for check, path, keywords in stop_checks._memory_entries(root, project_id):
            hits = stop_checks._keyword_hits(keywords, text)
            if hits and (best is None or hits > best[0]):
                best = (hits, check, path)
    if best is None:
        return
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": f"memory-reminder (task record): {best[1]} ({best[2]})",
        }
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")


def main() -> int:
    try:
        _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
