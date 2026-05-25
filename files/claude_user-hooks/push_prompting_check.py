#!/usr/bin/env python3
"""
Stop hook (user scope): detect push-prompting language in the
assistant's last turn. Block (exit 2) when detected — git push is
exclusively user-driven per user CLAUDE.md "Commit 自律則" and the
commit-discipline skill (push silence clause).

Legacy: user CLAUDE.md § Commit 自律則 (push silence) より

Stdin: Stop payload JSON with `transcript_path`.

Transcript walking is identical to the org-scope stop_checks.py:
walk backwards to the most recent human-input user entry (content
is a str), then collect text from all assistant entries after it.

Exit:
  0: no push-prompting detected
  2: push-prompting detected (block + stderr explanation)

Always exits 0 on any parse / IO error (fail-open).
"""

from __future__ import annotations

import json
import re
import sys

# Catches phrasings like:
#   "次にpushしますか?" / "push しますか？"
#   "push しましょうか" / "push しますか"
#   "push する予定" / "push するつもり"
#   "push しる予定" / "push します予定"
PUSH_PROMPT_RE = re.compile(
    r"(次に)?push\s?(し|を)?ますか[?？]"
    r"|push\s?しま(しょう|す)か"
    r"|push\s?する(予定|つもり)"
    r"|push\s?(し|を)?(る|ます)予定"
)


def _load_transcript(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path) as f:
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


def _last_assistant_text(entries: list[dict]) -> str:
    """Concatenated text from assistant entries since the most recent
    human-input user entry (content is str)."""
    start_idx = 0
    for i in range(len(entries) - 1, -1, -1):
        obj = entries[i]
        if obj.get("type") != "user":
            continue
        msg = obj.get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            start_idx = i + 1
            break
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


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0
    entries = _load_transcript(transcript_path)
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
