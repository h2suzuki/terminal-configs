#!/usr/bin/env python3
"""PreToolUse / Stop nudge: sandbox misreadings (dotfile shadows, config.lock read as a held lock).

Transcript assistant text often lags the tool call, so this scans prior text blocks (past
tool_result-only entries) and, for Bash, the command itself. Rules marked for Stop also block
the turn end so the final message is restated.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass

import sandbox_exclusions

STATE_DIR = os.environ.get("SANDBOX_SHADOW_NUDGE_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "sandbox_shadow_nudge"
)
TAIL_BYTES = 256 * 1024  # transcript window read backwards for the current utterance

SHADOW_NAMES = (
    ".bashrc",
    ".bash_profile",
    ".profile",
    ".zshrc",
    ".zprofile",
    ".gitconfig",
    ".gitmodules",
    ".ripgreprc",
    ".idea",
    ".vscode",
    ".mcp.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/agents",
    ".claude/commands",
    ".claude/hooks",
    ".claude/skills",
    ".claude/workflows",
    ".claude/routines",
    ".claude/output-styles",
    ".claude/launch.json",
    ".claude/loop.md",
    ".claude/scheduled_tasks.json",
)
CUE_WORDS = (
    "未追跡",
    "untracked",
    "??",
    "マウント点",
    "mount point",
    "文字デバイス",
    "char device",
    "character device",
    "shadow",
    "/dev/null",
)
# an immediate ~/ or /home/<user>/ prefix names a real HOME file, not the repo-root shadow
HOME_PREFIX_RE = re.compile(r"(?:~|/home/[^/\s]+)/\Z")
CUE_RE = re.compile("|".join(re.escape(w) for w in CUE_WORDS), re.IGNORECASE)

MSG = (
    "sandbox-shadow: repo 直下の .bashrc / .claude/settings.json 等の未追跡表示は sandbox が "
    "HOME の dotfile を /dev/null で shadow したもの。調査を即打ち切って元の作業へ戻れ "
    "(消さない・ignore しない・upstream を探さない)。\n"
    "教訓: /var/lib/claude-rag-memory/claude-lessons-learned/org/feedback_sandbox_dotfile_shadow.md"
)

CONFIG_LOCK_RE = re.compile(r"config\.lock")
# lock-holder framing: someone holds, left or must release a lock
LOCK_CUE_RE = re.compile(
    r"(?:ロック|lock)\s*(?:され|中|を\s*(?:保持|握|持|取得|解除|解放)|が\s*(?:残|掛|かか|取れ)|解除|解放)"
    r"|locked|lock\s+(?:is\s+)?held|hold(?:s|ing)?\s+the\s+lock|stale\s+lock"
    r"|lock\s+(?:holder|owner)|lockfile|unlock|release\s+the\s+lock"
    r"|別の\s*git|他の\s*git|git\s*プロセス|another\s+git|git\s+process|crash|クラッシュ|異常終了",
    re.IGNORECASE,
)
# the text already names the sandbox mask, so it is the correct reading
LOCK_CORRECT_RE = re.compile(
    r"mask|マスク|/dev/null|bind|78818|ロックではな|not\s+a\s+lock", re.IGNORECASE
)
# examining the sandbox itself: its mounts, namespaces or launcher
INTROSPECT_RE = re.compile(
    r"/proc/(?:self|\d+|\$\$|\$PPID)/(?:mountinfo|mounts|ns\b|status|comm)|\bbwrap\b"
)
SEGMENT_RE = re.compile(r"&&|\|\||[;|&\n]")
ASSIGNMENT_RE = re.compile(r"^\w+=\S*\s+")
# path-bearing inputs of the non-Bash tools that can look at a file
PATH_KEYS = {"Read": ("file_path",), "Grep": ("path",), "Glob": ("path", "pattern")}

# 文面は意図的に冗長: 行動の誤りと正しい確かめ方を両方書き下すため trim しない
PROBE_MSG = (
    "masked-probe: sandbox が覆ったファイルか sandbox の仕組み ({what}) を調べようとしている。"
    "中から見えるのは覆いだけで、実物の有無も中身も分からず、仕組みの説明は session 開始時の"
    "除外コマンド一覧と教訓に既にある。この行動は誤った方向へ進んでいる兆候なので、ここで止めて"
    "元の作業に戻れ。実物に関わる操作が必要なら、それを扱う除外コマンド (git / gh など) を"
    "Bash 呼び出しの先頭に裸名で置いて sandbox の外で実行し、その結果で判断する。"
    "同じターンで別の方法で確かめ直すと、その呼び出しは拒否される。"
)
PROBE_DENY = (
    "masked-probe: このターンで既に、覆われたファイルか sandbox の仕組みを調べて注意を受けている。"
    "今の呼び出しは、その注意を誤りと見なして別の方法で確かめ直す行動なので拒否した。"
    "確かめ直さずに元の作業に戻れ。実物に関わる操作は、除外コマンドを Bash 呼び出しの先頭に"
    "裸名で置いて sandbox の外で実行する。hook 自身はファイルを変更していない。"
)

# 文面は意図的に冗長: 誤読の訂正と次の行動を両方書き下すため trim しない
CONFIG_LOCK_MSG = (
    "config-lock: sandbox 内から見える `.git/config.lock` はロックの証拠にならない。sandbox が "
    "`.git/config` を書かせないために `/dev/null` を読み取り専用で被せた mask で "
    "(anthropics/claude-code#78818)、本物のロックがあっても sandbox 内からは見分けられない。"
    "確かめずに「ロックされている」「stale lock」と書いたのなら、直前の発言を訂正せよ。\n"
    "確かめ方: git を正しく実行する (除外コマンドの git を裸名で Bash 呼び出しの先頭に置き、"
    "sandbox の外で走らせる。`sandbox-host-recovery` の順序)。それでもエラーなら host に実在する。"
    "その場合も、隣の session が居ないか、その repo で作業していないなら残骸なので、自分で消して"
    "作業を続ける。作業中の session が居るなら、その session に確かめる。\n"
    "教訓: /var/lib/claude-rag-memory/claude-lessons-learned/project/"
    "github.com-h2suzuki-scorer/feedback_sandbox_mask_leaks_git_config_lock.md"
)

STOP_SUFFIX = "\n最終発言に上の誤りが含まれている。該当箇所を訂正した回答を書き直してから終了せよ。"


def _shadow_hit(text: str) -> str | None:
    """First shadow name literally present outside a real HOME path, or None."""
    for name in SHADOW_NAMES:
        for m in re.finditer(re.escape(name), text):
            if not HOME_PREFIX_RE.search(text[: m.start()]):
                return name
    return None


def _shadow_text(text: str) -> bool:
    return _shadow_hit(text) is not None and bool(CUE_RE.search(text))


def _shadow_command(command: str) -> bool:
    return _shadow_hit(command) is not None


def _lock_text(text: str) -> bool:
    return (
        bool(CONFIG_LOCK_RE.search(text))
        and bool(LOCK_CUE_RE.search(text))
        and not LOCK_CORRECT_RE.search(text)
    )


def _never(_: str) -> bool:
    return False


def _runs_on_host(command: str) -> bool:
    """One segment led by an excluded command takes the whole Bash call out of the sandbox."""
    patterns = sandbox_exclusions.load_patterns()
    for segment in SEGMENT_RE.split(command):
        segment = segment.strip()
        while ASSIGNMENT_RE.match(segment):
            segment = ASSIGNMENT_RE.sub("", segment, count=1)
        if any(sandbox_exclusions.glob_match(segment, p) for p in patterns):
            return True
    return False


def _masked_target(text: str) -> str | None:
    """The first covered file or sandbox internal the text names, in any spelling of HOME."""
    if CONFIG_LOCK_RE.search(text):
        return ".git/config.lock"
    if m := INTROSPECT_RE.search(text):
        return m.group(0)
    home = os.path.expanduser("~")
    for path in sandbox_exclusions.credential_paths():
        spellings = [path]
        if path.startswith(home + "/"):
            rest = path[len(home) :]
            spellings += ["~" + rest, "$HOME" + rest, "${HOME}" + rest]
        for s in spellings:
            if re.search(re.escape(s) + r"(?![\w.-])", text):
                return path.replace(home, "~", 1)
    return None


def _probe_target(payload: dict) -> str | None:
    """What a tool call looks at inside the sandbox's covers, from any tool that can look."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or _runs_on_host(command):
            return None
        return _masked_target(command)
    values = [tool_input.get(k) for k in PATH_KEYS.get(str(tool), ())]
    return _masked_target(" ".join(v for v in values if isinstance(v, str)))


def _turn_key(payload: dict) -> str:
    """Identity of the current turn: the last real prompt line of the transcript."""
    path = payload.get("transcript_path")
    try:
        lines = _tail_bytes(path).splitlines() if isinstance(path, str) else []
    except OSError:
        lines = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(entry, dict)
            and entry.get("type") == "user"
            and _is_real_prompt(entry)
        ):
            return hashlib.sha256(line).hexdigest()
    return "no-transcript"


@dataclass(frozen=True)
class Rule:
    name: str
    text_hit: Callable[[str], bool]
    command_hit: Callable[[str], bool]
    message: str
    on_stop: bool


RULES = (
    Rule("shadow", _shadow_text, _shadow_command, MSG, on_stop=False),
    Rule("config-lock", _lock_text, _never, CONFIG_LOCK_MSG, on_stop=True),
)


def _tail_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        start = max(0, f.tell() - TAIL_BYTES)
        f.seek(start)
        data = f.read()
    if start:  # the first line at a non-zero offset may be a partial line: drop it
        data = data.split(b"\n", 1)[1] if b"\n" in data else b""
    return data


def _is_real_prompt(entry: dict) -> bool:
    """A human turn (string content, or a list holding a text block) versus a tool_result-only entry."""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def _scan_blocks(path: str) -> list[str]:
    """Assistant text blocks from the tail back to the last real prompt; tool_result-only entries are skipped, not a boundary."""
    try:
        raw = _tail_bytes(path)
    except OSError:
        return []
    lines = raw.decode("utf-8", errors="replace").splitlines()
    blocks: list[str] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "user":
            if _is_real_prompt(entry):
                break
            continue  # tool_result-only: not yet updated with fresh text, keep scanning past it
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    blocks.append(text)
    blocks.reverse()
    return blocks


def _session_key(session_id: object) -> str:
    if not isinstance(session_id, str) or not session_id:
        return "unknown"
    return re.sub(r"[^\w.-]", "_", session_id)[:80]


def _already_nudged(session_id: object, key: str) -> bool:
    try:
        with open(
            os.path.join(STATE_DIR, _session_key(session_id)), encoding="utf-8"
        ) as f:
            return key in f.read().split()
    except OSError:
        return False


def _mark_nudged(session_id: object, key: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(
        os.path.join(STATE_DIR, _session_key(session_id)), "a", encoding="utf-8"
    ) as f:
        f.write(key + "\n")


def _transcript_blocks(payload: dict) -> list[str]:
    path = payload.get("transcript_path")
    return _scan_blocks(path) if isinstance(path, str) and path else []


def _text_hits(
    rules: tuple[Rule, ...], blocks: list[str], session_id: object
) -> tuple[list[Rule], list[str]]:
    """Rules with a hit block not yet nudged, and the per-rule block keys to mark."""
    fired: list[Rule] = []
    keys: list[str] = []
    for rule in rules:
        for block in blocks:
            if not block or not rule.text_hit(block):
                continue
            key = rule.name + ":" + hashlib.sha256(block.encode("utf-8")).hexdigest()
            if key in keys or _already_nudged(session_id, key):
                continue
            keys.append(key)
            if rule not in fired:
                fired.append(rule)
    return fired, keys


def _pre_tool_use(payload: dict) -> int:
    session_id = payload.get("session_id")
    fired, keys = _text_hits(RULES, _transcript_blocks(payload), session_id)

    messages = [rule.message for rule in fired]
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if payload.get("tool_name") == "Bash" and isinstance(command, str):
        for rule in RULES:
            marker = rule.name + ":bash-cmd"  # one flag per session per rule
            if rule.command_hit(command) and not _already_nudged(session_id, marker):
                keys.append(marker)
                if rule not in fired:
                    fired.append(rule)
                    messages.append(rule.message)

    if target := _probe_target(payload):
        turn = "masked-probe-turn:" + _turn_key(payload)
        if _already_nudged(session_id, turn):
            out = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": PROBE_DENY,
                }
            }
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            return 0
        keys.append(turn)
        messages.append(PROBE_MSG.format(what=target))

    if messages:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": "\n\n".join(messages),
            }
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        for key in keys:
            _mark_nudged(session_id, key)
    return 0


def _stop(payload: dict) -> int:
    session_id = payload.get("session_id")
    blocks = _transcript_blocks(payload)
    final = payload.get("last_assistant_message")
    if isinstance(final, str) and final and final not in blocks:
        blocks.append(final)
    fired, keys = _text_hits(
        tuple(rule for rule in RULES if rule.on_stop), blocks, session_id
    )
    if not fired:
        return 0
    for key in keys:  # per-block dedupe lets a restated answer end the turn
        _mark_nudged(session_id, key)
    sys.stderr.write("\n\n".join(rule.message for rule in fired) + STOP_SUFFIX + "\n")
    return 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        if payload.get("hook_event_name") == "Stop":
            # a one-off session spawned by another hook has no user to restate for
            return 0 if os.environ.get("CLAUDE_HOOK_CHILD") else _stop(payload)
        return _pre_tool_use(payload)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
