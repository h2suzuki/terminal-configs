#!/usr/bin/env python3
"""PreToolUse hook: keep Playwright listener registrations scoped to snippets.

Exit:
  0: allow the tool call or fail-open on parse/matcher errors.
  2: deny a page.on() registration without page.off() in the same snippet.

Always exits 0 on any parse / matcher error (fail-open).
"""

import json
import re
import sys

ON_RE = re.compile(r"\bpage\.on\(")
OFF_RE = re.compile(r"\bpage\.off\(")
TOOL = "mcp__playwright__browser_run_code_unsafe"


def _run(payload: object) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != TOOL:
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    code = tool_input.get("code")
    if not isinstance(code, str) or not ON_RE.search(code):
        return 0
    if OFF_RE.search(code):
        return 0
    sys.stderr.write("playwright-listener: `page.on()` を張ったら同じ snippet 内で `page.off()` する — 残留 listener が MCP server を落とす\n")  # fmt: skip
    return 2


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
