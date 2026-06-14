#!/usr/bin/env python3
"""
Push-prompting guard (user scope). git push is exclusively user-driven per
user CLAUDE.md "Commit 自律則" / commit-discipline skill (push silence).

Two entry points share the one regex:
- Stop: detect push-prompting in the assistant's last-turn TEXT and block.
- PreToolUse:AskUserQuestion: the Stop walk inspects text blocks only, so a
  solicitation phrased as a question/option evades it; scan tool_input here.

Stdin: Stop payload (`transcript_path`) or PreToolUse payload (`tool_name` +
`tool_input`).

Transcript walk (identical to org-scope stop_checks.py): backwards
to the most recent human-input user entry (content is str), then
collect text from assistant entries after it. No such entry
(corrupted / partial) → return empty rather than fall-broad scan.

Exit:
  0: no push-prompting detected
  2: push-prompting detected (block + stderr explanation)

Always exits 0 on any parse / IO error (fail-open).
"""

from __future__ import annotations

import json
import os
import re
import sys

# Case-insensitive. Factual reports (`push しました`, `未 push です`) are
# deliberately NOT matched — the same-clause `[^。、\n]` bound keeps the solicitation alternation tight.
PUSH_PROMPT_RE = re.compile(
    r"(次に)?push\s?(し|を)?ますか[?？]"
    r"|push\s?しま(しょう|す)か"
    r"|push\s?する(予定|つもり|タイミング|時|とき|なら|べき|か[?？])"
    r"|push\s?して?も?(い|良|よ)い?ですか"
    r"|push\s?(する|して)[^。、\n]{0,16}(お知らせ|教えて|指示|連絡|おっしゃって)",
    re.IGNORECASE,
)


_TAIL_BUFSIZE = 128 * 1024  # 実測 2545 turn の mean≈110KB / p75≈119KB を 1 read で覆う


def _is_prompt(obj: dict) -> bool:
    msg = obj.get("message", {})
    return obj.get("type") == "user" and isinstance(msg.get("content"), str)


def _load_tail(path: str, turns: int = 1, bufsize: int = _TAIL_BUFSIZE) -> list[dict]:
    """末尾から turn boundary を turns 個含むまで後方読みで返す; boundary が turns 未満なら全件。"""
    try:
        with open(path, "rb") as f:
            pos = f.seek(0, os.SEEK_END)
            pending = b""  # 行頭が手前ブロックにある途中行 (次の読みで結合される)
            tail: list[dict] = []  # newest-first
            seen = 0
            while pos > 0:
                step = min(bufsize, pos)
                pos -= step
                f.seek(pos)
                parts = (f.read(step) + pending).split(b"\n")
                pending = parts.pop(0)
                for raw in reversed(parts):
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tail.append(obj)
                    if _is_prompt(obj):
                        seen += 1
                        if seen >= turns:
                            tail.reverse()
                            return tail
            line = pending.strip()  # BOF: 先頭断片はこの時点で完全な 1 行
            if line:
                try:
                    tail.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            tail.reverse()
            return tail  # boundary < turns: 集めた全件
    except OSError:
        return []


def _last_assistant_text(entries: list[dict]) -> str:
    """Assistant text since the last human-input user entry; empty if no boundary (avoids fall-broad scan)."""
    start_idx = -1
    for i in range(len(entries) - 1, -1, -1):
        obj = entries[i]
        if obj.get("type") != "user":
            continue
        msg = obj.get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            start_idx = i + 1
            break
    if start_idx == -1:
        return ""

    parts: list[str] = []
    for obj in entries[start_idx:]:
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def _scan_ask_tool(tool_input: object) -> int:
    """PreToolUse:AskUserQuestion — scan question/option text the Stop walk can't see."""
    if not isinstance(tool_input, dict):
        return 0
    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        return 0
    for q in questions:
        if not isinstance(q, dict):
            continue
        texts = [q.get("question", ""), q.get("header", "")]
        opts = q.get("options")
        if isinstance(opts, list):
            for o in opts:
                if isinstance(o, dict):
                    texts.extend([o.get("label", ""), o.get("description", "")])
        for t in texts:
            m = PUSH_PROMPT_RE.search(str(t))
            if m:
                sys.stderr.write(
                    f"push-prompting detected in AskUserQuestion: 「{m.group(0)}」 "
                    f"(User CLAUDE.md §Commit 自律則 / commit-discipline skill)。 git "
                    f"push は user 指示を待ち、 こちらから提案 / 確認 / 予定告知しない。 "
                    f"該当の質問 / 選択肢から push の話題を外して問い直してください。\n"
                )
                return 2
    return 0


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") == "AskUserQuestion":
        return _scan_ask_tool(payload.get("tool_input"))
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0
    entries = _load_tail(transcript_path)
    if not entries:
        return 0
    text = _last_assistant_text(entries)
    if not text:
        return 0
    m = PUSH_PROMPT_RE.search(text)
    if not m:
        return 0
    sys.stderr.write(
        f"push-prompting detected: 「{m.group(0)}」 と発話 (User CLAUDE.md "
        f"§Commit 自律則 / commit-discipline skill)。 git push は user "
        f"指示を待ち、 こちらから提案 / 確認 / 予定告知しない。 該当発話を "
        f"取り消して再応答してください。\n"
    )
    return 2


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
