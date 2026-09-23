#!/usr/bin/env python3
"""PreToolUse:Edit/Write/MultiEdit hook: block edits whose content contains
dangling-prone references (terminal paths, project CLAUDE.md citation,
ephemeral tags, drafts/ files). Enforces writing-code「No dangling-prone refs in persistent files」.

Opt-out for the general patterns: include `dangling-ref-check: allow` anywhere in the content
when the pattern is intentional (rule file itself, hook source listing the pattern).

Opt-out for a drafts/ reference is line-scoped, like shellcheck: the marker must appear on the
same line as the reference, or alone (as a comment) on the line immediately before it in the
resulting text. A marker elsewhere in the file exempts nothing else.
"""

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

# The marker alone on a line (optionally commented / parenthesized): shellcheck-style
# "applies to the next line" for a drafts/ reference.
MARKER_ONLY_RE = re.compile(
    r"\s*(?:#|//|<!--)?\s*dangling-ref-check:\s*allow\s*(?:\([^)]*\))?\s*(?:-->)?\s*"
)

# A `drafts` path component followed by a concrete name; drafts/<slug> or drafts/* do not match.
DRAFTS_REF = re.compile(r"(?<![A-Za-z0-9_.-])drafts/[A-Za-z0-9_][A-Za-z0-9_./-]*")


def in_drafts(rel):
    return "drafts" in PurePosixPath(rel).parts


def marker_only_line(line):
    """True when `line` is nothing but the opt-out marker (a shellcheck-style "next line" marker)."""
    return bool(MARKER_ONLY_RE.fullmatch(line))


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
    """True when file_path is a non-ignored file, outside drafts/ itself, in a git work tree."""
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
    if rel.startswith(".." + os.sep) or in_drafts(rel):
        return False
    ignored = run_git(parent, "check-ignore", "-q", "--", path)
    return ignored is not None and ignored.returncode == 1


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def apply_edit(base, old, new):
    """(resulting text, start, end) of `new` after replacing the first `old` found in `base`."""
    offset = base.find(old) if old else -1
    if offset < 0:
        return new, 0, len(new)
    return base[:offset] + new + base[offset + len(old) :], offset, offset + len(new)


def edit_spans(payload, disk_text):
    """Yield (label, resulting_text, start, end): the text this call would produce, and the
    (start, end) offsets of the freshly written span within it (Write's whole `content` counts
    as the span; Edit/MultiEdit reconstruct it against `disk_text`, the target's current content)."""
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}
    if tool == "Write":
        content = inp.get("content", "") or ""
        yield "content", content, 0, len(content)
    elif tool == "Edit":
        resulting, start, end = apply_edit(
            disk_text or "", inp.get("old_string", ""), inp.get("new_string", "") or ""
        )
        yield "new_string", resulting, start, end
    elif tool == "MultiEdit":
        current = disk_text or ""
        for i, e in enumerate(inp.get("edits", []) or []):
            resulting, start, end = apply_edit(
                current, e.get("old_string", ""), e.get("new_string", "") or ""
            )
            yield f"edits[{i}].new_string", resulting, start, end
            current = resulting


def drafts_hits_in(label, resulting, start, end):
    """Findings for drafts/ references whose start offset falls in [start, end), line-scoped
    against `dangling-ref-check: allow` on the same line or alone on the line before it."""
    lines = resulting.split("\n")
    hits = []
    pos = 0
    for i, line in enumerate(lines):
        line_start = pos
        pos += len(line) + 1
        for m in DRAFTS_REF.finditer(line):
            if not (start <= line_start + m.start() < end):
                continue
            if OPT_OUT_RE.search(line):
                continue
            if i > 0 and marker_only_line(lines[i - 1]):
                continue
            hits.append(f"  - {label}: drafts/ 配下 file への参照 — '{m.group(0)}'")
    return hits


def drafts_findings(payload):
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not drafts_rule_applies(file_path):
        return []
    disk_text = read_text(file_path)
    hits = []
    for label, resulting, start, end in edit_spans(payload, disk_text):
        hits += drafts_hits_in(label, resulting, start, end)
    return hits


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

    # The general patterns keep a whole-call opt-out: a marker anywhere in the new content
    # skips them (unlike the drafts/ check below, which is line-scoped).
    full_text = "\n".join(t for _, t in chunks)
    findings = []
    if not OPT_OUT_RE.search(full_text):
        for label, text in chunks:
            if not text:
                continue
            for pat, pat_label in PATTERNS:
                for m in pat.finditer(text):
                    findings.append(f"  - {label}: {pat_label} — '{m.group(0)}'")

    drafts_hits = drafts_findings(payload)
    findings += drafts_hits

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
