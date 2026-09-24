#!/usr/bin/env python3
"""Require the turn's own research before a question reaches the user.

PreToolUse:AskUserQuestion — deny a question whose turn searched nothing.
Stop — block a turn whose final text asks the user something the turn never researched.

Required channels are only the ones this host actually has: the lessons clone
(`claude-lessons-learned`), the issue tracker (`gh` on a GitHub remote / `glab` on a GitLab
remote) and `docs/` or a repo-root README*.md. A search that errors still counts — the gate
asks for the attempt, so a broken CLI can never deadlock the turn.

Exit:
  0: allow / pass / fail-open. A PreToolUse deny is JSON on stdout and also exits 0.
  2: Stop block, reason on stderr.

Always exits 0 on any parse / IO error (fail-open).

deploy: /etc/claude-code/hooks/  session で同内容に保つ。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

MEMORY_ROOT = (
    os.environ.get("QUESTION_RESEARCH_MEMORY_ROOT")
    or "/var/lib/claude-rag-memory/claude-lessons-learned"
)
TURN_WINDOW_BYTES = 512 * 1024
GIT_TIMEOUT_SECONDS = 5
PROMPT_PREFIXES = (
    "<task-notification>",
    "<system-reminder>",
    "<local-command",
    "Skill /",
    "(Re-invocation of /",
    "Stop hook feedback",
)

FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
QUESTION_ENDINGS = ("?", "？", "ますか", "ましょうか", "でしょうか")
QUESTION_MARKER = "[質問]"

LESSON_RE = re.compile(
    r"memory_surface\.py[^\n]{0,120}--search|claude-lessons-learned|claude-rag-memory|"
    + re.escape(MEMORY_ROOT)
)
ISSUE_RE = {
    "github": re.compile(
        r"\bgh\s+issue\b|\bgh\s+search\s+issues\b|\bgh\s+api\b[^\n]{0,160}issues"
    ),
    "gitlab": re.compile(r"\bglab\s+issue\b|\bglab\s+api\b[^\n]{0,160}issues"),
}
DOCS_RE = re.compile(r"\bdocs(?=[/\s\"']|$)|README(?:\.[\w-]+)?\.md", re.IGNORECASE)
LABELS = {"lessons": "教訓", "issues": "issue tracker", "docs": "docs / README"}


def _is_prompt(entry: dict) -> bool:
    """A human prompt: the turn starts after the last one of these."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content:
        return False
    return not content.startswith(PROMPT_PREFIXES)


def _turn_entries(path: str) -> list[dict] | None:
    """Entries after the last human prompt, or None when the turn cannot be established."""
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            start = max(0, stream.tell() - TURN_WINDOW_BYTES)
            stream.seek(start)
            data = stream.read()
    except OSError:
        return None
    if start and b"\n" in data:
        data = data.split(b"\n", 1)[1]
    entries = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    boundary = -1
    for index, item in enumerate(entries):
        if _is_prompt(item):
            boundary = index
    if boundary == -1:
        return None
    return entries[boundary + 1 :]


def _tool_blob(entries: list[dict]) -> str:
    """Every tool input of the turn, so a search counts wherever it was issued from."""
    parts = []
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                parts.append(json.dumps(block.get("input"), ensure_ascii=False))
    return "\n".join(parts)


def _final_text(payload: dict, entries: list[dict]) -> str:
    text = payload.get("last_assistant_message")
    if isinstance(text, str) and text:
        return text
    parts = []
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                value = block.get("text")
                if isinstance(value, str):
                    parts.append(value)
    return "\n".join(parts)


def _asks_user(text: str) -> bool:
    body = FENCE_RE.sub("", text)
    if QUESTION_MARKER in body:
        return True
    for line in body.splitlines():
        stripped = line.strip().rstrip("。！!").strip()
        if stripped.endswith(QUESTION_ENDINGS):
            return True
    return False


def _git(cwd: str, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _tracker(cwd: str) -> str | None:
    """The issue tracker reachable from here; a host without the CLI is exempt, not deadlocked."""
    remotes = _git(cwd, "remote", "-v")
    if "gitlab" in remotes and shutil.which("glab"):
        return "gitlab"
    if "github" in remotes and shutil.which("gh"):
        return "github"
    return None


def _docs_available(cwd: str) -> bool:
    root = _git(cwd, "rev-parse", "--show-toplevel") or cwd
    if os.path.isdir(os.path.join(root, "docs")):
        return True
    try:
        names = os.listdir(root)
    except OSError:
        return False
    return any(
        name.lower().startswith("readme") and name.lower().endswith(".md")
        for name in names
    )


def _missing(cwd: str, blob: str) -> tuple[list[str], str | None]:
    tracker = _tracker(cwd)
    missing = []
    if os.path.isdir(MEMORY_ROOT) and not LESSON_RE.search(blob):
        missing.append("lessons")
    if tracker and not ISSUE_RE[tracker].search(blob):
        missing.append("issues")
    if _docs_available(cwd) and not DOCS_RE.search(blob):
        missing.append("docs")
    return missing, tracker


# --- deny emission (writing-skills の deny-wording 規律。文面は意図的に冗長・trim 禁止) ---


def _hint(channel: str, tracker: str | None) -> str:
    if channel == "lessons":
        return (
            f'{LABELS["lessons"]}: `~/.claude/hooks/memory_surface.py --search "<keywords>"` '
            "(CLI が無ければ lessons clone を grep)"
        )
    if channel == "issues":
        if tracker == "gitlab":
            return f'{LABELS["issues"]}: `glab issue list --search "<keywords>"`'
        return (
            f'{LABELS["issues"]}: `gh issue list --state all --search "<keywords>"` '
            'または `gh search issues "<keywords>"`'
        )
    return f'{LABELS["docs"]}: `grep -rn "<keywords>" docs/ README.md`'


def _reason(missing: list[str], tracker: str | None) -> str:
    hints = "、 ".join(_hint(channel, tracker) for channel in missing)
    return (
        "question-research-gate: user へ質問する前に、当 turn 内で実施すべき調査が残っています — "
        f"{hints}。 推測で質問を投げると、既に答えの出ている事柄を user に聞き直すことになります。 "
        "まず上記を検索し、答えが出たなら質問せずそのまま proceed し、出なかったなら "
        "「何を検索して何が無かったか」を質問文に添えてください。 検索が error で終わっても、"
        "当 turn 内で実行した事実で gate は解除されます。 この host に存在しない channel は要求しません "
        "(上に挙がっていない channel は、済んでいるか、この host に無いかのどちらかです)。 "
        "hook 自身は質問も file も変更しません。"
    )


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _context(payload: dict) -> tuple[str, list[dict]] | None:
    transcript = payload.get("transcript_path")
    cwd = payload.get("cwd")
    if not isinstance(transcript, str) or not isinstance(cwd, str) or not cwd:
        return None
    entries = _turn_entries(transcript)
    return None if entries is None else (cwd, entries)


def _ask_gate(payload: dict) -> int:
    context = _context(payload)
    if context is None:
        return 0
    cwd, entries = context
    missing, tracker = _missing(cwd, _tool_blob(entries))
    if missing:
        _emit_deny(_reason(missing, tracker))
    return 0


def _stop_gate(payload: dict) -> int:
    if payload.get("stop_hook_active"):
        return 0  # 継続 Stop は同じ block を繰り返さない
    context = _context(payload)
    if context is None:
        return 0
    cwd, entries = context
    if not _asks_user(_final_text(payload, entries)):
        return 0
    missing, tracker = _missing(cwd, _tool_blob(entries))
    if not missing:
        return 0
    sys.stderr.write(_reason(missing, tracker) + "\n")
    return 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        if payload.get("tool_name") == "AskUserQuestion":
            return _ask_gate(payload)
        if payload.get("hook_event_name") == "Stop":
            # a one-off session spawned by another hook runs no session hooks
            return 0 if os.environ.get("CLAUDE_HOOK_CHILD") else _stop_gate(payload)
    except Exception:
        return 0  # fail-open: hook bug が tool / turn を止めない
    return 0


if __name__ == "__main__":
    sys.exit(main())
