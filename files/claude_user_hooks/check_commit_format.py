#!/usr/bin/env python3
"""
check_commit_format hook for Claude Code.

Legacy: user CLAUDE.md「コミット・PUSH運用」 § 50/72 rule + <area>: <Imperative> より

PreToolUse hook on Bash. When `git commit` is invoked with a
message (via heredoc or first `-m`), validates:

  - subject: must match `<area>: <Capital-imperative> [<tag>...]`
    (regex `^\\S+: [A-Z]`), <= 72 chars (hard), <= 50 chars (soft)
  - body lines: <= 72 chars (soft)

Hard violations (block, exit 2):
  - subject > 72 chars
  - subject does not match `<area>: <Capital>` format

Soft violations (warn via additionalContext, exit 0):
  - subject 51-72 chars
  - body line > 72 chars

Message extraction:
  - heredoc form `... <<'EOF' ... EOF`: extract heredoc body
  - `-m "literal"` form: extract first -m argument
  - `-F file` or interactive editor: skip (fail open)

Exit:
  0: not git commit / no message / format passes / soft warnings only
  2: hard violation
"""

from __future__ import annotations

import json
import re
import sys

# Strip heredoc bodies and quoted strings to expose executable structure before
# detection. This prevents `echo 'git commit ...'` / grep / docs / heredoc body
# from false-triggering. Strip patterns mirror the deny-compound hooks.
HEREDOC_BODY = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[\s\S]*?^\1\b", re.MULTILINE)
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# After stripping, detect `git ... commit` invocation. With compound-deny
# upstream, the command is guaranteed single-command form here.
GIT_COMMIT_RE = re.compile(r"\bgit(?:\s+(?:-\S+|--\S+))*\s+commit\b")

# Block `-F` / `--file` form — we can't validate file content.
F_FLAG_RE = re.compile(r"(?:^|\s)(?:-F|--file)(?:\s|=)")

# Extract message from the ORIGINAL command after detection passes.
HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)(\w+)\1\s*\n(.*?)\n\s*\2\b",
    re.DOTALL,
)
M_FLAG_RE = re.compile(
    r"""
    -m \s+
    (?:
        "((?:[^"\\]|\\.)*)"                # group 1: double-quoted (handles \")
        | '((?:[^'\\]|\\.)*)'              # group 2: single-quoted
        | (\S+)                            # group 3: unquoted single word
    )
    """,
    re.VERBOSE | re.DOTALL,
)
SUBJECT_FORMAT_RE = re.compile(r"^\S+: [A-Z]")

SOFT_SUBJECT_LIMIT = 50
HARD_SUBJECT_LIMIT = 72
BODY_LINE_LIMIT = 72


def _extract_message(cmd: str) -> str | None:
    m = HEREDOC_RE.search(cmd)
    if m:
        return m.group(3)
    m = M_FLAG_RE.search(cmd)
    if m:
        return m.group(1) or m.group(2) or m.group(3)
    return None


def _emit_warn(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    # Detect on the stripped (heredoc + quote) command so `echo 'git commit'`
    # and similar string literals do not false-trigger.
    stripped = QUOTED.sub("", HEREDOC_BODY.sub("", cmd))
    if not GIT_COMMIT_RE.search(stripped):
        return 0

    # Block `-F` / `--file` form — file content is not reachable by the hook.
    if F_FLAG_RE.search(stripped):
        sys.stderr.write(
            "git commit -F / --file is not allowed — use inline -m or heredoc "
            "form so the commit message can be validated by check_commit_format.\n"
            "Retry: git commit -m \"...\" (or heredoc form).\n"
        )
        return 2

    msg = _extract_message(cmd)
    if msg is None:
        return 0

    lines = msg.splitlines()
    if not lines:
        return 0

    subject = lines[0].strip()
    body_lines = lines[1:]

    hard: list[str] = []
    soft: list[str] = []

    if len(subject) > HARD_SUBJECT_LIMIT:
        hard.append(
            f"subject ({len(subject)} chars) exceeds "
            f"{HARD_SUBJECT_LIMIT}-char hard limit"
        )
    elif len(subject) > SOFT_SUBJECT_LIMIT:
        soft.append(
            f"subject ({len(subject)} chars) exceeds "
            f"{SOFT_SUBJECT_LIMIT}-char soft limit (consider tightening)"
        )

    if not SUBJECT_FORMAT_RE.match(subject):
        hard.append(
            "subject does not match `<area>: <Capital-imperative>` format "
            "(e.g., `claude_user_hooks: Add check_commit_format`)"
        )

    for i, line in enumerate(body_lines, start=2):
        if len(line.rstrip()) > BODY_LINE_LIMIT:
            soft.append(
                f"body line {i} ({len(line.rstrip())} chars) exceeds "
                f"{BODY_LINE_LIMIT}-char limit"
            )

    if hard:
        sys.stderr.write(
            "commit message format violations (BLOCKING):\n"
            + "\n".join(f"  - {e}" for e in hard)
            + f"\n\nsubject was: {subject[:120]}\n"
            + (
                "\nsoft warnings:\n"
                + "\n".join(f"  - {w}" for w in soft)
                if soft
                else ""
            )
            + "\n\nFormat: `<area>: <Capital-imperative> [<tag>...]`, "
            "subject <= 50 (soft) / 72 (hard) chars, body lines <= 72.\n"
        )
        return 2
    if soft:
        _emit_warn(
            "commit message format soft warnings:\n"
            + "\n".join(f"  - {w}" for w in soft)
            + "\n(commit allowed; consider tightening)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
