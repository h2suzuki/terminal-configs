#!/usr/bin/env python3
"""PreToolUse nudge: steer background shell work to bg_watch; never blocks, silent on any failure."""

from __future__ import annotations

import fnmatch
import json
import re
import sys

# a lone "&" ending the command or sitting just before ";" / a newline; not "&&", "2>&1", "&>" or "|&"
LONE_AMPERSAND_RE = re.compile(r"(?<![&>|])&(?![&>])\s*(?:;|\n|\Z)")
DETACH_WORD_RE = re.compile(r"(?<![\w.-])(?:nohup|setsid|disown)(?![\w.-])")
MSG = (
    "bg-watch: 長時間の処理は `bg_watch -- <コマンド>` で包んで run_in_background で起動してください。"
    "15 分ごとと終了時に、あなたへ状況の知らせが届きます。"
    "& / nohup / setsid での切り離しは使わないでください（追跡されず放置されます）。"
)


def detaches(command: str) -> bool:
    return bool(LONE_AMPERSAND_RE.search(command) or DETACH_WORD_RE.search(command))


def excluded(command: str, settings: str | None) -> bool:
    """Commands run outside the sandbox stay unwrapped: bg_watch in front would pull them in."""
    if not settings:
        return False
    try:
        with open(settings, encoding="utf-8") as handle:
            globs = json.load(handle)["sandbox"]["excludedCommands"]
        return any(fnmatch.fnmatchcase(command, glob) for glob in globs)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def guidance(payload: object, exclusions: str | None = None) -> str | None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or "bg_watch" in command:
        return None
    if excluded(command, exclusions):
        return None
    if tool_input.get("run_in_background") is True or detaches(command):
        return MSG
    return None


def main() -> int:
    try:
        args = sys.argv[1:]
        exclusions = (
            args[args.index("--exclusions") + 1] if "--exclusions" in args else None
        )
        message = guidance(json.loads(sys.stdin.read() or "{}"), exclusions)
        if message:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": message,
                }
            }
            sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
