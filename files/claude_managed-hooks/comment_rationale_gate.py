#!/usr/bin/env python3
r"""PreToolUse:^(Edit|Write|MultiEdit)$ deny-gate — code comment rationale block.

writing-code §"Restrict comment length" forbids task / fix / 経緯 reference in
code comments ("rationale belongs in commit message, not in code"). This hook
scans Edit/Write/MultiEdit new_string for code-comment lines containing high-
precision rationale markers (avoids deprecation, migration aid, no longer
needed, instead of old, etc.) and denies, redirecting the rationale to the
commit message.

Narrow-recall/high-precision: false positive cost = 1 retry; a slip lets a
rationale comment land in code and rot vs. evolving callers / tools.

deploy: /etc/claude-code/hooks/  両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import json
import re
import sys

# Rationale markers — English + Japanese, high-precision (false positive cost = 1 retry).
RATIONALE_PATTERNS: list[str] = [
    r"avoids?\s+[^.\n]{0,40}?(deprecation|legacy|warning)",
    r"no\s+longer\s+(needed|required|necessary|used)",
    r"instead\s+of\s+[^.\n]{0,30}?(old|previous|legacy|former|npm\s+\w)",
    r"migration\s+aid",
    r"deprecated\s+(in\s+favor\s+of|since|because)",
    r"used\s+to\s+(use|have|do|call|require)",
    r"transitive\s+(dep|deprecation|tar|warning)",
    r"以前は",
    r"旧[\w\s]{0,10}(版|スクリプト|script)",
    r"移行(用|のため|完了|aid)",
    r"昔は",
    r"歴史的[な]?経緯",
]
RATIONALE_RE = re.compile("|".join(RATIONALE_PATTERNS), re.IGNORECASE)

# Comment-line prefixes for bash, JS, Python, C, SQL.
COMMENT_RE = re.compile(r"^\s*(#|//|--|/\*|\*\s)")


def _scan(text: str) -> str | None:
    """Return matched phrase if a comment line contains a rationale marker."""
    for line in text.splitlines():
        m = COMMENT_RE.match(line)
        if not m:
            continue
        comment = line[m.end() :]
        r = RATIONALE_RE.search(comment)
        if r:
            return r.group(0)
    return None


def _collect(tool_input: dict) -> list[str]:
    """Extract new content from Edit/Write/MultiEdit input shapes."""
    out: list[str] = []
    for key in ("new_string", "content"):
        v = tool_input.get(key)
        if isinstance(v, str):
            out.append(v)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict):
                v = e.get("new_string")
                if isinstance(v, str):
                    out.append(v)
    return out


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


# 文面は意図的に冗長 / trim せず維持 (writing-skills §Hook deny reason wording)。
def _deny(hit: str) -> None:
    _emit_deny(
        f"comment-rationale: 新規 code comment に 「{hit}」 を含みます "
        f"(writing-code §Restrict comment length: task / fix / 経緯への言及は "
        f"PR description / commit message に書き、 ファイルに残さない)。 "
        f"comment 内の rationale は code 進化と rot で乖離し、 未来の reader を "
        f"誤誘導する。 該当 phrase を comment から削除し、 rationale は commit "
        f"message に移してから再 Edit してください (hook 自身はファイルを変更しません)。 "
        f"genuine な WHY (非自明な不変条件 / 隠れた制約) を 1 行で書きたい場合は "
        f"rationale 語彙 (avoid / no longer / instead of / 以前は / 旧版 等) を "
        f"使わずに事実 framing で書き換える。"
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    for text in _collect(tool_input):
        hit = _scan(text)
        if hit:
            _deny(hit)
            return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # fail-open: hook bug が tool を block しない
        sys.exit(0)
