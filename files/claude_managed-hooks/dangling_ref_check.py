#!/usr/bin/env python3
"""PreToolUse:Edit/Write/MultiEdit hook: block edits whose content contains
dangling-prone references (terminal-specific paths, project CLAUDE.md
citation, ephemeral tags). Enforces code-writing Rules「No dangling-prone
references in persistent files」.

Opt-out: include `dangling-ref-check: allow` anywhere in the same content
(typically as a comment) when the pattern is intentional (e.g. the rule
file itself, hook source listing the pattern).
"""
import json
import re
import sys

# 各 entry: (compiled regex, human label)。
# 「dangling」 と判定された pattern を本文に書こうとしている場合に match。
PATTERNS = [
    (re.compile(r'~/\.claude/global-memory/'),
     '端末固有 path (~/.claude/global-memory/)'),
    (re.compile(r'/home/[^/]+/\.claude/global-memory/'),
     '端末固有 path (/home/<user>/.claude/global-memory/)'),
    (re.compile(r'\(global[ -]memory\)'),
     'global memory citation 句'),
    (re.compile(r'\(project CLAUDE\.md\)'),
     'project CLAUDE.md citation 句'),
    (re.compile(r'project CLAUDE\.md ルール'),
     'project CLAUDE.md ルール wording'),
    (re.compile(r'\bAI-\d+(?:\.\d+)?\b'),
     'Action Item ephemeral tag (AI-NNN)'),
    (re.compile(r'\bPlan [A-Z]\b'),
     'Plan ephemeral label (Plan A/B/C...)'),
    (re.compile(r'Phase [αβγδ]'),
     'Phase ephemeral label (Phase α/β/γ/δ)'),
    (re.compile(r'\bSprint-\d+\b'),
     'Sprint ephemeral label'),
]

# Opt-out marker: include this string anywhere in the content to suppress
# the check (intended for the rule file itself / hook source / tests).
OPT_OUT_RE = re.compile(r'dangling-ref-check:\s*allow')


def extract_edit_content(payload):
    """Return list of (location-label, text) tuples to scan for each tool."""
    tool = payload.get('tool_name', '')
    inp = payload.get('tool_input', {}) or {}

    if tool == 'Write':
        return [('content', inp.get('content', '') or '')]
    if tool == 'Edit':
        return [('new_string', inp.get('new_string', '') or '')]
    if tool == 'MultiEdit':
        edits = inp.get('edits', []) or []
        return [(f'edits[{i}].new_string', e.get('new_string', '') or '')
                for i, e in enumerate(edits)]
    return []


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # malformed input → don't block (defensive: stay out of the way)

    chunks = extract_edit_content(payload)
    if not chunks:
        return 0

    full_text = '\n'.join(t for _, t in chunks)
    if OPT_OUT_RE.search(full_text):
        return 0  # opt-out present, skip the check

    findings = []
    for label, text in chunks:
        if not text:
            continue
        for pat, pat_label in PATTERNS:
            for m in pat.finditer(text):
                findings.append(f"  - {label}: {pat_label} — '{m.group(0)}'")

    if not findings:
        return 0

    msg = (
        "dangling-ref-check: 永続 file に dangling-prone reference を入れない。\n"
        "\n"
        "検出:\n"
        + "\n".join(findings) + "\n"
        "\n"
        "修正: 内容を inline で書く / ephemeral tag は本文から削除。\n"
        "意図的なら content に `dangling-ref-check: allow` を含めて再実行。\n"
    )
    print(msg, file=sys.stderr)
    return 2  # block


if __name__ == '__main__':
    sys.exit(main())
