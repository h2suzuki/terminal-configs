#!/usr/bin/env python3
"""todos_completion_check hook for Claude Code.

PostToolUse:Bash. After a successful `git commit` that touched a repo-top
todos.md, reads that todos.md from the working tree and reminds Claude if any
parent-task block has all checkboxes [x] (= "completed" per writing-todos) yet
is still present — such a block must be deleted in the immediate next commit.

Reads the file directly (not `git show HEAD:todos.md`) so the working-tree
truth is evaluated even under partial staging; git is used only to scope the
trigger (diff-tree: did this commit touch todos.md) and resolve the repo root.

Channel: hookSpecificOutput.additionalContext + exit 0 (verified live to reach
the model on a PostToolUse:Bash hook; plain stdout does not). exit 0 never
disturbs the just-completed commit. Fail-open throughout.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys

_TODOS = "todos.md"
_H3 = re.compile(r"^###\s+(.+?)\s*$")
_H2 = re.compile(r"^##\s+\S")
_FENCE = re.compile(r"^\s*```")
_BOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]")
_GIT_COMMIT = re.compile(r"\bgit\b[^\n]*\bcommit\b")


def is_git_commit(cmd: str) -> bool:
    return bool(_GIT_COMMIT.search(cmd))


def completed_blocks(md: str) -> list[str]:
    """Parent-task headings whose checkboxes are all [x] (>=1 box, fences ignored)."""
    name: str | None = None
    boxes: list[bool] = []
    done: list[str] = []
    in_fence = False

    def flush() -> None:
        if name is not None and boxes and all(boxes):
            done.append(name)

    for line in md.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m3 = _H3.match(line)
        if m3:
            flush()
            name, boxes = m3.group(1), []
            continue
        if _H2.match(line):
            flush()
            name, boxes = None, []
            continue
        mb = _BOX.match(line)
        if mb and name is not None:
            boxes.append(mb.group(1).lower() == "x")
    flush()
    return done


def _git(args: list[str], cwd: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def _commit_touched_todos(cwd: str) -> bool:
    changed = _git(
        ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"], cwd
    )
    if changed is None:
        return False
    return any(line.strip() == _TODOS for line in changed.splitlines())


def _read_todos(cwd: str) -> str | None:
    root = _git(["rev-parse", "--show-toplevel"], cwd)
    if not root:
        return None
    try:
        with open(
            os.path.join(root.strip(), _TODOS), encoding="utf-8", errors="replace"
        ) as f:
            return f.read()
    except OSError:
        return None


def _emit(msg: str) -> None:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


def _run(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return
    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(cmd, str) or "commit" not in cmd or not is_git_commit(cmd):
        return
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return
    if not _commit_touched_todos(cwd):
        return
    md = _read_todos(cwd)
    if md is None:
        return
    done = completed_blocks(md)
    if not done:
        return
    names = "\n".join(f"  - {n}" for n in done)
    # 文面は意図的に冗長: trim せず維持 (両 resolution を reader=LLM に明示する)
    _emit(
        "todos_completion_check: todos.md に全 checkbox が [x] の完了済み block が "
        "残っています:\n"
        f"{names}\n"
        "writing-todos の block-level deletion: 完了 block は完了 commit の直後の "
        "commit で削除します (持ち越すと「意図的に残した記録」に見えて消えなくなる)。\n"
        "対応のどちらか: (a) 本当に完了 → 次の commit で block ごと削除 / "
        "(b) 保留作業 (人手レビュー承認・外部確認 待ち 等) が残る → prose の Note でなく "
        "`- [ ]` Exit Criterion として明記 (checkbox 化すれば本 reminder の対象外)。"
    )


def main() -> int:
    try:
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer, encoding="utf-8", errors="replace"
        )
    except Exception:
        pass
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    except Exception:
        pass
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        _run(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
