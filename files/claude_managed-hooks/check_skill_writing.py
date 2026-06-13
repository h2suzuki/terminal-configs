#!/usr/bin/env python3
"""
Skill-writing convention guard for Claude Code.

PreToolUse hook on Edit/Write/MultiEdit, acting only on a full Write to a
SKILL.md. Lints the proposed content against the writing-skills conventions
and ADVISES (allow + additionalContext) on any issue. Only Write carries the
whole file; Edit/MultiEdit are surgical and skipped. Advisory only — the
point is to surface convention drift, not to block. Fail-open (exit 0).

Checks:
- frontmatter fenced by --- with a name field
- name matches the skill's directory
- description present and ending with '.'
- when_to_use present with both TRIGGER and SKIP
- no `## ` section dropped vs the on-disk version (rewrite regression)
- at least one of Process/Rules/Output/Related when any `## ` header exists
"""

from __future__ import annotations

import json
import os
import re
import sys

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
PREFERRED = {"Process", "Rules", "Output", "Related"}


def _frontmatter(text: str) -> str | None:
    m = re.match(r"---\n(.*?)\n---\n", text or "", re.S)
    return m.group(1) if m else None


def _field(fm: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", fm, re.M)
    return m.group(1) if m else None


def _headers(text: str) -> set[str]:
    return set(SECTION_RE.findall(text or ""))


def lint(content: str, dir_name: str | None, current: str | None) -> list[str]:
    issues: list[str] = []
    fm = _frontmatter(content)
    if fm is None:
        issues.append("frontmatter (先頭を `---` で挟む) が見当たりません")
    else:
        name = _field(fm, "name")
        if not name:
            issues.append("frontmatter に `name:` がありません")
        elif dir_name and name != dir_name:
            issues.append(
                f"`name: {name}` が skill ディレクトリ名 `{dir_name}` と不一致です"
            )
        desc = _field(fm, "description")
        if not desc:
            issues.append("frontmatter に `description:` がありません")
        elif not desc.rstrip().endswith("."):
            issues.append(
                "`description` は英語 1 文で文末 `.` 推奨 (現状末尾が `.` でない)"
            )
        wtu = _field(fm, "when_to_use")
        if not wtu:
            issues.append("frontmatter に `when_to_use:` がありません")
        else:
            if "TRIGGER" not in wtu:
                issues.append("`when_to_use` に TRIGGER がありません")
            if "SKIP" not in wtu:
                issues.append(
                    "`when_to_use` に SKIP がありません (TRIGGER + SKIP は pair)"
                )
    headers = _headers(content)
    if headers and not (headers & PREFERRED):
        issues.append(
            "`## ` 節に Process/Rules/Output/Related が一つもありません (writing-skills は優先採用)"
        )
    if current is not None:
        dropped = sorted(_headers(current) - headers)
        if dropped:
            issues.append(f"rewrite で `## ` 節 [{' / '.join(dropped)}] が消えています")
    return issues


def _emit(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Write":
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    path = tool_input.get("file_path") or ""
    if not isinstance(path, str) or os.path.basename(path) != "SKILL.md":
        return
    content = tool_input.get("content")
    if not isinstance(content, str):
        return
    dir_name = os.path.basename(os.path.dirname(path)) or None
    current = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = None
    issues = lint(content, dir_name, current)
    if issues:
        body = "\n".join(f"- {i}" for i in issues)
        _emit(
            "SKILL.md の書き方を check しました (writing-skills 規約)。 "
            "意図的でなければ修正してください:\n" + body
        )


def main() -> int:
    try:
        _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        pass  # fail-open: a hook bug must never block Claude
    return 0


if __name__ == "__main__":
    sys.exit(main())
