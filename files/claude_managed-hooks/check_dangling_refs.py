#!/usr/bin/env python3
"""PreToolUse:Edit/Write/MultiEdit hook: block edits whose content contains
dangling-prone references (terminal paths, project CLAUDE.md citation,
ephemeral tags, drafts/ files). Enforces writing-code「No dangling-prone refs in persistent files」.

Opt-out: include `dangling-ref-check: allow` anywhere in the content when the
pattern is intentional (rule file itself, hook source listing the pattern).
"""

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath

# 各 entry: (compiled regex, human label)。
# 「dangling」 と判定された pattern を本文に書こうとしている場合に match。
PATTERNS = [
    (
        re.compile(r"~/\.claude/global-memory/"),
        "repo deploy 範囲外 path (~/.claude/global-memory/)",
    ),
    (
        re.compile(r"/home/[^/]+/\.claude/global-memory/"),
        "repo deploy 範囲外 path (/home/<user>/.claude/global-memory/)",
    ),
    (re.compile(r"\(global[ -]memory\)"), "global memory citation 句"),
    (re.compile(r"\(project CLAUDE\.md\)"), "project CLAUDE.md citation 句"),
    (re.compile(r"project CLAUDE\.md ルール"), "project CLAUDE.md ルール wording"),
    (re.compile(r"\bAI-\d+(?:\.\d+)?\b"), "Action Item ephemeral tag (AI-NNN)"),
    (re.compile(r"\bPlan [A-Z]\b"), "Plan ephemeral label (Plan A/B/C...)"),
    (re.compile(r"Phase [αβγδ]"), "Phase ephemeral label (Phase α/β/γ/δ)"),
    (re.compile(r"\bSprint-\d+\b"), "Sprint ephemeral label"),
]

# Opt-out marker: include this string anywhere in the content to suppress
# the check (intended for the rule file itself / hook source / tests).
OPT_OUT_RE = re.compile(r"dangling-ref-check:\s*allow")

# A `drafts` path component followed by a concrete name; drafts/<slug> or drafts/* do not match.
DRAFTS_REF = re.compile(r"(?<![A-Za-z0-9_.-])drafts/[A-Za-z0-9_][A-Za-z0-9_./-]*")
DRAFTS_EXEMPT_NAMES = ("todos.md", "*.test.*", "*.mutants.*", "test_*.py", "*_test.py")


def in_drafts(rel):
    return "drafts" in PurePosixPath(rel).parts


def drafts_exempt(rel):
    """True for repo-relative paths allowed to name drafts files: scratch, ledger, tests."""
    parts = PurePosixPath(rel).parts
    return (
        "drafts" in parts[:-1]
        or "tests" in parts[:-1]
        or any(fnmatch.fnmatchcase(parts[-1], name) for name in DRAFTS_EXEMPT_NAMES)
    )


def run_git(cwd, *args):
    """Completed git process, or None when git cannot run."""
    try:
        return subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def drafts_rule_applies(file_path):
    """True when file_path is a non-ignored, non-exempt file in a git work tree without the marker."""
    if not isinstance(file_path, str) or not file_path:
        return False
    path = os.path.realpath(file_path)
    parent = os.path.dirname(path)
    while not os.path.isdir(parent):
        parent = os.path.dirname(parent)
    top = run_git(parent, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return False
    rel = os.path.relpath(path, os.path.realpath(top.stdout.strip()))
    if rel.startswith(".." + os.sep) or drafts_exempt(rel):
        return False
    ignored = run_git(parent, "check-ignore", "-q", "--", path)
    if ignored is None or ignored.returncode != 1:
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return not OPT_OUT_RE.search(handle.read())
    except OSError:
        return True


def extract_edit_content(payload):
    """Return list of (location-label, text) tuples to scan for each tool."""
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}

    if tool == "Write":
        return [("content", inp.get("content", "") or "")]
    if tool == "Edit":
        return [("new_string", inp.get("new_string", "") or "")]
    if tool == "MultiEdit":
        edits = inp.get("edits", []) or []
        return [
            (f"edits[{i}].new_string", e.get("new_string", "") or "")
            for i, e in enumerate(edits)
        ]
    return []


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # malformed input → don't block (defensive: stay out of the way)

    chunks = extract_edit_content(payload)
    if not chunks:
        return 0

    full_text = "\n".join(t for _, t in chunks)
    if OPT_OUT_RE.search(full_text):
        return 0  # opt-out present, skip the check

    findings = []
    for label, text in chunks:
        if not text:
            continue
        for pat, pat_label in PATTERNS:
            for m in pat.finditer(text):
                findings.append(f"  - {label}: {pat_label} — '{m.group(0)}'")

    drafts_hits = [
        f"  - {label}: drafts/ 配下 file への参照 — '{m.group(0)}'"
        for label, text in chunks
        for m in DRAFTS_REF.finditer(text)
    ]
    tool_input = payload.get("tool_input") or {}
    if drafts_hits and drafts_rule_applies(tool_input.get("file_path")):
        findings += drafts_hits
    else:
        drafts_hits = []

    if not findings:
        return 0

    msg = (
        "dangling-ref-check: 永続 file に dangling-prone reference を入れない。\n"
        "\n"
        "検出:\n" + "\n".join(findings) + "\n"
        "\n"
        "修正: 内容を inline で書く / ephemeral tag は本文から削除。\n"
        + (
            "drafts/ は gitignore された scratch で、 他の環境にも他の reader にも存在しない。"
            " 必要な内容を本文に直接書くか、 tracked な場所へ移してからその path を書く。\n"
            if drafts_hits
            else ""
        )
        + "意図的なら content に `dangling-ref-check: allow` を含めて再実行"
        " (drafts/ 参照は file に既に marker があれば通る)。\n"
    )
    print(msg, file=sys.stderr)
    return 2  # block


if __name__ == "__main__":
    sys.exit(main())
