#!/usr/bin/env python3
"""Gate Codex delegation through the approved skill and isolated worktrees."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(.*)$", re.DOTALL)
TOKEN_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*=\([^)]*\)|&&|\|\||\$\(|[;|&(){}\n`]|"
    r"\d*(?:>>?|<<?)|(?:\\[;|&(){}<>`]|[^\s;|&(){}<>`\n])+"
)
QUOTE_TOKEN_RE = re.compile(r"\x00Q([0-9]+)\x00")
ORDER_RE = re.compile(r"(?<![\w./-])([^\s'\";|&()]+\.md)(?![\w./-])")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SEPARATORS = frozenset({";", "&&", "||", "|", "&", "\n", "(", ")", "{", "}", "`", "$("})
SHELL_KEYWORDS = frozenset("! do done elif else fi if then until while".split())
WRAPPERS = frozenset(
    "builtin bunx command env exec nohup npx sudo time timeout uvx xargs".split()
)
WRAPPER_VALUE_OPTIONS = {
    "env": frozenset("-u --unset -C --chdir".split()),
    "npx": frozenset("-p --package -c --call".split()),
    "sudo": frozenset(
        "-u --user -g --group -C -D --chdir -h --host -p --prompt -r --role -t --type -T -U".split()
    ),
    "time": frozenset("-f --format -o --output".split()),
    "timeout": frozenset("-s --signal -k --kill-after".split()),
    "xargs": frozenset(
        "-I -i -L -n -P -d -a -E -s --replace --max-lines --max-args --max-procs --delimiter --arg-file --eof --max-chars".split()
    ),
}
NODE_VALUE_OPTIONS = frozenset(
    "-r --require --import --loader --experimental-loader -C --conditions --input-type --env-file".split()
)
SHELL_C_RE = re.compile(r"-[A-Za-z]*c[A-Za-z]*")
HELP_FLAGS = frozenset({"--help", "-h", "--version", "-V"})
HEREDOC_RE = re.compile(r"<<(-?)(?!<)\s*\\?(['\"]?)([^\s'\"<>]+)\2")
SAFE_CLI = frozenset({"completion", "login", "logout", "mcp"})
SAFE_SKILLS = frozenset(
    f"codex:{name}"
    for name in "cancel codex-cli-runtime codex-delegation codex-result-handling help "
    "gpt-5-4-prompting result setup status".split()
)
ROOT_COMMANDS = frozenset({"task", "task-worker", "review", "adversarial-review"})
VALUE_FLAGS = frozenset(
    "--model -m --effort --cwd -C --prompt-file --resume --config -c".split()
)
TASK_FLAGS = frozenset(
    "--model -m --effort --cwd -C --prompt-file --json --write --resume-last "
    "--resume --fresh --background".split()
)
WRITE_FLAGS = frozenset({"--write", "--resume", "--resume-last"})
CORRECTION = "codex-delegation skill を invoke し、codex:codex-rescue subagent に発注書 path を渡してください。"
CORRECTIONS = dict.fromkeys(
    ("route", "skill", "cli", "order", "flag", "cjk"), CORRECTION
)
CORRECTIONS |= {
    "tree": "git worktree add で worktree を作り、単独の cd で移ってから --cwd <絶対 path> で起動してください。",
    "same-root": "発注前に単独の cd で対象 worktree へ移り、--cwd は絶対 path で書いてください。",
    "isolation": "isolation を外し、手動 worktree へ単独の cd で移ってから発注してください。",
    "workflow": "生成 step を Workflow の外に出し、codex-delegation skill を invoke して rescue に発注してください。",
}
ENDING = "この hook 自身は file を変更しません"


@dataclass(frozen=True)
class Launch:
    kind: str
    subcommand: str | None
    argv: tuple[str, ...]
    assignments: frozenset[str]
    after_cd: bool


@dataclass(frozen=True)
class Result:
    rule: str | None = None
    violation: str = ""
    context: str | None = None
    warning: str | None = None


def _remove_heredoc_bodies(command: str) -> str:
    lines = command.splitlines(keepends=True)
    output: list[str] = []
    delimiter: str | None = None
    strip_tabs = False
    for line in lines:
        if delimiter is not None:
            body_line = line.rstrip("\n")
            if (body_line.lstrip("\t") if strip_tabs else body_line) == delimiter:
                delimiter = None
            output.append("\n" if line.endswith("\n") else "")
            continue
        output.append(line)
        quoted: str | None = None
        marker_line: list[str] = []
        for index, char in enumerate(line):
            if char in "'\"" and (index == 0 or line[index - 1] != "\\"):
                quoted = None if quoted == char else char if quoted is None else quoted
            comment = char == "#" and quoted is None
            if comment and (index == 0 or line[index - 1].isspace()):
                break
            marker_line.append(char)
        match = HEREDOC_RE.search("".join(marker_line))
        if match:
            strip_tabs, delimiter = bool(match.group(1)), match.group(3)
    return "".join(output)


def strip_quotes_heredocs_comments(command: str) -> tuple[str, tuple[str, ...]]:
    source = _remove_heredoc_bodies(command.replace("\\\n", ""))
    source = re.sub(r"\b(?:cd|pushd)\s*\(\s*\)", "__CDG_FUNCTION__", source)
    output: list[str] = []
    quotes: list[str] = []

    def placeholder(value: str) -> str:
        token = f"\x00Q{len(quotes)}\x00"
        quotes.append(value)
        return token

    def substitution_end(start: int) -> int:
        depth = 1
        quoted: str | None = None
        cursor = start + 2
        while cursor < len(source):
            char = source[cursor]
            if quoted is not None:
                if quoted == '"' and char == "\\" and cursor + 1 < len(source):
                    cursor += 2
                    continue
                if char == quoted:
                    quoted = None
            elif char in "'\"":
                quoted = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return cursor
            cursor += 1
        return -1

    index = 0
    while index < len(source):
        char = source[index]
        if char in "'\"":
            quote = char
            index += 1
            value: list[str] = []
            while index < len(source):
                char = source[index]
                if quote == '"' and char == "\\" and index + 1 < len(source):
                    value.append(source[index + 1])
                    index += 2
                    continue
                if quote == '"' and source.startswith("$(", index):
                    if value:
                        output.append(placeholder("".join(value)))
                    value = []
                    end = substitution_end(index)
                    if end >= 0:
                        inner, inner_quotes = strip_quotes_heredocs_comments(
                            source[index + 2 : end]
                        )
                        inner = QUOTE_TOKEN_RE.sub(
                            lambda m, q=inner_quotes: placeholder(q[int(m.group(1))]),
                            inner,
                        )
                        output.extend(("$(", inner, ")"))
                        index = end + 1
                        continue
                    value.append("$(")
                    index += 2
                    continue
                if char == quote:
                    index += 1
                    break
                value.append(char)
                index += 1
            output.append(placeholder("".join(value)))
            continue
        if char == "#" and (index == 0 or source[index - 1].isspace()):
            newline = source.find("\n", index)
            if newline < 0:
                break
            output.append("\n")
            index = newline + 1
            continue
        output.append(char)
        index += 1
    return "".join(output), tuple(quotes)


def _decode(token: str, quotes: tuple[str, ...]) -> str:
    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return quotes[index] if index < len(quotes) else match.group(0)

    return QUOTE_TOKEN_RE.sub(replace, token)


def _segments(scan: tuple[str, tuple[str, ...]]) -> list[list[str]]:
    source, quotes = scan
    segments: list[list[str]] = []
    current: list[str] = []
    for token in TOKEN_RE.findall(source):
        if token in SEPARATORS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(_decode(token, quotes))
    if current:
        segments.append(current)
    return segments


def _without_redirects(tokens: list[str]) -> list[str]:
    cleaned: list[str] = []
    skip = False
    for token in tokens:
        if skip:
            skip = False
            continue
        if re.fullmatch(r"\d*(?:>>?|<<?)", token):
            skip = True
            continue
        if re.match(r"^\d*(?:>>?|<<?).+", token):
            continue
        cleaned.append(token)
    return cleaned


def _word(token: str) -> str:
    return os.path.basename(token).replace("\\", "")


def _peel(tokens: list[str]) -> tuple[int, frozenset[str], bool]:
    index = 0
    assignments: set[str] = set()
    changed_dir = False
    while index < len(tokens):
        token = tokens[index]
        if ASSIGNMENT_RE.fullmatch(token):
            assignments.add(token)
            index += 1
            continue
        name = _word(token)
        if name in SHELL_KEYWORDS:
            index += 1
            continue
        if name not in WRAPPERS:
            break
        index += 1
        value_options = WRAPPER_VALUE_OPTIONS.get(name, frozenset())
        while index < len(tokens):
            item = tokens[index]
            if name == "env" and ASSIGNMENT_RE.fullmatch(item):
                assignments.add(item)
                index += 1
                continue
            if not item.startswith("-"):
                break
            if name in {"command", "builtin"} and item in {"-v", "-V"}:
                return len(tokens), frozenset(assignments), changed_dir
            index += 1
            if name == "env" and item.split("=", 1)[0] in {"-C", "--chdir"}:
                changed_dir = True
            if item in value_options:
                index += 1
        if name == "timeout" and index < len(tokens):
            index += 1
    return index, frozenset(assignments), changed_dir


def _help_requested(argv: tuple[str, ...]) -> bool:
    positionals = 0
    for token in argv:
        if token in HELP_FLAGS:
            return positionals <= 1
        positionals += not token.startswith("-")
    return False


def _subcommand_index(argv: list[str]) -> int | None:
    index = 0
    while index < len(argv):
        token = argv[index]
        if not token.startswith("-"):
            return index
        name, separator, _inline = token.partition("=")
        attached = name.startswith(("-C", "-m")) and name not in {"-C", "-m"}
        index += 1
        if not attached and name in VALUE_FLAGS and not separator:
            index += 1
    return None


def _launch_from_segment(
    tokens: list[str], after_cd: bool, bindings: dict[str, str]
) -> Launch | None:
    tokens = _without_redirects(tokens)
    index, assignments, env_chdir = _peel(tokens)
    if index >= len(tokens):
        return None
    program = _word(tokens[index])
    rest = tokens[index + 1 :]
    if program in {"node", "nodejs"}:
        script_index = 0
        while script_index < len(rest) and rest[script_index].startswith("-"):
            script_index += 2 if rest[script_index] in NODE_VALUE_OPTIONS else 1
        if script_index >= len(rest):
            return None
        script = rest[script_index]
        variable = re.fullmatch(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))", script)
        if variable:
            script = bindings.get(variable.group(1) or variable.group(2), script)
        if not script.endswith("codex-companion.mjs"):
            return None
        argv_list = rest[script_index + 1 :]
        subcommand_index = _subcommand_index(argv_list)
        argv = tuple(argv_list)
        return Launch(
            "companion",
            argv[subcommand_index] if subcommand_index is not None else None,
            argv,
            assignments,
            after_cd or env_chdir,
        )
    if program == "codex":
        argv = tuple(rest)
        subcommand_index = _subcommand_index(rest)
        subcommand = rest[subcommand_index] if subcommand_index is not None else None
        return Launch("cli", subcommand, argv, assignments, after_cd or env_chdir)
    return None


def enumerate_launches(command: str) -> list[Launch]:
    scan = strip_quotes_heredocs_comments(command)
    segments = _segments(scan)
    bindings: dict[str, str] = {}
    for tokens in segments:
        _index, assignments, _env_chdir = _peel(_without_redirects(tokens))
        for assignment in assignments:
            name, value = assignment.split("=", 1)
            if value.endswith("codex-companion.mjs"):
                bindings[name] = value
    launches: list[Launch] = []
    after_cd = False
    for tokens in segments:
        cleaned = _without_redirects(tokens)
        index, _assignments, env_chdir = _peel(cleaned)
        program = _word(cleaned[index]) if index < len(cleaned) else ""
        if program in {"cd", "pushd"}:
            after_cd = True
            continue
        launch = _launch_from_segment(tokens, after_cd or env_chdir, bindings)
        if launch is not None:
            launches.append(launch)
        if program in {"bash", "sh", "zsh"}:
            options = [
                position
                for position in range(index + 1, len(cleaned) - 1)
                if SHELL_C_RE.fullmatch(cleaned[position])
            ]
            if options:
                target = options[0] + 1
                if cleaned[target] == "--" and target + 1 < len(cleaned):
                    target += 1
                launches.extend(enumerate_launches(cleaned[target]))
        elif program == "eval":
            launches.extend(enumerate_launches(" ".join(cleaned[index + 1 :])))
    return launches


def _options(launch: Launch) -> tuple[dict[str, list[str | None]], list[str]]:
    options: dict[str, list[str | None]] = {}
    positional: list[str] = []
    argv = list(launch.argv)
    subcommand_index = _subcommand_index(argv)
    if subcommand_index is not None:
        del argv[subcommand_index]
    index = 0
    option_mode = True
    while index < len(argv):
        token = argv[index]
        if option_mode and token == "--":
            option_mode = False
            index += 1
            continue
        if option_mode and token.startswith("-"):
            if token.startswith("-C") and token != "-C":
                options.setdefault("-C", []).append(token[2:])
                index += 1
                continue
            if token.startswith("-m") and token != "-m":
                options.setdefault("-m", []).append(token[2:])
                index += 1
                continue
            name, separator, inline = token.partition("=")
            value: str | None = inline if separator else None
            if name in VALUE_FLAGS and not separator and index + 1 < len(argv):
                index += 1
                value = argv[index]
            options.setdefault(name, []).append(value)
        else:
            positional.append(token)
        index += 1
    return options, positional


def _launch_cwd(launch: Launch, payload_cwd: str) -> tuple[str | None, bool]:
    options, _positional = _options(launch)
    values = options.get("--cwd", []) + options.get("-C", [])
    if not values:
        return payload_cwd, True
    value = values[-1]
    if value is None or re.search(r"[$`*?\[\\]", value) or re.match(r"^~[^/]", value):
        return None, False
    expanded = os.path.expanduser(value)
    if not os.path.isabs(expanded):
        expanded = os.path.join(payload_cwd, expanded)
    return os.path.abspath(expanded), True


def _git_info(cwd: str) -> tuple[str, str, str] | None:
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                cwd,
                "rev-parse",
                "--show-toplevel",
                "--git-dir",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = proc.stdout.splitlines()
    if proc.returncode or len(lines) != 3:
        return None
    return lines[0], lines[1], lines[2]


def _skill_checkpoint(payload: dict[str, object]) -> bool:
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return True
    path = (
        Path.home()
        / ".claude/hooks/state/skill_reminder/active"
        / session
        / "main.json"
    )
    try:
        with path.open(encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        return bool(payload.get("agent_id"))
    except (OSError, ValueError, TypeError):
        return True
    record = state.get("codex-delegation") if isinstance(state, dict) else None
    if not isinstance(record, dict):
        return False
    if payload.get("agent_id"):
        return True
    prompt_id = payload.get("prompt_id")
    if prompt_id is not None:
        return record.get("prompt_id") == prompt_id
    timestamp = record.get("ts")
    return isinstance(timestamp, (int, float)) and time.time() - timestamp <= 1800


def _lint_order(path: str) -> dict[str, object] | None:
    executable = os.environ.get("CODEX_ORDER_LINT", "/usr/local/bin/codex_order_lint")
    try:
        proc = subprocess.run(
            [executable, "--metadata", path],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        data = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _check_task_launch(launch: Launch, payload: dict[str, object]) -> Result:
    if launch.subcommand not in {"task", "task-worker"}:
        return Result()
    options, positional = _options(launch)
    if launch.subcommand == "task":
        unknown = [name for name in options if name not in TASK_FLAGS]
        if unknown:
            return Result(
                "flag",
                f"task に未受理の option {unknown[0]} があります。task の受理 option は plugin 同梱 skill "
                "codex:codex-cli-runtime を Read してください。",
            )
        if (
            "--prompt-file" not in options
            and len(CJK_RE.findall(" ".join(positional))) > 200
        ):
            return Result("cjk", "長い CJK prompt は --prompt-file で渡してください。")
    payload_cwd = payload.get("cwd")
    if not isinstance(payload_cwd, str):
        return Result(warning="cwd を判定できないため fail-open しました")
    launch_cwd, static = _launch_cwd(launch, payload_cwd)
    if not static or launch_cwd is None:
        return Result("same-root", "--cwd を静的に解決できません。")
    resume = "--resume" in options or "--resume-last" in options
    write = bool(WRITE_FLAGS.intersection(options))
    prompt_files = [value for value in options.get("--prompt-file", []) if value]
    order_names = (
        prompt_files[-1:] if prompt_files else ORDER_RE.findall(" ".join(positional))
    )
    if launch.subcommand == "task" and not resume and order_names:
        if write and len(order_names) != 1:
            return Result(
                "order", "write task には発注書を正確に 1 つ指定してください。"
            )
        if len(order_names) == 1:
            order_path = order_names[0]
            if not os.path.isabs(order_path):
                order_path = os.path.join(launch_cwd, order_path)
            order_path = os.path.abspath(order_path)
            regular = os.path.isfile(order_path)
            metadata = _lint_order(order_path) if regular else None
            if write and (
                metadata is None
                or not metadata.get("order_document")
                or bool(metadata.get("findings"))
            ):
                return Result(
                    "order", "write task の発注書が lint 契約を満たしません。"
                )
            if (
                metadata is not None
                and metadata.get("report_path")
                and "--write" not in options
            ):
                return Result(
                    "order", "report_path のある発注書には --write が必要です。"
                )
    elif launch.subcommand == "task" and write and not resume:
        return Result("order", "write task には発注書を正確に 1 つ指定してください。")
    if write:
        info = _git_info(launch_cwd)
        if info is None:
            return Result(warning="git worktree を判定できないため fail-open しました")
        _root, git_dir, common_dir = info
        primary = git_dir == common_dir
        if primary and "CODEX_SHARED_TREE_OK=1" not in launch.assignments:
            return Result("tree", "primary checkout への write task は許可されません。")
        if primary:
            return Result(
                context="CODEX_SHARED_TREE_OK=1 により primary checkout を共有します"
            )
    return Result()


def _check_same_root(launch: Launch, payload: dict[str, object]) -> Result:
    if launch.subcommand not in ROOT_COMMANDS:
        return Result()
    if launch.after_cd:
        return Result("same-root", "launch 前の cd / pushd / env -C は許可されません。")
    payload_cwd = payload.get("cwd")
    if not isinstance(payload_cwd, str):
        return Result(warning="cwd を判定できないため fail-open しました")
    launch_cwd, static = _launch_cwd(launch, payload_cwd)
    if not static or launch_cwd is None:
        return Result("same-root", "--cwd を静的に解決できません。")
    launch_info = _git_info(launch_cwd)
    session_info = _git_info(payload_cwd)
    if launch_info is None or session_info is None:
        return Result(warning="git root を判定できないため fail-open しました")
    launch_root = launch_info[0]
    session_root = session_info[0]
    same_root = launch_root == session_root
    if not same_root:
        return Result(
            "same-root", "launch cwd と session cwd の git root が一致しません。"
        )
    return Result()


def _check_launches(payload: dict[str, object], command: str) -> Result:
    launches = enumerate_launches(command)
    if not launches:
        return Result()
    first_context: Result | None = None
    first_warning: Result | None = None
    for launch in launches:
        agent_id = payload.get("agent_id")
        agent_type = payload.get("agent_type")
        if agent_id:
            if isinstance(agent_type, str) and "codex-rescue" not in agent_type:
                return Result(
                    "route",
                    "Codex launch は codex-rescue subagent から実行してください。",
                )
        elif launch.kind == "companion":
            return Result("route", "main agent から companion を直接起動できません。")
        if launch.kind == "cli" and "CODEX_DELEGATION_OK=1" not in launch.assignments:
            if launch.subcommand not in SAFE_CLI and not _help_requested(launch.argv):
                return Result("cli", "素の codex CLI による委譲は許可されません。")
        if launch.kind == "companion" and agent_id and not _skill_checkpoint(payload):
            return Result("skill", "codex-delegation checkpoint がありません。")
        result = _check_same_root(launch, payload)
        if result.rule:
            return result
        first_warning = first_warning or (result if result.warning else None)
        result = _check_task_launch(launch, payload)
        if result.rule:
            return result
        if result.context and first_context is None:
            first_context = result
        first_warning = first_warning or (result if result.warning else None)
    return first_context or first_warning or Result()


def _delegation_surface(payload: dict[str, object]) -> Result:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return Result()
    if tool in {"Bash", "Monitor"}:
        command = tool_input.get("command")
        return (
            _check_launches(payload, command) if isinstance(command, str) else Result()
        )
    if tool in {"Agent", "Task"}:
        subagent = tool_input.get("subagent_type")
        if not isinstance(subagent, str) or "codex" not in subagent.lower():
            return Result()
        if not _skill_checkpoint(payload):
            return Result("skill", "codex-delegation checkpoint がありません。")
        if tool_input.get("isolation") == "worktree":
            return Result(
                "isolation", "Codex delegation に isolation worktree は指定できません。"
            )
        prompt = tool_input.get("prompt")
        if not isinstance(prompt, str) or not ORDER_RE.findall(prompt):
            return Result("order", "Codex delegation には .md 発注書 path が必要です。")
        return Result()
    if tool == "Skill":
        skill = tool_input.get("skill")
        if (
            not isinstance(skill, str)
            or not skill.startswith("codex:")
            or skill in SAFE_SKILLS
        ):
            return Result()
        if not _skill_checkpoint(payload):
            return Result("skill", "codex-delegation checkpoint がありません。")
        args = tool_input.get("args")
        if not isinstance(args, str) or (
            "--resume" not in args and not ORDER_RE.findall(args)
        ):
            return Result("order", "Codex skill には .md 発注書 path が必要です。")
        return Result()
    if tool == "Workflow":
        script = tool_input.get("script")
        if not isinstance(script, str):
            script_path = tool_input.get("scriptPath")
            if isinstance(script_path, str):
                try:
                    with open(script_path, encoding="utf-8") as handle:
                        script = handle.read(65536)
                except OSError:
                    return Result()
        if isinstance(script, str) and re.search(
            r"(?:agentType|subagent_type|subagentType)['\"]?\s*:\s*['\"`]codex:", script
        ):
            return Result(
                "workflow", "Workflow 内の Codex generation step は許可されません。"
            )
    return Result()


def _emit(result: Result) -> None:
    if result.warning:
        sys.stderr.write(f"codex-delegation-gate: {result.warning}\n")
    elif result.context:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": result.context,
            }
        }
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    elif result.rule:
        correction = CORRECTIONS.get(result.rule)
        reason = (
            f"codex-delegation-gate: [{result.rule}] {result.violation} "
            f"{f'{correction} ' if correction else ''}{ENDING}"
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise TypeError("payload is not an object")
        if payload.get("hook_event_name") != "PreToolUse":
            raise ValueError("event is not PreToolUse")
        _emit(_delegation_surface(payload))
    except Exception as error:
        message = str(error).replace("\n", " ")
        sys.stderr.write(f"codex-delegation-gate: fail-open: {message}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
