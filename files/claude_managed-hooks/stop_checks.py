#!/usr/bin/env python3
"""
Combined Stop hook for org-managed Claude Code:

  H1 empty-learning (enforcement, exit 2):
    Detect 「学習した」「次回から気をつけ」「反省」 系 assistant text;
    block unless a memory file (~/.claude/global-memory/**/*.md or
    */memory/**/*.md) was Written/Edited/MultiEdited in this turn.

  H7 deferral (warning-only, exit 0):
    Detect 「後で対処」「別タスクに切り出」「TODO として」 系 text;
    warn unless a TaskCreate/TaskUpdate/TodoWrite call OR Write/Edit
    on todos.md happened in this turn.

  H8 claim-without-evidence (warning-only, exit 0):
    Detect 「不明」「該当なし」「未確認」「わかりません」 系 text;
    warn unless any of Read/Grep/Glob/WebSearch/WebFetch was used
    in this turn.

Legacy: org CLAUDE.md §報告・応答 (空学習禁止 + claim-without-evidence)
+ §計画と遂行 (deferral) より

Stop hook input: JSON via stdin with session_id, transcript_path,
hook_event_name = "Stop".

Transcript format: JSONL where each line is a dict with `type`
(user / assistant / system / ...) and `message` (containing role,
content). For user entries, content is a str when it is a human
prompt and a list (of tool_result blocks) when it is a tool
result. For assistant entries, content is a list of text /
thinking / tool_use blocks.

Current-turn boundary: walk backwards in the transcript to the
most recent user entry whose content is a str (= human prompt),
then consider all assistant entries after that index as the
current turn.

Exit:
  0: no enforcement triggered (warnings may be emitted on stderr)
  2: H1 triggered (empty-learning without memory persistence)

Always exits 0 on any parse / IO error (fail-open).
"""

from __future__ import annotations

import json
import re
import sys

EMPTY_LEARNING_RE = re.compile(
    r"学習した|次回(から)?(は)?気をつけ|もう間違え(ない|ません)|反省し|今後は気をつけ"
)
DEFERRAL_RE = re.compile(
    r"後で(対処|やる|考える)|別タスクに(切り出|分け)|今は(処置|対処)しません|後回し|TODO として|次回(に)?(対応|やる)"
)
CLAIM_RE = re.compile(
    r"不明|該当なし|存在しません|未確認|わかりません|分かりません"
)

# Memory file path heuristics. Matches both the global memory dir
# (`~/.claude/global-memory/...`) and per-project memory subtrees
# (`.../memory/...`).
MEMORY_PATH_RE = re.compile(r"(global-memory|/memory/)")

# A todos.md anywhere in the path counts as a deferral sink.
TODOS_PATH_RE = re.compile(r"todos\.md$")

# Tools that constitute "evidence collection" for claim-without-evidence.
EVIDENCE_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch"}

# Tools that constitute "deferral registration" for the H7 check
# (TodoWrite is kept for legacy transcripts).
TASK_TOOLS = {"TaskCreate", "TaskUpdate", "TodoWrite"}

# Tools whose file_path / notebook_path inputs are recorded for
# memory- and todos-path matching.
PATH_RECORDING_TOOLS = {"Write", "Edit", "MultiEdit"}


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


def _current_turn(entries: list[dict]) -> tuple[str, set[str], list[str]]:
    """Return (assistant_text, tool_names, tool_paths) for the current turn.

    Current turn starts after the most recent user entry whose
    `message.content` is a string (= human prompt; tool_result entries
    use a list of content blocks).
    """
    start_idx = 0
    for i in range(len(entries) - 1, -1, -1):
        obj = entries[i]
        if obj.get("type") != "user":
            continue
        msg = obj.get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            start_idx = i + 1
            break

    text_parts: list[str] = []
    tool_names: set[str] = set()
    tool_paths: list[str] = []

    for obj in entries[start_idx:]:
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(str(block.get("text", "")))
            elif btype == "tool_use":
                name = str(block.get("name", ""))
                if name:
                    tool_names.add(name)
                if name in PATH_RECORDING_TOOLS:
                    inp = block.get("input") or {}
                    if isinstance(inp, dict):
                        fp = inp.get("file_path") or inp.get("notebook_path")
                        if isinstance(fp, str):
                            tool_paths.append(fp)

    return "\n".join(text_parts), tool_names, tool_paths


def _check(
    text: str, tool_names: set[str], tool_paths: list[str]
) -> tuple[int, list[str]]:
    """Return (exit_code, stderr_lines)."""
    warnings: list[str] = []
    blocking: list[str] = []

    # H1 empty-learning (enforcement)
    m = EMPTY_LEARNING_RE.search(text)
    if m:
        memory_updated = any(MEMORY_PATH_RE.search(p) for p in tool_paths)
        if not memory_updated:
            blocking.append(
                f"empty-learning: 「{m.group(0)}」 と発話したが当ターンで "
                f"memory file (~/.claude/global-memory/**/*.md または */memory/**/*.md) "
                f"への Write/Edit/MultiEdit が記録されていません (System §報告・応答)。 "
                f"memory-routing skill を起動して persistence を行うか、 "
                f"該当発話を取り消して再応答してください。"
            )

    # H7 deferral (warning-only)
    m = DEFERRAL_RE.search(text)
    if m:
        todos_via_path = any(TODOS_PATH_RE.search(p) for p in tool_paths)
        todos_via_tool = bool(tool_names & TASK_TOOLS)
        if not (todos_via_path or todos_via_tool):
            warnings.append(
                f"deferral detected: 「{m.group(0)}」 と発話したが当ターンで "
                f"TaskCreate / TaskUpdate / TodoWrite の呼び出しまたは todos.md "
                f"への Write/Edit が記録されていません (System §計画と遂行)。"
            )

    # H8 claim-without-evidence (warning-only)
    m = CLAIM_RE.search(text)
    if m:
        evidence_used = bool(tool_names & EVIDENCE_TOOLS)
        if not evidence_used:
            warnings.append(
                f"claim-without-evidence: 「{m.group(0)}」 と発話したが当ターンで "
                f"Read / Grep / Glob / WebSearch / WebFetch のいずれも使われていません "
                f"(System §報告・応答)。 verify-spec-before-dismissal skill 参照。"
            )

    out_lines = warnings + blocking
    exit_code = 2 if blocking else 0
    return exit_code, out_lines


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0
    entries = _load_transcript(transcript_path)
    if not entries:
        return 0
    text, tool_names, tool_paths = _current_turn(entries)
    if not text:
        return 0
    exit_code, lines = _check(text, tool_names, tool_paths)
    for line in lines:
        sys.stderr.write(line + "\n")
    return exit_code


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
