#!/usr/bin/env python3
"""PreToolUse:^(Task|Agent)$ hook — subagent-gate overuse warning (advisory).

Inspects tool_input (prompt / subagent_type / description) and emits a stderr
advisory when a spawn looks unlikely to amortize its context-switch +
result-integration + token overhead. Always exits 0
(warn-only) — the spawn proceeds; this hook is judgment-aid, not a gate.

Heuristic for "overuse candidate" (3 条件 AND, false-positive 抑制目的):
  - prompt < OVERUSE_PROMPT_THRESHOLD (200 chars) AND
  - subagent_type が general-purpose / 未指定 / empty (specialized domain
    agent は skill 条件 (d) を自動的に満たすので除外) AND
  - description が短い動詞句 (≤ DESC_WORD_THRESHOLD words) または
    DESC_PATTERN_RE (Read X / Check Y 等の lookup 動詞開始)

subagent-gate skill (4 条件 a-d) を mechanical proxy で補助。 judgment は
LLM 側に残す。

Exit:
  0: silent pass (not detected) or stderr advisory (warn, never block)。

parse / IO error は fail-open (exit 0) — 誤 block で user 作業を止めない。
"""

from __future__ import annotations

import json
import re
import sys


# Heuristic thresholds (tune via observation; intentionally conservative
# to suppress false positives — narrow recall, high precision).
OVERUSE_PROMPT_THRESHOLD = 200  # chars
DESC_WORD_THRESHOLD = 3  # description が "Read foo.py" 程度 (1-3 words) なら短い

# specialized 系 subagent_type は skill 条件 (d) を自動的に満たすので除外。
# general-purpose / empty / 不明 のみが warn 対象。
SPECIALIZED_AGENT_TYPES = {
    "explore",
    "code-reviewer",
    "security-review",
    "security-reviewer",
    "test-runner",
    "debugger",
}

# 単純 lookup 動詞で始まる description — 「単一 file / 単一 query で済む」 を
# 示唆する syntactic shape を補助 detect。 word-boundary anchored、 ascii のみ。
DESC_PATTERN_RE = re.compile(
    r"^\s*("
    r"read|check|look|find|grep|search|view|inspect|show|"
    r"open|cat|ls|list|count"
    r")\b",
    re.IGNORECASE,
)


def _is_short_description(desc: str) -> bool:
    """description が単純 lookup 動詞句か (≤3 words または lookup verb 開始)。"""
    if not isinstance(desc, str):
        return False
    stripped = desc.strip()
    if not stripped:
        return False
    # ≤N words、 または lookup verb 始まり (長い description も対象)
    return len(stripped.split()) <= DESC_WORD_THRESHOLD or bool(
        DESC_PATTERN_RE.match(stripped)
    )


def _is_overuse_candidate(
    prompt: str,
    subagent_type: str,
    description: str,
) -> bool:
    """3 条件 AND で判定 (false positive 抑制目的)。"""
    # (1) prompt 短い
    if not isinstance(prompt, str):
        prompt = ""
    if len(prompt) >= OVERUSE_PROMPT_THRESHOLD:
        return False
    # (2) subagent_type が specialized でない (general-purpose / empty)
    st_lower = (subagent_type or "").strip().lower()
    if st_lower in SPECIALIZED_AGENT_TYPES:
        return False
    # (3) description が短い動詞句
    if not _is_short_description(description):
        return False
    return True


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    tool_name = payload.get("tool_name", "")
    # settings.json の matcher で既に絞られているはずだが defensive check。
    if tool_name not in ("Task", "Agent"):
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    prompt = tool_input.get("prompt", "") or ""
    subagent_type = tool_input.get("subagent_type", "") or ""
    description = tool_input.get("description", "") or ""

    if not _is_overuse_candidate(prompt, subagent_type, description):
        return 0

    # advisory: writing-skills template-hook.md の「judge framing / corrective 直接書き」規律
    # 遵守 — hook を変更主体に誤読させず corrective を直接書き下す。 trim 抑止の冗長性は意図的。
    prompt_len = len(prompt)
    st_display = subagent_type if subagent_type else "(未指定)"
    sys.stderr.write(
        f"subagent-gate (warn): prompt 短い ({prompt_len}ch) + "
        f"subagent_type={st_display} で context overhead が payoff しない "
        f"可能性があります。 subagent-gate skill の 4 条件 "
        f"(a) parallelizable / (b) large output / (c) 3+ query 探索 / "
        f"(d) specialized agent のいずれが該当するか verbalize してから "
        f"proceed してください。 該当しなければ直接実行 (Read / Grep / Bash) "
        f"の方が cheap です。\n"
    )
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        return _run(payload)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
