#!/usr/bin/env python3
"""
Root-directory litter guard for Bash.

A Bash call that matches sandbox.excludedCommands runs on the host, where
TMPDIR is unset, so `$TMPDIR/x` expands to `/x` and a root session litters
`/` in silence. PreToolUse denies that form outright and snapshots the root
directory listing; PostToolUse / PostToolUseFailure diff the snapshot and
report anything new to both Claude and the user. The hook never creates,
moves or deletes anything outside its own snapshot files.

Exit:
  0: pass, or a litter report via decision:block + systemMessage
  2: denied (PreToolUse)
Always exits 0 on any unexpected error (fail-open).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

from sandbox_exclusions import glob_match, load_patterns, sandbox_restricts_commands

ROOT_DIR = os.environ.get("ROOT_DIR_GUARD_ROOT") or "/"
STATE_DIR = os.environ.get("ROOT_DIR_GUARD_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "root_dir_guard"
)
SNAPSHOT_TTL = 3600
SEGMENT_CAP = 10000  # Claude Code matches a longer command as one segment
SAFE_VAR = "CLAUDE_TMPDIR"
SANDBOX_VARS = ("TMPDIR", "TMP", "TEMP", "TEMPDIR")

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


def hazard_vars() -> tuple[str, ...]:
    """Variables that expand to nothing on the host: sandbox-only ones, plus an unset CLAUDE_TMPDIR."""
    return SANDBOX_VARS if os.environ.get(SAFE_VAR) else (*SANDBOX_VARS, SAFE_VAR)


def var_reference(cmd: str, names: tuple[str, ...]) -> str:
    """Return the first named variable the shell would expand, or empty."""
    scanned = HEREDOC.sub(lambda m: "_" + m.group(3) if m.group(1) else m.group(0), cmd)
    scanned = QUOTED.sub(lambda m: m.group(0) if m.group(0)[0] == '"' else "_", scanned)
    found = re.search(rf"\$\{{?(?P<name>{'|'.join(names)})\b", scanned)
    return f"${found.group('name')}" if found else ""


# 文面は意図的に冗長: deny 理由 + 展開の仕組み + 次に取る行動を 1 度で読ませる。
def _deny_reason(
    cmd: str, tool_input: dict, patterns: list[str], restricted: bool
) -> str:
    ref = var_reference(cmd, hazard_vars())
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
    if ref == f"${SAFE_VAR}":
        why = f"この環境では `{ref}` が設定されていないため"
        safe = "絶対 path (例: `/var/tmp/<name>`)"
    else:
        why = f"`{ref}` は sandbox の中でしか設定されないため、 host 側では"
        safe = f"`${SAFE_VAR}` (host / sandbox の両方で同じ session tmp dir を指します)"
    return (
        f"root-dir-guard: この Bash 呼び出しは{where}。\n"
        f"{why} `{ref}` は空文字に展開され、 `{ref}/x` は `/x` になります。 root で動く "
        "session では / 直下にファイルが作られ、 一般ユーザーでは Permission denied で失敗します。\n"
        f"Retry: 一時ファイルの path は `{ref}` ではなく {safe} を使ってください。 "
        "あるいは、 一時ファイルを作る segment と除外コマンドの segment を別々の Bash 呼び出しに"
        "分けてください。 この規則に例外はありません (default 値付きの展開や事前代入も deny)。 "
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


def _new_root_entries(payload: dict) -> list[str]:
    """Return root entries absent from this call's snapshot; the snapshot is consumed."""
    path = _snapshot_path(_key(payload))
    try:
        with open(path, encoding="utf-8") as f:
            before = set(json.load(f))
        os.unlink(path)
    except (OSError, ValueError, TypeError):
        return []
    return [
        os.path.join(ROOT_DIR, n) for n in sorted(set(os.listdir(ROOT_DIR)) - before)
    ]


# 文面は意図的に冗長: 何が起きたか + 原因 + 報告義務 + hook は動かしていない旨を 1 度で読ませる。
def _litter_report(entries: list[str]) -> dict:
    listed = ", ".join(entries)
    reason = (
        f"root-dir-guard: この Bash 呼び出しの後で {ROOT_DIR} 直下に新しい entry が現れました: "
        f"{listed}\n典型的な原因は host 実行 (除外コマンドを含む呼び出し、 または sandbox 無効) で "
        "空の変数が `/` に展開されることです ($TMPDIR 等)。\n"
        "作業を続ける前に、 この entry と原因の command をユーザーへ報告してください "
        "(黙って続行しない)。 消す・戻すはユーザーの指示に従い、 勝手に削除や移動をしないでください。 "
        f"次の呼び出しでは `${SAFE_VAR}` か絶対 path を使ってください。 "
        "hook 自身は entry を移動も削除もしていません。"
    )
    return {
        "decision": "block",
        "reason": reason,
        "systemMessage": f"root-dir-guard: {ROOT_DIR} 直下に新しい entry: {listed}",
    }


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
        entries = _new_root_entries(payload)
        if entries:
            sys.stdout.write(
                json.dumps(_litter_report(entries), ensure_ascii=False) + "\n"
            )
    return 0


def main() -> int:
    try:
        return _run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
