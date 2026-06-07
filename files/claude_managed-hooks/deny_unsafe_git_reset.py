#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: advise-once guard for destructive / pathless
`git reset` and `git restore` in a shared working tree.

A parallel Claude session sharing this tree can hold uncommitted edits or
staged files; a broad reset/restore (or `--hard`) silently discards them.
This hook makes the model pause once: on a gated command it warns on stderr
and exits 2 (deny); the SAME command run again is allowed (advise-once),
treated as "I have confirmed no parallel session is at risk".

Gated (advise-once):
  - `git reset --hard ...`        discards the working tree
  - pathless `git reset ...`      no `--`-separated path (mixed / keep / merge)
  - `git restore .` / `:/`        whole tree
  - pathless `git restore`        no file path

Not gated (allowed):
  - `git reset --soft ...`        HEAD only; recoverable
  - `git reset ... -- <paths>`    names files
  - `git restore <file>` / `--staged <file>`   names files

State: STATE_DIR/<sid>/<hash(command)>; the marker is consumed on the
allowed retry and expires after TTL. If state is unwritable the hook
fails open (allow) rather than deny-looping.

Exit 0 allow / 2 deny. Always exits 0 on any parse error (fail-open).
"""

import hashlib
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "hooks", "state", "deny_unsafe_git_reset")
TTL_SECONDS = 600  # advise-once retry window
PRUNE_SECONDS = 24 * 3600

WHOLE_TREE = {".", "./", ":/", ":/."}
SOURCE_FLAGS = ("-s", "--source")  # take a value (separate-token form)

# Detect `reset`/`restore` after `git` past intervening flags (`git -C r reset`).
GIT_RR = re.compile(
    r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+(?P<sub>reset|restore)\b(?![\w-])"
)

# Strip quoted strings so `echo "git reset"` won't false-trigger.
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# Strip heredoc body, keeping trailing shell code on the opener line.
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)


def _strip_heredoc(m: re.Match) -> str:
    return "_" + m.group(2)


def _classify(sub: str, args: list[str]) -> tuple[bool, bool]:
    """Return (has_file_path, whole_tree) for reset/restore operands.

    reset commit-vs-path is ambiguous without `--`, so a bare reset operand
    is treated as no-path (conservative gate); restore operands are paths.
    """
    after_ddash = False
    skip_next = False
    has_path = False
    whole_tree = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if not after_ddash and a == "--":
            after_ddash = True
            continue
        if not after_ddash and a.startswith("-"):
            if a in SOURCE_FLAGS:
                skip_next = True
            continue
        if a in WHOLE_TREE:
            whole_tree = True
        elif after_ddash or sub == "restore":
            has_path = True
    return has_path, whole_tree


def _guard_reason(stripped: str) -> str | None:
    m = GIT_RR.search(stripped)
    if not m:
        return None
    sub = m.group("sub")
    args = stripped[m.end() :].split("\n", 1)[0].split()
    flags = {a for a in args if a.startswith("-")}
    if sub == "reset" and "--soft" in flags:
        return None  # --soft keeps index + worktree (recoverable)
    if sub == "reset" and "--hard" in flags:
        return "`git reset --hard` は working tree を破棄します"
    has_path, whole_tree = _classify(sub, args)
    if whole_tree:
        return f"`git {sub} .` は tree 全体が対象です"
    if not has_path:
        return f"file 名無しの `git {sub}`"
    return None


def _marker(sid: str, cmd: str) -> str:
    h = hashlib.sha256(cmd.encode("utf-8")).hexdigest()[:16]
    return os.path.join(STATE_DIR, sid, h)


def _fresh(path: str, now: float) -> bool:
    try:
        return now - os.path.getmtime(path) < TTL_SECONDS
    except OSError:
        return False


def _prune(now: float) -> None:
    cutoff = now - PRUNE_SECONDS
    try:
        sids = os.listdir(STATE_DIR)
    except OSError:
        return
    for sid in sids:
        d = os.path.join(STATE_DIR, sid)
        try:
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
            os.rmdir(d)  # only succeeds if now empty
        except OSError:
            pass


# Deny wording is intentionally verbose (writing-skills) — do not trim.
WARNING = (
    "deny-unsafe-git-reset: {reason}。\n"
    "並列セッションが走っている、 もしくは不明なときは、 対象ファイルを名指しし、 "
    "その reset / restore についてユーザーに許可を得てください。\n"
    "対象外: `git reset --soft` / ファイル名指しの `git reset -- <path>` / "
    "`git restore <file>`。\n"
    "同じコマンドをもう一度実行すれば通します (並列セッション無しを確認済みとみなす "
    "advise-once)。 この hook 自身はファイルや index を変更しません。\n"
)


def _run(payload: dict) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str) or not cmd:
        return 0
    stripped = HEREDOC.sub(_strip_heredoc, cmd)
    stripped = QUOTED.sub("_", stripped)
    reason = _guard_reason(stripped)
    if reason is None:
        return 0
    sid = payload.get("session_id")
    if not isinstance(sid, str) or not sid:
        sid = "_"
    marker = _marker(sid, cmd)
    now = time.time()
    if _fresh(marker, now):  # advise-once retry -> allow, consume marker
        try:
            os.remove(marker)
        except OSError:
            pass
        return 0
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(cmd)
    except OSError:
        return 0  # cannot persist advise-once state -> fail-open (no deny-loop)
    _prune(now)
    sys.stderr.write(WARNING.format(reason=reason))
    return 2


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
