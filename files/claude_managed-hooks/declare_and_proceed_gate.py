#!/usr/bin/env python3
"""PreToolUse:^AskUserQuestion$ hook — declare-and-proceed nudge (advisory).

Fires before an AskUserQuestion call. When the question text looks like a
DECIDABLE routing question ("A 経由 か B 経由 か" / "どちらから") or a
per-unit/per-batch confirmation ("この style で良い?" / "進めて良い?"), emits a
model-visible hookSpecificOutput.additionalContext nudge toward
/declare-and-proceed. Always non-blocking (no permissionDecision) — the
question still proceeds; this is judgment-aid, not a gate. The genuine
exceptions (user-taste / design-level / destructive-op pre-approval) use
open "which X?" phrasing and do not match these narrow patterns.

Twin of subagent_gate_warn.py (same narrow-recall / high-precision / fail-open
philosophy), but routed through additionalContext (model-visible, injected next
to the tool result) rather than stderr, so the nudge reaches Claude's judgment.

Exit:
  0: silent pass (no decidable-question pattern) or advisory emitted.

parse / IO error は fail-open (exit 0, 出力なし)。 block しない設計なので誤 block
の懸念は無く、 advisory の取りこぼしを許容する側に倒す。
"""
from __future__ import annotations

import json
import re
import sys


# Per-unit / per-batch confirmation — "これで良い?" 系。 design 質問は通常
# open form ("which X?") なので、 yes/no 承認を求める closed form のみ拾う。
# 高確度語に限定 (false positive 抑制)。
CONFIRM_PATTERNS: list[str] = [
    r"これで(良|よ)い",
    r"で(良|よ)いです(か|ね)",
    r"で(良|よ)い\s*[?？]",
    r"で問題(ありません|ない)\s*(か|ですか|でしょうか)",
    r"進めて(も)?(良|よ)い",
    r"この(まま|style|形式|方針|案|内容|draft|wording)で(良|よ|問題な)",
    r"適用して(も)?(良|よ)い",
    r"してもよいですか",
    r"このスタイルで",
]

# Routing — investigation/execution route の binary/ternary。 "どちらから" /
# "A 経由 か B 経由 か" 系。 design-level の "which architecture" は除外したいので
# route 語 (経由/から調査/から着手/どちら(から)) に anchor する。
ROUTING_PATTERNS: list[str] = [
    r"どちら(から|を先に|で進め|を調査)",
    r"どっち(から|を先に)",
    r"経由\s*(で|か)[^。\n]{0,20}(経由|か[?？])",
    r"(から|を)\s*調査しますか",
    r"(から|を)\s*着手しますか",
    r"どこから\s*(調査|着手|始め|見)",
    r"先に\s*(調査|確認|読み?)\s*ますか",
]

CONFIRM_RE = re.compile("|".join(CONFIRM_PATTERNS), re.IGNORECASE)
ROUTING_RE = re.compile("|".join(ROUTING_PATTERNS), re.IGNORECASE)


def _question_text(tool_input: dict) -> str:
    """Concatenate every question / header / option label for scanning."""
    parts: list[str] = []
    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        return ""
    for q in questions:
        if not isinstance(q, dict):
            continue
        for key in ("question", "header"):
            v = q.get(key)
            if isinstance(v, str):
                parts.append(v)
        options = q.get("options")
        if isinstance(options, list):
            for opt in options:
                if isinstance(opt, dict) and isinstance(opt.get("label"), str):
                    parts.append(opt["label"])
    return "\n".join(parts)


def _detect(text: str) -> str | None:
    """Return a citation string for the matched pattern, or None."""
    m = CONFIRM_RE.search(text)
    if m:
        return "per-unit 確認: 「%s」" % m.group(0)
    m = ROUTING_RE.search(text)
    if m:
        return "routing: 「%s」" % m.group(0)
    return None


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "AskUserQuestion":
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    text = _question_text(tool_input)
    if not text:
        return 0
    hit = _detect(text)
    if hit is None:
        return 0
    # advisory (writing-skills template-hook.md: hook を変更主体に誤読させず
    # corrective を直接書き下す。 trim 抑止の冗長性は意図的)。
    context = (
        f"declare-and-proceed (nudge): この質問は {hit} を含み、 自分で決められる "
        f"routing / per-batch 確認の可能性があります。 /declare-and-proceed の 1 拍 "
        f"verbalize を行ってください — material が code/log/config/doc で取れるか、 "
        f"default で進めるか、 parallel 実行で両立できるか。 いずれかで yes なら "
        f"user に投げず自分で決め、 1 unit 目で方針を verbalize 宣言して proceed し、 "
        f"事後 chat log review に委ねる。 genuine な user-taste / design-level "
        f"(architecture / naming / priority / scope) / 不可逆 destructive op の "
        f"pre-approval のみ ask に残す。 該当するならこの質問はそのまま続行で構いません。"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
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
