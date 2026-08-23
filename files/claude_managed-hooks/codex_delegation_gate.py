#!/usr/bin/env python3
r"""
codex 委譲 gate for org-managed Claude Code.

Purpose
=======
codex への委譲を 2 軸で deny する。

  軸 A (checkpoint): `codex-delegation` skill を当 turn で invoke せずに委譲する
  軸 B (invocation lint): 委譲の command 形自体が codex-delegation の Rules に反する

軸 A は 「skill 本文が既に context に載っているから invoke は無意味」 という判断で
skip された事故への対策。 invoke の値打ちは文言の再読ではなく、 これから打つ command を
Rules と 1 行ずつ突き合わせる checkpoint にある。 軸 B はその突き合わせを skip しても
残る決定的な違反 (worktree 外への write・報告書が回収できない起動・sandbox 落ち等) を
機械的に止める。

発火点
======
PreToolUse (matcher 無し)。 tool_name で dispatch する。

  Agent / Task   subagent_type に codex を含む spawn、 または prompt が codex 起動を含む
  Skill          codex: 名前空間の skill (SAFE_CODEX_SKILLS 以外)
  Bash / Monitor main agent の codex-companion.mjs 全起動、 および素の codex CLI
  Workflow       script 本文に codex の生成 step を含むもの
  SendMessage    宛先に codex を含むもの
  mcp__*codex*   codex を名乗る MCP tool

Bash と Monitor は同じ shell を実行するので同じ検査に掛ける。 shell 経由の間接実行
(`bash -c ...` / launcher script) は 1 段だけ展開して中身を見る。

skill-active state
==================
`skill_reminder_gate.py` の record-skill が書く
`~/.claude/hooks/state/skill_reminder/active/<session_id>/<agent_key>.json` を再利用する。

  main agent (agent_id 無し) : companion の直接起動を一律 deny する
  subagent   (agent_id あり) : main bucket に記録が 1 件でもあれば通す

codex-rescue subagent は `tools: Bash` のみで skill を invoke できず、 Bash 失敗時は
「何も返さない」 と指示されているため、 subagent を deny すると回復手段も deny 文面も
無い沈黙失敗になる。 checkpoint は委譲元 main agent の spawn 時点で取り、 subagent 側は
「session 内で一度も invoke されていない」 場合だけ止める。 main bucket が空のときは
記録経路の故障と区別できないので通す。 自分の bucket は見ない (自己解除の防止)。

軸 B の違反 id
==============
  bare-codex-cli        素の codex CLI 経由の委譲 (escape hatch で切り分け用途を許可)
  sandbox-wrapper       env / npx 等 wrapper 経由で excludedCommands 照合を外す起動
  effort                companion が受理しない reasoning effort
  model-nickname        俗称 model (API が 400 で弾く)
  unknown-task-flag     task が受理しない flag。 例外にならず発注本文へ流れる
  review-swallowed-flag review 系が受理しない flag。 focus text へ流れ job record に届かない
  order-file            発注書 file を渡していない write 委譲
  order-lint            発注書が codex_order_lint に不合格
  review-without-lint-pass task 経由の review が発注書 lint を通過していない
  review-metadata        review 発注書の metadata が破損または曖昧
  report-without-write  報告書を成果物とする発注を --write 無しで起動
  cjk-inline            起動 command 行への長い日本語直書き
  kill-by-port          委譲と同じ command 内の fuser -k / pkill
  isolation             Agent の isolation: "worktree"
  monitor-launch        Monitor tool からの委譲起動
  workflow-codex        workflow script 内の codex 生成 step

`unknown-task-flag` / `review-swallowed-flag` の受理集合は companion の
parseCommandInput が subcommand ごとに宣言する集合をそのまま写している。 `--` 以降は
flag 解釈の対象外だが、 companion が prompt に連結するため内容検査の対象に含める。

既存 hook との境界 (重複実装しない)
===================================
  codex_worktree_gate.py     companion の task を共有 checkout / 非正規経路で起動する形
  sandbox_exclusion_guard.py 除外コマンドの path 前置・sudo 前置 (env / npx 等は warn 止まり)
  codex_delegation_surface.py 委譲前後の nudge (deny しない)

本 hook は上記が素通しする範囲を埋める: Agent / Skill / Workflow 経路、 review 系
subcommand、 素の codex CLI、 option の規約違反、 委譲文脈での wrapper 落ち。

emit / fail-open
================
deny は JSON permissionDecision (exit 0) — hook bug が tool を block しない。
全例外を握り潰し exit 0。 state が読めない・payload が欠ける等の判定不能は ALLOW、
state が正常に読めて記録が無い場合だけ DENY (skill_reminder_gate と同方針)。

residual (閉じない・既知)
=========================
- shell interpreter ではない。 `bash -c` / `eval` / 変数展開 / alias / 別 script 経由の
  起動は静的に解けない。 脅威主体は敵対者でなく発注側自身の不注意なので網羅を目指さない
- Workflow / SendMessage の被覆は harness が tool_input を payload に載せることに依存する
- `cjk-inline` の閾値は SKILL.md に数値が無いため本 hook が定める契約値
- kill-by-port は codex 起動を含む command に限って見る。 単独の pkill は射程外
- `order-lint` の parse と発注書本文の読取は codex_order_lint に一本化する
- resume で write 権限を引き継げるかは plugin state を読まないと分からない。
  `--write` × `--resume` は stderr warning に留める

canonical source: files/claude_managed-hooks/codex_delegation_gate.py
deploy: /etc/claude-code/hooks/  両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from typing import Any

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "hooks", "state", "skill_reminder")
DIRECT_STATE_DIR = os.path.join(
    HOME, ".claude", "hooks", "state", "codex_delegation_gate"
)
REQUIRED_SKILL = "codex-delegation"
FALLBACK_WINDOW_SECONDS = 1800
ORDER_LINT = "/usr/local/bin/codex_order_lint"
ORDER_LINT_TIMEOUT = 10
CJK_INLINE_MAX = 200
ATTEMPT_LINE_MAX_BYTES = 4096

COMPANION_SCRIPT = "codex-companion.mjs"
CODEX_CLI = "codex"
NODE_NAMES = frozenset({"node", "nodejs"})

DELEGATING_SUBCOMMANDS = frozenset(
    {"task", "task-worker", "review", "adversarial-review"}
)
CLI_NON_DELEGATING = frozenset(
    {"login", "logout", "mcp", "completion", "help", "app-server"}
)

VALID_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
MODEL_NICKNAMES = frozenset({"luna", "sol", "terra"})
RESUME_FLAGS = frozenset({"--resume-last", "--resume"})
MODEL_OPTIONS = ("--model", "-m")
# companion の parseCommandInput が subcommand ごとに受理する集合。 これ以外の flag は
# 例外にならず positional (= prompt / focus 本文) へ流れ、 指定が job record に届かない。
TASK_OPTIONS = frozenset(
    {
        "--model",
        "-m",
        "--effort",
        "--cwd",
        "--prompt-file",
        "--json",
        "--write",
        "--resume-last",
        "--resume",
        "--fresh",
        "--background",
    }
)
REVIEW_OPTIONS = frozenset(
    {"--base", "--scope", "--model", "-m", "--cwd", "--json", "--background", "--wait"}
)
TASK_VALUE_OPTIONS = frozenset({"--model", "-m", "--effort", "--cwd", "--prompt-file"})
REVIEW_VALUE_OPTIONS = frozenset({"--base", "--scope", "--model", "-m", "--cwd"})
WORKTREE_VALUE_OPTIONS = frozenset({"--cwd", "-C", "--model", "--log"})
VALUE_OPTIONS = TASK_VALUE_OPTIONS | REVIEW_VALUE_OPTIONS | WORKTREE_VALUE_OPTIONS
# 実際に flag として解釈されうる形だけを対象にする (先頭が `--` の prompt 本文を除く)。
FLAG_SHAPE = re.compile(r"^--?[A-Za-z][\w-]*(=.*)?$")

SEGMENT_OPERATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")", ";;"})
ASSIGNMENT = re.compile(r"^\w+=")
ESCAPE_HATCH = "CODEX_DELEGATION_OK=1"
TRANSPARENT_WRAPPERS = frozenset(
    {"command", "builtin", "time", "nohup", "exec", "xargs"}
)
# option や数値 operand を取る wrapper。 剥がし損ねると実行語が flag や duration にずれる。
OPTION_WRAPPERS = frozenset(
    {
        "stdbuf",
        "ionice",
        "chrt",
        "nice",
        "setsid",
        "unbuffer",
        "script",
        "timeout",
        "watch",
    }
)
OPERAND_WRAPPERS = frozenset({"flock"})
NUMERIC_OPERAND = re.compile(r"^[\d.]+[smhd]?$")
# 照合前に剥がされず sandbox へ落ちる wrapper。 sandbox_exclusion_guard は warn 止まり。
SANDBOX_BREAKING_WRAPPERS = frozenset({"env", "npx", "bunx", "uvx"})
SHELL_NAMES = frozenset({"bash", "sh", "zsh", "ksh", "dash"})
# 制御語は実行語ではない。 剥がさないと `do node x` / `while node x` の実行語が制御語に見える。
SHELL_KEYWORDS = frozenset(
    {
        "do",
        "then",
        "else",
        "elif",
        "fi",
        "done",
        "esac",
        "in",
        "!",
        "{",
        "}",
        "while",
        "until",
        "if",
        "for",
        "case",
    }
)
SCRIPT_READ_LIMIT = 65536
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")
MARKDOWN_TOKEN = re.compile(r"[\w./~-]+\.md\b")
REPORT_HINT = re.compile(r"-report\.md|報告書")
REVIEW_PROMPT = re.compile(
    r"敵対レビュー|adversarial|レビュー観点"
    r"|\b(?:review|audit|inspect)\b|(?:レビュー|監査)(?!済み)",
    re.IGNORECASE,
)
MONITOR_LOOP = re.compile(r"\b(while|until|for)\b")
# workflow script は shell ではないので、 起動の形をそのまま探す。 file 名の言及だけでは
# 発火しない (hook 自身をレビューする workflow を誤って止めないため)。
WORKFLOW_CODEX = re.compile(
    r"codex-companion\.mjs[\"']?\s+(?:-[-\w]+(?:[= ]\S+)?\s+)*(?:task|task-worker)\b"
    r"|(?:agentType|subagent_type|subagentType)\s*[:=]\s*[\"'][^\"']*codex"
    r"|\bcodex\s+exec\b"
)

# Skill 経路のうち委譲でないもの。 未知の codex: skill は委譲側 (deny 側) に倒す。
SAFE_CODEX_SKILLS = frozenset(
    {
        "codex:setup",
        "codex:status",
        "codex:result",
        "codex:cancel",
        "codex:codex-cli-runtime",
        "codex:codex-result-handling",
        "codex:gpt-5-4-prompting",
    }
)

REBUTTAL = (
    "「skill 本文はもう context に載っているから invoke しても情報が増えない」"
    " は skip の理由になりません。"
    " invoke の値打ちは文言の再読ではなく、"
    " これから打つ command を Rules と 1 行ずつ突き合わせる checkpoint そのものです。"
    " 突き合わせを飛ばすと、 載っている本文を読み落としたまま実行することになります。"
)


def _emit_deny(reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def _lines(command: str) -> list[str]:
    """引用の外側の改行だけで行に割る。"""
    lines: list[str] = []
    buffer: list[str] = []
    quote = ""
    escaped = False
    for char in command:
        if escaped:
            buffer.append(char)
            escaped = False
            continue
        if char == "\\" and quote != "'":
            buffer.append(char)
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            buffer.append(char)
            continue
        if char in "\"'":
            quote = char
            buffer.append(char)
            continue
        if char == "\n":
            lines.append("".join(buffer))
            buffer = []
            continue
        buffer.append(char)
    lines.append("".join(buffer))
    return lines


def _segments(command: str) -> list[list[str]]:
    """command を実行単位の token 列へ割る。 解釈できなければ空 list。"""
    segments: list[list[str]] = []
    for line in _lines(command):
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            continue
        current: list[str] = []
        for token in tokens:
            if token in SEGMENT_OPERATORS:
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append(token)
        if current:
            segments.append(current)
    return segments


def _skip_options(segment: list[str], index: int) -> int:
    """flag と、 それに続く数値 operand (duration / niceness) をまとめて読み飛ばす。"""
    while index < len(segment) and (
        segment[index].startswith("-") or NUMERIC_OPERAND.match(segment[index])
    ):
        index += 1
    return index


def _strip_prefix(segment: list[str]) -> tuple[int, frozenset[str], bool]:
    """実行語の index、 剥がした sandbox 落ち wrapper 名、 escape hatch の有無。"""
    index = 0
    wrappers: set[str] = set()
    escaped = False
    while index < len(segment):
        token = segment[index]
        name = os.path.basename(token)
        if ASSIGNMENT.match(token):
            escaped = escaped or token == ESCAPE_HATCH
            index += 1
            continue
        if name in TRANSPARENT_WRAPPERS or name in SHELL_KEYWORDS:
            index += 1
            continue
        if name in OPTION_WRAPPERS:
            index = _skip_options(segment, index + 1)
            continue
        if name in OPERAND_WRAPPERS:
            index = _skip_options(segment, index + 1) + 1  # lockfile
            continue
        if name in SANDBOX_BREAKING_WRAPPERS or name == "sudo":
            if name in SANDBOX_BREAKING_WRAPPERS:
                wrappers.add(name)
            index = _skip_options(segment, index + 1)
            continue
        break
    return index, frozenset(wrappers), escaped


class Launch:
    """codex 起動 1 件。 kind は companion / cli。"""

    def __init__(
        self,
        kind: str,
        args: list[str],
        wrappers: frozenset[str],
        escaped: bool = False,
    ) -> None:
        self.kind = kind
        self.args = args
        self.wrappers = wrappers
        self.escaped = escaped
        # companion は argv[0] を subcommand として読むので同じ規則で取る。
        self.subcommand = args[0] if kind == "companion" and args else None
        if kind != "companion":
            self.subcommand = _subcommand(args)

    @property
    def delegating(self) -> bool:
        if self.kind == "companion":
            return self.subcommand in DELEGATING_SUBCOMMANDS
        if self.subcommand is None:
            return not any(
                token in {"--version", "-V", "--help", "-h"} for token in self.args
            )
        return self.subcommand not in CLI_NON_DELEGATING


def _before_passthrough(args: list[str]) -> list[str]:
    return args[: args.index("--")] if "--" in args else args


def _subcommand(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token in VALUE_OPTIONS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def _positional(args: list[str]) -> list[str]:
    """subcommand 後の prompt 部。 `--` 以降は flag 解釈せず prompt に含める。"""
    result: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            result.extend(args[index + 1 :])
            break
        if token in VALUE_OPTIONS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        result.append(token)
        index += 1
    return result[1:]


def _unknown_flags(args: list[str], accepted: frozenset[str]) -> list[str]:
    """companion が解釈せず prompt 本文へ流してしまう flag。"""
    return [
        token
        for token in _before_passthrough(args)
        if FLAG_SHAPE.match(token) and token.split("=", 1)[0] not in accepted
    ]


def _option_value(args: list[str], *names: str) -> str | None:
    for index, token in enumerate(args):
        for name in names:
            if token == name and index + 1 < len(args):
                return args[index + 1]
            if token.startswith(name + "="):
                return token.split("=", 1)[1]
    return None


def _has_flag(args: list[str], names: frozenset[str]) -> bool:
    return any(token.split("=", 1)[0] in names for token in args)


def _indirect_sources(segment: list[str], start: int, cwd: str) -> list[str]:
    """shell 経由の間接実行から、 1 段だけ中身を取り出す。"""
    sources: list[str] = []
    index = start + 1
    while index < len(segment):
        token = segment[index]
        if token == "-c" and index + 1 < len(segment):
            sources.append(segment[index + 1])
            break
        if token.startswith("-"):
            index += 1
            continue
        path = token if os.path.isabs(token) else os.path.join(cwd or os.curdir, token)
        if os.path.isfile(path):
            sources.append(_read_regular_head(path, SCRIPT_READ_LIMIT))
        break
    return sources


def _launches(command: str, cwd: str = "", depth: int = 0) -> list[Launch]:
    launches: list[Launch] = []
    for segment in _segments(command):
        start, wrappers, escaped = _strip_prefix(segment)
        if start >= len(segment):
            continue
        head = os.path.basename(segment[start])
        if head == CODEX_CLI:
            launches.append(Launch("cli", segment[start + 1 :], wrappers, escaped))
            continue
        if head == COMPANION_SCRIPT:
            launches.append(
                Launch("companion", segment[start + 1 :], wrappers, escaped)
            )
            continue
        if head in NODE_NAMES:
            for index in range(start + 1, len(segment)):
                if os.path.basename(segment[index]) == COMPANION_SCRIPT:
                    launches.append(
                        Launch("companion", segment[index + 1 :], wrappers, escaped)
                    )
                    break
            continue
        if head in SHELL_NAMES and depth == 0:
            for source in _indirect_sources(segment, start, cwd):
                launches.extend(_launches(source, cwd, depth + 1))
    return launches


def _kill_by_port(command: str) -> bool:
    for segment in _segments(command):
        start, _, _ = _strip_prefix(segment)
        if start >= len(segment):
            continue
        head = os.path.basename(segment[start])
        if head == "pkill":
            return True
        if head == "fuser" and any(
            token.startswith("-k") or token == "--kill"
            for token in segment[start + 1 :]
        ):
            return True
    return False


def _mentions_order(args: list[str]) -> bool:
    """引用された prompt の内側に書かれた path も発注書の言及として数える。"""
    return any(MARKDOWN_TOKEN.search(token) for token in args)


def _order_path(launch: Launch, cwd: str) -> str | None:
    """発注書 path が一意に決まるときだけ返す。"""
    explicit = _option_value(launch.args, "--prompt-file")
    if explicit:
        candidates = [explicit]
    else:
        found: list[str] = []
        for token in launch.args:
            found.extend(MARKDOWN_TOKEN.findall(token))
        candidates = sorted(set(found))
    if len(candidates) != 1:
        return None
    path = os.path.expanduser(candidates[0])
    base = (
        _option_value(launch.args, "--cwd") or _option_value(launch.args, "-C") or cwd
    )
    if not os.path.isabs(path):
        path = os.path.join(base or os.curdir, path)
    return path if os.path.isfile(path) else None


def _read_regular_head(path: str, limit: int) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _lint_order(path: str) -> tuple[dict[str, Any] | None, str | None]:
    if not os.path.isfile(ORDER_LINT):
        return None, f"lint script {ORDER_LINT} が存在しません。"
    try:
        done = subprocess.run(
            [ORDER_LINT, "--metadata", path],
            capture_output=True,
            text=True,
            timeout=ORDER_LINT_TIMEOUT,
            check=False,
        )
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as error:
        return None, f"発注書 lint を実行できません ({error})。"
    if done.stderr:
        sys.stderr.write(done.stderr)
    try:
        metadata = json.loads(done.stdout)
    except (TypeError, ValueError) as error:
        detail = done.stdout.strip() or "出力なし"
        return (
            None,
            f"発注書 lint metadata が不正です ({error}; rc={done.returncode}; {detail})。",
        )
    if done.returncode not in {0, 1}:
        return None, f"発注書 lint が rc={done.returncode} でした。"
    if not isinstance(metadata, dict):
        return None, "発注書 lint metadata が object ではありません。"
    findings = metadata.get("findings")
    if not isinstance(findings, list) or not all(
        isinstance(finding, str) for finding in findings
    ):
        return None, "発注書 lint metadata の findings が不正です。"
    if not isinstance(metadata.get("order_document"), bool):
        return None, "発注書 lint metadata の order_document が不正です。"
    review_kind = metadata.get("review_kind")
    if review_kind not in {None, "none", "adversarial", "acceptance"}:
        return None, "発注書 lint metadata の review_kind が不正です。"
    if metadata.get("scope") not in {None, "diff", "artifact"}:
        return None, "発注書 lint metadata の scope が不正です。"
    round_number = metadata.get("round")
    if round_number is not None and (type(round_number) is not int or round_number < 1):
        return None, "発注書 lint metadata の round が不正です。"
    if not isinstance(metadata.get("methods"), list):
        return None, "発注書 lint metadata の methods が不正です。"
    if not isinstance(metadata.get("has_previous_verdict"), bool):
        return None, "発注書 lint metadata の has_previous_verdict が不正です。"
    if metadata.get("report_path") is not None and not isinstance(
        metadata["report_path"], str
    ):
        return None, "発注書 lint metadata の report_path が不正です。"
    if metadata.get("path") != os.path.abspath(path):
        return None, "発注書 lint metadata の path が入力と一致しません。"
    return metadata, None


def _bash_violations(command: str, cwd: str) -> tuple[list[str], bool]:
    """(違反文言, 軸 A の checkpoint を要求するか) を返す。"""
    violations: list[str] = []
    delegating = False
    for launch in _launches(command, cwd):
        if not launch.delegating:
            continue
        delegating = delegating or launch.kind == "companion" or not launch.escaped
        if launch.kind == "cli" and not launch.escaped:
            violations.append(
                "[bare-codex-cli] 素の codex CLI で委譲しています。 正規経路は"
                " codex:codex-rescue subagent または codex-companion.mjs で、 素の CLI は"
                " codex_worktree_gate の射程外のため共有 checkout を壊しても止まりません。"
                f" companion 障害の切り分け目的で codex exec を直接叩くなら、"
                f" segment 先頭に {ESCAPE_HATCH} を置いてください。"
            )
        if launch.wrappers:
            violations.append(
                f"[sandbox-wrapper] {' / '.join(sorted(launch.wrappers))} 経由の起動は "
                "excludedCommands の照合を外れて sandbox に落ち、 監視と通信が遮断されます。 "
                "wrapper を外して直接起動してください。"
            )
        if launch.kind != "companion":
            continue
        args = _before_passthrough(launch.args)
        if launch.subcommand in {"review", "adversarial-review"}:
            swallowed = _unknown_flags(args, REVIEW_OPTIONS)
            if swallowed:
                violations.append(
                    f"[review-swallowed-flag] {' / '.join(swallowed)} は"
                    f" {launch.subcommand} が受理しない flag で、 例外にならず focus text"
                    f" として prompt に連結されます (指定は job record に届きません)。"
                    f" 報告書を成果物にするなら task --write を使ってください。"
                )
        if launch.subcommand in {"task", "task-worker"}:
            unknown = _unknown_flags(args, TASK_OPTIONS)
            if unknown:
                violations.append(
                    f"[unknown-task-flag] {' / '.join(unknown)} は task が受理しない flag で、"
                    f" 解釈されず発注本文として codex に渡ります。"
                    f" 受理するのは {' / '.join(sorted(TASK_OPTIONS))} だけです。"
                )
        effort = _option_value(args, "--effort")
        if effort is not None and effort.strip().lower() not in VALID_EFFORTS:
            violations.append(
                f"[effort] --effort {effort} は無効です。 有効値は "
                f"{' / '.join(sorted(VALID_EFFORTS))} で、 max は wrapper が起動前に弾きます。"
            )
        model = _option_value(args, *MODEL_OPTIONS)
        if model is not None and model.strip().lower() in MODEL_NICKNAMES:
            violations.append(
                f"[model-nickname] --model {model} は俗称で、 API が 400 で弾きます。"
                f" 正式 id (gpt-5.6-{model.strip().lower()} 等) を渡してください。"
            )
        if launch.subcommand not in {"task", "task-worker"}:
            continue
        prompt = " ".join(_positional(launch.args))
        resume = _has_flag(launch.args, RESUME_FLAGS)
        order = _order_path(launch, cwd)
        metadata, metadata_error = (
            _lint_order(order) if order is not None else (None, None)
        )
        review_kind = metadata.get("review_kind") if metadata else None
        review_requested = bool(REVIEW_PROMPT.search(prompt)) or review_kind in {
            "adversarial",
            "acceptance",
        }
        # 発注書を要求するのは write 権限のある起動だけ。 read-only の調査 rescue に
        # 7 節の発注書を強いると、 委譲 cost が作業 cost を上回って委譲自体が消える。
        writable = _has_flag(launch.args, frozenset({"--write"})) or resume
        if resume and _has_flag(launch.args, frozenset({"--write"})):
            sys.stderr.write(
                "codex-delegation-gate (warn): resume は元 thread の sandbox を引き継ぎます。"
                " job record の直近 entry の write を確かめ、"
                " read-only task を挟んでいれば --fresh で張り直してください。\n"
            )
        if writable and not resume and not _mentions_order(launch.args):
            violations.append(
                "[order-file] 発注書 file を渡していません。"
                " 依頼は chat 文でなく発注書 file に固定し、"
                " その path (または --prompt-file) を起動に含めてください。"
            )
        elif writable and not resume and order is None:
            violations.append(
                "[order-file] 発注書 path が一意な regular file ではありません。"
            )
        if review_requested:
            if order is None or metadata_error or metadata is None:
                detail = metadata_error or "regular file の発注書 path がありません。"
                violations.append(
                    "[review-without-lint-pass] task 経由の review は"
                    f" codex_order_lint 通過が必須です。 {detail}"
                )
            elif REVIEW_PROMPT.search(prompt) and review_kind == "none":
                violations.append(
                    "[review-metadata] prompt roster と review-kind: none が矛盾しています。"
                )
            elif review_kind not in {"adversarial", "acceptance"}:
                violations.append(
                    "[review-metadata] review-kind が一意な adversarial / acceptance"
                    " ではありません。"
                )
            elif metadata["findings"]:
                violations.append(
                    "[review-without-lint-pass] task 経由の review 発注書が規約違反です:\n"
                    + "\n".join(str(finding) for finding in metadata["findings"])
                )
        elif metadata is not None and (
            metadata["order_document"] or _option_value(launch.args, "--prompt-file")
        ):
            if metadata["findings"]:
                violations.append(
                    f"[order-lint] 発注書 {order} が規約違反です:\n"
                    + "\n".join(str(finding) for finding in metadata["findings"])
                )
        elif metadata_error:
            violations.append(f"[order-lint] {metadata_error}")
        if order is not None:
            report_path = metadata.get("report_path") if metadata else None
            if not _has_flag(launch.args, frozenset({"--write"})) and (
                report_path or REPORT_HINT.search(prompt)
            ):
                violations.append(
                    "[report-without-write] 報告書を成果物とする発注を"
                    " --write 無しで起動しています。"
                    " 既定 sandbox は read-only で報告書 1 file すら書けず、"
                    " 分析が完走しても成果物ゼロで終わります。"
                )
        if len(CJK.findall(prompt)) > CJK_INLINE_MAX and not _option_value(
            launch.args, "--prompt-file"
        ):
            violations.append(
                f"[cjk-inline] 起動 command 行に長い日本語 prompt を直書きしています"
                f" (CJK {len(CJK.findall(prompt))} 文字 > {CJK_INLINE_MAX})。"
                f" auto-mode の classifier が確率的に deny します。"
                f" 発注書 path を渡すか --prompt-file を使ってください。"
            )
    if delegating and _kill_by_port(command):
        violations.append(
            "[kill-by-port] 同じ command に fuser -k / pkill が含まれています。"
            " port が塞がっていれば別 port を使い、"
            " 止められない process は放置して報告してください。"
        )
    return violations, delegating


def _warn_handmade_monitor(command: str) -> None:
    if COMPANION_SCRIPT not in command or "codex_task_sentinel" in command:
        return
    if not MONITOR_LOOP.search(command) or "status" not in command:
        return
    sys.stderr.write(
        "codex-delegation-gate (warn): 監視 loop を手書きしています。 判定は "
        "codex_task_sentinel <job-id> --artifact <path> --token <str> が決定的に実装済みです。\n"
    )


def _skill_delegation(name: str) -> str | None:
    lowered = name.strip().lower()
    if lowered == "codex:codex-rescue":
        return (
            "[skill-not-a-skill] codex:codex-rescue は skill ではなく subagent です。 "
            "Agent tool の subagent_type に渡してください。"
        )
    if lowered.startswith("codex:") and lowered not in SAFE_CODEX_SKILLS:
        return ""
    return None


def _active_path(session_id: str, agent_key: str) -> str:
    return os.path.join(STATE_DIR, "active", session_id, agent_key + ".json")


def _load_active(session_id: str, agent_key: str) -> dict | None:
    path = _active_path(session_id, agent_key)
    if not os.path.lexists(path):
        return {}
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def _skill_active(payload: dict, now: float) -> bool | None:
    """None は判定不能 (ALLOW)。"""
    session_id = payload.get("session_id")
    if not session_id:
        return None
    state = _load_active(session_id, "main")
    if state is None:
        return None
    record = state.get(REQUIRED_SKILL)
    if payload.get("agent_id"):
        # subagent は skill を invoke できず、 deny 文面も main へ届かない (codex-rescue は
        # Bash 失敗時 return nothing)。 session 内で一度も invoke されていない時だけ止める。
        return None if not state else isinstance(record, dict)
    if not isinstance(record, dict):
        return False
    prompt_id = payload.get("prompt_id")
    if prompt_id is None:
        return now - record.get("ts", 0) <= FALLBACK_WINDOW_SECONDS
    return record.get("prompt_id") == prompt_id


def _direct_companion(payload: dict) -> tuple[str, str] | None:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if tool not in {"Bash", "Monitor"} or not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    cwd_value = payload.get("cwd")
    cwd = cwd_value if isinstance(cwd_value, str) else ""
    parsed = any(launch.kind == "companion" for launch in _launches(command, cwd))
    segments = _segments(command)
    executable = not segments
    for segment in segments:
        # 実行語は前置きを剥がした先頭にしかない。 塊全体を見ると引数の言及まで起動に見える。
        start, wrappers, _escaped = _strip_prefix(segment)
        head = os.path.basename(segment[start]) if start < len(segment) else ""
        executable = executable or bool(
            wrappers
            or head in NODE_NAMES
            or head in SHELL_NAMES
            or head == COMPANION_SCRIPT
        )
    if not parsed and (COMPANION_SCRIPT not in command or not executable):
        return None
    return tool, command


def _direct_route_denial(payload: dict) -> str | None:
    if not payload.get("agent_id"):
        return "main agent の Bash / Monitor からの companion 起動は禁止です。"
    fields = ("agent_type", "subagent_type", "agentType", "subagentType")
    known = [str(payload.get(field) or "").strip().lower() for field in fields]
    known = [value for value in known if value]
    if known and not any("codex-rescue" in value for value in known):
        return "種別を判別できる subagent は codex-rescue 系だけが companion を起動できます。"
    if _skill_active(payload, time.time()) is False:
        return f"main bucket に `{REQUIRED_SKILL}` checkpoint がありません。"
    return None


def _log_direct_attempt(command: str, event: str = "direct-launch-attempt") -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{stamp}\t{event}\t{json.dumps(command, ensure_ascii=True)}"
    encoded = line.encode("ascii")
    if len(encoded) >= ATTEMPT_LINE_MAX_BYTES:
        marker = b"..."
        encoded = encoded[: ATTEMPT_LINE_MAX_BYTES - len(marker) - 1] + marker
    try:
        os.makedirs(DIRECT_STATE_DIR, mode=0o700, exist_ok=True)
        path = os.path.join(DIRECT_STATE_DIR, "direct-launch-attempts.log")
        with open(path, "ab") as handle:
            handle.write(encoded + b"\n")
    except OSError:
        pass


def _direct_deny_text(surface: str, detail: str) -> str:
    route = (
        f"codex-delegation-gate: {surface} の companion 直接起動を deny しました。 {detail} "
        "正規ルートは codex:rescue skill 経由です。 cancel / status はユーザーが起動します。"
    )
    harm = (
        "直接起動 habit の実害:\n"
        "- 監視の誤判定・空待ちの事故 7 件\n"
        "- 品質保証に 76 巡・145 commits\n"
        "- launcher 試作の全損廃棄\n"
        "- 版固定による古い companion の誤用"
    )
    rebuttal = (
        "今回だけ・thin だから・status を見るだけだからは例外になりません。 "
        "例外は上記の実害を再生産した経路そのものです。"
    )
    return "\n\n".join((route, harm, rebuttal))


def _deny_text(surface: str, violations: list[str], skill_missing: bool) -> str:
    parts = [f"codex-delegation-gate: {surface} で codex への委譲を検出しました。"]
    if violations:
        parts.append(
            "次の規約違反があります:\n" + "\n".join(f"- {v}" for v in violations)
        )
    if skill_missing:
        parts.append(
            f"`{REQUIRED_SKILL}` skill を当 turn 内で invoke してから、"
            f" 同じ command を実行し直してください。 {REBUTTAL}"
        )
    parts.append("この hook 自身は file を変更しません。")
    return " ".join(parts) if len(parts) == 2 else "\n\n".join(parts)


def _surface(payload: dict) -> tuple[str, list[str], bool] | None:
    """(経路名, 違反, 委譲か) を返す。 委譲でなく違反も無ければ None。"""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool in {"Agent", "Task"}:
        subagent = str(tool_input.get("subagent_type") or "")
        prompt = str(tool_input.get("prompt") or "")
        # 非 codex 型 subagent に codex 起動を指示する迂回も委譲として捕まえる。
        if "codex" not in subagent.lower() and not WORKFLOW_CODEX.search(prompt):
            return None
        violations = []
        if tool_input.get("isolation") == "worktree":
            violations.append(
                '[isolation] Agent の isolation: "worktree" は使わないでください。 harness の '
                "unchanged 自動掃除が走行中の codex の worktree を削除した実例があります。 "
                "発注側が git worktree add した worktree を --cwd に渡してください。"
            )
        if not MARKDOWN_TOKEN.search(prompt):
            violations.append(
                "[order-file] 発注書 file の path を prompt に含めていません。"
                " 依頼は chat 文でなく発注書 file に固定し、 その path を渡してください。"
            )
        return (f"{tool}(subagent_type={subagent})", violations, True)
    if tool == "Skill":
        name = str(tool_input.get("skill") or "")
        outcome = _skill_delegation(name)
        if outcome is None:
            return None
        violations = [outcome] if outcome else []
        args = str(tool_input.get("args") or "")
        if "--resume" not in args and not MARKDOWN_TOKEN.search(args):
            violations.append(
                "[order-file] 発注書 file の path を渡していません。"
                " 依頼は chat 文でなく発注書 file に固定し、 その path を引数に含めてください。"
            )
        return (f"Skill({name})", violations, True)
    if tool in {"Bash", "Monitor"}:
        command = tool_input.get("command")
        if not isinstance(command, str) or not command:
            return None
        _warn_handmade_monitor(command)
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
        violations, delegating = _bash_violations(command, cwd or "")
        if not violations and not delegating:
            return None
        if tool == "Monitor":
            violations.append(
                "[monitor-launch] Monitor は event を流す tool で、 委譲の起動口ではありません。"
                " 起動は Bash、 監視は codex_task_sentinel <job-id> --artifact <path>"
                " --token <str> に分けてください。"
            )
        return (tool, violations, delegating)
    if tool == "Workflow":
        script = tool_input.get("script")
        if not isinstance(script, str):
            path = tool_input.get("scriptPath")
            script = (
                _read_regular_head(path, SCRIPT_READ_LIMIT)
                if isinstance(path, str) and path
                else ""
            )
        if not WORKFLOW_CODEX.search(script or ""):
            return None
        return (
            "Workflow",
            [
                "[workflow-codex] workflow script 内に codex 生成 step を入れないでください。 "
                "静穏待ちができず moving-target レビューになります。 生成は workflow の外で "
                "行い、 レビューだけを workflow 化してください。"
            ],
            False,
        )
    if tool == "SendMessage":
        target = str(tool_input.get("to") or "")
        if "codex" not in target.lower():
            return None
        return (f"SendMessage(to={target})", [], True)
    if isinstance(tool, str) and tool.startswith("mcp__") and "codex" in tool.lower():
        return (tool, [], True)
    return None


def cmd(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    if payload.get("hook_event_name") not in (None, "PreToolUse"):
        return 0
    direct = _direct_companion(payload)
    if direct is not None:
        direct_surface, command = direct
        route_denial = _direct_route_denial(payload)
        if route_denial is not None:
            _log_direct_attempt(command)
            _emit_deny(_direct_deny_text(direct_surface, route_denial))
            return 0
    found = _surface(payload)
    if found is None:
        return 0
    surface, violations, delegating = found
    skill_missing = False
    if delegating and _skill_active(payload, time.time()) is False:
        skill_missing = True
    if violations or skill_missing:
        if direct is not None:
            _log_direct_attempt(direct[1])
            detail = "次の規約違反があります:\n" + "\n".join(
                f"- {violation}" for violation in violations
            )
            _emit_deny(_direct_deny_text(surface, detail))
        else:
            _emit_deny(_deny_text(surface, violations, skill_missing))
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        return cmd(payload)
    except Exception:
        pass  # fail-open
    return 0


class GateTest(unittest.TestCase):
    """emit-vs-comply。 Run: python3 -m unittest codex_delegation_gate"""

    COMPANION = "/plugins/codex/scripts/codex-companion.mjs"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_state = globals()["STATE_DIR"]
        self.old_direct_state = globals()["DIRECT_STATE_DIR"]
        self.old_lint = globals()["ORDER_LINT"]
        globals()["STATE_DIR"] = os.path.join(self.tmp, "skill")
        globals()["DIRECT_STATE_DIR"] = os.path.join(self.tmp, "direct")
        globals()["ORDER_LINT"] = os.path.join(
            self.tmp, "absent-lint"
        )  # host 依存を断つ

    def tearDown(self):
        globals()["STATE_DIR"] = self.old_state
        globals()["DIRECT_STATE_DIR"] = self.old_direct_state
        globals()["ORDER_LINT"] = self.old_lint
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, prompt_id="p1", ts=None, skill=REQUIRED_SKILL, agent_key="main"):
        path = _active_path("s1", agent_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    skill: {
                        "ts": time.time() if ts is None else ts,
                        "prompt_id": prompt_id,
                    }
                },
                handle,
            )
        return path

    def _run(self, payload):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cmd(payload)
        self.assertEqual(code, 0)
        text = out.getvalue().strip()
        parsed = json.loads(text)["hookSpecificOutput"] if text else None
        return parsed, err.getvalue()

    def _bash(self, command, **extra):
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "session_id": "s1",
            "prompt_id": "p1",
            "cwd": self.tmp,
        }
        extra.setdefault("agent_id", "agent-1")
        extra.setdefault("agent_type", "codex-rescue")
        payload.update(extra)
        return self._run(payload)

    def _reason(self, parsed):
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["permissionDecision"], "deny")
        return parsed["permissionDecisionReason"]

    def _order(self, name="x-order.md", body="発注書\n"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def _metadata_lint(
        self,
        order,
        *,
        review_kind="none",
        findings=None,
        order_document=True,
        report_path=None,
        returncode=0,
    ):
        metadata = {
            "path": os.path.abspath(order),
            "order_document": order_document,
            "review_kind": review_kind,
            "round": None,
            "scope": None,
            "methods": [],
            "has_previous_verdict": False,
            "report_path": report_path,
            "findings": findings or [],
        }
        script = os.path.join(self.tmp, "metadata-lint")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/bin/sh\nprintf '%s\\n' '"
                + json.dumps(metadata, ensure_ascii=False)
                + f"'\nexit {returncode}\n"
            )
        os.chmod(script, 0o755)
        globals()["ORDER_LINT"] = script
        return script

    # --- 経路検出 ---

    def test_agent_codex_without_skill_denies(self):
        parsed, _ = self._run(
            {
                "tool_name": "Agent",
                "tool_input": {
                    "subagent_type": "codex:codex-rescue",
                    "prompt": "order.md を読んで",
                },
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        reason = self._reason(parsed)
        self.assertIn(REQUIRED_SKILL, reason)
        self.assertIn("context に載っている", reason)

    def test_agent_codex_with_skill_allows(self):
        self._seed()
        parsed, _ = self._run(
            {
                "tool_name": "Agent",
                "tool_input": {
                    "subagent_type": "codex:codex-rescue",
                    "prompt": "drafts/x-order.md に従って",
                },
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIsNone(parsed)

    def test_agent_other_type_ignored(self):
        parsed, _ = self._run(
            {
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "general-purpose", "prompt": "hi"},
                "session_id": "s1",
            }
        )
        self.assertIsNone(parsed)

    def test_agent_isolation_worktree_denies_even_with_skill(self):
        self._seed()
        parsed, _ = self._run(
            {
                "tool_name": "Agent",
                "tool_input": {
                    "subagent_type": "codex:codex-rescue",
                    "prompt": "drafts/o.md",
                    "isolation": "worktree",
                },
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn("[isolation]", self._reason(parsed))

    def test_agent_without_order_path_denies(self):
        self._seed()
        parsed, _ = self._run(
            {
                "tool_name": "Agent",
                "tool_input": {
                    "subagent_type": "codex:codex-rescue",
                    "prompt": "直して",
                },
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn("[order-file]", self._reason(parsed))

    def test_skill_codex_namespace_gated_but_safe_ones_pass(self):
        parsed, _ = self._run(
            {
                "tool_name": "Skill",
                "tool_input": {"skill": "codex:rescue"},
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))
        for safe in ("codex:status", "codex-delegation", "writing-code"):
            parsed, _ = self._run(
                {
                    "tool_name": "Skill",
                    "tool_input": {"skill": safe},
                    "session_id": "s1",
                }
            )
            self.assertIsNone(parsed, safe)

    def test_skill_codex_rescue_subagent_name_denies_as_wrong_invocation(self):
        self._seed()
        parsed, _ = self._run(
            {
                "tool_name": "Skill",
                "tool_input": {"skill": "codex:codex-rescue"},
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn("[skill-not-a-skill]", self._reason(parsed))

    def test_bash_companion_task_without_skill_denies(self):
        order = self._order()
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order}", agent_id=None
        )
        self.assertIn("main agent", self._reason(parsed))

    def test_bash_companion_all_main_subcommands_deny(self):
        for sub in (
            "status",
            "cancel",
            "result",
            "setup",
            "task-resume-candidate",
            "task-worker",
        ):
            parsed, _ = self._bash(f"node {self.COMPANION} {sub} --json", agent_id=None)
            self.assertIn("直接起動を deny", self._reason(parsed), sub)

    def test_bash_companion_review_is_delegation(self):
        parsed, _ = self._bash(
            f"node {self.COMPANION} adversarial-review --wait", agent_id=None
        )
        self.assertIn("main agent", self._reason(parsed))

    def test_direct_deny_message_has_three_parts_without_telemetry_disclosure(self):
        parsed, _ = self._bash(f"node {self.COMPANION} status --json", agent_id=None)
        reason = self._reason(parsed)
        self.assertEqual(len(reason.split("\n\n")), 3)
        for fact in (
            "監視の誤判定・空待ちの事故 7 件",
            "品質保証に 76 巡・145 commits",
            "launcher 試作の全損廃棄",
            "版固定による古い companion の誤用",
            "今回だけ・thin だから・status を見るだけだから",
        ):
            self.assertIn(fact, reason)
        self.assertNotIn("telemetry", reason)
        self.assertNotIn("direct-launch-attempts.log", reason)

    def test_direct_attempt_log_is_single_line_capped_and_append_failure_is_quiet(self):
        from unittest.mock import patch

        command = f"node {self.COMPANION} status --json"
        parsed, err = self._bash(command, agent_id=None)
        self.assertIn("直接起動を deny", self._reason(parsed))
        self.assertEqual(err, "")
        log = os.path.join(DIRECT_STATE_DIR, "direct-launch-attempts.log")
        with open(log, "rb") as handle:
            lines = handle.readlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0].decode("ascii"), r"^\d{4}-\d\d-\d\dT.*Z\t")
        self.assertIn(json.dumps(command).encode("ascii"), lines[0])
        long_command = f"node {self.COMPANION} status {'あ' * 5000}"
        parsed, _ = self._bash(long_command, agent_id=None)
        self.assertIn("直接起動を deny", self._reason(parsed))
        with open(log, "rb") as handle:
            lines = handle.readlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(line) <= ATTEMPT_LINE_MAX_BYTES for line in lines))
        with patch("builtins.open", side_effect=PermissionError):
            parsed, err = self._bash(long_command, agent_id=None)
        self.assertIn("直接起動を deny", self._reason(parsed))
        self.assertEqual(err, "")

    def test_known_non_rescue_subagent_denies_but_unknown_type_keeps_checkpoint(self):
        self._seed()
        command = f"node {self.COMPANION} status --json"
        parsed, _ = self._bash(command, agent_type="general-purpose")
        self.assertIn("codex-rescue", self._reason(parsed))
        parsed, _ = self._bash(command, agent_type=None)
        self.assertIsNone(parsed)

    def test_quote_split_companion_name_is_still_direct_launch(self):
        command = "node /plugins/codex-'companion.mjs' status --json"
        self.assertNotIn(COMPANION_SCRIPT, command)
        parsed, _ = self._bash(command, agent_id=None)
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_rg_companion_mention_is_not_a_direct_launch(self):
        parsed, _ = self._bash("rg -n 'codex-companion.mjs' path", agent_id=None)
        self.assertIsNone(parsed)

    def test_grep_companion_mention_is_not_a_direct_launch(self):
        parsed, _ = self._bash("grep -c codex-companion.mjs path", agent_id=None)
        self.assertIsNone(parsed)

    def test_node_companion_path_remains_a_direct_launch(self):
        parsed, _ = self._bash(
            'node "/path/codex-companion.mjs" task ...', agent_id=None
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_variable_companion_path_remains_a_direct_launch(self):
        parsed, _ = self._bash(
            'CC=/path/codex-companion.mjs; node "$CC"', agent_id=None
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_compound_variable_launch_remains_a_direct_launch(self):
        parsed, _ = self._bash(
            'CC=/path/codex-companion.mjs; rg foo && node "$CC"', agent_id=None
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_shell_companion_launch_remains_a_direct_launch(self):
        parsed, _ = self._bash(
            "sh -c 'node /path/codex-companion.mjs task'", agent_id=None
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_single_line_while_companion_launch_is_denied(self):
        parsed, _ = self._bash(
            "while true; do node /path/codex-companion.mjs status; sleep 5; done",
            agent_id=None,
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_single_line_if_companion_launch_is_denied(self):
        parsed, _ = self._bash(
            "if true; then node /path/codex-companion.mjs task; fi", agent_id=None
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_companion_in_loop_condition_is_denied(self):
        """本 gate が止めたい実害は監視 loop。 条件位置は本体位置と同じく起動である。"""
        for command in (
            "while node /path/codex-companion.mjs status; do sleep 5; done",
            "until node /path/codex-companion.mjs status; do sleep 5; done",
            "if node /path/codex-companion.mjs task; then echo ok; fi",
            "until node /path/codex-companion.mjs status | grep -q done; do sleep 10; done",
        ):
            with self.subTest(command=command):
                parsed, _ = self._bash(command, agent_id=None)
                self.assertIn("直接起動を deny", self._reason(parsed))

    def test_watch_wrapped_companion_is_denied(self):
        """watch は option を取る wrapper。 剥がさないと実行語が `-n5` にずれる。"""
        parsed, _ = self._bash(
            "watch -n5 node /path/codex-companion.mjs status", agent_id=None
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_unparseable_companion_command_is_denied(self):
        parsed, _ = self._bash(
            "node /path/codex-companion.mjs task 'unclosed", agent_id=None
        )
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_wrapper_fallback_branch_is_denied(self):
        command = 'CC=/path/codex-companion.mjs; env "$CC" status'
        self.assertEqual(_launches(command), [])
        parsed, _ = self._bash(command, agent_id=None)
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_shell_fallback_branch_is_denied(self):
        command = "CC=/path/codex-companion.mjs; sh -c '\"$CC\" status'"
        self.assertEqual(_launches(command), [])
        parsed, _ = self._bash(command, agent_id=None)
        self.assertIn("直接起動を deny", self._reason(parsed))

    def test_execution_names_work_at_segment_start_and_middle(self):
        names = (
            NODE_NAMES
            | SHELL_NAMES
            | SANDBOX_BREAKING_WRAPPERS
            | frozenset({COMPANION_SCRIPT})
        )
        for name in names:
            if name == COMPANION_SCRIPT:
                commands = (
                    ("先頭", "/path/codex-companion.mjs status"),
                    ("途中", "X=1 /path/codex-companion.mjs status"),
                )
            else:
                invocation = f'{name} "$CC" status'
                commands = (
                    ("先頭", f"CC=/path/codex-companion.mjs; {invocation}"),
                    (
                        "途中",
                        f"CC=/path/codex-companion.mjs; if true; then {invocation}; fi",
                    ),
                )
            for position, command in commands:
                with self.subTest(name=name, position=position):
                    parsed, _ = self._bash(command, agent_id=None)
                    self.assertIn("直接起動を deny", self._reason(parsed))

    def test_bash_bare_codex_cli_denies_with_route_reason(self):
        self._seed()
        parsed, _ = self._bash("codex exec 'fix the bug'")
        self.assertIn("[bare-codex-cli]", self._reason(parsed))

    def test_bash_codex_login_and_neighbour_binaries_pass(self):
        for command in (
            "codex login",
            "codex --version",
            "codex_task_sentinel job-1 --artifact x --token T",
            "/usr/local/bin/codex_order_lint drafts/o.md",
        ):
            parsed, _ = self._bash(command)
            self.assertIsNone(parsed, command)

    def test_sendmessage_to_codex_is_delegation(self):
        parsed, _ = self._run(
            {
                "tool_name": "SendMessage",
                "tool_input": {"to": "codex-rescue", "message": "続けて"},
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))

    def test_workflow_with_codex_step_denies_regardless_of_skill(self):
        self._seed()
        parsed, _ = self._run(
            {
                "tool_name": "Workflow",
                "tool_input": {
                    "script": f"await agent('x'); // node {self.COMPANION} task"
                },
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn("[workflow-codex]", self._reason(parsed))

    def test_workflow_without_codex_passes(self):
        parsed, _ = self._run(
            {
                "tool_name": "Workflow",
                "tool_input": {"script": "await agent('review the diff')"},
                "session_id": "s1",
            }
        )
        self.assertIsNone(parsed)

    # --- 軸 A: skill-active ---

    def test_subagent_other_skill_denies_and_corrupt_state_allows(self):
        order = self._order()
        self._metadata_lint(order)
        self._seed(skill="writing-code")
        parsed, _ = self._bash(f"node {self.COMPANION} task --write {order}")
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))
        path = _active_path("s1", "main")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ broken")
        parsed, _ = self._bash(f"node {self.COMPANION} task --write {order}")
        self.assertIsNone(parsed)

    def test_main_direct_deny_ignores_current_checkpoint(self):
        order = self._order()
        self._seed()
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order}", agent_id=None
        )
        self.assertIn("main agent", self._reason(parsed))

    def test_subagent_passes_on_any_main_record_regardless_of_turn(self):
        order = self._order()
        self._metadata_lint(order)
        self._seed(prompt_id="parent-turn", ts=time.time() - 6 * 3600)
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order}", agent_id="agent-1"
        )
        self.assertIsNone(parsed)

    def test_subagent_denied_when_main_invoked_other_skills_only(self):
        order = self._order()
        self._seed(skill="writing-code")
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order}", agent_id="agent-1"
        )
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))

    def test_subagent_allowed_when_main_bucket_absent(self):
        order = self._order()
        self._metadata_lint(order)
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order}", agent_id="agent-1"
        )
        self.assertIsNone(parsed)

    def test_monitor_tool_is_gated_like_bash(self):
        self._seed()
        order = self._order()
        parsed, _ = self._run(
            {
                "tool_name": "Monitor",
                "tool_input": {
                    "command": f"node {self.COMPANION} task --write {order}",
                    "description": "codex run",
                },
                "session_id": "s1",
                "prompt_id": "p1",
                "cwd": self.tmp,
            }
        )
        self.assertIn("companion 直接起動を deny", self._reason(parsed))

    def test_monitor_running_sentinel_passes(self):
        parsed, _ = self._run(
            {
                "tool_name": "Monitor",
                "tool_input": {"command": "codex_task_sentinel j1 --token T"},
                "session_id": "s1",
                "prompt_id": "p1",
                "cwd": self.tmp,
            }
        )
        self.assertIsNone(parsed)

    def test_shell_indirection_one_level(self):
        order = self._order()
        self._seed(skill="writing-code")
        inner = f"node {self.COMPANION} task --write {order}"
        parsed, _ = self._bash(f"bash -c '{inner}'")
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))
        script = os.path.join(self.tmp, "launch.sh")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(f"#!/bin/bash\n{inner}\n")
        parsed, _ = self._bash(f"bash {script}")
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))

    def test_option_taking_wrappers_do_not_hide_the_launch(self):
        order = self._order()
        self._seed(skill="writing-code")
        for prefix in ("timeout -k 5 600", "stdbuf -oL", "setsid", "nice -n 10"):
            parsed, _ = self._bash(
                f"{prefix} node {self.COMPANION} task --write {order}"
            )
            self.assertIn(REQUIRED_SKILL, self._reason(parsed), prefix)

    def test_substitution_and_subshell_forms_are_detected(self):
        order = self._order()
        self._seed(skill="writing-code")
        for form in (
            f"X=$(node {self.COMPANION} task --write {order})",
            f"(node {self.COMPANION} task --write {order})",
        ):
            parsed, _ = self._bash(form)
            self.assertIn(REQUIRED_SKILL, self._reason(parsed), form)

    def test_escape_hatch_cannot_waive_companion_checkpoint(self):
        order = self._order()
        self._seed(skill="writing-code")
        parsed, _ = self._bash(
            f"{ESCAPE_HATCH} node {self.COMPANION} task --write {order}"
        )
        reason = self._reason(parsed)
        self.assertIn(REQUIRED_SKILL, reason)
        self.assertNotIn(ESCAPE_HATCH, reason)

    def test_agent_prompt_ordering_codex_launch_is_delegation(self):
        parsed, _ = self._run(
            {
                "tool_name": "Agent",
                "tool_input": {
                    "subagent_type": "general-purpose",
                    "prompt": "drafts/o.md を読み codex exec で直して",
                },
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))

    def test_mcp_codex_tool_is_delegation(self):
        parsed, _ = self._run(
            {
                "tool_name": "mcp__codex__run_task",
                "tool_input": {"prompt": "x"},
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))

    def test_task_resume_candidate_is_not_delegation(self):
        parsed, _ = self._bash(f"node {self.COMPANION} task-resume-candidate --json")
        self.assertIsNone(parsed)

    def test_read_only_task_does_not_require_order_file(self):
        self._seed()
        parsed, _ = self._bash(f'node {self.COMPANION} task "この panic の原因を見て"')
        self.assertIsNone(parsed)

    def test_review_only_workflow_passes(self):
        parsed, _ = self._run(
            {
                "tool_name": "Workflow",
                "tool_input": {
                    "script": f"// node {self.COMPANION} adversarial-review --wait"
                },
                "session_id": "s1",
            }
        )
        self.assertIsNone(parsed)

    def test_subagent_own_bucket_does_not_self_authorize(self):
        order = self._order()
        self._seed(skill="writing-code")  # main は別 skill だけ invoke
        self._seed(agent_key="agent-1")  # subagent 自身は codex-delegation を持つ
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order}", agent_id="agent-1"
        )
        self.assertIn(REQUIRED_SKILL, self._reason(parsed))

    def test_missing_session_id_does_not_open_main_direct_route(self):
        order = self._order()
        parsed, _ = self._run(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": f"node {self.COMPANION} task --write {order}"
                },
                "cwd": self.tmp,
            }
        )
        self.assertIn("main agent", self._reason(parsed))

    # --- 軸 B: invocation lint ---

    def test_companion_dispatch_and_worktree_value_options_are_pinned(self):
        launch = Launch("companion", ["--cwd", self.tmp, "task"], frozenset())
        self.assertEqual(launch.subcommand, "--cwd")
        self.assertEqual(
            WORKTREE_VALUE_OPTIONS, frozenset({"--cwd", "-C", "--model", "--log"})
        )
        self.assertLessEqual(WORKTREE_VALUE_OPTIONS, VALUE_OPTIONS)

    def test_effort_and_model_are_option_position_only(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order)
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write --effort max --model sol {order}"
        )
        reason = self._reason(parsed)
        self.assertIn("[effort]", reason)
        self.assertIn("[model-nickname]", reason)
        self.assertEqual(len(reason.split("\n\n")), 3)
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order} "
            "'--effort max と --model sol は使うな'"
        )
        self.assertIsNone(parsed)

    def test_valid_effort_and_official_model_pass(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order)
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write --effort xhigh --model gpt-5.6-sol {order}"
        )
        self.assertIsNone(parsed)

    def test_sandbox_breaking_wrapper_denies(self):
        self._seed()
        order = self._order()
        parsed, _ = self._bash(f"env node {self.COMPANION} task --write {order}")
        self.assertIn("[sandbox-wrapper]", self._reason(parsed))

    def test_transparent_wrapper_passes(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order)
        parsed, _ = self._bash(
            f"CODEX_ROUTE_OK=1 timeout 60 node {self.COMPANION} task --write {order}"
        )
        self.assertIsNone(parsed)

    def test_order_file_missing_denies_but_resume_exempt(self):
        self._seed()
        parsed, _ = self._bash(f'node {self.COMPANION} task --write "続きをやって"')
        self.assertIn("[order-file]", self._reason(parsed))
        parsed, _ = self._bash(
            f'node {self.COMPANION} task --write --resume-last "続きをやって"'
        )
        self.assertIsNone(parsed)

    def test_order_path_inside_quoted_prompt_counts(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order)
        parsed, _ = self._bash(
            f'node {self.COMPANION} task --write "Read {order} and follow it"'
        )
        self.assertIsNone(parsed)
        launch = _launches(f'node {self.COMPANION} task --write "Read {order} x"')[0]
        self.assertEqual(_order_path(launch, self.tmp), order)

    def test_report_artifact_requires_write(self):
        self._seed()
        order = self._order(body="## 成果物\n\ndrafts/x-report.md を書く\n")
        self._metadata_lint(order, report_path="drafts/x-report.md")
        parsed, _ = self._bash(f"node {self.COMPANION} task {order}")
        self.assertIn("[report-without-write]", self._reason(parsed))
        parsed, _ = self._bash(f"node {self.COMPANION} task --write {order}")
        self.assertIsNone(parsed)

    def test_cjk_inline_prompt_denies(self):
        self._seed()
        parsed, _ = self._bash(
            f'node {self.COMPANION} task --write "{"あ" * (CJK_INLINE_MAX + 1)} x.md"'
        )
        self.assertIn("[cjk-inline]", self._reason(parsed))

    def test_kill_by_port_only_in_executable_position(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order)
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order} && fuser -k 5273/tcp"
        )
        self.assertIn("[kill-by-port]", self._reason(parsed))
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order} 'fuser -k と pkill は禁止'"
        )
        self.assertIsNone(parsed)

    def test_order_lint_failure_denies(self):
        self._seed()
        order = self._order(body="## スコープ\n\n節が 1 つしかない発注書\n")
        self._metadata_lint(
            order, findings=["必須の節がない: ## スコープ"], returncode=1
        )
        parsed, _ = self._bash(f"node {self.COMPANION} task --write {order}")
        self.assertIn("[order-lint]", self._reason(parsed))

    def test_missing_lint_denies_all_mode_and_order_route_cells(self):
        self._seed()
        order = self._order()
        for writable in (False, True):
            for prompt_file in (False, True):
                route = f"--prompt-file {order}" if prompt_file else order
                write = "--write " if writable else ""
                with self.subTest(writable=writable, prompt_file=prompt_file):
                    parsed, _ = self._bash(f"node {self.COMPANION} task {write}{route}")
                    self.assertIn("[order-lint]", self._reason(parsed))

    def test_corrupt_lint_denies_both_writable_order_routes(self):
        self._seed()
        order = self._order()
        script = os.path.join(self.tmp, "corrupt-lint")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nprintf 'not-json\\n'\n")
        os.chmod(script, 0o755)
        globals()["ORDER_LINT"] = script
        for route in (order, f"--prompt-file {order}"):
            with self.subTest(route=route):
                parsed, _ = self._bash(f"node {self.COMPANION} task --write {route}")
                self.assertIn("[order-lint]", self._reason(parsed))

    def test_lint_timeout_denies_both_writable_order_routes(self):
        from unittest import mock

        self._seed()
        order = self._order()
        self._metadata_lint(order)
        for route in (order, f"--prompt-file {order}"):
            with (
                self.subTest(route=route),
                mock.patch.object(
                    subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired("lint", ORDER_LINT_TIMEOUT),
                ),
            ):
                parsed, _ = self._bash(f"node {self.COMPANION} task --write {route}")
                self.assertIn("[order-lint]", self._reason(parsed))

    def test_referenced_doc_that_is_not_an_order_is_not_linted(self):
        self._seed()
        doc = self._order(name="methodology.md", body="# 手順書\n\n本文\n")
        self._metadata_lint(
            doc,
            findings=["必須の節がない"],
            order_document=False,
            returncode=1,
        )
        parsed, _ = self._bash(f'node {self.COMPANION} task --write "{doc} の手順で"')
        self.assertIsNone(parsed)

    def test_task_review_requires_lint_metadata_and_uses_it_statelessly(self):
        self._seed()
        parsed, _ = self._bash(f'node {self.COMPANION} task "敵対レビューを実施"')
        self.assertIn("[review-without-lint-pass]", self._reason(parsed))
        order = self._order(body="review-kind: adversarial\ntarget: auth-fix\n")
        self._metadata_lint(order, review_kind="adversarial")
        parsed, _ = self._bash(
            f'node {self.COMPANION} task "敵対レビューを実施 {order}"'
        )
        self.assertIsNone(parsed)
        self.assertEqual(
            set(os.listdir(self.tmp)),
            {"direct", "metadata-lint", "skill", "x-order.md"},
        )

    def test_review_prompt_and_lint_metadata_must_agree(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order, review_kind="none")
        parsed, _ = self._bash(
            f'node {self.COMPANION} task "敵対レビューを実施 {order}"'
        )
        self.assertIn("[review-metadata]", self._reason(parsed))
        self._metadata_lint(
            order,
            review_kind="adversarial",
            findings=["review contract が不正"],
            returncode=1,
        )
        parsed, _ = self._bash(f"node {self.COMPANION} task {order}")
        self.assertIn("[review-without-lint-pass]", self._reason(parsed))

    def test_review_roster_words_require_review_metadata_but_completed_forms_do_not(
        self,
    ):
        self._seed()
        order = self._order()
        self._metadata_lint(order, review_kind="none")
        for word in ("review", "audit", "inspect", "レビュー", "監査"):
            with self.subTest(word=word):
                parsed, _ = self._bash(f'node {self.COMPANION} task "{word} {order}"')
                self.assertIn("[review-metadata]", self._reason(parsed))
        for word in ("reviewed", "preaudit", "inspection", "レビュー済み"):
            with self.subTest(word=word):
                parsed, _ = self._bash(f'node {self.COMPANION} task "{word} {order}"')
                self.assertIsNone(parsed)

    def test_gate_does_not_open_the_order_document(self):
        from unittest.mock import patch

        self._seed()
        order = self._order()
        self._metadata_lint(order)
        real_open = open

        def reject_order(path, *args, **kwargs):
            if os.fspath(path) == order:
                raise AssertionError("gate opened order")
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=reject_order):
            parsed, _ = self._bash(f"node {self.COMPANION} task --write {order}")
        self.assertIsNone(parsed)

    def test_special_order_file_is_denied_without_opening_it(self):
        self._seed()
        pipe = os.path.join(self.tmp, "pipe.md")
        link = os.path.join(self.tmp, "link.md")
        os.mkfifo(pipe)
        os.symlink(pipe, link)
        parsed, _ = self._bash(f"node {self.COMPANION} task --write {link}")
        self.assertIn("regular file", self._reason(parsed))

    def test_review_swallows_unsupported_flags(self):
        self._seed()
        parsed, _ = self._bash(
            f"node {self.COMPANION} adversarial-review --effort xhigh --write 'auth'"
        )
        reason = self._reason(parsed)
        self.assertIn("[review-swallowed-flag]", reason)
        self.assertIn("--effort", reason)
        parsed, _ = self._bash(
            f"node {self.COMPANION} adversarial-review --base main --wait 'auth'"
        )
        self.assertIsNone(parsed)

    def test_task_typo_flag_becomes_prompt_text(self):
        self._seed()
        order = self._order()
        parsed, _ = self._bash(f"node {self.COMPANION} task --wirte {order}")
        self.assertIn("[unknown-task-flag]", self._reason(parsed))
        parsed, _ = self._bash(f"node {self.COMPANION} task --help")
        self.assertIn("[unknown-task-flag]", self._reason(parsed))

    def test_passthrough_and_prompt_text_are_not_flags(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order)
        parsed, _ = self._bash(
            f"node {self.COMPANION} task --write {order} -- --review-focus x"
        )
        reason = self._reason(parsed)
        self.assertIn("[review-metadata]", reason)
        self.assertNotIn("[unknown-task-flag]", reason)

    def test_prompt_content_checks_cover_both_sides_of_passthrough(self):
        self._seed()
        order = self._order()
        self._metadata_lint(order)
        cases = (
            ("review", "--write", "adversarial review", "[review-metadata]"),
            ("report", "", "報告書 を書く", "[report-without-write]"),
            (
                "cjk",
                "--write",
                "あ" * (CJK_INLINE_MAX + 1),
                "[cjk-inline]",
            ),
            ("harmless", "--write", "implement safely", None),
        )
        # args.mjs:12-20 と codex-companion.mjs:648 の prompt 連結仕様。
        for side in ("before", "after"):
            for family, write, content, expected in cases:
                separator = "-- " if side == "after" else ""
                command = (
                    f"node {self.COMPANION} task {write} {order} "
                    f"{separator}{shlex.quote(content)}"
                )
                with self.subTest(side=side, family=family):
                    parsed, _ = self._bash(command)
                    if expected is None:
                        self.assertIsNone(parsed)
                    else:
                        self.assertIn(expected, self._reason(parsed))

    def test_bare_cli_bisection_allowed_with_escape_hatch(self):
        self._seed()
        parsed, _ = self._bash(f"{ESCAPE_HATCH} codex exec --cd /tmp/wt 'probe'")
        self.assertIsNone(parsed)

    def test_skill_rescue_requires_order_path(self):
        self._seed()
        parsed, _ = self._run(
            {
                "tool_name": "Skill",
                "tool_input": {"skill": "codex:rescue", "args": "この bug を直して"},
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIn("[order-file]", self._reason(parsed))
        parsed, _ = self._run(
            {
                "tool_name": "Skill",
                "tool_input": {
                    "skill": "codex:rescue",
                    "args": "--background drafts/x-order.md に従って",
                },
                "session_id": "s1",
                "prompt_id": "p1",
            }
        )
        self.assertIsNone(parsed)

    def test_order_lint_absent_binary_is_denied(self):
        self._seed()
        order = self._order()
        old = globals()["ORDER_LINT"]
        globals()["ORDER_LINT"] = os.path.join(self.tmp, "no-such-lint")
        try:
            parsed, _ = self._bash(f"node {self.COMPANION} task --write {order}")
            self.assertIn("[order-lint]", self._reason(parsed))
        finally:
            globals()["ORDER_LINT"] = old

    def test_resume_with_write_warns_without_denying(self):
        self._seed()
        parsed, err = self._bash(
            f"node {self.COMPANION} task --write --resume-last '続き'"
        )
        self.assertIsNone(parsed)
        self.assertIn("--fresh", err)

    def test_handmade_monitor_warns_without_denying(self):
        self._seed()
        parsed, err = self._bash(
            f"until node {self.COMPANION} status --json | grep -q done; do sleep 10; done"
        )
        self.assertIsNone(parsed)
        self.assertIn("codex_task_sentinel", err)

    # --- fail-open ---

    def test_fail_open_shapes(self):
        for payload in (
            None,
            [],
            {},
            {"tool_name": "Bash"},
            {"tool_name": "Bash", "tool_input": None},
        ):
            parsed, _ = self._run(payload)
            self.assertIsNone(parsed, repr(payload))

    def test_unparseable_command_is_not_a_launch(self):
        self.assertEqual(_launches("node 'unbalanced"), [])

    def test_main_fail_open_when_cmd_raises(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("{}")
            buffer = io.StringIO()
            with patch(__name__ + ".cmd", side_effect=RuntimeError("boom")):
                with redirect_stdout(buffer):
                    self.assertEqual(main(), 0)
            self.assertEqual(buffer.getvalue(), "")
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    sys.exit(main())
