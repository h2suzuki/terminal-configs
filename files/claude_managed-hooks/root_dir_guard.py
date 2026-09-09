#!/usr/bin/env python3
"""
Root-directory litter guard for Bash.

A Bash call that matches sandbox.excludedCommands runs on the host, where
TMPDIR is unset, so `$TMPDIR/x` expands to `/x` and a root session litters
`/` in silence. PreToolUse denies that form outright and snapshots the root
directory listing; PostToolUse / PostToolUseFailure diff the snapshot, move
anything new into the quarantine dir and report it, so the litter never
stays in `/` and is never silent.

Exit:
  0: pass (fail-open on any unexpected error)
  2: denied (PreToolUse) or litter quarantined (PostToolUse / PostToolUseFailure)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time

from sandbox_exclusions import glob_match, load_patterns, sandbox_restricts_commands

ROOT_DIR = os.environ.get("ROOT_DIR_GUARD_ROOT") or "/"
STATE_DIR = os.environ.get("ROOT_DIR_GUARD_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "root_dir_guard"
)
SNAPSHOT_TTL = 3600
SEGMENT_CAP = 10000  # Claude Code matches a longer command as one segment
SAFE_VAR = "$CLAUDE_TMPDIR"
TMP_VARS = "TMPDIR|TMP|TEMP|TEMPDIR"

HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n[\s\S]*?^[ \t]*\2\b", re.MULTILINE
)
QUOTED = re.compile(r'"(?:\\[\s\S]|[^"\\])*"|\'[^\']*\'')
SUBST = re.compile(r"\$\((?:[^()]|\([^()]*\))*\)|`[^`]*`|\$\{[^}]*\}")
COMMENT = re.compile(r"(?:^|(?<=\s))#[^\n]*")
TOKEN = re.compile(r"\|&|&&|\|\||[;|&\n(){}]|[^\s;|&(){}]+")
BREAKERS = re.compile(r"[\s;|&(){}#]")  # quoted text stays one word after unquoting
SEPARATORS = frozenset({"&&", "||", "|", "|&", ";", "&", "\n"})
OPENERS = frozenset({"if", "while", "until", "for", "select", "case"})
CLOSERS = frozenset({"fi", "done", "esac"})
ASSIGNMENT = re.compile(r"^([A-Za-z_]\w*)(?:\[[^\]]*\])?\+?=")
UNSTRIPPED = re.compile(r"^(?:LD_|DYLD_|PATH$)")
TIMEOUT_FLAG = re.compile(
    r"^(?:--(?:foreground|preserve-status|verbose)|-v|--(?:kill-after|signal)=\S+|-[ks]\S+)$"
)
TIMEOUT_VALUED = frozenset({"--kill-after", "--signal", "-k", "-s"})
DURATION = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
TMP_ASSIGNED = re.compile(rf"(?:^|[\s;&|])(?:export\s+)?(?:{TMP_VARS})=")
TMP_REFERENCE = re.compile(
    rf"\$(?P<bare>{TMP_VARS})\b|\$\{{(?P<braced>{TMP_VARS})\b(?!:?[-=?])"
)


def _statements(cmd: str) -> list[str]:
    """Return the top-level statements Claude Code matches against excludedCommands."""
    scanned = HEREDOC.sub(lambda m: "_" + m.group(3), cmd)
    scanned = QUOTED.sub(lambda m: BREAKERS.sub("_", m.group(0)[1:-1]), scanned)
    scanned = COMMENT.sub("", SUBST.sub("_", scanned))
    if len(cmd) > SEGMENT_CAP:
        return [scanned.strip()]
    statements: list[str] = []
    current: list[str] = []
    paren = brace = compound = 0
    at_start, opaque = True, False
    for token in TOKEN.findall(scanned):
        if token in SEPARATORS:
            if current and not opaque and not (paren or brace or compound):
                statements.append(" ".join(current))
            current, at_start, opaque = [], True, False
            continue
        if token in "({":
            paren, brace = paren + (token == "("), brace + (token == "{")
            at_start = True
            continue
        if token in ")}":
            paren = max(paren - (token == ")"), 0)
            brace = max(brace - (token == "}"), 0)
        elif at_start and token in OPENERS:
            compound += 1
        elif at_start and token in CLOSERS:
            compound = max(compound - 1, 0)
        elif at_start and token == "!":
            opaque = True
        elif not (paren or brace or compound or opaque):
            current.append(token)
        at_start = False
    if current and not opaque and not (paren or brace or compound):
        statements.append(" ".join(current))
    return statements


def _wrapper_span(tokens: list[str]) -> int:
    """Return how many leading tokens a stripped wrapper occupies, 0 if none."""
    head, n = tokens[0], 1
    if head == "timeout":
        while n < len(tokens) and TIMEOUT_FLAG.match(tokens[n]):
            n += 1
        while n + 1 < len(tokens) and tokens[n] in TIMEOUT_VALUED:
            n += 2
        n += n < len(tokens) and tokens[n] == "--"
        return n + 1 if n < len(tokens) and DURATION.match(tokens[n]) else 0
    if head == "nice":
        if (
            n + 1 < len(tokens)
            and tokens[n] == "-n"
            and re.match(r"^-?\d+$", tokens[n + 1])
        ):
            n += 2
        elif n < len(tokens) and re.match(r"^-\d+$", tokens[n]):
            n += 1
    elif head == "stdbuf":
        while n < len(tokens) and re.match(r"^-[ioe][LN0-9]+$", tokens[n]):
            n += 1
    elif head == "command":
        while n < len(tokens) and re.match(r"^-p+$", tokens[n]):
            n += 1
    elif head not in ("time", "nohup", "builtin", "noglob"):
        return 0
    n += n < len(tokens) and tokens[n] == "--" and head != "noglob"
    if head in ("command", "builtin", "noglob") and (
        n >= len(tokens) or tokens[n].startswith("-")
    ):
        return 0
    return n


def _bare_command(statement: str) -> str:
    """Strip the assignment and wrapper prefixes Claude Code strips before matching."""
    tokens = statement.split()
    while tokens:
        assignment = ASSIGNMENT.match(tokens[0])
        if assignment:
            if UNSTRIPPED.match(assignment.group(1)):
                break
            tokens.pop(0)
            continue
        span = _wrapper_span(tokens)
        if not span:
            break
        del tokens[:span]
    return " ".join(tokens)


def host_run(cmd: str, patterns: list[str]) -> str:
    """Return the statement that makes Claude Code run the whole call on the host."""
    for statement in _statements(cmd):
        bare = _bare_command(statement)
        if bare and any(glob_match(bare, pattern) for pattern in patterns):
            return bare
    return ""


def tmp_reference(cmd: str) -> str:
    """Return the sandbox-only temp variable the command expands, or empty."""
    scanned = HEREDOC.sub(lambda m: "_" + m.group(3) if m.group(1) else m.group(0), cmd)
    scanned = QUOTED.sub(lambda m: m.group(0) if m.group(0)[0] == '"' else "_", scanned)
    if TMP_ASSIGNED.search(scanned):
        return ""
    found = TMP_REFERENCE.search(scanned)
    return f"${found.group('bare') or found.group('braced')}" if found else ""


# 文面は意図的に冗長: deny 理由 + 展開の仕組み + 次に取る行動を 1 度で読ませる。
def _deny_reason(
    cmd: str, tool_input: dict, patterns: list[str], restricted: bool
) -> str:
    ref = tmp_reference(cmd)
    if not ref:
        return ""
    if tool_input.get("dangerouslyDisableSandbox") is True:
        where = (
            "`dangerouslyDisableSandbox` 指定のため sandbox の外 (host) で実行されます"
        )
    elif not restricted:
        if os.environ.get("TMPDIR"):
            return ""
        where = (
            "sandbox が command を制限していないため sandbox の外 (host) で実行されます"
        )
    else:
        host = host_run(cmd, patterns)
        if not host:
            return ""
        where = f"除外コマンド `{host}` を含むため、 呼び出し全体が sandbox の外 (host) で実行されます"
    return (
        f"root-dir-guard: この Bash 呼び出しは{where}。\n"
        f"host 側では TMPDIR が設定されていないため `{ref}` は空文字に展開され、 "
        f"`{ref}/x` は `/x` になります。 root で動く session では / 直下にファイルが作られ、 "
        "一般ユーザーでは Permission denied で失敗します。\n"
        f"Retry: 一時ファイルの path は `{ref}` ではなく `{SAFE_VAR}` を使ってください "
        "(host / sandbox の両方で同じ session tmp dir を指します)。 あるいは、 一時ファイルを"
        "作る segment と除外コマンドの segment を別々の Bash 呼び出しに分けてください。 "
        "hook 自身はファイルを変更していません。\n"
    )


def _key(payload: dict) -> str:
    for field in ("tool_use_id", "session_id"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return re.sub(r"[^\w.-]", "_", value)[:80]
    return "unkeyed"


def _snapshot_path(key: str) -> str:
    return os.path.join(STATE_DIR, f"snap-{key}.json")


def _purge_stale() -> None:
    cutoff = time.time() - SNAPSHOT_TTL
    for name in os.listdir(STATE_DIR):
        path = os.path.join(STATE_DIR, name)
        if name.startswith("snap-") and os.path.getmtime(path) < cutoff:
            os.unlink(path)


def _take_snapshot(payload: dict) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        _purge_stale()
        path = _snapshot_path(_key(payload))
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(os.listdir(ROOT_DIR), f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


def _quarantine(payload: dict) -> tuple[list[str], list[str], str]:
    """Move root entries missing from the snapshot; return moved, failed, destination."""
    key = _key(payload)
    path = _snapshot_path(key)
    try:
        with open(path, encoding="utf-8") as f:
            before = set(json.load(f))
        os.unlink(path)
    except (OSError, ValueError, TypeError):
        return [], [], ""
    new = sorted(set(os.listdir(ROOT_DIR)) - before)
    if not new:
        return [], [], ""
    dest = os.path.join(
        STATE_DIR, "quarantine", f"{time.strftime('%Y%m%d-%H%M%S')}-{key}"
    )
    moved: list[str] = []
    failed: list[str] = []
    for name in new:
        src = os.path.join(ROOT_DIR, name)
        try:
            os.makedirs(dest, exist_ok=True)
            shutil.move(src, os.path.join(dest, name))
            moved.append(src)
        except OSError:
            failed.append(src)
    return moved, failed, dest


# 文面は意図的に冗長: 何が起きたか + どこへ動かしたか + 次の行動 + 報告義務を 1 度で読ませる。
def _litter_report(moved: list[str], failed: list[str], dest: str) -> str:
    lines = [
        f"root-dir-guard: この Bash 呼び出しの後で {ROOT_DIR} 直下に新しい entry が現れました: "
        + ", ".join(moved + failed)
    ]
    if moved:
        lines.append(
            f"{len(moved)} 件を `{dest}` へ移動しました (削除はしていません。 内容が要るなら"
            "そこから読めます)。"
        )
    if failed:
        lines.append(
            "移動できなかった entry: " + ", ".join(failed) + " (手で退避が必要です)。"
        )
    lines.append(
        "典型的な原因は host 実行 (除外コマンドを含む呼び出し、 または sandbox 無効) で "
        "空の変数が `/` に展開されることです ($TMPDIR 等)。 次の呼び出しでは "
        f"`{SAFE_VAR}` か絶対 path を使ってください。 この出来事は必ずユーザーに報告してください "
        "(黙って続行しない)。"
    )
    return "\n".join(lines) + "\n"


def _run(
    payload: object, patterns: list[str] | None = None, restricted: bool | None = None
) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(cmd, str):
        return 0
    event = payload.get("hook_event_name")
    if event == "PreToolUse":
        patterns = load_patterns() if patterns is None else patterns
        restricted = sandbox_restricts_commands() if restricted is None else restricted
        reason = _deny_reason(cmd, tool_input, patterns, restricted)
        if reason:
            sys.stderr.write(reason)
            return 2
        _take_snapshot(payload)
        return 0
    if event in ("PostToolUse", "PostToolUseFailure"):
        moved, failed, dest = _quarantine(payload)
        if moved or failed:
            sys.stderr.write(_litter_report(moved, failed, dest))
            return 2
    return 0


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
