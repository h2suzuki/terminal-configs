#!/usr/bin/env python3
"""PreToolUse / Stop nudge: sandbox misreadings (dotfile shadows, config.lock, blaming the sandbox).

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
LOCK_CMD_RE = re.compile(r"\b(?:rm|unlink|lsof|fuser)\b")

# 文面は意図的に冗長: 誤読の訂正と次の行動を両方書き下すため trim しない
CONFIG_LOCK_MSG = (
    "config-lock: `.git/config.lock` はロックではない。保持している git プロセスも、"
    "crash の残した stale lock も存在しない。sandbox が `.git/config` を書かせないために "
    "`/dev/null` を読み取り専用で被せた mask である (anthropics/claude-code#78818)。"
    "保持者を探す・待つ・「ロックされている」と報告するのは誤りなので、直前の発言を訂正せよ。\n"
    "`could not lock config file ... File exists` で git が失敗したら、sandbox の仕組みを調べ直さず、"
    "まず自分の呼び出し方を直す (除外コマンドを裸名で Bash 呼び出しの先頭に置く。"
    "`sandbox-host-recovery` の順序)。host に 0-byte・mode 444 の残骸が実在し、"
    "使用中でないなら自分で消して作業を続ける。\n"
    "教訓: /var/lib/claude-rag-memory/claude-lessons-learned/project/"
    "github.com-h2suzuki-scorer/feedback_sandbox_mask_leaks_git_config_lock.md"
)

SANDBOX_WORD_RE = re.compile(r"sandbox|サンドボックス", re.IGNORECASE)
# giving up because of the sandbox, or claiming the command ran inside it
BLAME_CUE_RE = re.compile(
    r"できな|できませ|できず|られませ|られず|られな|られていませ|読めず|読めな|書けず|書けな"
    r"|消せず|消せな|使えず|使えな|制約|制限|のせい|権限では|はずなのに|行き詰|外で(?:の)?実行"
    r"|(?:sandbox|サンドボックス)\s*の?\s*(?:内|中|側|内部)\s*(?:で|の|から)?\s*(?:動|走|実行)"
    r"|Permission denied|Read-only|cannot|can't|unable|blocked|not allowed"
    r"|runs?\s+(?:inside|in)\s+the\s+sandbox",
    re.IGNORECASE,
)
# the sentence names a calling form, or a target no excluded command can write (root-owned deploy)
BLAME_EXEMPT_RE = re.compile(
    r"呼び出し方|呼び方|invocation|裸名|先頭|パイプ|pipe|リダイレクト|標準入力|stdin|ループ"
    r"|--jq|segment|代入|wrapper|前置|root\s*所有|/etc/|/usr/local|deploy|デプロイ|配備|sudo",
    re.IGNORECASE,
)
# prose names an excluded command by what it serves
NAME_ALIASES = {"gh": ("GitHub",), "jev": ("judge",)}

# 文面は意図的に冗長: 同じ誤りが繰り返されているため、訂正と次の行動を両方書き下す
ENV_BLAME_MSG = (
    "invocation-first: 除外コマンド (git / gh 等) は sandbox の外で走る。"
    "「sandbox 内で動いた」「sandbox が塞いだ」と環境のせいにしたのは誤りなので、直前の発言を訂正せよ。"
    "sandbox 内に入ったなら原因は自分の呼び出し方である: 除外コマンドを裸名で Bash 呼び出しの"
    "先頭に置いたか (変数代入の segment・path 前置・wrapper で始めていないか) を確かめ、"
    "`sandbox-host-recovery` の順で呼び出しを直してから結論を書く。"
    "sandbox の仕組みを調べ直したりユーザーに確かめ直したりするのは、"
    "自分の発言を相手に尋ね返すのと同じ無駄であり、ユーザーの負担になる。"
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


# a quote followed by "と誤解する" / "と書いても" is a claim under discussion, not one being made
DISCUSSED_QUOTE_RE = re.compile(
    r"(?:「[^」]*」|“[^”]*”)(?=\s*(?:と|という|って)[^。\n「]{0,6}?"
    r"(?:誤解|勘違い|思い込|書|言|発言|断定|主張|報告))"
)


def _unquoted(text: str) -> str:
    return DISCUSSED_QUOTE_RE.sub("", text)


def _lock_text(text: str) -> bool:
    text = _unquoted(text)
    return (
        bool(CONFIG_LOCK_RE.search(text))
        and bool(LOCK_CUE_RE.search(text))
        and not LOCK_CORRECT_RE.search(text)
    )


def _lock_command(command: str) -> bool:
    return bool(CONFIG_LOCK_RE.search(command)) and bool(LOCK_CMD_RE.search(command))


def _excluded_names() -> tuple[str, ...]:
    """Single-word excluded command names; patterns with arguments (`systemctl --no-pager ...`) read as prose too often."""
    try:
        patterns = sandbox_exclusions.load_patterns()
    except Exception:
        return ()
    names = {p.rstrip("*").strip() for p in patterns}
    return tuple(sorted(n for n in names if n and not re.search(r"[\s*]", n)))


def _names_excluded_command(text: str, names: tuple[str, ...]) -> bool:
    words = [a for n in names for a in (n, *NAME_ALIASES.get(n, ()))]
    # ASCII-only boundaries: Japanese right after a name (`gitの`) still counts as a mention
    return any(
        re.search(r"(?<![A-Za-z0-9_/.-])" + re.escape(w) + r"(?![A-Za-z0-9_-])", text)
        for w in words
    )


def _blame_text(text: str) -> bool:
    text = _unquoted(text)
    if not SANDBOX_WORD_RE.search(text):
        return False
    names = _excluded_names()
    return any(  # the sandbox, the give-up cue and the command must share a sentence
        SANDBOX_WORD_RE.search(s)
        and BLAME_CUE_RE.search(s)
        and not BLAME_EXEMPT_RE.search(s)
        and _names_excluded_command(s, names)
        for s in re.split(r"[。\n]|(?<=[.!?])\s", text)
    )


def _never(_: str) -> bool:
    return False


@dataclass(frozen=True)
class Rule:
    name: str
    text_hit: Callable[[str], bool]
    command_hit: Callable[[str], bool]
    message: str
    on_stop: bool


RULES = (
    Rule("shadow", _shadow_text, _shadow_command, MSG, on_stop=False),
    Rule("config-lock", _lock_text, _lock_command, CONFIG_LOCK_MSG, on_stop=True),
    Rule("env-blame", _blame_text, _never, ENV_BLAME_MSG, on_stop=True),
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

    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if payload.get("tool_name") == "Bash" and isinstance(command, str):
        for rule in RULES:
            marker = rule.name + ":bash-cmd"  # one flag per session per rule
            if rule.command_hit(command) and not _already_nudged(session_id, marker):
                keys.append(marker)
                if rule not in fired:
                    fired.append(rule)

    if fired:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": "\n\n".join(rule.message for rule in fired),
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
