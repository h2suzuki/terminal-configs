#!/usr/bin/env python3
r"""PreToolUse:^AskUserQuestion$ deny-gate — declare-and-proceed enforcement.

When the question is a DECIDABLE routing ("A経由かB経由か" / "どちらから調査") or
per-unit/per-batch confirmation ("この draft で良い?"), the gate requires the
declare-and-proceed skill be invoked in the current turn (∪ recent 5 min);
otherwise it DENIES via JSON permissionDecision so the 3-check (material 取得可? /
default 可? / parallel 両立可?) runs BEFORE the question, not after.

After invoking the skill the model either decides itself or, for a genuine
exception (user-taste / design-level / unrecoverable destructive-op pre-approval),
re-issues the question (now allowed). Such exceptions are phrased openly
("which X?") and do not match these narrow patterns, so they never need the skill.

Twin of skill_reminder_gate.py (turn-scan, 5-min window, JSON deny, fail-open),
scoped to one tool/skill. Narrow-recall/high-precision: a false-positive costs
one skill invoke + re-ask, a slip lets a decidable question reach the user ungated.

deploy: /etc/claude-code/hooks/ (copy_dir で自動)。canonical source は
files/claude_managed-hooks/。両者を同 session で同内容に保つ。
"""
from __future__ import annotations

import datetime
import json
import re
import sys
import time

TARGET_SKILL = "declare-and-proceed"
SKILL_WINDOW_SECONDS = 300  # 現 turn ∪ 直近 5 分 (skill_reminder_gate と同じ窓)

# Per-unit/per-batch 確認 ("これで良い?" 系) の closed form のみ拾う。 design は
# 通常 open form ("which X?") なので除外。 高確度語限定で false positive 抑制。
CONFIRM_PATTERNS: list[str] = [
    r"これで(良|よ)い",
    r"で(良|よ)いです(か|ね)",
    r"で(良|よ)い\s*[?？]",
    r"で問題(ありません|ない)\s*(か|ですか|でしょうか)",
    r"進めて(も)?(良|よ)い",
    r"この(まま|style|スタイル|形式|方針|案|内容|draft|wording)で(良|よ|問題な)",
    r"適用して(も)?(良|よ)い",
    r"してもよいですか",
]

# 調査/実行 route の binary/ternary ("どちらから" / "A 経由 か B 経由 か")。 design-level
# の "which architecture" を除外するため route 語に anchor する。
ROUTING_PATTERNS: list[str] = [
    r"どちら(から|を先に|で進め|を調査)",
    r"どっち(から|を先に)",
    r"経由\s*(で|か)[^。\n]{0,20}(経由|か[?？])",
    r"(から|を)\s*調査しますか",
    r"(から|を)\s*着手しますか",
    r"どこから\s*(調査|着手|始め|見)",
    r"先に\s*(調査|確認|読み?)\s*ますか",
    r"[ぁ-んァ-ヶ一-鿿\w]+するか\s*[ぁ-んァ-ヶ一-鿿\w]+するか",  # SKILL の正典 trigger
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
    """Return a citation string for the matched decidable pattern, or None."""
    m = CONFIRM_RE.search(text)
    if m:
        return "per-unit 確認: 「%s」" % m.group(0)
    m = ROUTING_RE.search(text)
    if m:
        return "routing: 「%s」" % m.group(0)
    return None


# --- current-turn skill scan ---

def _load_transcript(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _is_turn_boundary(obj: dict) -> bool:
    """human-input turn の起点か。isMeta(skill 展開) と tool_result 継続は起点でない。"""
    if obj.get("type") != "user" or obj.get("isMeta"):
        return False
    msg = obj.get("message", {})
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") != "tool_result" for b in content
        )
    return False


def _parse_ts(ts) -> float | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _skill_active(entries: list[dict], skill: str, now: float, window_s: int) -> bool | None:
    """target skill が 現 turn ∪ 直近 window_s 秒 に invoke 済か。boundary 不在は None (fail-open ALLOW)。

    Skill 呼出形: assistant tool_use, name=="Skill", input=={"skill":"<name>"}.
    """
    start_idx = -1
    for i in range(len(entries) - 1, -1, -1):
        if _is_turn_boundary(entries[i]):
            start_idx = i + 1
            break
    if start_idx == -1:
        return None
    cutoff = now - window_s
    for idx, obj in enumerate(entries):
        if obj.get("type") != "assistant":
            continue
        ep = _parse_ts(obj.get("timestamp"))
        if not (idx >= start_idx or (ep is not None and ep >= cutoff)):
            continue
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Skill":
                continue
            inp = block.get("input") or {}
            if isinstance(inp, dict) and inp.get("skill") == skill:
                return True
    return False


# --- deny emission (writing-skills の deny-wording 規律。文面は意図的に冗長・trim 禁止) ---

def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _deny(hit: str) -> None:
    _emit_deny(
        f"この AskUserQuestion は {hit} を含み、 自分で決められる routing / per-batch "
        f"確認に見えます。 編集前に /declare-and-proceed を当 turn で invoke して 3-check "
        f"(material が code/log/config/doc で取れるか / default で進めるか / parallel 実行で "
        f"両立できるか) を verbalize してください。 いずれか yes なら user に投げず自分で "
        f"決め、 1 unit 目で方針を宣言して proceed します。 genuine な user-taste / "
        f"design-level (architecture / naming / priority / scope) / 不可逆 destructive op "
        f"の pre-approval なら、 skill invoke 後そのまま AskUserQuestion が通ります "
        f"(hook 自身は質問を変更しません)。"
    )


def cmd_gate(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("tool_name") != "AskUserQuestion":
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    text = _question_text(tool_input)
    if not text:
        return
    hit = _detect(text)
    if hit is None:
        return  # decidable でない質問は素通り (genuine 例外を含む)
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return  # fail-open
    entries = _load_transcript(transcript_path)
    if not entries:
        return  # fail-open
    active = _skill_active(entries, TARGET_SKILL, time.time(), SKILL_WINDOW_SECONDS)
    if active is None or active:
        return  # fail-open (boundary 不在) / skill 当 turn invoke 済 → 通す
    _deny(hit)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        cmd_gate(payload)
    except Exception:
        pass  # fail-open: hook bug が tool を block しない
    return 0


if __name__ == "__main__":
    sys.exit(main())
