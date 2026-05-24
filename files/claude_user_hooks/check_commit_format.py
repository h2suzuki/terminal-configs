#!/usr/bin/env python3
"""
check_commit_format hook for Claude Code.

Legacy: user CLAUDE.md「コミット・PUSH運用」 § 50/72 rule + <area>: <Imperative> より

PreToolUse hook on Bash. When `git commit` is invoked with a
message (via heredoc or `-m` / `--message`), validates:

  - subject: must match `<area>: <Capital-imperative> [<tag>...]`
    (regex `^\\S+: [A-Z]`), <= 72 chars (hard), <= 50 chars (soft)
  - body lines: <= 72 chars (soft)

The subject length / format check is computed on `lines[0].rstrip()`
(trailing whitespace trimmed but leading whitespace preserved), so
an indented heredoc subject is judged against what git actually
stores.

Hard violations (block, exit 2):
  - subject > 72 chars
  - subject does not match `<area>: <Capital>` format
  - `git commit -F`/`--file` (cannot read file content from hook)

Soft violations (warn via additionalContext, exit 0):
  - subject 51-72 chars
  - body line > 72 chars

Multi-`-m`: git concatenates `-m a -m b` as `a\\n\\nb`. The hook
extracts all `-m` / `--message` args in order and joins them with
blank-line separators so the body-length check sees the same body
git will commit.

Exit:
  0: not git commit / no message / format passes / soft warnings only
  2: hard violation

Always exits 0 on any parse / matcher error (fail-open).
"""

from __future__ import annotations

import json
import re
import sys

# Strip heredoc bodies and quoted strings to expose executable structure before
# detection. Substitutes a single `_` placeholder so `-c "..."` still reads as
# `-c _` (preserving the flag-arg pairing), and so `echo "git commit"` doesn't
# false-trigger.
# Heredoc body strip: closing delimiter may be tab-indented under `<<-`, and the
# opener line may carry trailing shell code that must be preserved.
HEREDOC_BODY = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# After stripping, detect `git ... commit` invocation allowing intervening
# flags with optional space- or `=`-separated args.
GIT_COMMIT_RE = re.compile(r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+commit\b(?![\w.])")

# Block `-F` / `--file` / `--file=` forms — file content is unreachable from
# the hook. Match the flag at a token boundary so `-Fmsg` / `-F-` / `-F<file>`
# / `--file file` / `--file=file` are all caught.
F_FLAG_RE = re.compile(r"(?:^|\s)(?:-F\S*|--file(?:=|\s|$))")

# Extract message from the ORIGINAL command after detection passes.
# Closing delimiter may be tab-indented (`<<-EOF`); require the delimiter
# to be alone on its line (optional leading whitespace, then word boundary
# and end of line) so body lines that happen to start with the delim word
# don't truncate the message.
HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n[ \t]*\2\s*(?:\n|$)",
    re.DOTALL,
)
# After quoted strings are replaced with `__Q<i>__` placeholders, `-m` /
# `--message` always takes one whitespace-delimited token (either a
# placeholder or a bare word) — no need for triple-alternative regex.
M_FLAG_RE = re.compile(r"(?:^|\s)(?:-m|--message)(?:\s+|=)(\S+)")
SUBJECT_FORMAT_RE = re.compile(r"^\S+: [A-Z]")

SOFT_SUBJECT_LIMIT = 50
HARD_SUBJECT_LIMIT = 72
BODY_LINE_LIMIT = 72


def _strip_with_placeholders(text: str) -> tuple[str, list[str]]:
    """Replace quoted strings with `__Q<i>__` placeholders, returning the
    stripped text and a list mapping placeholder index to the original
    string (with outer quotes removed and double-quote escapes processed).

    Unlike a bare `_` substitution, this preserves the inner content so
    later extraction (e.g. `M_FLAG_RE`) can recover the actual value.
    Crucially, since the regex now scans the stripped text, a literal
    `-m fake` that appeared INSIDE a quoted string is hidden behind the
    placeholder and cannot false-match.
    """
    contents: list[str] = []

    def _sub(m: re.Match) -> str:
        raw = m.group(0)
        if raw.startswith('"'):
            inner = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        else:
            inner = raw[1:-1]
        idx = len(contents)
        contents.append(inner)
        return f"__Q{idx}__"

    stripped = QUOTED.sub(_sub, text)
    return stripped, contents


def _resolve_placeholder(val: str, contents: list[str]) -> str:
    if val.startswith("__Q") and val.endswith("__"):
        try:
            idx = int(val[3:-2])
            if 0 <= idx < len(contents):
                return contents[idx]
        except ValueError:
            pass
    return val


def _extract_message(cmd: str) -> str | None:
    m = HEREDOC_RE.search(cmd)
    if m:
        return m.group(3)
    # Use placeholder substitution so `-m "fake"` appearing inside an outer
    # quoted string (e.g. `echo "text -m fake" | git commit -m "real"`) is
    # hidden behind the placeholder and does NOT false-match.
    stripped, quoted_contents = _strip_with_placeholders(cmd)
    # Restrict the M_FLAG scan to the SAME statement as `git commit`. A
    # multi-line / multi-statement Bash payload may legitimately contain
    # `-m` belonging to other commands (e.g. `install -m 0755 ...` in a
    # different line). Stop at the first newline / compound op after the
    # commit token.
    git_commit_match = GIT_COMMIT_RE.search(stripped)
    if not git_commit_match:
        return None
    start = git_commit_match.end()
    end_pos = len(stripped)
    for stop_str in ("\n", "&&", "||", ";", "|"):
        p = stripped.find(stop_str, start)
        if 0 <= p < end_pos:
            end_pos = p
    segment = stripped[start:end_pos]
    pieces: list[str] = []
    for m in M_FLAG_RE.finditer(segment):
        pieces.append(_resolve_placeholder(m.group(1), quoted_contents))
    if pieces:
        # git joins multiple -m args as "<a>\n\n<b>\n\n<c>...".
        return "\n\n".join(pieces)
    return None


def _emit_context(msg: str) -> None:
    # Emit additionalContext only — no permissionDecision — so this hook's
    # warning does not aggregate-vote against any future PreToolUse hook
    # that might want to ask/deny.
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return 0
    # Detect on the stripped (heredoc + quote) command so `echo 'git commit'`
    # and similar string literals do not false-trigger.
    stripped = QUOTED.sub("_", HEREDOC_BODY.sub("_", cmd))
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

    # rstrip preserves leading whitespace so format/length checks match the
    # subject git actually stores.
    subject = lines[0].rstrip()
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
        _emit_context(
            "commit message format soft warnings:\n"
            + "\n".join(f"  - {w}" for w in soft)
            + "\n(commit allowed; consider tightening)"
        )
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
