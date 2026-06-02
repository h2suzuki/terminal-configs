#!/usr/bin/env python3
"""UserPromptSubmit hook — subagent-gate spawn suggest (advisory).

subagent-friendly pattern 検出時に hookSpecificOutput.additionalContext で
advisory を出す。 does NOT decide for the LLM — option-space を surface する
だけで、 4 条件 (a-d) の判定は LLM が行う。

Patterns: compound 形のみ requiring (false positive 抑制目的)。
subagent-gate skill (4 条件 a-d) の mechanical proxy。

Exit:
  0: 常に exit 0 (fail-open)。 detect 時のみ stdout に JSON 出力、 他は silent。
     parse / IO error も fail-open (exit 0、 出力なし)。
"""
from __future__ import annotations

import json
import re
import sys


# compound 形を要求して false positive を抑制。 skill 条件 (a/b/c) ごとに
# group 化し、 advisory で該当条件を提示できるよう inline comment で明記。
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
    """Emit hookSpecificOutput.additionalContext。"""
    # writing-skills 規律: hook を変更主体に誤読させず corrective を直接書き下す。
    # context の冗長性は trim 抑止のため意図的に残す。
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
