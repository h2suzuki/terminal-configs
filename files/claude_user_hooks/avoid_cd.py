#!/usr/bin/env python3
"""
Avoid-cd hook for Claude Code.

Legacy: user CLAUDE.md「Bash 運用」より

PreToolUse hook on Bash. Detects commands starting with `cd ` (or
bare `cd`) and emits hookSpecificOutput.additionalContext suggesting
alternatives (pushd/popd, absolute paths, `git -C <repo>`).

The git-push allowlist exception (`git push origin main` must be
run as the bare string for the permission allowlist to match) is
documented in the warning text; the hook does not need a separate
carve-out because that command does not match ^cd\\s.

Exit code is always 0 (fail-open).
"""

from __future__ import annotations

import json
import re
import sys

CD_PREFIX_RE = re.compile(r"^\s*cd(\s|$)")


def _emit(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not CD_PREFIX_RE.match(cmd):
        return 0
    snippet = cmd if len(cmd) <= 80 else cmd[:80] + "..."
    _emit(
        f"cd で始まる Bash コマンドが検出されました: `{snippet}`\n"
        "次のいずれかへの置換を検討してください:\n"
        "- 絶対パスで直接コマンドを書く (例: `mkdir /a/b/c && mv /a/b/x /a/b/c/`)\n"
        "- git なら `git -C <repo>` を使う (例: `git -C /repo status`)\n"
        "- どうしても cd が必要なら `pushd` / `popd` / `dirs` でスタックを意識する\n"
        "例外: `git push origin main` のみ allowlist 文字列マッチのため `-C` 抜き必須 "
        "(詳細は project memory `feedback_git_push_allowlist.md`)。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
