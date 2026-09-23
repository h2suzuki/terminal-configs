#!/usr/bin/env python3
"""PreToolUse nudge: repo-root sandbox dotfile shadows look untracked but are not; stop investigating.

Transcript assistant text often lags the tool call, so this scans prior text blocks (past
tool_result-only entries) and, for Bash, the command itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

STATE_DIR = os.environ.get("SANDBOX_SHADOW_NUDGE_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "sandbox_shadow_nudge"
)
TAIL_BYTES = 256 * 1024  # transcript window read backwards for the current utterance

SHADOW_NAMES = (
    ".bashrc",
    ".bash_profile",
    ".profile",
    ".zshrc",
    ".zprofile",
    ".gitconfig",
    ".gitmodules",
    ".ripgreprc",
    ".idea",
    ".vscode",
    ".mcp.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/agents",
    ".claude/commands",
    ".claude/hooks",
    ".claude/skills",
    ".claude/workflows",
    ".claude/routines",
    ".claude/output-styles",
    ".claude/launch.json",
    ".claude/loop.md",
    ".claude/scheduled_tasks.json",
)
CUE_WORDS = (
    "未追跡",
    "untracked",
    "??",
    "マウント点",
    "mount point",
    "文字デバイス",
    "char device",
    "character device",
    "shadow",
    "/dev/null",
)
# an immediate ~/ or /home/<user>/ prefix names a real HOME file, not the repo-root shadow
HOME_PREFIX_RE = re.compile(r"(?:~|/home/[^/\s]+)/\Z")
CUE_RE = re.compile("|".join(re.escape(w) for w in CUE_WORDS), re.IGNORECASE)

MSG = (
    "sandbox-shadow: repo 直下の .bashrc / .claude/settings.json 等の未追跡表示は sandbox が "
    "HOME の dotfile を /dev/null で shadow したもの。調査を即打ち切って元の作業へ戻れ "
    "(消さない・ignore しない・upstream を探さない)。\n"
    "教訓: /var/lib/claude-rag-memory/claude-lessons-learned/org/feedback_sandbox_dotfile_shadow.md"
)


def _shadow_hit(text: str) -> str | None:
    """First shadow name literally present outside a real HOME path, or None."""
    for name in SHADOW_NAMES:
        for m in re.finditer(re.escape(name), text):
            if not HOME_PREFIX_RE.search(text[: m.start()]):
                return name
    return None


def _tail_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        start = max(0, f.tell() - TAIL_BYTES)
        f.seek(start)
        data = f.read()
    if start:  # the first line at a non-zero offset may be a partial line: drop it
        data = data.split(b"\n", 1)[1] if b"\n" in data else b""
    return data


def _is_real_prompt(entry: dict) -> bool:
    """A human turn (string content, or a list holding a text block) versus a tool_result-only entry."""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def _scan_blocks(path: str) -> list[str]:
    """Assistant text blocks from the tail back to the last real prompt; tool_result-only entries are skipped, not a boundary."""
    try:
        raw = _tail_bytes(path)
    except OSError:
        return []
    lines = raw.decode("utf-8", errors="replace").splitlines()
    blocks: list[str] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "user":
            if _is_real_prompt(entry):
                break
            continue  # tool_result-only: not yet updated with fresh text, keep scanning past it
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    blocks.append(text)
    blocks.reverse()
    return blocks


def _session_key(session_id: object) -> str:
    if not isinstance(session_id, str) or not session_id:
        return "unknown"
    return re.sub(r"[^\w.-]", "_", session_id)[:80]


def _already_nudged(session_id: object, digest: str) -> bool:
    try:
        with open(
            os.path.join(STATE_DIR, _session_key(session_id)), encoding="utf-8"
        ) as f:
            return digest in f.read().split()
    except OSError:
        return False


def _mark_nudged(session_id: object, digest: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(
        os.path.join(STATE_DIR, _session_key(session_id)), "a", encoding="utf-8"
    ) as f:
        f.write(digest + "\n")


def _emit() -> None:
    payload = {
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": MSG}
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


CMD_MARKER = "bash-cmd-nudged"  # one flag per session; not a sha256 digest, so it can't collide with one


def _run(payload: dict) -> int:
    session_id = payload.get("session_id")
    fired = False
    to_mark: list[str] = []

    transcript_path = payload.get("transcript_path")
    if isinstance(transcript_path, str) and transcript_path:
        for block in _scan_blocks(transcript_path):
            if not block or _shadow_hit(block) is None or not CUE_RE.search(block):
                continue
            digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
            if not _already_nudged(session_id, digest):
                fired = True
                to_mark.append(digest)

    if payload.get("tool_name") == "Bash":
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if (
            isinstance(command, str)
            and _shadow_hit(command) is not None
            and not _already_nudged(session_id, CMD_MARKER)
        ):
            fired = True
            to_mark.append(CMD_MARKER)

    if fired:
        _emit()
        for key in to_mark:
            _mark_nudged(session_id, key)
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        return _run(payload) if isinstance(payload, dict) else 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
