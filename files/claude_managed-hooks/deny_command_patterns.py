#!/usr/bin/env python3
"""PreToolUse(Bash) hook for unsafe or sandbox-bound command patterns.
Rules: kill-by-port, unbounded loops, non-interactive autosquash, voicevox without
loopback, and indirect sandbox excluded-command invocations.
Exit 0 allows or fails open (including unreadable input/settings); exit 2 denies."""

from functools import partial
import glob
import json
import os
import re
import sys

KILL_RE = re.compile(r"\b(?:fuser\s+-k|pkill|killall)\b")
TIMEOUT_RE = re.compile(r"\btimeout\b")
LOOP_RE = re.compile(
    r"\bwhile\s+(?:true\b|:|\[\s*1\s*\])|\buntil\s+false\b|\bfor\s+\(\(\s*;\s*;\s*\)\)"
)
AUTOSQUASH_RE = re.compile(r"\bgit\b[^;&|\n]*\brebase\b[^;&|\n]*--autosquash\b")
INTERACTIVE_RE = re.compile(
    r"(?<!\w)-i(?!\w)|(?<!\w)--interactive\b|GIT_SEQUENCE_EDITOR"
)
VOICEVOX_RE = re.compile(r"\bvoicevox_paplay\b")
LOOPBACK_RE = re.compile(r"(?<!\w)--loopback\b")
QUOTED_RE = re.compile(r'"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\'')
HEREDOC_RE = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)
TOKEN_RE = re.compile(r"&&|\|\||[;|&()\n]|[^\s;|&()]+")
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_]\w*=.*$")
WHICH_RE = re.compile(r"\$\(\s*which\s+([^\s()]+)\s*\)")
COMMAND_V_RE = re.compile(r"\$\(\s*command\s+-v\s+([^\s()]+)\s*\)")
HEAD_RE = re.compile(r"^([^\s*]+) \*$")
START_EXEMPT = frozenset({"git"})
WRAPPERS = frozenset({"timeout", "env", "sudo", "exec", "nohup", "xargs"})
SEPARATORS = frozenset({";", "&&", "||", "|", "&", "(", ")", "\n"})


def strip_quotes_and_heredocs(command: str) -> str:
    return QUOTED_RE.sub("_", HEREDOC_RE.sub(r"_\2", command))


def load_heads() -> set[str]:
    settings_dir = os.environ.get("CLAUDE_MANAGED_SETTINGS_DIR", "/etc/claude-code")
    paths = [os.path.join(settings_dir, "managed-settings.json")]
    paths += sorted(
        glob.glob(os.path.join(settings_dir, "managed-settings.d", "*.json"))
    )
    heads: set[str] = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                values = json.load(handle)["sandbox"]["excludedCommands"]
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
        if not isinstance(values, list):
            continue
        for value in values:
            match = HEAD_RE.match(value.strip()) if isinstance(value, str) else None
            if match:
                heads.add(match.group(1))
    return heads


def wrapped_target(tokens: list[str]) -> str | None:
    rest = tokens[1:]
    while rest and (ASSIGNMENT_RE.fullmatch(rest[0]) or rest[0].startswith("-")):
        if rest.pop(0) in {"-u", "--user"} and rest:
            rest.pop(0)
    if tokens[0] == "timeout" and rest:
        rest.pop(0)
    return rest[0] if rest else None


def sandbox_violation(command: str, heads=None, probe=None):
    heads = load_heads() if heads is None else heads
    if not heads and probe is None:
        return False
    for pattern in (WHICH_RE, COMMAND_V_RE):
        for match in pattern.finditer(command):
            name = os.path.basename(match.group(1))
            if name in heads and (pattern is WHICH_RE or name not in START_EXEMPT):
                return True

    def bad(p: str, d: bool) -> bool:
        n = os.path.basename(p)
        return n in heads and ("/" in p or n not in START_EXEMPT and not d)

    first, tokens = True, []
    for token in TOKEN_RE.findall(command) + [";"]:
        if token not in SEPARATORS:
            tokens.append(token)
            continue
        if tokens and tokens[0] in {"do", "then", "else"}:
            tokens.pop(0)
        prefix = 0
        while prefix < len(tokens) and ASSIGNMENT_RE.fullmatch(tokens[prefix]):
            prefix += 1
        if prefix < len(tokens):
            program = tokens[prefix]
            target = wrapped_target(tokens[prefix:]) if program in WRAPPERS else None
            if probe and probe(tokens[prefix:], program, target):
                return True
            if bad(program, first and not prefix) or target and bad(target, False):
                return True
        tokens = []
        first = False
    return False


KILL_REASON = "host のプロセスが死ぬ。launcher 裸名で止めるか放置して報告"
LOOP_REASON = "期待時間の 3 倍の timeout か試行回数上限を入れる"
AUTOSQUASH_REASON = "`GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash` にする"
LOOPBACK_REASON = "`--loopback` を引数の早い位置に付ける"
SANDBOX_REASON = (
    "除外 command は裸名で command の先頭に置く (先頭一致で sandbox を外れる)"
)


def without(pattern: re.Pattern[str], exception: re.Pattern[str], text: str) -> bool:
    return bool(pattern.search(text)) and not exception.search(text)


def segment_hit(pattern, tokens, program, target, exception=None):
    index = tokens.index(target, 1) if target else 0
    program = target or program
    phrase = " ".join((os.path.basename(program), *tokens[index + 1 : index + 2]))
    if (match := pattern.search(phrase)) and match.start() == 0:
        return exception is None or not exception.search(" ".join(tokens[index:]))
    return False


def program_hit(pattern, command: str, exception=None) -> bool:
    probe = partial(segment_hit, pattern, exception=exception)
    return sandbox_violation(command, set(), probe=probe)


LOOP_HIT = partial(without, LOOP_RE, TIMEOUT_RE)
AUTOSQUASH_HIT = partial(without, AUTOSQUASH_RE, INTERACTIVE_RE)
KILL_HIT = partial(program_hit, KILL_RE)
VOICEVOX_HIT = partial(program_hit, VOICEVOX_RE, exception=LOOPBACK_RE)


RULES = (
    ("kill-by-port", KILL_HIT, KILL_REASON),
    ("unbounded-loop", LOOP_HIT, LOOP_REASON),
    ("noninteractive-autosquash", AUTOSQUASH_HIT, AUTOSQUASH_REASON),
    ("voicevox-loopback", VOICEVOX_HIT, LOOPBACK_REASON),
    ("sandbox-invocation", sandbox_violation, SANDBOX_REASON),
)


def run(payload: object) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input", {})
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return 0
    stripped = strip_quotes_and_heredocs(command)
    matched = []
    for name, matcher, reason in RULES:
        if matcher(stripped):
            matched.append(f"- {name}: {reason}")
    if not matched:
        return 0
    sys.stderr.write("command-pattern:\n" + "\n".join(matched) + "\n")
    return 2


def main() -> int:
    try:
        return run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
