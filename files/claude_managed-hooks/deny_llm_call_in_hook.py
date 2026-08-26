#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit) hook: block LLM calls written into hooks.

Exit:
  0: allow the tool call or fail-open on parse/matcher errors.
  2: deny matching text in an in-scope hook file.

Always exits 0 on any parse / matcher error (fail-open).
"""

import json
import os
import re
import sys

LLM_CALL_RE = re.compile(r"\bclaude\s+(?:-p|--bg)\b")
EXEMPT_PREFIXES = ("claude-md-lint",)
# Keep the matcher literal for the orderer's mutation seam.
# fmt: off
HOOK_DIR_RE = re.compile(r"(?:claude_managed-hooks|claude_user-hooks|\.claude/hooks|claude-code/hooks|skel/hooks)/[^/]+$")
# fmt: on


def _texts(tool_name, tool_input):
    if tool_name == "Write":
        value = tool_input.get("content")
        return [value] if isinstance(value, str) else []
    if tool_name == "Edit":
        value = tool_input.get("new_string")
        return [value] if isinstance(value, str) else []
    texts = []
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            value = edit.get("new_string")
            if isinstance(value, str):
                texts.append(value)
    return texts


def _run(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    tool_name = payload.get("tool_name")
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not HOOK_DIR_RE.search(path):
        return 0
    basename = os.path.basename(path)
    if basename.startswith(EXEMPT_PREFIXES) or basename.endswith(
        (".test.py", ".mutants.py")
    ):
        return 0
    if any(LLM_CALL_RE.search(text) for text in _texts(tool_name, tool_input)):
        sys.stderr.write(
            "hook-llm-call: hook から LLM を呼ばない — 判断が要る検査は決定的な形へ落とすか hook の外へ出す (例外は claude-md-lint)\n"
        )
        return 2
    return 0


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
