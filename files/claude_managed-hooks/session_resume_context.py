#!/usr/bin/env python3
"""SessionStart hook: inject the prior session's last RECENT_TURNS turns as resume context (startup / clear only; fail-open)."""

from __future__ import annotations

import glob
import json
import os
import sys


HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
# resume context として読む直近 turn 数 (handoff は末尾数 turn に残る公算)
RECENT_TURNS = 3
MAX_INJECT_LEN = 4000  # 超過時は末尾 (= 最新 = handoff 側) を残して truncate
MIN_TEXT_LEN = 30  # これ未満の抽出 text は inject しない


def _encoded_project_id(cwd: str) -> str:
    """Match Claude Code's projects/<encoded-cwd>/ form: '/' -> '-'."""
    return cwd.replace("/", "-")


def _find_prior_session(cwd: str, current_session_id: str) -> str | None:
    project_dir = os.path.join(PROJECTS_DIR, _encoded_project_id(cwd))
    if not os.path.isdir(project_dir):
        return None
    files = glob.glob(os.path.join(project_dir, "*.jsonl"))
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    for f in files:
        sid = os.path.basename(f).rsplit(".", 1)[0]
        if sid != current_session_id:
            return f
    return None


_TAIL_BUFSIZE = 128 * 1024  # 後方読みブロック


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


def _load_tail(path: str, turns: int = 1, bufsize: int = _TAIL_BUFSIZE) -> list[dict]:
    """末尾から turn boundary を turns 個含むまで後方読みで返す; boundary が turns 未満なら全件。"""
    try:
        with open(path, "rb") as f:
            pos = f.seek(0, os.SEEK_END)
            pending = b""  # 行頭が手前ブロックにある途中行 (次の読みで結合)
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
                    if _is_turn_boundary(obj):
                        seen += 1
                        if seen >= turns:
                            tail.reverse()
                            return tail
            line = pending.strip()  # BOF: 先頭断片は完全な 1 行
            if line:
                try:
                    tail.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            tail.reverse()
            return tail  # boundary < turns: 集めた全件
    except OSError:
        return []


def _turns_text(entries: list[dict]) -> str:
    """entries (= 直近 turn 群) から user prompt と assistant text を時系列で抽出・整形。"""
    parts: list[str] = []
    for obj in entries:
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if (
            obj.get("type") == "user"
            and not obj.get("isMeta")
            and isinstance(content, str)
        ):
            t = content.strip()
            if t:
                parts.append("👤 " + t)
        elif obj.get("type") == "assistant" and isinstance(content, list):
            texts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
            ]
            joined = "\n".join(texts).strip()
            if joined:
                parts.append("🤖 " + joined)
    return "\n\n".join(parts)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    source = payload.get("source")
    if source not in ("startup", "clear"):
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return 0
    session_id = payload.get("session_id") or ""
    prior = _find_prior_session(cwd, session_id)
    if not prior:
        return 0
    text = _turns_text(_load_tail(prior, RECENT_TURNS)).strip()
    if len(text) < MIN_TEXT_LEN:
        return 0
    if len(text) > MAX_INJECT_LEN:  # 末尾 (最新=handoff 側) を残す
        text = "…(truncated)\n" + text[-MAX_INJECT_LEN:].lstrip()
    ctx = (
        "## Prior session tail (resume context)\n"
        f"\nSource: `{prior}`\n"
        f"\n前回 session の最終 {RECENT_TURNS} turn (👤=ユーザ / 🤖=assistant):\n"
        f"\n---\n{text}\n---\n"
        "\n必要なら上記 jsonl を Read で full log 確認、 "
        "`todos.md` / handoff doc も併せて参照。"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
