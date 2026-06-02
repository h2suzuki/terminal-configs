#!/usr/bin/env python3
"""
check_commit_author hook for Claude Code.

PreToolUse hook on Bash. On `git commit`, verifies the target repo's
effective `user.email` equals the expected email (argv[1]); blocks on
mismatch OR unset. Expected email is passed in (not hardcoded) so the
script stays generic; the user-specific value lives in settings.json.

Effective-email precedence (matches git's own rules):
  1. GIT_AUTHOR_EMAIL / GIT_COMMITTER_EMAIL env var
  2. `-c user.email=...` inline override
  3. Repo config — target is `-C <path>` if present, else payload.cwd

Override / env detection runs against the QUOTE-STRIPPED command so
`-c user.email=evil` inside a quoted `-m` message does not false-block.

Exit:
  0: command not git commit, OR email matches expected
  2: email mismatch or unset (commit blocked; stderr fed to Claude)

Always exits 0 on any parse / matcher error (fail-open).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# Strip heredoc bodies + quoted strings to expose executable structure, so
# `echo "git commit"` and quoted `-m` args don't false-trigger. Heredoc close
# delimiter may be tab-indented (`<<-`); opener trailing code must survive.
HEREDOC_BODY = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# Match `git ... commit` allowing intervening flags with optional space- or
# `=`-separated args, so `git -C /repo commit`, `git -c key=val commit`, and
# `git --git-dir /x commit` are detected.
GIT_COMMIT_RE = re.compile(r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+commit\b(?![\w.])")

# Detect inline `-c user.email=...` override that would supersede repo / global
# config for the single command.
INLINE_EMAIL_OVERRIDE_RE = re.compile(
    r"""-c\s+["']?user\.email=["']?([^"'\s]+)"""
)

# Detect env-var bypass `GIT_AUTHOR_EMAIL=value git commit` (and
# GIT_COMMITTER_EMAIL). Git honours these env vars over both -c and config,
# so they must be checked first.
ENV_EMAIL_RE = re.compile(
    r"\b(?:GIT_AUTHOR_EMAIL|GIT_COMMITTER_EMAIL)=([^\s;&|]+)"
)

# Detect `git -C <path>` to retarget the repo lookup.
C_PATH_RE = re.compile(
    r"\bgit\b(?:\s+-\S+(?:[ =]\S+)?)*\s+-C\s+(\S+)"
)


def _git_user_email(target: str, payload_cwd: str | None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", target, "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=payload_cwd or None,
        )
        if result.returncode == 0:
            v = result.stdout.strip()
            return v if v else None
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _resolve(path: str, payload_cwd: str | None) -> str:
    """Expand ~, then resolve relative against payload.cwd."""
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded) and payload_cwd:
        expanded = os.path.join(payload_cwd, expanded)
    return expanded


def _strip_with_placeholders(text: str) -> tuple[str, list[str]]:
    """Replace quoted strings with `__Q<i>__` placeholders, returning stripped text + index->original map (so `-c user.email="real@x"` resolves back, not a value-losing `_`)."""
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


def _run(payload: dict, expected_email: str) -> int:
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

    # Strip heredoc bodies (content unused downstream), then quote strings via
    # indexed placeholders so `-c user.email="real@x"` resolves back, not `_`.
    after_heredoc = HEREDOC_BODY.sub("_", cmd)
    stripped, quoted_contents = _strip_with_placeholders(after_heredoc)
    if not GIT_COMMIT_RE.search(stripped):
        return 0

    payload_cwd = payload.get("cwd")
    if not payload_cwd or not isinstance(payload_cwd, str):
        # No known cwd: fail-open rather than validate against the hook's own cwd.
        return 0

    # Effective author email in git's precedence; inspect `stripped` so quoted
    # `-m` patterns don't false-trigger; resolve placeholders to real content.
    env_match = ENV_EMAIL_RE.search(stripped)
    override_match = INLINE_EMAIL_OVERRIDE_RE.search(stripped)
    c_path_match = C_PATH_RE.search(stripped)
    actual: str | None
    if env_match:
        actual = _resolve_placeholder(env_match.group(1), quoted_contents).strip("'\"")
    elif override_match:
        actual = _resolve_placeholder(override_match.group(1), quoted_contents).strip("'\"")
    else:
        raw_target = (
            _resolve_placeholder(c_path_match.group(1), quoted_contents)
            if c_path_match
            else payload_cwd
        )
        target = _resolve(raw_target, payload_cwd)
        # If target doesn't exist, let git itself produce the real error.
        if not os.path.isdir(target):
            return 0
        actual = _git_user_email(target, payload_cwd)
    if actual == expected_email:
        return 0

    sys.stderr.write(
        f"commit author mismatch in {payload_cwd}:\n"
        f"  effective user.email = {actual or '(unset)'}\n"
        f"  expected user.email  = {expected_email}\n"
        f"Fix: git -C {payload_cwd} config user.email '{expected_email}'  "
        f"(or set globally: git config --global user.email '{expected_email}')\n"
        "Blocking commit.\n"
    )
    return 2


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1]:
        # No expected email configured: fail open (cannot validate).
        return 0
    expected_email = sys.argv[1]
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        return _run(payload, expected_email)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
