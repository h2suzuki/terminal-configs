#!/usr/bin/env python3
"""SessionStart hook: inject the prior session's last assistant text as resume context (startup / clear only; fail-open)."""

from __future__ import annotations

import glob
import json
import os
import sys


HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
MAX_INJECT_LEN = 2000  # truncate prior tail at this length
MIN_TEXT_LEN = 30  # skip if last assistant text is shorter than this


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


def _extract_last_assistant_text(jsonl_path: str) -> str:
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "assistant":
            continue
        content = obj.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        texts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
        ]
        if texts:
            return "\n".join(texts)
    return ""


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
    text = _extract_last_assistant_text(prior).strip()
    if len(text) < MIN_TEXT_LEN:
        return 0
    if len(text) > MAX_INJECT_LEN:
        text = text[:MAX_INJECT_LEN].rstrip() + "\n…(truncated)"
    ctx = (
        "## Prior session tail (resume context)\n"
        f"\nSource: `{prior}`\n"
        "\n前回 session の最後の assistant 発話:\n"
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
