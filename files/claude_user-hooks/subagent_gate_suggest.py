#!/usr/bin/env python3
"""UserPromptSubmit hook — subagent-gate spawn suggest (advisory).

Inspects the user prompt and, when subagent-friendly patterns appear
(sweeps / multi-file scans / parallel exploration 系), surfaces an
advisory via hookSpecificOutput.additionalContext so main can verbalize
whether to delegate to an Agent tool.

This hook does NOT decide for the LLM — it only surfaces option-space
that LLM tends to skip when it has already locked into "main で直接やる"
mode. Skill 4 条件 (a-d) の判定は最終的に LLM が行う。

Patterns: specific な compound 形のみ (false positive 抑制目的 — 「全部」
単独より「全 file」 / 「全件」 / 「すべての <ext>」 等の compound form)。
Origin: subagent-gate skill (4 条件 a-d) を mechanical proxy で補助。
memory_surface.py の context-inject 出力形式 (hookSpecificOutput) を流用。

Exit:
  0: 常に exit 0 (fail-open)。 detect 時は stdout に
     hookSpecificOutput.additionalContext JSON を出力、 非 detect 時は silent。

parse / IO error は fail-open (exit 0、 stdout 出力なし)。
"""
from __future__ import annotations

import json
import re
import sys


# subagent-friendly patterns — compound 形を要求して false positive を抑制。
# 各 pattern は対応する skill 条件 (a/b/c) を comment で明記し、 advisory
# 出力時に該当条件を user に提示できるよう group 化している。
#
# Pattern naming convention:
#   - 「全 file」 / 「全件」 / 「すべての .py」 系 = sweep (条件 b: large output)
#   - 「並列に / parallel に」 系 = (条件 a: parallelizable)
#   - 「複数 endpoint / N 個の file 比較」 系 = (条件 c: 3+ query 探索)
#   - 「codebase 全体で / 全 repo で」 系 = sweep (条件 b)
SUBAGENT_FRIENDLY_PATTERNS: list[str] = [
    # Sweep / 全件系 (条件 b)
    r"全\s?file\s?(を|で)?\s?(scan|読|read|確認|チェック|inspect)",
    r"全件\s?(確認|読|read|scan)",
    r"全部\s?(read|読)(む|んで|み出)",
    r"すべての\s?\.\s?[a-z]{1,5}\s?(file|を|で)",  # 「すべての .py で」
    r"すべての\s?file\s?(を|で)",
    r"全\s?repo(sitory)?\s?(で|を)?\s?(scan|grep|検索)",
    r"codebase\s?全体\s?(で|を)?\s?(scan|grep|検索|read)",
    r"repo\s?全体\s?(で|を)?\s?(scan|grep|検索)",
    # Parallel / 並列系 (条件 a)
    r"並列に\s?(調査|検索|read|scan|実行|処理)",
    r"parallel\s?(に|で)\s?(調査|検索|read|scan|実行|処理|分け)",
    r"同時に\s?(調査|検索|複数)",
    # 複数対象系 (条件 c — 3+ query)
    r"複数\s?(の\s?)?endpoint",
    r"複数\s?(の\s?)?file\s?(を|の)\s?比較",
    r"複数\s?(の\s?)?(repo|repository)\s?(を|で)",
    r"[3-9]\s?(個|つ|件)\s?以上\s?の\s?file",
    r"N\s?個\s?の\s?file\s?を\s?比較",
    # Exploration系 (条件 c)
    r"どこに\s?(あるか|定義されて)\s?(分から|不明|わから)",
    r"探索範囲\s?(が)?\s?(不明|広い)",
]
SUBAGENT_FRIENDLY_RE = re.compile(
    "|".join(SUBAGENT_FRIENDLY_PATTERNS),
    re.IGNORECASE,
)


def _detect(prompt: str) -> str | None:
    """Return matched substring (for advisory citation) or None."""
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    m = SUBAGENT_FRIENDLY_RE.search(prompt)
    if not m:
        return None
    return m.group(0)


def _emit_advisory(matched: str) -> None:
    """Emit hookSpecificOutput.additionalContext (memory_surface.py 流用形式)。"""
    # writing-skills template-hook.md の 「judge framing / corrective action
    # 直接書き」 規律遵守 — hook を変更主体に誤読させず、 corrective を直接
    # 書き下す。 trim 抑止の冗長性は意図的に残す。
    context = (
        f"subagent-gate (suggest): user 要求に 「{matched}」 を検出しました。 "
        f"subagent-gate skill 4 条件のうち (b) large output / "
        f"(c) 3+ query 探索 / (a) 並列実行 のいずれかに該当する可能性が "
        f"あります。 main で直接 Read / Grep を連発するよりも、 Agent tool "
        f"で subagent (Explore / general-purpose) に delegate して結論だけ "
        f"受け取る選択肢を verbalize してから proceed してください。 "
        f"単一 file / 単一 query で完結するなら subagent は不要です。"
    )
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    prompt = payload.get("prompt") or ""
    matched = _detect(prompt)
    if matched is None:
        return 0
    _emit_advisory(matched)
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
