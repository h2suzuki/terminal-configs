#!/usr/bin/env python3
"""
Skill-writing convention guard for Claude Code.

PostToolUse hook on Write/Edit/MultiEdit. After the edit lands, reads the
resulting SKILL.md from disk (the true post-edit state — no staged/working
ambiguity) and checks it against the writing-skills + template-skill.md
conventions. On any violation it DENIES via exit 2 + stderr, which surfaces
the issues to Claude so the skill is fixed rather than left broken. (At
PostToolUse the tool already ran, so additionalContext would be passive;
exit 2 actively prompts Claude.) Clean / opt-out / error -> exit 0.

Opt out an intentional deviation with `skill-lint: allow` in the file.

Checks (writing-skills spec, mechanically verifiable subset):
- frontmatter fenced by --- with a kebab-case name matching the directory
- description present, English-only, ending with '.'
- when_to_use present (unless disable-model-invocation) with TRIGGER + SKIP,
  and quoting Japanese keywords with "..." not corner brackets
- an H1 title line
- at least one of Process/Rules/Output/Related when any `## ` header exists
- those preferred sections in canonical order Process<Rules<Output<Related
(h2-English is only 推奨 per template, so Japanese headers are not flagged.)
"""

from __future__ import annotations

import json
import os
import re
import sys

OPT_OUT = "skill-lint: allow"
CJK = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
PREFERRED = ["Process", "Rules", "Output", "Related"]


def _frontmatter(text: str) -> str | None:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None


def _field(fm: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", fm, re.M)
    return m.group(1) if m else None


def lint(content: str, dir_name: str | None) -> list[str]:
    issues: list[str] = []
    fm = _frontmatter(content)
    if fm is None:
        return ["frontmatter (先頭を `---` で挟む) が見当たりません"]
    name = _field(fm, "name")
    if not name:
        issues.append("frontmatter に `name:` がありません")
    elif not re.fullmatch(r"[a-z0-9-]+", name):
        issues.append(f"`name: {name}` が kebab-case ではありません")
    elif dir_name and name != dir_name:
        issues.append(
            f"`name: {name}` が skill ディレクトリ名 `{dir_name}` と不一致です"
        )

    desc = _field(fm, "description")
    if not desc:
        issues.append("frontmatter に `description:` がありません")
    else:
        if not desc.rstrip().endswith("."):
            issues.append(
                "`description` は英語 1 文で文末 `.` 推奨 (末尾が `.` でない)"
            )
        if CJK.search(desc):
            issues.append("`description` は英語のみ (日本語が混ざっています)")

    no_auto = re.search(r"^disable-model-invocation:\s*true", fm, re.M) is not None
    wtu = _field(fm, "when_to_use")
    if not wtu:
        if not no_auto:
            issues.append("frontmatter に `when_to_use:` がありません (TRIGGER + SKIP)")
    else:
        if "TRIGGER" not in wtu:
            issues.append("`when_to_use` に TRIGGER がありません")
        # SKIP は skip 条件が実在するときだけ書く。 常時適用 skill では省略可ゆえ非検査
        if "「" in wtu or "」" in wtu:
            issues.append(
                '`when_to_use` の日本語 keyword は `「」` でなく `"..."` で quote'
            )

    if not re.search(r"^#\s+\S", content, re.M):
        issues.append("`# ` の H1 タイトルがありません")

    headers = SECTION_RE.findall(content)
    preferred_seen = [h for h in headers if h in PREFERRED]
    if headers and not preferred_seen:
        issues.append("`## ` 節に Process/Rules/Output/Related が一つもありません")
    order = [PREFERRED.index(h) for h in preferred_seen]
    if order != sorted(order):
        seq = " → ".join(preferred_seen)
        issues.append(
            f"`## ` 節の順序が Process→Rules→Output→Related に従っていません ({seq})"
        )
    return issues


def _run(payload: dict) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") not in (
        "Write",
        "Edit",
        "MultiEdit",
    ):
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    path = tool_input.get("file_path") or ""
    if not isinstance(path, str) or os.path.basename(path) != "SKILL.md":
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return 0
    if OPT_OUT in content:
        return 0
    issues = lint(content, os.path.basename(os.path.dirname(path)) or None)
    if not issues:
        return 0
    body = "\n".join(f"- {i}" for i in issues)
    sys.stderr.write(
        "SKILL.md が writing-skills 規約に反しています (hook 自身はファイルを変更しません):\n"
        f"{body}\n"
        "上記を修正してから次へ進んでください。 意図的な逸脱なら本文に `skill-lint: allow` を入れてください。\n"
    )
    return 2


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0  # fail-open: a hook bug must never block Claude


if __name__ == "__main__":
    sys.exit(main())
