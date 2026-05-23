#!/usr/bin/env python3
"""
check_commit_author hook for Claude Code.

Legacy: user CLAUDE.md「コミット・PUSH運用」 § Author は ... で統一 より

PreToolUse hook on Bash. When the command contains `git commit`,
verifies that the target repo's effective `user.email` equals
the expected email passed as argv[1]. On mismatch OR unset,
blocks the commit (exit 2).

The expected email is supplied at invocation time (from
settings.json `command` field) rather than hardcoded, so the
hook script itself is generic and contains no user-specific
data. The user-specific value lives in settings.json (which is
already user-deployed) as the argument.

Repo detection: uses payload.cwd as the target. Does NOT parse
`-C <path>` from the command body.

Exit:
  0: command not git commit, OR email matches EXPECTED_EMAIL
  2: email mismatch or unset (commit blocked; stderr fed to Claude)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# Match `git ... commit` with any number of pre-commit flags between (e.g.
# `git -C /path commit`, `git -c user.email=evil commit`, `git --git-dir=...
# commit`). The flag block `-\S+(?:[ =]\S+)?` covers both `-c key=value` and
# `-C /path` / `--git-dir=...` styles.
# Strip heredoc bodies and quoted strings to expose executable structure before
# detection. Prevents `echo 'git commit'` etc. from false-triggering. With
# deny-compound upstream, the post-strip command is single-command form.
HEREDOC_BODY = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[\s\S]*?^\1\b", re.MULTILINE)
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

GIT_COMMIT_RE = re.compile(r"\bgit(?:\s+(?:-\S+|--\S+))*\s+commit\b")

# Detect inline `-c user.email=...` override that would supersede repo / global
# config for the single command. Handles bare and quoted (single/double) forms:
#   -c user.email=value
#   -c "user.email=value"
#   -c 'user.email=value'
#   -c user.email="value"
#   -c user.email='value'
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


def _git_user_email(cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            v = result.stdout.strip()
            return v if v else None
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1]:
        # No expected email configured: fail open (cannot validate).
        return 0
    expected_email = sys.argv[1]
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

    cwd = payload.get("cwd") or "."
    # Compute the effective author email in git's actual precedence:
    #   1. GIT_AUTHOR_EMAIL / GIT_COMMITTER_EMAIL env var
    #   2. `-c user.email=...` inline override
    #   3. Repo config (target = `-C <path>` if present, else cwd)
    env_match = ENV_EMAIL_RE.search(cmd)
    override_match = INLINE_EMAIL_OVERRIDE_RE.search(cmd)
    c_path_match = C_PATH_RE.search(cmd)
    actual: str | None
    if env_match:
        actual = env_match.group(1).strip("'\"")
    elif override_match:
        actual = override_match.group(1).strip("'\"")
    else:
        target = c_path_match.group(1) if c_path_match else cwd
        # If target doesn't exist, let git itself produce the real error.
        if not os.path.isdir(target):
            return 0
        actual = _git_user_email(target)
    if actual == expected_email:
        return 0

    sys.stderr.write(
        f"commit author mismatch in {cwd}:\n"
        f"  effective user.email = {actual or '(unset)'}\n"
        f"  expected user.email  = {expected_email}\n"
        f"Fix: git -C {cwd} config user.email '{expected_email}'  "
        f"(or set globally: git config --global user.email '{expected_email}')\n"
        "Blocking commit.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
