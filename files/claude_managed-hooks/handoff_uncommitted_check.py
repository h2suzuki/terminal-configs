#!/usr/bin/env python3
"""
UserPromptSubmit hook: when user signals session wind-down
(handoff / お疲れさま / 終わります / sign off 等), check for
uncommitted changes in cwd. If any, inject additionalContext to
remind Claude of the commit-discipline rule ("don't leave dirty
state at session end").

Legacy: org CLAUDE.md → commit-discipline skill (session wind-down
clause) より

Why UserPromptSubmit (not Stop): the user's intent to end the
session is best detected from their own message; Stop hook fires
after every assistant turn regardless of session state, and
checking for uncommitted state on every Stop is noisy.

Stdin: UserPromptSubmit payload JSON with `prompt`, `cwd`,
`session_id`, `transcript_path`.

Stdout: hookSpecificOutput JSON with additionalContext when a
handoff phrase is detected AND uncommitted changes exist.
Otherwise empty.

Exit:
  0: always (this hook only injects context, never blocks).

Always exits 0 on any parse / IO error (fail-open).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HANDOFF_RE = re.compile(
    r"handoff|セッション(終了|リセット)|お疲れさま(でし)?(た)?|終わります|またね|sign\s?off|本日は(これで)?"
)

MAX_FILES_LISTED = 20


def _git_uncommitted(cwd: str) -> list[str]:
    """Return list of uncommitted entries via `git status --porcelain`.

    Returns empty list on any error (not in a repo, git missing,
    timeout, non-zero exit). Each entry is the path portion of a
    porcelain v1 line, with the leading 3-char status code stripped.
    """
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
        # porcelain v1 line is `XY<space>path[<space>-><space>renamed]`,
        # so column 3 onwards is the path. Strip to drop the rename
        # arrow notation cleanly enough for a user-facing listing.
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
