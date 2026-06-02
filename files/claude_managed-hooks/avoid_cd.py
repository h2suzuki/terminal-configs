#!/usr/bin/env python3
"""
Avoid-cd hook for Claude Code.

PreToolUse hook on Bash. Detects commands starting with `cd ` (or
bare `cd`) and emits hookSpecificOutput.additionalContext suggesting
alternatives (pushd/popd, absolute paths, `git -C <repo>`).

Scope is intentionally narrow: only leading-`cd` is flagged. Embedded
forms (`; cd`, `bash -c 'cd ...'`, `(cd /tmp; ls)`) are NOT flagged
here; the runtime-symptom detector `detect_cwd_pollution.py`
(PostToolUseFailure) catches their consequences when they actually
pollute cwd. Broadening this prefix check would over-flag legitimate
subshell idioms.

The git-push allowlist exception (`git push origin main` must be
run as the bare string for the permission allowlist to match) does
not match `^cd\\s`, so no carve-out is required.

Exit code is always 0 (fail-open). Any unexpected exception during
parsing is swallowed silently so a hook bug never blocks Claude.
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


def _run(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("tool_name") != "Bash":
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return
    if not CD_PREFIX_RE.match(cmd):
        return
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


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        _run(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
