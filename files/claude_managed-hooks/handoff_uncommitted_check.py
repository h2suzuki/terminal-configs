#!/usr/bin/env python3
"""
UserPromptSubmit hook: on session wind-down phrase (handoff / お疲れさま /
終わります / sign off 等), inject additionalContext reminding Claude of the
commit-discipline rule "don't leave dirty state at session end".

Why UserPromptSubmit (not Stop): end-intent is detected from the user's own
message; Stop fires after every turn, so checking uncommitted state there is
noisy.

Stdin: UserPromptSubmit payload JSON (`prompt`, `cwd`, `session_id`, `transcript_path`).
Stdout: hookSpecificOutput additionalContext only when a handoff phrase AND
uncommitted changes both hold; else empty.

Exit:
  0: always. This hook only injects context, never blocks; exits 0 on any
     parse / IO error (fail-open).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# Case-insensitive for `Handoff` / `Sign Off` etc.
# `本日はこれで` requires これで to avoid matching neutral `本日は…` (e.g. 本日は晴天なり).
HANDOFF_RE = re.compile(
    r"handoff|セッション(終了|リセット)|お疲れさま(でし)?(た)?|終わります|またね|sign\s?off|本日はこれで",
    re.IGNORECASE,
)

MAX_FILES_LISTED = 20


def _git_uncommitted(cwd: str) -> list[str]:
    """Return uncommitted paths via `git status --porcelain`; empty list on any error (fail-open)."""
    if not cwd or not os.path.isdir(cwd):
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        # porcelain v1 is `XY<space>path...`, so col 3+ is the path;
        # strip is good-enough for the user-facing rename-arrow case.
        if len(line) < 4:
            continue
        path_part = line[3:].strip()
        if path_part:
            files.append(path_part)
    return files


def _emit_context(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return 0
    if not HANDOFF_RE.search(prompt):
        return 0
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    files = _git_uncommitted(cwd)
    if not files:
        return 0
    n = len(files)
    head = files[:MAX_FILES_LISTED]
    listing = "\n".join(f"  - {f}" for f in head)
    more = f"\n  ... 他 {n - MAX_FILES_LISTED} 件" if n > MAX_FILES_LISTED else ""
    msg = (
        f"未コミット変更が {n} 件あります:\n{listing}{more}\n\n"
        "セッション終了示唆 (handoff / お疲れさま / 終わります 等) を検出。 "
        "commit-discipline skill 「session wind-down 時に未コミットを残さない」 "
        "規約に従い、 整理して commit を済ませてください。"
    )
    _emit_context(msg)
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
