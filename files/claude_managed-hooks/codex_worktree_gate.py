#!/usr/bin/env python3
"""Deny shared-tree write-capable codex tasks from a PreToolUse Bash hook.

この hook は token 列の走査であり shell interpreter ではない。``cd`` は追跡
するが、変数展開・コマンド置換・``cd -``・``popd``・裸の ``pushd``・
``pushd -n`` は確定できない。``&``・pipeline の subshell 内 cd や条件付き非実行
(``false && cd ...``)、``bash -c``・``eval`` も静的には解さない。``$'...'`` 内の
escape sequence は解さず、``--cwd`` の変数展開・コマンド置換はせず literal として扱う。

この gate が防ぐ脅威は、発注側自身の不注意で共有 checkout へ write 委譲する事故である。
迂回主体は agent 自身なので敵対的な bypass は脅威に数えず、任意 bash の静的解析で網羅を目指さない。
静的に解けない形は上記の caveat に含まれ、確実に判定させたいときは ``--cwd <絶対 path>`` を明示する。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


GIT_TIMEOUT_SECONDS = 2
CODEX_SCRIPT = "codex-companion.mjs"
WRITE_FLAGS = {"--write", "--resume-last", "--resume"}
SHELL_PUNCTUATION = frozenset(";&|()")
LEXER_PUNCTUATION = ";&|()`"
ESCAPE_HATCH = "CODEX_SHARED_TREE_OK=1"
ASSIGNMENT = re.compile(r"^\w+=\S*$")
CD_OPTIONS = {"-P", "-L", "-e", "-@"}
COMMAND_PREFIXES = {
    "{",
    "if",
    "then",
    "else",
    "elif",
    "do",
    "while",
    "until",
    "for",
    "builtin",
    "command",
    "time",
    "nohup",
    "env",
}
HOME_UNSET = "__codex_worktree_gate_home_unset__"
POPD_UNCERTAIN = "__codex_worktree_gate_popd_uncertain__"
PUSHD_NO_OPERAND = "__codex_worktree_gate_pushd_no_operand__"
PUSHD_NO_CHANGE = "__codex_worktree_gate_pushd_no_change__"

# The reason is intentionally verbose so corrective actions survive model trimming.
DENY_REASON = (
    "codex-worktree-gate: 共有 checkout では書き込みを伴う codex task を起動できません。"
    "codex が実際に走る cwd を git で実測した結果、linked worktree ではありません。"
    "発注側が git worktree add で worktree を作り、その path を codex の --cwd に渡してください。"
    'Agent の isolation: "worktree" は使わないでください（走行中の worktree が自動掃除される実例あり）。'
    "read-only レビューなら --write を外せば通ります。"
    "意図的に共有ツリーへ書く場合は、codex を起動するセグメントの先頭に CODEX_SHARED_TREE_OK=1 を付けてください。"
    "この hook 自身は file を変更しません。"
)
ESCAPE_CONTEXT = (
    "共有ツリーへの codex 書き込みを明示許可で通過。"
    "並行セッションの変更が混在する可能性がある。"
)


def _emit(output: dict[str, str]) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    **output,
                }
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def _fail_open(reason: str) -> None:
    sys.stderr.write(
        f"codex-worktree-gate: {reason}; allowing because git context was not verified.\n"
    )


class _ShellToken(str):
    def __new__(
        cls, value: str, raw: str, unquoted_markers: frozenset[str]
    ) -> _ShellToken:
        token = str.__new__(cls, value)
        token.raw = raw
        token.unquoted_markers = unquoted_markers
        return token


def _raw_shell_tokens(command: str) -> list[tuple[str, frozenset[str]]]:
    command = _prepare_shell_command(command)
    tokens: list[tuple[str, frozenset[str]]] = []
    raw: list[str] = []
    markers: set[str] = set()
    quote: str | None = None
    token_started = False
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            raw.append(char)
            token_started = True
            if char == quote:
                quote = None
            elif quote == '"' and char == "\\" and index + 1 < len(command):
                index += 1
                raw.append(command[index])
            index += 1
            continue
        if char.isspace():
            if token_started:
                tokens.append(("".join(raw), frozenset(markers)))
                raw = []
                markers = set()
                token_started = False
            index += 1
            continue
        if char in LEXER_PUNCTUATION:
            if token_started:
                tokens.append(("".join(raw), frozenset(markers)))
                raw = []
                markers = set()
                token_started = False
            punctuation: list[str] = []
            while index < len(command) and command[index] in LEXER_PUNCTUATION:
                punctuation.append(command[index])
                index += 1
            tokens.append(("".join(punctuation), frozenset(punctuation)))
            continue
        raw.append(char)
        token_started = True
        if char in "\\" and index + 1 < len(command):
            index += 1
            raw.append(command[index])
        elif char in "'\"":
            quote = char
        elif char in "$`()":
            markers.add(char)
        index += 1
    if token_started:
        tokens.append(("".join(raw), frozenset(markers)))
    return tokens


def _shell_tokens(command: str) -> list[str]:
    normalized_command = _prepare_shell_command(command)
    lexer = shlex.shlex(
        normalized_command, posix=True, punctuation_chars=LEXER_PUNCTUATION
    )
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        parsed = list(lexer)
    except ValueError:
        _fail_open("command could not be tokenized")
        return []
    raw_tokens = _raw_shell_tokens(normalized_command)
    if len(parsed) != len(raw_tokens):
        return parsed
    return [
        _ShellToken(value, raw, markers)
        for value, (raw, markers) in zip(parsed, raw_tokens, strict=True)
    ]


def _prepare_shell_command(command: str) -> str:
    command = re.sub(r"\\(?:\r\n|\n)", "", command)
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            result.append(char)
            if char == quote:
                quote = None
            elif quote == '"' and char == "\\" and index + 1 < len(command):
                index += 1
                result.append(command[index])
            index += 1
            continue
        if char in "'\"":
            quote = char
            result.append(char)
        elif char == "$" and index + 1 < len(command) and command[index + 1] in "'\"":
            index += 1
            result.append(command[index])
            quote = command[index]
        else:
            result.append(char)
        index += 1
    return "".join(result).replace("\r\n", ";").replace("\n", ";")


# bash -c/eval recursion is out of scope; only this shell level is tokenized.


def _is_separator(token: str) -> bool:
    markers = _token_markers(token)
    return (
        bool(token)
        and bool(markers)
        and all(char in SHELL_PUNCTUATION for char in token)
    )


def _is_codex_script(token: str) -> bool:
    return token == CODEX_SCRIPT or token.replace("\\", "/").endswith(
        f"/{CODEX_SCRIPT}"
    )


def _argument_words(tokens: list[str]) -> list[str]:
    return [word.strip("\"'") for token in tokens for word in token.split()]


def _command_prefix(segment: list[str]) -> tuple[int, str | None]:
    index = 0
    while index < len(segment) and (
        ASSIGNMENT.match(segment[index]) or segment[index] in COMMAND_PREFIXES
    ):
        index += 1
    return index, segment[index] if index < len(segment) else None


def _token_raw(token: str) -> str:
    return getattr(token, "raw", token)


def _token_markers(token: str) -> frozenset[str]:
    return getattr(token, "unquoted_markers", frozenset())


def _substitution_end(arguments: list[str], start: int, closing: str) -> int | None:
    for index in range(start + 1, len(arguments)):
        if arguments[index] == closing and not (
            _token_markers(arguments[index]) - {closing}
        ):
            return index
    return None


def _resolve_path_operand(
    operand: str,
    token: str,
    effective_cwd: str | None,
    payload_cwd: str | None,
) -> tuple[str | None, str | None]:
    if _token_markers(token):
        return effective_cwd, _token_raw(token)
    if operand == "-":
        return payload_cwd, _token_raw(token)
    expanded = os.path.expanduser(operand)
    if expanded.startswith("~"):
        return payload_cwd, _token_raw(token)
    path = os.path.abspath(os.path.join(effective_cwd or os.curdir, expanded))
    if not os.path.isdir(path):
        return payload_cwd, _token_raw(token)
    return path, None


def _env_prefix_index(segment: list[str]) -> int | None:
    index = 0
    while index < len(segment) and (
        ASSIGNMENT.match(segment[index]) or segment[index] in COMMAND_PREFIXES
    ):
        if segment[index] == "env":
            return index
        index += 1
    return None


def _env_chdir(
    segment: list[str], effective_cwd: str | None, payload_cwd: str | None
) -> tuple[str | None, str | None] | None:
    env_index = _env_prefix_index(segment)
    if env_index is None:
        return None
    arguments = segment[env_index + 1 :]
    selected: str | None = None
    selected_token: str | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"-C", "--chdir"}:
            if index + 1 >= len(arguments) or not arguments[index + 1]:
                return payload_cwd, _token_raw(argument)
            selected = arguments[index + 1]
            selected_token = arguments[index + 1]
            index += 2
            continue
        if argument.startswith("--chdir="):
            selected = argument.split("=", 1)[1]
            selected_token = argument
            index += 1
            continue
        if argument.startswith("-"):
            index += 1
            continue
        break
    if selected is None or selected_token is None:
        return effective_cwd, None
    return _resolve_path_operand(selected, selected_token, effective_cwd, payload_cwd)


def _cd_path(
    segment: list[str], effective_cwd: str | None, payload_cwd: str | None
) -> tuple[str | None, str | None]:
    env_result = _env_chdir(segment, effective_cwd, payload_cwd)
    if env_result is not None:
        return env_result
    prefix_index, program = _command_prefix(segment)
    if program not in {"cd", "pushd", "popd"}:
        return effective_cwd, None
    if program == "popd":
        return payload_cwd, POPD_UNCERTAIN
    arguments = segment[prefix_index + 1 :]
    operand: str | None = None
    operand_index: int | None = None
    after_double_dash = False
    option_letters = {letter for option in CD_OPTIONS for letter in option[1:]}
    for index, argument in enumerate(arguments):
        if program == "pushd" and argument == "-n":
            return payload_cwd, PUSHD_NO_CHANGE
        if after_double_dash:
            operand = argument
            operand_index = index
            break
        if argument == "--":
            after_double_dash = True
            continue
        if argument in CD_OPTIONS or (
            argument.startswith("-")
            and len(argument) > 1
            and set(argument[1:]) <= option_letters
        ):
            continue
        operand = argument
        operand_index = index
        break
    if operand is None:
        if program == "pushd":
            return payload_cwd, PUSHD_NO_OPERAND
        operand = os.environ.get("HOME")
        if not operand:
            return payload_cwd, HOME_UNSET
    token = arguments[operand_index] if operand_index is not None else operand
    return _resolve_path_operand(operand, token, effective_cwd, payload_cwd)


def _has_env_chdir(segment: list[str]) -> bool:
    env_index = _env_prefix_index(segment)
    if env_index is None:
        return False
    arguments = segment[env_index + 1 :]
    index = 0
    while index < len(arguments):
        if arguments[index] in {"-C", "--chdir"}:
            return True
        if arguments[index].startswith("--chdir="):
            return True
        if not arguments[index].startswith("-"):
            return False
        index += 1
    return False


def _subcommand(arguments: list[str]) -> str | None:
    index = 0
    options_with_values = {"--cwd", "-C", "--model", "--log"}
    substitution_seen = False
    while index < len(arguments):
        raw_argument = arguments[index]
        argument = raw_argument.strip("\"'")
        if argument in options_with_values:
            if index + 1 < len(arguments) and _token_markers(arguments[index + 1]):
                substitution_seen = True
            index += 2
            continue
        if _token_markers(raw_argument) & {"$", "`"}:
            substitution_seen = True
            index += 1
            continue
        if argument.startswith("-"):
            index += 1
            continue
        if substitution_seen:
            if argument == "task":
                return argument
            index += 1
            continue
        return argument
    return None


def _scan_segment(
    segment: list[str],
    effective_cwd: str | None,
    payload_cwd: str | None,
    uncertain_cd: str | None,
    matches: list[tuple[list[str], int, str | None, str | None]],
) -> tuple[str | None, str | None]:
    new_cwd, new_uncertain = _cd_path(segment, effective_cwd, payload_cwd)
    segment_cwd = new_cwd if _has_env_chdir(segment) else effective_cwd
    segment_uncertain = new_uncertain if _has_env_chdir(segment) else uncertain_cd
    for index, candidate in enumerate(segment):
        if not _is_codex_script(candidate):
            continue
        arguments = segment[index + 1 :]
        words = _argument_words(arguments)
        has_task = _subcommand(arguments) == "task"
        has_write_flag = any(
            argument.split("=", 1)[0] in WRITE_FLAGS for argument in words
        )
        if has_task and has_write_flag:
            matches.append((segment.copy(), index, segment_cwd, segment_uncertain))
    if _has_env_chdir(segment):
        return effective_cwd, uncertain_cd
    if _command_prefix(segment)[1] in {"cd", "pushd", "popd"}:
        return new_cwd, new_uncertain
    return new_cwd, uncertain_cd


def _find_codex_write_segment(
    command: str,
    payload_cwd: str | None = None,
) -> list[tuple[list[str], int, str | None, str | None]]:
    segment: list[str] = []
    matches: list[tuple[list[str], int, str | None, str | None]] = []
    effective_cwd = os.path.abspath(payload_cwd) if payload_cwd else None
    uncertain_cd: str | None = None
    segment_start_cwd = effective_cwd
    segment_start_uncertain = uncertain_cd
    group_stack: list[tuple[str, str | None, str | None, list[str], str | None]] = []
    tokens = [*_shell_tokens(command), _ShellToken("&&", "&&", frozenset("&"))]
    for token in tokens:
        if _is_separator(token) or (token == "`" and "`" in _token_markers(token)):
            if token == "`" and (not group_stack or group_stack[-1][0] != "backtick"):
                _scan_segment(
                    segment,
                    effective_cwd,
                    payload_cwd,
                    uncertain_cd,
                    matches,
                )
                group_stack.append(
                    ("backtick", effective_cwd, uncertain_cd, segment.copy(), None)
                )
                segment = []
                segment_start_cwd = effective_cwd
                segment_start_uncertain = uncertain_cd
                continue
            if token == "(":
                previous = segment[-1] if segment else None
                previous_raw = _token_raw(previous) if previous is not None else ""
                is_attached_substitution = bool(
                    previous is not None
                    and "$" in _token_markers(previous)
                    and previous_raw.endswith("$")
                )
                is_substitution = bool(segment) and (
                    previous == "$" or is_attached_substitution
                )
                if is_substitution:
                    prefix = segment[:-1]
                    base = "" if previous == "$" else previous_raw[:-1]
                    _scan_segment(
                        prefix,
                        effective_cwd,
                        payload_cwd,
                        uncertain_cd,
                        matches,
                    )
                    group_stack.append(
                        (
                            "substitution",
                            effective_cwd,
                            uncertain_cd,
                            prefix,
                            base,
                        )
                    )
                else:
                    effective_cwd, uncertain_cd = _scan_segment(
                        segment,
                        effective_cwd,
                        payload_cwd,
                        uncertain_cd,
                        matches,
                    )
                    group_stack.append(("group", effective_cwd, uncertain_cd, [], None))
                segment = []
                segment_start_cwd = effective_cwd
                segment_start_uncertain = uncertain_cd
                continue
            if token == "`" and group_stack[-1][0] == "backtick":
                _, saved_cwd, saved_uncertain, prefix, _ = group_stack.pop()
                _scan_segment(
                    segment,
                    effective_cwd,
                    payload_cwd,
                    uncertain_cd,
                    matches,
                )
                raw_substitution = f"`{' '.join(_token_raw(part) for part in segment)}`"
                synthetic = _ShellToken(
                    raw_substitution, raw_substitution, frozenset("`")
                )
                segment = [*prefix, synthetic]
                effective_cwd = saved_cwd
                uncertain_cd = saved_uncertain
                segment_start_cwd = effective_cwd
                segment_start_uncertain = uncertain_cd
                continue
            if token == ")" and group_stack:
                stack_kind, saved_cwd, saved_uncertain, prefix, base = group_stack.pop()
                if stack_kind == "substitution":
                    _scan_segment(
                        segment,
                        effective_cwd,
                        payload_cwd,
                        uncertain_cd,
                        matches,
                    )
                    prefix_substitution = f"{base}$" if base else "$"
                    raw_substitution = (
                        f"{prefix_substitution}("
                        f"{' '.join(_token_raw(part) for part in segment)})"
                    )
                    synthetic = _ShellToken(
                        raw_substitution, raw_substitution, frozenset("$(")
                    )
                    segment = [*prefix, synthetic]
                    effective_cwd = saved_cwd
                    uncertain_cd = saved_uncertain
                else:
                    effective_cwd, uncertain_cd = _scan_segment(
                        segment,
                        effective_cwd,
                        payload_cwd,
                        uncertain_cd,
                        matches,
                    )
                    effective_cwd, uncertain_cd = saved_cwd, saved_uncertain
                    segment = []
                segment_start_cwd = effective_cwd
                segment_start_uncertain = uncertain_cd
            else:
                new_cwd, new_uncertain = _scan_segment(
                    segment,
                    effective_cwd,
                    payload_cwd,
                    uncertain_cd,
                    matches,
                )
                if token in {"&", "|", "|&"}:
                    effective_cwd, uncertain_cd = (
                        segment_start_cwd,
                        segment_start_uncertain,
                    )
                else:
                    effective_cwd, uncertain_cd = new_cwd, new_uncertain
                segment = []
                segment_start_cwd = effective_cwd
                segment_start_uncertain = uncertain_cd
        else:
            segment.append(token)
    return matches


def _resolve_command_cwd(
    segment: list[str],
    script_index: int,
    payload_cwd: str,
    cd_path: str | None = None,
) -> str | None:
    effective_cwd = cd_path if cd_path is not None else payload_cwd
    arguments = segment[script_index + 1 :]
    selected_path: str | None = None
    selected_token: str | None = None
    selected_option = False
    selected_invalid = False
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"--cwd", "-C"}:
            if index + 1 >= len(arguments) or not arguments[index + 1]:
                selected_option = True
                selected_path = None
                selected_token = argument
                selected_invalid = True
                index += 1
                continue
            selected_path = arguments[index + 1]
            selected_token = arguments[index + 1]
            selected_option = True
            selected_invalid = False
            index += 2
            continue
        if argument.startswith("--cwd="):
            selected_path = argument.split("=", 1)[1]
            selected_token = argument
            selected_option = True
            selected_invalid = not selected_path
        index += 1
    if selected_invalid:
        _fail_open("codex cwd option has no path")
        return None
    if not selected_option or selected_path is None or selected_token is None:
        return effective_cwd
    diagnostic_operand = _diagnostic_operand(selected_token)
    if _token_markers(selected_token):
        sys.stderr.write(
            f'codex-worktree-gate: --cwd "{diagnostic_operand}" '
            "could not determine cwd; using tracked cwd for the check. Add --cwd "
            "<absolute path> if the intended launch directory differs.\n"
        )
        return effective_cwd
    expanded = os.path.expanduser(selected_path)
    if expanded.startswith("~"):
        sys.stderr.write(
            f'codex-worktree-gate: --cwd "{diagnostic_operand}" '
            "could not determine cwd; using tracked cwd for the check. Add --cwd "
            "<absolute path> if the intended launch directory differs.\n"
        )
        return effective_cwd
    resolved = os.path.abspath(os.path.join(effective_cwd, expanded))
    if not os.path.isdir(resolved):
        sys.stderr.write(
            f'codex-worktree-gate: --cwd "{diagnostic_operand}" '
            "could not determine cwd; using tracked cwd for the check. Add --cwd "
            "<absolute path> if the intended launch directory differs.\n"
        )
        return effective_cwd
    return resolved


def _diagnostic_operand(token: str) -> str:
    raw = _token_raw(token)
    if raw.startswith("--cwd="):
        raw = raw.split("=", 1)[1]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    return raw[:60]


def _has_absolute_command_cwd(segment: list[str], script_index: int) -> bool:
    arguments = segment[script_index + 1 :]
    selected_path: str | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"--cwd", "-C"}:
            if index + 1 < len(arguments):
                selected_path = arguments[index + 1]
                index += 2
                continue
            selected_path = None
        elif argument.startswith("--cwd="):
            selected_path = argument.split("=", 1)[1]
        index += 1
    return selected_path is not None and os.path.isabs(selected_path)


def _has_marker_command_cwd(segment: list[str], script_index: int) -> bool:
    arguments = segment[script_index + 1 :]
    selected: str | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"--cwd", "-C"}:
            if index + 1 < len(arguments):
                selected = arguments[index + 1]
                index += 2
                continue
            selected = None
        elif argument.startswith("--cwd="):
            selected = argument
        index += 1
    return selected is not None and bool(_token_markers(selected))


def _is_linked_worktree(git_dir: str, common_dir: str) -> bool:
    return os.path.realpath(git_dir) != os.path.realpath(common_dir)


def _git_dir(cwd: str) -> tuple[str, str] | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        _fail_open("git rev-parse timed out")
        return None
    except Exception as exc:
        _fail_open(f"git rev-parse could not run ({type(exc).__name__})")
        return None
    if result.returncode != 0:
        detail = result.stderr.strip() if isinstance(result.stderr, str) else ""
        _fail_open(
            f"git rev-parse exited with status {result.returncode}"
            + (f": {detail}" if detail else "")
        )
        return None
    lines = result.stdout.splitlines() if isinstance(result.stdout, str) else []
    if len(lines) < 2 or not lines[0].strip() or not lines[1].strip():
        _fail_open("git rev-parse returned incomplete git directories")
        return None
    git_dir = os.path.realpath(os.path.abspath(lines[0].strip()))
    common_dir = os.path.realpath(os.path.abspath(os.path.join(cwd, lines[1].strip())))
    return git_dir, common_dir


def _gate(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return
    # agent_id でも codex-rescue subagent の Bash から起動されるため判定を省略しない。
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command")
    if not isinstance(command, str):
        return
    cwd = payload.get("cwd")
    payload_cwd = cwd if isinstance(cwd, str) and cwd else None
    matches = _find_codex_write_segment(command, payload_cwd)
    if not matches:
        return
    needs_cwd = any(segment[0] != ESCAPE_HATCH for segment, _, _, _ in matches)
    if payload_cwd is None and needs_cwd:
        _fail_open("payload cwd is missing")
        return
    escaped = False
    for segment, script_index, effective_cwd, uncertain_cd in matches:
        if segment and segment[0] == ESCAPE_HATCH:
            escaped = True
            continue
        effective_cwd = _resolve_command_cwd(
            segment, script_index, payload_cwd or "", effective_cwd
        )
        if effective_cwd is None:
            continue
        if (
            uncertain_cd is not None
            and not _has_absolute_command_cwd(segment, script_index)
            and not _has_marker_command_cwd(segment, script_index)
        ):
            if uncertain_cd == HOME_UNSET:
                sys.stderr.write(
                    "codex-worktree-gate: cd without an operand could not determine cwd "
                    "because HOME is not set; using payload cwd for the check. Add --cwd "
                    "<absolute path> if the intended launch directory differs.\n"
                )
            elif uncertain_cd == POPD_UNCERTAIN:
                sys.stderr.write(
                    "codex-worktree-gate: popd is statically unresolved; using payload cwd "
                    "for the check. Add --cwd <absolute path> if the intended launch directory "
                    "differs.\n"
                )
            elif uncertain_cd == PUSHD_NO_OPERAND:
                sys.stderr.write(
                    "codex-worktree-gate: bare pushd is statically unresolved; using payload cwd "
                    "for the check. Add --cwd <absolute path> if the intended launch directory "
                    "differs.\n"
                )
            elif uncertain_cd == PUSHD_NO_CHANGE:
                sys.stderr.write(
                    "codex-worktree-gate: pushd -n does not change cwd statically; using payload "
                    "cwd for the check. Add --cwd <absolute path> if the intended launch directory "
                    "differs.\n"
                )
            else:
                token = uncertain_cd[:60]
                sys.stderr.write(
                    f'codex-worktree-gate: cd "{token}" could not determine cwd; '
                    "using payload cwd for the check. If the intended launch directory differs, "
                    "add --cwd <absolute path>.\n"
                )
        git_dirs = _git_dir(effective_cwd)
        if git_dirs is None or _is_linked_worktree(*git_dirs):
            continue
        _emit(
            {
                "permissionDecision": "deny",
                "permissionDecisionReason": DENY_REASON,
            }
        )
        return
    if escaped:
        _emit({"additionalContext": ESCAPE_CONTEXT})


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception as exc:
        _fail_open(f"hook payload could not be parsed ({type(exc).__name__})")
        return 0
    try:
        _gate(payload)
    except Exception as exc:
        _fail_open(f"unexpected gate error ({type(exc).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def _git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(["init", "-q"], cwd=path)
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(["add", "tracked.txt"], cwd=path)
    _git(
        [
            "-c",
            "user.name=Codex Gate Test",
            "-c",
            "user.email=codex-gate@example.invalid",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=path,
    )


class GitFixture:
    """Real git primary and linked worktrees shared by the whole suite."""

    def __init__(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.primary = self.root / "primary"
        _init_repo(self.primary)
        self.linked = self.root / "linked"
        _git(["worktree", "add", "-q", str(self.linked), "HEAD"], cwd=self.primary)
        self.paren_linked = self.root / "linked (v2)"
        _git(
            ["worktree", "add", "-q", str(self.paren_linked), "HEAD"],
            cwd=self.primary,
        )
        self.subdir = self.linked / "nested"
        self.subdir.mkdir()

    def close(self) -> None:
        self.tempdir.cleanup()


def _invoke(payload: object | str) -> tuple[int, dict | None, str]:
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(sys, "stdin", stdin),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = main()
    text = stdout.getvalue().strip()
    return exit_code, json.loads(text) if text else None, stderr.getvalue()


class CodexWorktreeGateTest(unittest.TestCase):
    """Order document claims are observed at the hook boundary."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.git = GitFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.git.close()

    @staticmethod
    def _payload(command: str, cwd: Path | None = None, **extra: object) -> dict:
        tool_input: dict[str, object] = {"command": command}
        payload = {"tool_name": "Bash", "tool_input": tool_input, **extra}
        if cwd is not None:
            payload["cwd"] = str(cwd)
        return payload

    def _allow(self, payload: dict) -> tuple[dict | None, str]:
        exit_code, output, stderr = _invoke(payload)
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        return output, stderr

    def _deny(self, payload: dict) -> str:
        exit_code, output, stderr = _invoke(payload)
        self.assertEqual(exit_code, 0)
        if output is None:
            self.fail("expected a hook output for a denied command")
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(stderr, "")
        return output["hookSpecificOutput"]["permissionDecisionReason"]

    def test_primary_task_write_denies_with_recovery_actions(self):
        reason = self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self.assertIn("git worktree add", reason)
        self.assertIn("--write を外せば", reason)
        self.assertIn("CODEX_SHARED_TREE_OK=1", reason)
        self.assertIn("hook 自身は file を変更しません", reason)

    def test_linked_worktree_task_write_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )

    def test_linked_worktree_subdirectory_task_write_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.subdir,
            )
        )

    def test_primary_read_only_task_allows(self):
        self._allow(
            self._payload("node /opt/codex-companion.mjs task", self.git.primary)
        )

    def test_primary_directory_named_worktrees_still_denies(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "worktrees" / "proj"
            _init_repo(repo)
            self._deny(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    repo,
                )
            )

    def test_git_dir_passes_timeout_to_git(self):
        calls = []

        def recorder(*args, **kwargs):
            calls.append(kwargs)
            return subprocess.CompletedProcess(
                args,
                0,
                "/tmp/repo/.git\n/tmp/repo/.git\n",
                "",
            )

        with mock.patch.object(subprocess, "run", side_effect=recorder):
            self.assertEqual(
                _git_dir("/tmp/repo"),
                ("/tmp/repo/.git", "/tmp/repo/.git"),
            )
        self.assertEqual(calls[0]["timeout"], GIT_TIMEOUT_SECONDS)

    def test_primary_resume_last_denies_without_write_flag(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --resume-last",
                self.git.primary,
            )
        )

    def test_primary_resume_denies_without_write_flag(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --resume",
                self.git.primary,
            )
        )

    def test_explicit_shared_tree_token_allows_with_context(self):
        exit_code, output, stderr = _invoke(
            self._payload(
                "CODEX_SHARED_TREE_OK=1 node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        if output is None:
            self.fail("expected escape-hatch context")
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("共有ツリーへの codex 書き込みを明示許可で通過", context)

    def test_newlines_are_segment_boundaries_and_escape_is_scoped(self):
        for separator in ("\n", "\r\n"):
            with self.subTest(separator=repr(separator)):
                self._deny(
                    self._payload(
                        "CODEX_SHARED_TREE_OK=1 node /opt/codex-companion.mjs task --write"
                        f"{separator}node /opt/codex-companion.mjs task --write",
                        self.git.primary,
                    )
                )
                self._allow(
                    self._payload(
                        "node /opt/codex-companion.mjs task --write"
                        f"{separator}node /opt/codex-companion.mjs task --write",
                        self.git.linked,
                    )
                )

    def test_hash_comments_do_not_hide_following_write(self):
        for command in (
            "# launch\nnode /opt/codex-companion.mjs task --write",
            "echo hi  # note\nnode /opt/codex-companion.mjs task --write",
        ):
            with self.subTest(command=command):
                self._deny(self._payload(command, self.git.primary))

    def test_command_substitution_does_not_hide_write_invocation(self):
        for command in (
            "node /opt/codex-companion.mjs task --write --log $(date +%s).log",
            "node /opt/codex-companion.mjs task --write --log $(date).log && echo done",
            "node /opt/codex-companion.mjs --log=$(date +%s).log task --write",
            "node /opt/codex-companion.mjs --log $(date).log task --write",
        ):
            with self.subTest(command=command):
                self._deny(self._payload(command, self.git.primary))
        exit_code, output, stderr = _invoke(
            self._payload(
                "node /opt/codex-companion.mjs --cwd $(pwd) task --write",
                self.git.primary,
            )
        )
        self.assertEqual(exit_code, 0)
        if output is None:
            self.fail("expected a denial output")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("$(pwd)", stderr)

    def test_cwd_diagnostics_quote_only_operand_once(self):
        cases = (
            "node /opt/codex-companion.mjs --cwd=$(pwd) task --write",
            'node /opt/codex-companion.mjs --cwd "$PWD" task --write',
            "node /opt/codex-companion.mjs --cwd $(git rev-parse --show-toplevel) task --write",
        )
        for command in cases:
            with self.subTest(command=command):
                exit_code, output, stderr = _invoke(
                    self._payload(command, self.git.primary)
                )
                self.assertEqual(exit_code, 0)
                if output is None:
                    self.fail("expected a denial output")
                self.assertEqual(
                    output["hookSpecificOutput"]["permissionDecision"], "deny"
                )
                self.assertNotIn('--cwd "--cwd=', stderr)
                self.assertNotIn('""', stderr)
                if "rev-parse" in command:
                    self.assertIn("git rev-parse --show-toplevel", stderr)

    def test_literal_cwd_marker_follows_tracked_cwd(self):
        for cwd, expected_output in (
            (self.git.linked, None),
            (self.git.primary, "deny"),
        ):
            exit_code, output, stderr = _invoke(
                self._payload(
                    'node /opt/codex-companion.mjs --cwd "$PWD" task --write',
                    cwd,
                )
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                None
                if output is None
                else output["hookSpecificOutput"]["permissionDecision"],
                expected_output,
            )
            self.assertIn("$PWD", stderr)

    def test_line_continuations_preserve_one_command(self):
        for continuation in ("\\\n", "\\\r\n", "\\\n\t"):
            with self.subTest(continuation=repr(continuation)):
                self._deny(
                    self._payload(
                        "node /opt/codex-companion.mjs "
                        f"{continuation}--cwd {self.git.primary} "
                        f"{continuation}task --write",
                        self.git.primary,
                    )
                )

    def test_quoted_shell_separators_do_not_hide_write(self):
        for operator in (";", "&&"):
            with self.subTest(operator=operator):
                self._deny(
                    self._payload(
                        f"node /opt/codex-companion.mjs task '{operator}' --write",
                        self.git.primary,
                    )
                )

    def test_command_cwd_is_last_wins(self):
        for options in (
            f"--cwd {self.git.linked} --cwd {self.git.primary}",
            f"-C {self.git.linked} --cwd {self.git.primary}",
        ):
            with self.subTest(options=options):
                self._deny(
                    self._payload(
                        f"node /opt/codex-companion.mjs {options} task --write",
                        self.git.linked,
                    )
                )

    def test_env_chdir_is_scoped_to_its_segment(self):
        for option in (f"-C {self.git.primary}", f"--chdir={self.git.primary}"):
            with self.subTest(option=option):
                exit_code, output, stderr = _invoke(
                    self._payload(
                        f"env {option} node /opt/codex-companion.mjs task --write",
                        self.git.linked,
                    )
                )
                self.assertEqual(exit_code, 0)
                if output is None:
                    self.fail("expected a denial output")
                self.assertEqual(
                    output["hookSpecificOutput"]["permissionDecision"], "deny"
                )
                self.assertEqual(stderr, "")

    def test_ansi_c_write_flag_is_detected(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task $'--write'",
                self.git.primary,
            )
        )

    def test_prompt_quote_is_resplit_for_write_detection(self):
        self._deny(
            self._payload(
                'node /opt/codex-companion.mjs task "prompt \\"--write\\""',
                self.git.primary,
            )
        )

    def test_marker_command_cwd_uses_tracked_cd_cwd(self):
        exit_code, output, stderr = _invoke(
            self._payload(
                f"cd {self.git.linked} && node /opt/codex-companion.mjs --cwd $(pwd) "
                "task --write",
                self.git.primary,
            )
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        self.assertIn("$(pwd)", stderr)

    def test_backtick_write_invocation_is_detected(self):
        self._deny(
            self._payload(
                "X=`node /opt/codex-companion.mjs task --write`",
                self.git.primary,
            )
        )

    def test_newline_cd_segments_update_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.linked}\ncd {self.git.primary}\n"
                "node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked}\nnode /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_shared_tree_token_after_codex_args_does_not_bypass(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write --env CODEX_SHARED_TREE_OK=1",
                self.git.primary,
            )
        )

    def test_review_with_write_flag_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs review --write",
                self.git.primary,
            )
        )

    def test_review_prompt_containing_task_allows(self):
        self._allow(
            self._payload(
                'node /opt/codex-companion.mjs review --write "fix this task"',
                self.git.primary,
            )
        )

    def test_segment_boundaries_prevent_cross_command_match(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --dry-run && echo --write",
                self.git.primary,
            )
        )
        self._allow(
            self._payload(
                "echo codex-companion.mjs task ; node /opt/other.mjs --write",
                self.git.primary,
            )
        )

    def test_all_write_capable_segments_are_evaluated(self):
        self._deny(
            self._payload(
                f"node /opt/codex-companion.mjs task --cwd {self.git.linked} --write "
                "&& node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self._allow(
            self._payload(
                f"node /opt/codex-companion.mjs task --cwd {self.git.linked} --write "
                "&& node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )

    def test_escape_hatch_is_scoped_to_its_segment(self):
        self._deny(
            self._payload(
                "CODEX_SHARED_TREE_OK=1 node /opt/codex-companion.mjs task --write "
                "&& node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_backup_script_name_does_not_match(self):
        self._allow(
            self._payload(
                "node /opt/backup-codex-companion.mjs.bak task --write",
                self.git.primary,
            )
        )

    def test_quoted_write_flags_are_detected(self):
        self._deny(
            self._payload(
                'node /opt/codex-companion.mjs task "--write --background prompt"',
                self.git.primary,
            )
        )

    def test_command_cwd_options_use_effective_cwd(self):
        for option in (
            f"--cwd {self.git.primary}",
            f"--cwd={self.git.primary}",
            f"-C {self.git.primary}",
        ):
            self._deny(
                self._payload(
                    f"node /opt/codex-companion.mjs {option} task --write",
                    self.git.linked,
                )
            )
        self._allow(
            self._payload(
                f"node /opt/codex-companion.mjs --cwd {self.git.linked} task --write",
                self.git.primary,
            )
        )

    def test_relative_command_cwd_uses_payload_base(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs --cwd ../primary task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs --cwd ../linked task --write",
                self.git.primary,
            )
        )

    def test_command_cwd_preserves_spaces_in_raw_tokens(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            primary = root / "primary with space"
            linked = root / "linked with space"
            _init_repo(primary)
            _git(["worktree", "add", "-q", str(linked), "HEAD"], cwd=primary)
            _, stderr = self._allow(
                self._payload(
                    f"node /opt/codex-companion.mjs --cwd '{linked}' task --write",
                    primary,
                )
            )
            self.assertEqual(stderr, "")
            self._deny(
                self._payload(
                    f"node /opt/codex-companion.mjs --cwd '{primary}' task --write",
                    linked,
                )
            )

    def test_parenthesized_segments_are_detected(self):
        self._deny(
            self._payload(
                "(node /opt/codex-companion.mjs task --write)",
                self.git.primary,
            )
        )
        self._deny(
            self._payload(
                f"(cd {self.git.primary} && node /opt/codex-companion.mjs task --write)",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"(cd {self.git.linked} && node /opt/codex-companion.mjs task --write)",
                self.git.primary,
            )
        )

    def test_subshell_inherits_outer_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && (node /opt/codex-companion.mjs task --write)",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked} && (node /opt/codex-companion.mjs task --write)",
                self.git.primary,
            )
        )

    def test_subshell_cd_does_not_leak_to_outer_segment(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && (cd {self.git.linked} && "
                "node /opt/codex-companion.mjs task --write) && "
                "node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )

    def test_cd_prefix_sets_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked} && node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_shell_wrappers_do_not_hide_cd(self):
        commands = (
            "{{ cd {path}; node /opt/codex-companion.mjs task --write; }}",
            "if true; then cd {path}; node /opt/codex-companion.mjs task --write; fi",
            "for d in x; do cd {path}; node /opt/codex-companion.mjs task --write; done",
            "builtin cd {path} && node /opt/codex-companion.mjs task --write",
            "command cd {path} && node /opt/codex-companion.mjs task --write",
        )
        for command in commands:
            with self.subTest(command=command):
                self._deny(
                    self._payload(
                        command.format(path=self.git.primary), self.git.linked
                    )
                )

    def test_cd_options_pushd_and_assignment_set_effective_cwd(self):
        for command in (
            "cd -- {path} && node /opt/codex-companion.mjs task --write",
            "cd -P {path} && node /opt/codex-companion.mjs task --write",
            "cd -LP -- {path} && node /opt/codex-companion.mjs task --write",
            "pushd {path} && node /opt/codex-companion.mjs task --write",
            "FOO=1 cd {path} && node /opt/codex-companion.mjs task --write",
        ):
            with self.subTest(command=command):
                self._deny(
                    self._payload(
                        command.format(path=self.git.primary), self.git.linked
                    )
                )
        self._allow(
            self._payload(
                f"cd -- {self.git.linked} && node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self._allow(
            self._payload(
                f"pushd {self.git.linked} && node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_cd_without_operand_uses_home(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.git.primary)}):
            self._deny(
                self._payload(
                    "cd && node /opt/codex-companion.mjs task --write",
                    self.git.linked,
                )
            )

    def test_pushd_without_operand_falls_back_to_payload_cwd(self):
        exit_code, output, stderr = _invoke(
            self._payload(
                "pushd && node /opt/codex-companion.mjs task --write", self.git.primary
            )
        )
        self.assertEqual(exit_code, 0)
        if output is None:
            self.fail("expected a denial output")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("bare pushd is statically unresolved", stderr)

    def test_pushd_no_change_falls_back_to_payload_cwd(self):
        exit_code, output, stderr = _invoke(
            self._payload(
                "pushd -n /tmp && node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self.assertEqual(exit_code, 0)
        if output is None:
            self.fail("expected a denial output")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("pushd -n does not change cwd statically", stderr)

    def test_home_unset_has_dedicated_diagnostic(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            exit_code, output, stderr = _invoke(
                self._payload(
                    "cd && node /opt/codex-companion.mjs task --write",
                    self.git.primary,
                )
            )
        self.assertEqual(exit_code, 0)
        if output is None:
            self.fail("expected a denial output")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("HOME is not set", stderr)
        self.assertNotIn('cd "HOME"', stderr)

    def test_tilde_cd_uses_home_expansion(self):
        with tempfile.TemporaryDirectory() as home:
            home_path = Path(home)
            _init_repo(home_path / "project")
            with mock.patch.dict(os.environ, {"HOME": str(home_path)}):
                self._deny(
                    self._payload(
                        "cd ~/project && node /opt/codex-companion.mjs task --write",
                        self.git.linked,
                    )
                )
        with mock.patch.dict(os.environ, {"HOME": str(self.git.root)}):
            self._allow(
                self._payload(
                    "cd ~/linked && node /opt/codex-companion.mjs task --write",
                    self.git.primary,
                )
            )

    def test_unknown_tilde_user_falls_back_to_payload_cwd(self):
        _, output, stderr = _invoke(
            self._payload(
                "cd ~codex_gate_missing_user/x && node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        if output is None:
            self.fail("expected a denial output")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("codex_gate_missing_user", stderr)

    def test_quoted_parentheses_in_cd_path_are_literal(self):
        self._allow(
            self._payload(
                f"cd '{self.git.paren_linked}' && node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_symlink_primary_is_not_a_linked_worktree(self):
        link = self.git.root / "primary-link"
        link.symlink_to(self.git.primary, target_is_directory=True)
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                link,
            )
        )
        self._deny(
            self._payload(
                f"cd {link} && node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )
        self._deny(
            self._payload(
                f"node /opt/codex-companion.mjs --cwd {link} task --write",
                self.git.linked,
            )
        )

    def test_uncertain_cd_falls_back_to_payload_cwd_with_diagnostic(self):
        cases = (
            ('cd "$WORKDIR"', self.git.primary, "deny"),
            ("cd $(get_dir)", self.git.linked, "allow"),
            ("cd -", self.git.primary, "deny"),
            ("cd /nonexistent/xyz", self.git.primary, "deny"),
        )
        for prefix, cwd, decision in cases:
            with self.subTest(prefix=prefix):
                payload = self._payload(
                    f"{prefix} && node /opt/codex-companion.mjs task --write",
                    cwd,
                )
                if decision == "deny":
                    exit_code, output, stderr = _invoke(payload)
                    self.assertEqual(exit_code, 0)
                    if output is None:
                        self.fail("expected a denial output")
                    self.assertEqual(
                        output["hookSpecificOutput"]["permissionDecision"], "deny"
                    )
                else:
                    exit_code, output, stderr = _invoke(payload)
                    self.assertEqual(exit_code, 0)
                    self.assertIsNone(output)
                    self.assertIn("get_dir", stderr)
                self.assertIn("could not determine", stderr)
                self.assertIn("payload cwd", stderr)
                self.assertIn("--cwd <absolute path>", stderr)

    def test_subshell_uncertain_cd_does_not_leak_to_outer_segment(self):
        _, output, stderr = _invoke(
            self._payload(
                '( cd "$X" && true ) && node /opt/codex-companion.mjs task --write',
                self.git.linked,
            )
        )
        self.assertIsNone(output)
        self.assertEqual(stderr, "")

    def test_absolute_command_cwd_suppresses_uncertain_cd_diagnostic(self):
        _, output, stderr = _invoke(
            self._payload(
                f'cd "$X" && node /opt/codex-companion.mjs --cwd {self.git.primary} '
                "task --write",
                self.git.linked,
            )
        )
        if output is None:
            self.fail("expected a denial output")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(stderr, "")

    def test_popd_is_uncertain_and_falls_back_to_payload_cwd(self):
        payload = self._payload(
            "popd && node /opt/codex-companion.mjs task --write", self.git.primary
        )
        exit_code, output, stderr = _invoke(payload)
        self.assertEqual(exit_code, 0)
        if output is None:
            self.fail("expected a denial output")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("popd is statically unresolved", stderr)

    def test_relative_command_cwd_uses_cd_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && node /opt/codex-companion.mjs --cwd . "
                "task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked} && node /opt/codex-companion.mjs --cwd . "
                "task --write",
                self.git.primary,
            )
        )

    def test_command_cwd_expands_user_and_falls_back_for_variables(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.git.root)}):
            self._deny(
                self._payload(
                    "node /opt/codex-companion.mjs --cwd ~/primary task --write",
                    self.git.linked,
                )
            )
        exit_code, output, stderr = _invoke(
            self._payload(
                'node /opt/codex-companion.mjs --cwd "$PWD" task --write',
                self.git.linked,
            )
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        self.assertIn("$PWD", stderr)

    def test_pipeline_and_background_cd_do_not_change_parent_cwd(self):
        for command in (
            f"cd {self.git.primary} & node /opt/codex-companion.mjs task --write",
            f"cd {self.git.primary} | cat ; node /opt/codex-companion.mjs task --write",
        ):
            with self.subTest(command=command):
                self._allow(self._payload(command, self.git.linked))

    def test_quoted_shell_operator_is_not_a_separator(self):
        self._deny(
            self._payload(
                'node /opt/codex-companion.mjs task "--write &"',
                self.git.primary,
            )
        )

    def test_unrelated_bash_allows(self):
        self._allow(self._payload("printf 'hello'", self.git.primary))

    def test_non_task_codex_subcommand_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs status --json",
                self.git.primary,
            )
        )

    def test_non_repo_cwd_fails_open_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as tempdir:
            _, stderr = self._allow(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    Path(tempdir),
                )
            )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("git", stderr.lower())
        self.assertIn("exited with status", stderr)

    def test_missing_cwd_fails_open_with_diagnostic(self):
        _, stderr = self._allow(
            self._payload("node /opt/codex-companion.mjs task --write")
        )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("cwd", stderr.lower())

    def test_missing_git_executable_fails_open_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as empty_path:
            with mock.patch.dict(os.environ, {"PATH": empty_path}, clear=False):
                _, stderr = self._allow(
                    self._payload(
                        "node /opt/codex-companion.mjs task --write",
                        self.git.primary,
                    )
                )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("git", stderr.lower())
        self.assertIn("could not run", stderr)

    def test_git_timeout_fails_open_with_diagnostic(self):
        timeout = subprocess.TimeoutExpired(["git", "rev-parse"], 0.1)
        with mock.patch.object(subprocess, "run", side_effect=timeout):
            _, stderr = self._allow(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    self.git.primary,
                )
            )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("timed out", stderr.lower())

    def test_tokenize_failure_fails_open_with_diagnostic(self):
        exit_code, output, stderr = _invoke(
            self._payload(
                "node /opt/codex-companion.mjs task --write $'unterminated",
                self.git.primary,
            )
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        self.assertIn("could not be tokenized", stderr)

    def test_invalid_json_fails_open_with_diagnostic(self):
        exit_code, output, stderr = _invoke("{")
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        self.assertIn("could not be parsed", stderr)

    def test_file_is_executable(self):
        self.assertTrue(os.access(os.path.abspath(__file__), os.X_OK))

    def test_subprocess_entrypoint_denies(self):
        process = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            input=json.dumps(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    self.git.primary,
                )
            ),
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(process.returncode, 0)
        output = json.loads(process.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(process.stderr, "")

    def test_agent_id_does_not_bypass_primary_tree_deny(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
                agent_id="agent-123",
            )
        )

    def test_non_bash_tool_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
                tool_name="Read",
            )
        )
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
