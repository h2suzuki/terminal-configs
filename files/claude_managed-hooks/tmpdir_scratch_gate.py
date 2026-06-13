#!/usr/bin/env python3
"""
TMPDIR scratch gate for Claude Code.

PreToolUse hook on Bash. We cannot persistently force TMPDIR (no managed
shell profile; shell state does not survive across Bash calls), so instead
we CHECK at call time that temp files route to the per-session scratch dir
/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID/ that session_cleanup.py removes
on SessionEnd. Bare /tmp is a scarce tmpfs and is NOT swept per session, so
unrouted temps leak and can fill /tmp.

Two strengths, by signal confidence:
- DENY `mktemp` not routed to the scratch dir or /var/tmp. Calling mktemp
  unambiguously creates a temp file, so requiring routing is safe.
- ADVISE (allow + additionalContext) on a write-redirect to bare /tmp
  (`> /tmp/x`, `tee /tmp/x`); redirect parsing is heuristic, so nudge
  rather than block to avoid false positives.

A command counts as routed when it mentions `claude-scratch` or `/var/tmp`.
Reads from /tmp are never flagged. Opt out with `tmp-scratch: allow`.

Exit 0 always (fail-open): any parsing exception is swallowed so a hook bug
never blocks Claude.
"""

from __future__ import annotations

import json
import re
import sys

OPT_OUT = "tmp-scratch: allow"
ROUTED_HINTS = ("claude-scratch", "/var/tmp")
MKTEMP_RE = re.compile(r"\bmktemp\b")
# write-redirect (`>`, `>>`, `2>`, `&>`) to a bare /tmp path that is not the
# scratch dir. Reads (`< /tmp`, `cat /tmp`) lack the redirect operator.
REDIR_TMP_RE = re.compile(r"""[0-9]*>>?\s*["']?/tmp/(?!claude-scratch-)""")
TEE_TMP_RE = re.compile(r"""\btee\b\s+(?:-a\s+)?["']?/tmp/(?!claude-scratch-)""")

_DENY = (
    "mktemp が session scratch / /var/tmp ではなく既定の /tmp に temp を作ろうとしています。\n"
    "/tmp は tmpfs で容量が希少、 SessionEnd の自動削除も scratch dir 配下しか効きません。\n"
    "次のいずれかにしてください:\n"
    "(1) `TMPDIR=/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID` を前置 (`mkdir -p` 済) して mktemp\n"
    "(2) `mktemp -p /tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID`\n"
    "(3) 大きい / mmap / reboot 跨ぎなら `mktemp -p /var/tmp`\n"
    "意図的に外す場合は command に `tmp-scratch: allow` を含めてください。\n"
    "(詳細は temp-file-discipline skill。 hook 自身はファイルを変更しません)"
)
_ADVISE = (
    "`/tmp/...` への書き込みリダイレクトを検出。 /tmp は容量希少で、 SessionEnd の自動削除は "
    "scratch dir 配下のみ効きます。 出力は `/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID/` 配下へ、 "
    "大きい / mmap / reboot 跨ぎは /var/tmp へ。 (temp-file-discipline skill)"
)


def classify(cmd: str) -> tuple[str, str] | None:
    """Return ('deny'|'allow', message), or None to stay silent."""
    if OPT_OUT in cmd:
        return None
    routed = any(h in cmd for h in ROUTED_HINTS)
    if MKTEMP_RE.search(cmd) and not routed:
        return ("deny", _DENY)
    if not routed and (REDIR_TMP_RE.search(cmd) or TEE_TMP_RE.search(cmd)):
        return ("allow", _ADVISE)
    return None


def _emit(decision: str, msg: str) -> None:
    key = "permissionDecisionReason" if decision == "deny" else "additionalContext"
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            key: msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return
    verdict = classify(cmd)
    if verdict is not None:
        _emit(*verdict)


def main() -> int:
    try:
        _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        pass  # fail-open: a hook bug must never block Claude
    return 0


if __name__ == "__main__":
    sys.exit(main())
