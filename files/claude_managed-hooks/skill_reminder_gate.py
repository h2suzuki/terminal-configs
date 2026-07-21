#!/usr/bin/env python3
r"""
Skill-active gate hook for Claude Code.

Purpose
=======
writing-* skill は LLM の self-invoke 依存で発火率が低い。本 hook は Edit/Write/
MultiEdit を 「関連 skill が **当 turn で invoke 済か**」 で gate する。正規ルート
(skill 発動 → 同 turn で編集) は通し、 skip = detour は deny → kind declare →
skill invoke → 編集、 へ誘導する。

mechanism
=========
3 mode (argv[1] で dispatch):

  gate    PreToolUse(^(Edit|Write|MultiEdit)$) hook。下記 flow で allow/deny。
  commit-gate
          PreToolUse(Bash) hook。commit 対象 file の関連 skill が active かを gate。
          commit の実行主体が、その turn 内に対象 kind の規約 skill を invoke 済み
          であることを要求する。
          `git ... commit` 形のみを対象とし、commit-tree、merge、cherry-pick、revert、
          rebase --continue、stash 等の別経路は射程外。
          改行で区切られた直接可視の commit は全行検査する。
          bash -c、変数 command、展開 subcommand、git alias、別言語 process 内は検出対象外。
          pathless / -a の commit は deny-broad-git-commit が deny するため到達しない。
          commit 対象の取得に失敗した場合は file kind を判定できないため deny。
  declare model が Bash で実行する CLI:
            skill_reminder_gate.py declare <ABS-path> <kind>[,<kind>...]
          拡張子なし file の kind 真実源を session state に記録。sid は env
          $CLAUDE_CODE_SESSION_ID (== payload session_id) から取る。path は
          **絶対 path 必須** — gate は payload.cwd、 declare は shell cwd で
          解決するため、 相対だと cwd drift 時に hash 不一致で永久 deny loop。
          同じ絶対 path を後続 Edit でも使う。

gate flow:
  agent_id あり (subagent) → ALLOW
  declared(sid, path) あり:
      拡張子あり → required = relevant_skills(path) ∪ ∪(宣言 kind の skill)
                   (declare は **追加のみ**。 auto-detect を下回れない —
                    .py を else 宣言で gating 無効化する穴を塞ぐ)
      拡張子なし → required = ∪(宣言 kind の skill)  (declare が唯一の真実源)
  elif 拡張子あり → required = relevant_skills(path)
  else (拡張子なし・未宣言):
      shebang (#!.../bash|python) → required = KIND_SKILLS[kind]
        (Write は新 content の 1 行目 — 全置換ゆえ disk より優先。 Edit は既存 file)
      shebang 無し/未知 interp → DENY「kind を declare せよ」; return
  required が空            → ALLOW (skill-less file。transcript 非読込)
  active = 現 turn かつ直近 5 分以内の Skill invoke 集合 (現 turn を後方 1 つ読み ts で drop)
  active 判定不能 (corrupted) → ALLOW (fail-open)
  transcript stale (newest entry ts < now-120s) → ALLOW (fail-open; resume/subagent)
  required ⊆ active        → ALLOW
  else                    → DENY「<missing> を invoke してから編集」

kind 語彙 → skill (additive。else 必須):
  code   → writing-code
  python → writing-code + writing-python
  bash   → writing-code + writing-bash
  test   → writing-code + writing-tests   (lang は別 kind で additive 宣言)
  skills → writing-skills
  todos  → writing-todos
  memory → memory-routing  (実 gate は memory_routing_gate、本 hook は通す)
  else   → ∅  (skill の無い file。これが無いと拡張子なし file が Write 不能)

gate mode の skill-active 窓 (現 turn かつ直近 5 分以内) の根拠
================================================================
現 turn を後方 1 つだけ読み (_load_tail、boundary は positional ゆえ ts 単調性に
非依存で sound)、その中で直近 5 分以内に invoke された skill のみ active とみなす
(5 分以上前は drop)。5 分は長い作業中の再 invoke friction 抑制と、無関係に古い
invoke が通るリスク回避の折衷。現 turn のみ読むため cross-turn の recency は無い。

運用症状 (再調査不要)
=====================
長い turn で skill invoke 後に診断 Bash/Read 等を挟むと invoke が窓から脱落し、
Edit が「<missing> を invoke せよ」で連続 deny する (required の抜けが skill 別に
rotate して見える)。sandbox 阻害ではない — hook は非 sandbox 実行で transcript/
state I/O は正常 (read_before_edit の WAL state 書込も成功)。回復: required skill を
fresh に invoke して即 Edit (間に Bash/Read を挟まない)。

turn boundary 判定 (load-bearing — 変更時は false-allow/deny を再発させる)
=========================================================================
直近の human-input user entry を boundary とする。boundary 判定:
  - isMeta==True の user entry は除外 (Skill invoke 後の skill 展開 injection。
    boundary 扱いすると Skill invoke を turn から弾いて誤 deny)
  - content が str → boundary (典型 human prompt)
  - content が list で **非 tool_result block を 1 つ以上含む** → boundary
    (画像+テキスト / steering 等の list 形 human prompt。取りこぼすと前 turn の
     skill が active に leak して誤 allow)
  - content が list で全 tool_result → 継続 (boundary でない)
boundary 不在の corrupted transcript では None → fail-open ALLOW。

deny 方式・fail-open
====================
deny は JSON permissionDecision: "deny" (exit 0) — hook bug が誤って tool を
block しない。全例外を握り潰し exit 0 (fail-open)。transcript が読めない /
boundary 不在のときも ALLOW に倒す。
commit-gate は commit 対象取得失敗時のみ判定不能を ALLOW にせず DENY に倒し、
理由と再実行条件を表示する。
以下の stale transcript valve は gate mode のみに適用し、commit-gate には適用しない。
Stale transcript (newest entry ts older than TRANSCRIPT_FRESH_SECONDS) also falls
to ALLOW: resumed-session bg-notification turns (2026-07-09) and subagents
(2026-07-06) were observed handing the gate transcript content missing the
just-made Skill invoke, turning every legit invoke->edit into a false deny.
A stale transcript proves nothing about invoke absence, so the gate must not
deny from it.

residual (閉じない・既知)
=========================
- 拡張子なし file の kind 語彙選択は model 判断 (bash を else 誤宣言ですり抜け)。
  detour deny で declare は強制できるが語彙は model が選ぶ。 未宣言 file は shebang で
  bash/python を auto-detect (declared 分岐は従来通り declare が真実源・shebang 非適用)。
- 未収載の exotic 言語拡張子 (CODE_EXTENSIONS 外) は skill-less 扱い。
- .j2/.in/.tmpl 等 templating 拡張子は config 多数ゆえ skill-less 許容 (.bak/
  .orig/.swp/~ の backup/swap は元拡張子を復元して gate)。
- symlink: _canonical の realpath が skill/hook-dir segment を解決し分類が変わり
  得る (現 deploy の symlink は分類保存、 SKILL.md は basename 判定で不変 = 現状
  未発火。latent)。

canonical source: files/claude_managed-hooks/skill_reminder_gate.py
deploy: /etc/claude-code/hooks/  両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unittest

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "hooks", "state", "skill_reminder")
DECL_STALE_SECONDS = 7 * 24 * 3600  # 放置宣言 session dir の自己掃除閾値
SKILL_WINDOW_SECONDS = 300  # skill-active 窓 = 現 turn かつ直近 5 分以内
TRANSCRIPT_FRESH_SECONDS = (
    120  # newest-entry age beyond this = stale transcript -> fail-open
)
GATE_TOOLS = ("Edit", "Write", "MultiEdit")

GIT_COMMIT_RE = re.compile(r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+commit\b(?![\w.])")
COMMIT_QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
COMMIT_HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)
COMMIT_TAIL_DELIMITER = re.compile(r"&&|\|\||;|\|")
COMMIT_WRAPPER = re.compile(
    r"^(?:\(+\s*|[A-Za-z_][A-Za-z0-9_]*=\S+\s+|timeout\s+\S+\s+|xargs\s+)+"
)


@dataclass(frozen=True)
class CommitInvocation:
    args: tuple[str, ...]
    cwd_override: str
    pathspecs: tuple[str, ...]
    amend_like: bool
    has_all: bool
    has_include: bool


# kind → 当該 kind が要求する skill 集合 (additive。else は ∅)。
KIND_SKILLS: dict[str, set[str]] = {
    "code": {"writing-code"},
    "python": {"writing-code", "writing-python"},
    "bash": {"writing-code", "writing-bash"},
    "test": {"writing-code", "writing-tests"},
    "skills": {"writing-skills"},
    "todos": {"writing-todos"},
    "memory": {"memory-routing"},
    "else": set(),
}

# source code 拡張子 (any language) → writing-code (universal) を要求。広めに列挙し
# 未収載は skill-less (residual)。LANGUAGES の managed add-on を上に積む。
CODE_EXTENSIONS: set[str] = {
    ".py",
    ".pyi",
    ".pyw",
    ".sh",
    ".bash",
    ".zsh",
    ".ksh",
    ".fish",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".cts",
    ".mts",
    ".go",
    ".rs",
    ".rb",
    ".rake",
    ".php",
    ".pl",
    ".pm",
    ".lua",
    ".tcl",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hpp",
    ".hh",
    ".hxx",
    ".m",
    ".mm",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".groovy",
    ".gradle",
    ".clj",
    ".cljs",
    ".cljc",
    ".cs",
    ".fs",
    ".fsx",
    ".vb",
    ".swift",
    ".dart",
    ".r",
    ".jl",
    ".ex",
    ".exs",
    ".erl",
    ".hrl",
    ".hs",
    ".ml",
    ".mli",
    ".nim",
    ".zig",
    ".sql",
    ".vim",
    ".el",
    ".lisp",
    ".scm",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    ".astro",
    ".proto",
    ".thrift",
    ".tf",
    ".tfvars",
    ".hcl",
    ".bicep",
    ".sol",
}

# managed language add-on skill (writing-code の上に積む)。bash add-on は bash 系
# のみ (writing-bash は zsh/fish を SKIP)。
LANGUAGES: dict[str, str] = {
    ".py": "writing-python",
    ".pyi": "writing-python",
    ".pyw": "writing-python",
    ".sh": "writing-bash",
    ".bash": "writing-bash",
}

# hook script として writing-skills を要求する拡張子 (hook dir 内のみ)。
HOOK_SCRIPT_EXTS = {".py", ".pyi", ".pyw", ".sh", ".bash"}

# backup/swap suffix。剥いで元拡張子で再判定 (script.py.bak → .py、 foo.bash~ → .bash)。
STRIP_SUFFIXES = (".bak", ".orig", ".swp", ".rej")

# CC hook dir anchor (hook script 編集 → writing-skills)。
HOOK_DIR_RE = re.compile(
    r"/(claude_managed-hooks|claude_user-hooks)/|"
    r"/etc/claude-code/hooks/|/\.claude/hooks/"
)

# test file 判定 (code file にのみ writing-tests を足す)。anchored で誤検出抑制。
TEST_NAME_RE = re.compile(
    r"^test_.+\.[a-z0-9]+$"  # test_foo.py
    r"|.+_test\.[a-z0-9]+$"  # foo_test.go / foo_test.py
    r"|.+_spec\.[a-z0-9]+$"  # foo_spec.rb
    r"|.+\.test\.[a-z0-9]+$"  # foo.test.ts
    r"|.+\.spec\.[a-z0-9]+$",  # foo.spec.js
    re.IGNORECASE,
)
TEST_DIR_RE = re.compile(r"/(tests?|__tests__|spec)/")


def _canonical(raw_path: str, cwd: str) -> str:
    if not isinstance(raw_path, str) or not raw_path:
        return ""
    expanded = os.path.expanduser(raw_path)
    if not os.path.isabs(expanded):
        base = cwd if cwd else os.getcwd()
        expanded = os.path.join(base, expanded)
    return os.path.realpath(expanded)


def _has_extension(path: str) -> bool:
    return bool(os.path.splitext(os.path.basename(path))[1])


def _effective_ext(base: str) -> str:
    """backup/swap suffix を剥いだ後の拡張子 (lower)。script.py.bak → .py。"""
    name = base[:-1] if base.endswith("~") else base
    stem, sfx = os.path.splitext(name)
    if sfx.lower() in STRIP_SUFFIXES:
        name = stem
    return os.path.splitext(name)[1].lower()


def _is_test(path: str) -> bool:
    return bool(TEST_NAME_RE.match(os.path.basename(path)) or TEST_DIR_RE.search(path))


def relevant_skills(path: str) -> set[str]:
    """拡張子あり file の auto-detect。skill 不要なら空集合。"""
    base = os.path.basename(path)
    low = base.lower()
    if low == "todos.md":
        return {"writing-todos"}
    skills: set[str] = set()
    ext = _effective_ext(base)
    if low == "skill.md" or (HOOK_DIR_RE.search(path) and ext in HOOK_SCRIPT_EXTS):
        skills.add("writing-skills")
    if ext in CODE_EXTENSIONS:
        skills.add("writing-code")
        lang = LANGUAGES.get(ext)
        if lang:
            skills.add(lang)
        if _is_test(path):
            skills.add("writing-tests")
    return skills


SHEBANG_MAXLEN = 256


def _shebang_kind(path: str) -> str | None:
    """既存 file の 1 行目 shebang から kind (bash|python) を判定。無し/未知/読めない → None。"""
    try:
        with open(path, "rb") as f:
            first = f.readline(SHEBANG_MAXLEN).decode("utf-8", "replace")
    except OSError:
        return None
    return _shebang_kind_text(first)


def _shebang_kind_text(text) -> str | None:
    """text 先頭行の shebang から kind (bash|python) を判定。無し/未知/非 str → None。"""
    if not isinstance(text, str):
        return None
    first = text[:SHEBANG_MAXLEN].split("\n", 1)[0].strip()
    if not first.startswith("#!"):
        return None
    tokens = first[2:].split()
    if not tokens:
        return None
    interp = os.path.basename(tokens[0])
    if interp == "env":  # `#!/usr/bin/env [VAR=v]... <interp>`
        rest = [t for t in tokens[1:] if not t.startswith("-") and "=" not in t]
        if not rest:
            return None
        interp = os.path.basename(rest[0])
    if interp.startswith("python"):
        return "python"
    if interp == "sh" or interp.endswith("bash"):
        return "bash"
    return None


# --- declare state (拡張子なし file 用・session persistent) ---


def _session_dir(sid: str) -> str:
    return os.path.join(STATE_DIR, sid)


def _decl_path(sid: str, path: str) -> str:
    h = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    return os.path.join(_session_dir(sid), "decl-" + h)


def _declared_kinds(sid: str, path: str) -> list[str] | None:
    """記録済の宣言 kind list。未宣言なら None。"""
    if not sid:
        return None
    try:
        with open(_decl_path(sid, path), encoding="utf-8") as f:
            first = f.readline().strip()
    except OSError:
        return None
    return [k for k in first.split(",") if k]


def _prune_old_sessions() -> None:
    cutoff = time.time() - DECL_STALE_SECONDS
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return
    for name in names:
        d = os.path.join(STATE_DIR, name)
        try:
            if os.path.getmtime(d) < cutoff:
                for f in os.listdir(d):
                    try:
                        os.remove(os.path.join(d, f))
                    except OSError:
                        pass
                os.rmdir(d)
        except OSError:
            pass


# --- current-turn skill scan ---


_TAIL_BUFSIZE = 128 * 1024  # 後方読みブロック。実測 turn mean≈110KB を 1 read で覆う


def _load_tail(path: str, turns: int = 1, bufsize: int = _TAIL_BUFSIZE) -> list[dict]:
    """末尾から turn boundary を turns 個含むまで後方読みで返す; boundary が turns 未満なら全件。"""
    try:
        with open(path, "rb") as f:
            pos = f.seek(0, os.SEEK_END)
            pending = b""  # 行頭が手前ブロックにある途中行 (次の読みで結合)
            tail: list[dict] = []  # newest-first
            seen = 0
            while pos > 0:
                step = min(bufsize, pos)
                pos -= step
                f.seek(pos)
                parts = (f.read(step) + pending).split(b"\n")
                pending = parts.pop(0)
                for raw in reversed(parts):
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tail.append(obj)
                    if _is_turn_boundary(obj):
                        seen += 1
                        if seen >= turns:
                            tail.reverse()
                            return tail
            line = pending.strip()  # BOF: 先頭断片は完全な 1 行
            if line:
                try:
                    tail.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            tail.reverse()
            return tail  # boundary < turns: 集めた全件
    except OSError:
        return []


def _is_turn_boundary(obj: dict) -> bool:
    """human-input turn の起点か。isMeta(skill 展開) と tool_result 継続は起点でない。"""
    # isSidechain entry が現 format に出現すると通常 entry として数え、turn 判定がずれうる。
    if obj.get("type") != "user" or obj.get("isMeta"):
        return False
    msg = obj.get("message", {})
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") != "tool_result" for b in content
        )
    return False


def _parse_ts(ts) -> float | None:
    """Transcript entry timestamp (ISO8601, trailing 'Z') -> epoch sec, else None."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _transcript_stale(entries: list[dict], now: float, fresh_s: int) -> bool:
    """True iff newest parsed entry ts is older than now - fresh_s (no ts at all -> False)."""
    newest = None
    for obj in entries:
        ep = _parse_ts(obj.get("timestamp"))
        if ep is not None and (newest is None or ep > newest):
            newest = ep
    return newest is not None and newest < now - fresh_s


def _active_skills(
    entries: list[dict], now: float, window_s: int | None
) -> set[str] | None:
    """現 turn の invoke 済 skill。window_s=None は時刻で絞らない。"""
    start_idx = -1
    for i in range(len(entries) - 1, -1, -1):
        if _is_turn_boundary(entries[i]):
            start_idx = i + 1
            break
    if start_idx == -1:
        return None

    cutoff = now - window_s if window_s is not None else None
    active: set[str] = set()
    for idx, obj in enumerate(entries):
        if obj.get("type") != "assistant":
            continue
        if idx < start_idx:
            continue  # 現 turn 外
        ep = _parse_ts(obj.get("timestamp"))
        if cutoff is not None and ep is not None and ep < cutoff:
            continue  # 現 turn 内でも 300 秒以上前は drop
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Skill":
                continue
            inp = block.get("input") or {}
            name = inp.get("skill") if isinstance(inp, dict) else None
            if isinstance(name, str) and name:
                active.add(name)
    return active


# --- deny emission (writing-skills の deny-wording 規律。文面は意図的に冗長・trim 禁止) ---


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


_VOCAB = "python / bash / code / test / skills / todos / memory / else"


def _deny_declare(basename: str) -> None:
    _emit_deny(
        f"拡張子の無い file 「{basename}」 は kind を自動判定できません。 "
        f"編集前に **絶対 path** で kind を declare してください: "
        f"`/etc/claude-code/hooks/skill_reminder_gate.py declare <絶対path> <kind>` "
        f"(kind = {_VOCAB}、 複数なら comma 区切り)。 相対 path は gate と解決基準が "
        f"ずれて match しないため必ず絶対 path で、 後続の Edit/Write でも同じ絶対 "
        f"path を使ってください。 skill の不要な file は `else` を declare すれば "
        f"通ります。 declare 後そのまま編集が通ります (hook 自身は file を変更しません)。"
    )


def _deny_missing(missing: set[str]) -> None:
    names = " / ".join(sorted(missing))
    _emit_deny(
        f"この編集には {names} skill を当 turn 内で invoke してから入って "
        f"ください (正規ルート = skill 発動 → 同 turn で編集)。 skill を skip "
        f"して編集に入る detour を gate しています。 該当 skill を invoke 後、 "
        f"そのまま編集が通ります (hook 自身は file を変更しません)。 skill が "
        f"不要な file なら `declare <絶対path> else` で宣言してください。"
    )


def _strip_commit_heredoc(match: re.Match) -> str:
    """Hide heredoc data while preserving shell code after its opener."""
    return "_" + match.group(2)


def _masked_commit_command(command: str) -> tuple[str, str, list[str]]:
    quoted: list[str] = []

    def replace_quote(match: re.Match) -> str:
        value = match.group(0)[1:-1]
        if match.group(0).startswith('"'):
            value = value.replace('\\"', '"').replace("\\\\", "\\")
        quoted.append(value)
        return f"__Q{len(quoted) - 1}__"

    without_bodies = COMMIT_HEREDOC.sub(
        _strip_commit_heredoc, command.replace("\\\n", " ")
    )
    tokenized = COMMIT_QUOTED.sub(replace_quote, without_bodies)
    return COMMIT_QUOTED.sub("_", without_bodies), tokenized, quoted


def _resolve_commit_token(token: str, quoted: list[str]) -> str:
    def replace_placeholder(match: re.Match) -> str:
        position = int(match.group(1))
        return quoted[position] if position < len(quoted) else match.group(0)

    return re.sub(r"__Q(\d+)__", replace_placeholder, token)


def _commit_flags(args: tuple[str, ...]) -> tuple[bool, bool, bool]:
    amend_like = False
    has_all = False
    has_include = False
    limit = args.index("--") if "--" in args else len(args)
    for token in args[:limit]:
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            amend_like |= name in {"--amend", "--fixup", "--squash"}
            has_all |= name == "--all"
            has_include |= name == "--include"
            continue
        if not token.startswith("-") or token == "-":
            continue
        for char in token[1:]:
            if char in {"m", "F", "C", "c", "t", "S", "u"}:
                break
            has_all |= char == "a"
            has_include |= char == "i"
    return amend_like, has_all, has_include


def _commit_cwd(prefix: str, quoted: list[str]) -> str:
    tokens = [_resolve_commit_token(token, quoted) for token in prefix.split()]
    cwd = ""
    position = 1
    while position < len(tokens) - 1:
        token = tokens[position]
        if token in {"-C", "--work-tree"} and position + 1 < len(tokens) - 1:
            position += 1
            cwd = tokens[position]
        elif token.startswith("-C") and token != "-C":
            cwd = token[2:]
        elif token.startswith("--work-tree="):
            cwd = token.split("=", 1)[1]
        position += 1
    return cwd


def _find_commits(command: str) -> list[CommitInvocation]:
    """Find every directly visible commit line without parsing shell grammar."""
    masked, tokenized, quoted = _masked_commit_command(command)
    commits: list[CommitInvocation] = []
    for masked_line, tokenized_line in zip(
        masked.splitlines(), tokenized.splitlines(), strict=True
    ):
        if masked_line.lstrip().startswith("#"):
            continue
        if GIT_COMMIT_RE.search(COMMIT_WRAPPER.sub("", masked_line.lstrip())) is None:
            continue
        tokenized_candidate = COMMIT_WRAPPER.sub("", tokenized_line.lstrip())
        tokenized_match = GIT_COMMIT_RE.search(tokenized_candidate)
        if tokenized_match is None:
            continue
        tail = tokenized_candidate[tokenized_match.end() :]
        delimiter = COMMIT_TAIL_DELIMITER.search(tail)
        if delimiter is not None:
            tail = tail[: delimiter.start()]
        raw_args: list[str] = []
        for token in tail.split():
            if token.startswith("#") or re.match(r"(?:\d?>|>&)", token):
                break
            raw_args.append(
                token.rstrip(")") if masked_line.lstrip().startswith("(") else token
            )
        args = tuple(_resolve_commit_token(token, quoted) for token in raw_args)
        pathspecs = args[args.index("--") + 1 :] if "--" in args else ()
        amend_like, has_all, has_include = _commit_flags(args)
        commits.append(
            CommitInvocation(
                args,
                _commit_cwd(
                    tokenized_candidate[
                        tokenized_match.start() : tokenized_match.end()
                    ],
                    quoted,
                ),
                pathspecs,
                amend_like,
                has_all,
                has_include,
            )
        )
    return commits


def _nul_paths(output: str) -> list[str]:
    return [path for path in output.split("\0") if path]


def _staged_under(pathspecs: list[str], cwd: str) -> tuple[list[str], str, bool]:
    """pathspec を index/worktree の file へ展開し、成否と基準 path を返す。"""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z", "--", *pathspecs],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        worktree = subprocess.run(
            ["git", "diff", "--name-only", "-z", "--", *pathspecs],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as e:
        sys.stderr.write(
            f"commit-gate: pathspec 展開に失敗したため deny します ({e}).\n"
        )
        return pathspecs, cwd, False
    files = sorted(set(_nul_paths(staged)) | set(_nul_paths(worktree)))
    return (files, root, True) if files and root else (pathspecs, cwd, True)


def _amend_paths(commit: CommitInvocation, cwd: str) -> tuple[list[str], str] | None:
    """Return staged ∪ HEAD paths, plus worktree paths for all/include flags."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        previous = subprocess.run(
            ["git", "show", "--pretty=", "--name-only", "-z", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        paths = set(_nul_paths(staged)) | set(_nul_paths(previous))
        if commit.has_all or commit.has_include:
            worktree = subprocess.run(
                ["git", "diff", "--name-only", "-z"],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            paths.update(_nul_paths(worktree))
        return sorted(paths), root
    except (OSError, subprocess.SubprocessError) as e:
        sys.stderr.write(
            f"commit-gate: commit 対象 path の取得に失敗したため deny します ({e}).\n"
        )
        return None


def _skills_for_declared_kinds(kinds: list[str]) -> set[str]:
    skills: set[str] = set()
    for kind in kinds:
        skills |= KIND_SKILLS.get(kind, set())
    return skills


def _commit_required_skills(path: str, sid: str) -> set[str]:
    """Return required skills; unknown extensionless files require no skill."""
    required = relevant_skills(path)
    declared = _declared_kinds(sid, path)
    if declared is None:
        if _has_extension(path):
            return required
        kind = _shebang_kind(path)
        return set(KIND_SKILLS[kind]) if kind else set()
    declared_skills = _skills_for_declared_kinds(declared)
    if _has_extension(path):
        return required | declared_skills
    return declared_skills


def _deny_commit_missing(missing_by_path: dict[str, set[str]]) -> None:
    details = "; ".join(
        f"{path}: {' / '.join(sorted(skills))}"
        for path, skills in missing_by_path.items()
    )
    # 解除条件と次回回避行動を自己完結させるため、deny 文面は意図的に冗長・trim 禁止。
    _emit_deny(
        f"commit 対象 file に必要な規約 skill が active ではありません: {details}。 "
        f"解除するには、該当 skill を invoke してから commit をやり直してください。 "
        f"次回この deny を避けるには、編集を subagent や codex に委譲する場合も、 "
        f"commit を実行する主体自身が、その turn 内に対象 file kind の規約 skill を "
        f"invoke し、その規約を委譲内容に反映してから編集を委譲してください。"
        f"hook 自身は file を変更しません。"
    )


def _deny_unresolved_pathspec(pathspecs: list[str]) -> None:
    names = " / ".join(pathspecs)
    _emit_deny(
        f"commit 対象の pathspec ({names}) を展開できず、file kind を判定できません。 "
        f"repo の cwd と git の状態を確認し、commit 対象を明示してやり直してください。"
        f"hook 自身は file を変更しません。"
    )


# --- modes ---


def cmd_gate(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    # subagent には自身の invoke 履歴が渡るとは限らず判定できないため fail-open
    if payload.get("agent_id"):
        return
    if payload.get("tool_name") not in GATE_TOOLS:
        return
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        return
    cwd = payload.get("cwd") or ""
    path = _canonical(inp.get("file_path") or "", cwd)
    if not path:
        return
    sid = payload.get("session_id") or ""

    declared = _declared_kinds(sid, path)
    if declared is not None:
        declared_skills = _skills_for_declared_kinds(declared)
        # 拡張子あり: declare は追加のみ (auto-detect を下回れない)。なし: declare が唯一源。
        if _has_extension(path):
            required = relevant_skills(path) | declared_skills
        else:
            required = declared_skills
    elif _has_extension(path):
        required = relevant_skills(path)
    else:
        # Write は全置換ゆえ新 content の shebang が真実源、Edit は既存 file の shebang
        if payload.get("tool_name") == "Write":
            kind = _shebang_kind_text(inp.get("content"))
        else:
            kind = _shebang_kind(path)
        if kind is None:
            _deny_declare(os.path.basename(path))
            return
        required = set(KIND_SKILLS[kind])

    if not required:
        return  # skill-less file。transcript 非読込。

    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return  # fail-open: enforce 不能なら止めない
    now = time.time()
    entries = _load_tail(
        transcript_path, 1
    )  # 現 turn のみ (drop は _active_skills が ts で実施)
    if not entries:
        return  # fail-open
    if _transcript_stale(entries, now, TRANSCRIPT_FRESH_SECONDS):
        return  # fail-open: stale transcript (resume/subagent) cannot prove invoke absence
    active = _active_skills(entries, now, SKILL_WINDOW_SECONDS)
    if active is None:
        return  # fail-open: boundary 不在

    missing = required - active
    if missing:
        _deny_missing(missing)


def cmd_commit_gate(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        return
    command = inp.get("command") or ""
    if not isinstance(command, str):
        return
    commits = _find_commits(command)
    if not commits:
        return
    payload_cwd = payload.get("cwd")
    if not isinstance(payload_cwd, str) or not payload_cwd:
        return
    sid = payload.get("session_id") or ""
    required_by_path: dict[str, set[str]] = {}
    for commit in commits:
        cwd = payload_cwd
        if commit.cwd_override:
            cwd = (
                commit.cwd_override
                if os.path.isabs(commit.cwd_override)
                else os.path.join(cwd, commit.cwd_override)
            )
        if "--" in commit.args:
            pathspecs = list(commit.pathspecs)
            paths, base, expanded = _staged_under(pathspecs, cwd)
            if not expanded:
                _deny_unresolved_pathspec(pathspecs)
                return
        elif commit.amend_like:
            amended = _amend_paths(commit, cwd)
            if amended is None:
                _deny_unresolved_pathspec(["amend target"])
                return
            paths, base = amended
        else:
            continue
        for raw_path in paths:
            path = _canonical(raw_path, base)
            if not path:
                continue
            required = _commit_required_skills(path, sid)
            if required:
                required_by_path.setdefault(path, set()).update(required)
    if not required_by_path:
        return
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return
    entries = _load_tail(transcript_path, 1)
    if not entries:
        return
    # commit は編集から時間が空くため、wall-clock の鮮度窓は規約確認の尺度にしない。
    # transcript の更新遅延だけで allow すると enforcement の穴になるため staleness も使わない。
    active = _active_skills(entries, time.time(), None)
    if active is None:
        return
    # commit の実行主体が同 turn に規約 skill を invoke 済みかを判定し、agent_id では分岐しない。
    missing_by_path = {
        path: required - active
        for path, required in required_by_path.items()
        if required - active
    }
    if missing_by_path:
        _deny_commit_missing(missing_by_path)


def cmd_declare(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(
            "usage: skill_reminder_gate.py declare <ABS-path> <kind>[,<kind>...]\n"
            f"  kind = {_VOCAB}\n"
        )
        return 2
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not sid:
        sys.stderr.write(
            "declare: $CLAUDE_CODE_SESSION_ID が未設定で session を特定できません。\n"
        )
        return 2
    expanded = os.path.expanduser(argv[0])
    if not os.path.isabs(expanded):
        sys.stderr.write(
            "declare: 絶対 path を指定してください。 gate は session cwd で、 declare "
            "は shell cwd で path を解決するため、 相対 path だと cwd drift 時に "
            "hash 不一致で永久に match しません。 後続の Edit/Write と同じ絶対 path "
            "を使ってください。\n"
        )
        return 2
    path = os.path.realpath(expanded)
    kinds = [k.strip() for k in argv[1].split(",") if k.strip()]
    unknown = [k for k in kinds if k not in KIND_SKILLS]
    if not kinds or unknown:
        bad = ", ".join(unknown) if unknown else "(空)"
        sys.stderr.write(f"declare: 未知の kind {bad}。 使える kind = {_VOCAB}。\n")
        return 2
    try:
        os.makedirs(_session_dir(sid), exist_ok=True)
        with open(_decl_path(sid, path), "w", encoding="utf-8") as f:
            f.write(",".join(kinds) + "\n" + path + "\n")
    except OSError as e:
        sys.stderr.write(f"declare: 記録に失敗 ({e}).\n")
        return 1
    _prune_old_sessions()
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    sub = sys.argv[1]
    if sub == "declare":
        try:
            return cmd_declare(sys.argv[2:])
        except Exception as e:
            sys.stderr.write(f"declare: {e}\n")
            return 1
    if sub == "gate":
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            return 0
        try:
            cmd_gate(payload)
        except Exception:
            pass  # fail-open: hook bug が tool を block しない
        return 0
    if sub == "commit-gate":
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            return 0
        try:
            cmd_commit_gate(payload)
        except Exception:
            pass  # fail-open: hook bug が tool を block しない
        return 0
    return 0


class GateTest(unittest.TestCase):
    """emit-vs-comply + branch coverage (lost /tmp smoke, now tracked).
    Run: python3 -m unittest skill_reminder_gate"""

    HOOKDIR = "/x/claude_managed-hooks"

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls._repo_temp = tempfile.TemporaryDirectory()
        cls.REPO = cls._repo_temp.name
        cls._init_repo(cls.REPO, {"README.md": "initial\n"})

    @classmethod
    def tearDownClass(cls):
        cls._repo_temp.cleanup()

    @staticmethod
    def _iso(ep):
        return datetime.datetime.fromtimestamp(ep, datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

    @staticmethod
    def _user(content="do it"):
        return {"type": "user", "message": {"content": content}}

    @classmethod
    def _skill(cls, name, ts=None):
        e = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": {"skill": name}}
                ]
            },
        }
        if ts is not None:
            e["timestamp"] = cls._iso(ts)
        return e

    @classmethod
    def _text(cls, ts):
        return {
            "type": "assistant",
            "timestamp": cls._iso(ts),
            "message": {"content": [{"type": "text", "text": "x"}]},
        }

    @staticmethod
    def _transcript(entries):
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return p

    @staticmethod
    def _declare_quiet(argv):
        import io
        from contextlib import redirect_stderr

        with redirect_stderr(io.StringIO()):
            return cmd_declare(argv)

    def _gate(
        self,
        file_path,
        entries=None,
        sid="s1",
        tool="Edit",
        transcript=True,
        content=None,
    ):
        import io
        from contextlib import redirect_stdout

        payload = {
            "tool_name": tool,
            "tool_input": {"file_path": file_path},
            "cwd": "/tmp",
            "session_id": sid,
        }
        if content is not None:
            payload["tool_input"]["content"] = content
        if transcript:
            payload["transcript_path"] = self._transcript(entries or [])
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_gate(payload)
        out = buf.getvalue().strip()
        return json.loads(out) if out else None

    def _commit_gate(
        self,
        command,
        entries=None,
        transcript=True,
        agent_id=None,
        cwd=None,
    ):
        import io
        from contextlib import redirect_stdout

        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": cwd if cwd is not None else self.REPO,
            "session_id": "s1",
        }
        if transcript:
            payload["transcript_path"] = self._transcript(entries or [])
        if agent_id is not None:
            payload["agent_id"] = agent_id
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_commit_gate(payload)
        out = buf.getvalue().strip()
        return json.loads(out) if out else None

    @staticmethod
    def _init_repo(repo, files):
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        for relative, content in files.items():
            path = os.path.join(repo, relative)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        subprocess.run(["git", "add", "--all"], cwd=repo, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-qm",
                "initial",
            ],
            cwd=repo,
            check=True,
        )

    def _reason(self, result):
        self.assertIsNotNone(result)
        hso = result["hookSpecificOutput"]
        self.assertEqual(hso["permissionDecision"], "deny")
        return hso["permissionDecisionReason"]

    # --- C1: extensioned auto-detect (relevant_skills) ---
    def test_relevant_skills_by_extension(self):
        self.assertEqual(
            relevant_skills("/p/foo.py"), {"writing-code", "writing-python"}
        )
        self.assertEqual(relevant_skills("/p/foo.sh"), {"writing-code", "writing-bash"})
        self.assertEqual(relevant_skills("/p/foo.zsh"), {"writing-code"})  # no add-on
        self.assertEqual(
            relevant_skills("/p/test_foo.py"),
            {"writing-code", "writing-python", "writing-tests"},
        )
        self.assertEqual(
            relevant_skills("/p/foo_test.go"), {"writing-code", "writing-tests"}
        )
        self.assertEqual(relevant_skills("/p/todos.md"), {"writing-todos"})
        self.assertEqual(relevant_skills("/p/SKILL.md"), {"writing-skills"})
        self.assertEqual(relevant_skills("/p/README.md"), set())  # skill-less
        self.assertEqual(
            relevant_skills(self.HOOKDIR + "/g.py"),
            {"writing-skills", "writing-code", "writing-python"},
        )

    def test_relevant_skills_strips_backup_suffix(self):
        self.assertEqual(
            relevant_skills("/p/foo.py.bak"), {"writing-code", "writing-python"}
        )
        self.assertEqual(
            relevant_skills("/p/foo.bash~"), {"writing-code", "writing-bash"}
        )

    # --- C2: shebang kind for extensionless existing files ---
    def test_shebang_kind(self):
        import tempfile

        d = tempfile.mkdtemp()
        cases = {
            "#!/usr/bin/env python3\n": "python",
            "#!/bin/bash\n": "bash",
            "#!/bin/sh\n": "bash",
            "#!/usr/bin/env -S python3 -u\n": "python",
            "#!/usr/bin/perl\n": None,
            "no shebang here\n": None,
            "": None,
        }
        for i, (data, want) in enumerate(cases.items()):
            self.assertEqual(_shebang_kind_text(data), want, repr(data))
            p = os.path.join(d, f"f{i}")
            with open(p, "w", encoding="utf-8") as f:
                f.write(data)
            self.assertEqual(_shebang_kind(p), want, repr(data))
        self.assertIsNone(_shebang_kind(os.path.join(d, "does-not-exist")))
        self.assertIsNone(_shebang_kind_text(None))

    # --- C5: active = current turn AND within 5 min ---
    def test_active_skills_window_and_turn(self):
        now, w = 1_000_000.0, SKILL_WINDOW_SECONDS
        u = self._user()
        self.assertEqual(
            _active_skills([u, self._skill("writing-code", now - 60)], now, w),
            {"writing-code"},
        )
        self.assertEqual(  # same turn but older than window -> dropped
            _active_skills([u, self._skill("writing-code", now - 600)], now, w), set()
        )
        self.assertEqual(  # prior-turn skill excluded (boundary = last user)
            _active_skills(
                [u, self._skill("writing-code", now - 10), self._user()], now, w
            ),
            set(),
        )
        meta = {"type": "user", "isMeta": True, "message": {"content": "expand"}}
        self.assertEqual(  # isMeta is not a turn boundary
            _active_skills([u, self._skill("writing-code", now - 10), meta], now, w),
            {"writing-code"},
        )
        self.assertEqual(  # exactly at window edge -> kept (cutoff is strict <)
            _active_skills([u, self._skill("writing-code", now - w)], now, w),
            {"writing-code"},
        )
        self.assertEqual(  # no timestamp -> not dropped (counts as active)
            _active_skills([u, self._skill("writing-code")], now, w), {"writing-code"}
        )
        self.assertIsNone(  # boundary absent -> fail-open signal
            _active_skills([self._skill("writing-code")], now, w)
        )

    # --- C8: declare CLI round-trip ---
    def test_declare_roundtrip(self):
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        abs_path = os.path.join(d, "runme")
        real = os.path.realpath(abs_path)
        with (
            mock.patch.object(sys.modules[__name__], "STATE_DIR", d),
            mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "t1"}),
        ):
            self.assertEqual(self._declare_quiet([abs_path, "python"]), 0)
            self.assertEqual(_declared_kinds("t1", real), ["python"])
            self.assertEqual(self._declare_quiet([abs_path, "else"]), 0)  # overwrite
            self.assertEqual(_declared_kinds("t1", real), ["else"])
            self.assertEqual(
                self._declare_quiet([abs_path, "frobnicate"]), 2
            )  # unknown
            self.assertEqual(self._declare_quiet(["rel/path", "python"]), 2)  # relative
            self.assertEqual(self._declare_quiet([abs_path, ""]), 2)  # empty kind
            self.assertEqual(self._declare_quiet([]), 2)  # too few args
        with (
            mock.patch.object(sys.modules[__name__], "STATE_DIR", d),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(self._declare_quiet([abs_path, "python"]), 2)  # no sid

    # --- C7/C6: cmd_gate emit-vs-comply ---
    def test_gate_denies_code_file_without_skill(self):
        r = self._reason(self._gate("/tmp/foo.py", entries=[self._user()]))
        self.assertIn("writing-code", r)
        self.assertIn("writing-python", r)

    def test_gate_allows_subagent_without_skill(self):
        # Fresh transcript w/ boundary but no skill invoke -> would DENY without agent_id skip.
        self.assertEqual(
            self._raw(
                {
                    "agent_id": "agent-1",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/tmp/foo.py"},
                    "cwd": "/tmp",
                    "session_id": "s1",
                    "transcript_path": self._transcript(
                        [self._user(), self._text(time.time())]
                    ),
                }
            ),
            "",
        )

    def test_gate_denies_same_fresh_payload_without_agent_id(self):
        result = self._raw(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/tmp/foo.py"},
                "cwd": "/tmp",
                "session_id": "s1",
                "transcript_path": self._transcript(
                    [self._user(), self._text(time.time())]
                ),
            }
        )
        self.assertNotEqual(result, "")
        self._reason(json.loads(result))

    def test_gate_allows_code_file_with_skills_active(self):
        self.assertIsNone(
            self._gate(
                "/tmp/foo.py",
                entries=[
                    self._user(),
                    self._skill("writing-code"),
                    self._skill("writing-python"),
                ],
            )
        )

    def test_gate_allows_skill_less_file(self):
        self.assertIsNone(self._gate("/tmp/README.md", entries=[self._user()]))
        self.assertIsNone(self._gate("/tmp/README.md", transcript=False))  # unread

    def test_gate_denies_extensionless_undeclared(self):
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "newcmd")  # nonexistent -> no shebang
        self.assertIn("declare", self._reason(self._gate(p, entries=[self._user()])))

    def test_gate_declare_else_cannot_bypass_extensioned(self):
        # C3: declare is additive; "else" on a .py cannot drop below auto-detect.
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        py = os.path.join(d, "foo.py")
        with (
            mock.patch.object(sys.modules[__name__], "STATE_DIR", d),
            mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}),
        ):
            self.assertEqual(self._declare_quiet([py, "else"]), 0)
            r = self._reason(self._gate(py, entries=[self._user()], sid="s1"))
        self.assertIn("writing-code", r)

    def test_gate_extensionless_declared_else_allows(self):
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        cmdfile = os.path.join(d, "runme")
        with (
            mock.patch.object(sys.modules[__name__], "STATE_DIR", d),
            mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}),
        ):
            self.assertEqual(self._declare_quiet([cmdfile, "else"]), 0)
            self.assertIsNone(self._gate(cmdfile, entries=[self._user()], sid="s1"))

    def test_gate_failopen(self):
        self.assertIsNone(self._gate("/tmp/foo.py", tool="Read"))  # non-gate tool
        self.assertIsNone(  # no transcript -> enforce 不能で素通り
            self._gate("/tmp/foo.py", entries=[self._user()], transcript=False)
        )
        self.assertIsNone(  # boundary absent -> fail-open
            self._gate("/tmp/foo.py", entries=[self._skill("writing-code")])
        )
        self.assertIsNone(self._gate("/tmp/foo.py", entries=[]))  # empty transcript
        self.assertEqual(self._raw("nope"), "")  # non-dict payload
        self.assertEqual(  # non-dict tool_input
            self._raw({"tool_name": "Edit", "tool_input": None}), ""
        )
        self.assertEqual(  # empty file_path
            self._raw({"tool_name": "Edit", "tool_input": {"file_path": ""}}), ""
        )

    @staticmethod
    def _raw(payload):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_gate(payload)
        return buf.getvalue().strip()

    def test_gate_denies_when_skill_too_old(self):
        # C5 end-to-end: same-turn invoke older than 5 min is dropped -> deny.
        old = time.time() - SKILL_WINDOW_SECONDS - 60
        r = self._reason(
            self._gate(
                "/tmp/foo.py",
                entries=[
                    self._user(),
                    self._skill("writing-code", old),
                    self._skill("writing-python", old),
                    self._text(
                        time.time()
                    ),  # fresh anchor: transcript itself is current
                ],
            )
        )
        self.assertIn("writing-code", r)

    def test_transcript_stale(self):
        now, f = 1_000_000.0, TRANSCRIPT_FRESH_SECONDS
        self.assertFalse(_transcript_stale([self._user(), self._text(now - 5)], now, f))
        self.assertTrue(
            _transcript_stale([self._user(), self._text(now - f - 1)], now, f)
        )
        self.assertFalse(
            _transcript_stale([self._user()], now, f)
        )  # no ts: undecidable

    def test_gate_failopen_on_stale_transcript(self):
        # Stale transcript (resume/subagent) proves nothing -> allow, never deny.
        old = 1_000_000  # epoch far before real time.time()
        self.assertIsNone(
            self._gate("/tmp/foo.py", entries=[self._user(), self._text(old)])
        )

    def test_gate_shebang_extensionless(self):
        # C2 end-to-end: undeclared extensionless file, kind from shebang.
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "runme")
        with open(p, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env python3\n")
        self.assertIn(
            "writing-python", self._reason(self._gate(p, entries=[self._user()]))
        )
        self.assertIsNone(  # both required skills active -> allow
            self._gate(
                p,
                entries=[
                    self._user(),
                    self._skill("writing-code"),
                    self._skill("writing-python"),
                ],
            )
        )

    def test_gate_write_shebang_from_content(self):
        # C2-W: Write は全置換ゆえ新 content の 1 行目 shebang が真実源 (disk より優先)。
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "newtool")  # not on disk yet
        bash = "#!/bin/bash\necho hi\n"
        r = self._reason(
            self._gate(p, entries=[self._user()], tool="Write", content=bash)
        )
        self.assertIn("writing-bash", r)
        self.assertIsNone(  # required skills active -> allow
            self._gate(
                p,
                entries=[
                    self._user(),
                    self._skill("writing-code"),
                    self._skill("writing-bash"),
                ],
                tool="Write",
                content=bash,
            )
        )
        with open(p, "w", encoding="utf-8") as f:  # disk says python; content wins
            f.write("#!/usr/bin/env python3\n")
        self.assertIn(
            "writing-bash",
            self._reason(
                self._gate(p, entries=[self._user()], tool="Write", content=bash)
            ),
        )
        self.assertIn(  # shebang-less content -> declare deny (unchanged path)
            "declare",
            self._reason(
                self._gate(p, entries=[self._user()], tool="Write", content="plain\n")
            ),
        )

    def test_gate_declared_kinds(self):
        # C3: extensionless uses declared kinds only; extensioned unions with auto-detect.
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        cmdfile = os.path.join(d, "runme")
        py = os.path.join(d, "mod.py")
        with (
            mock.patch.object(sys.modules[__name__], "STATE_DIR", d),
            mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}),
        ):
            self.assertEqual(self._declare_quiet([cmdfile, "python"]), 0)
            self.assertIn(  # extensionless declared python -> needs code+python
                "writing-python",
                self._reason(self._gate(cmdfile, entries=[self._user()], sid="s1")),
            )
            self.assertIsNone(
                self._gate(
                    cmdfile,
                    entries=[
                        self._user(),
                        self._skill("writing-code"),
                        self._skill("writing-python"),
                    ],
                    sid="s1",
                )
            )
            self.assertEqual(self._declare_quiet([py, "test"]), 0)
            self.assertIn(  # .py auto-detect {code,python} ∪ declared test -> +tests
                "writing-tests",
                self._reason(
                    self._gate(
                        py,
                        entries=[
                            self._user(),
                            self._skill("writing-code"),
                            self._skill("writing-python"),
                        ],
                        sid="s1",
                    )
                ),
            )

    def test_gate_session_isolation(self):
        # declared state is keyed by session_id; another session does not inherit it.
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        cmdfile = os.path.join(d, "runme")
        with (
            mock.patch.object(sys.modules[__name__], "STATE_DIR", d),
            mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}),
        ):
            self.assertEqual(self._declare_quiet([cmdfile, "else"]), 0)
            self.assertIsNone(self._gate(cmdfile, entries=[self._user()], sid="s1"))
            self.assertIn(  # sid s2 has no declaration -> falls to declare-deny
                "declare",
                self._reason(self._gate(cmdfile, entries=[self._user()], sid="s2")),
            )

    def test_main_failopen_on_exception(self):
        # 全例外を握り潰し exit 0 (fail-open): _load_tail raising must not deny.
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/tmp/foo.py"},
                "cwd": "/tmp",
                "session_id": "s1",
                "transcript_path": "/x",
            }
        )
        buf = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", io.StringIO(payload)),
            mock.patch.object(sys, "argv", ["x", "gate"]),
            mock.patch.object(
                sys.modules[__name__], "_load_tail", side_effect=RuntimeError("boom")
            ),
            redirect_stdout(buf),
        ):
            rc = main()
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "")  # no deny emitted

    def test_is_turn_boundary(self):
        self.assertTrue(
            _is_turn_boundary({"type": "user", "message": {"content": "hi"}})
        )
        self.assertFalse(  # isMeta (skill expansion) is not a boundary
            _is_turn_boundary(
                {"type": "user", "isMeta": True, "message": {"content": "x"}}
            )
        )
        self.assertFalse(_is_turn_boundary({"type": "assistant", "message": {}}))
        self.assertFalse(  # list of only tool_result -> continuation
            _is_turn_boundary(
                {"type": "user", "message": {"content": [{"type": "tool_result"}]}}
            )
        )
        self.assertTrue(  # list with a non-tool_result block -> boundary
            _is_turn_boundary(
                {
                    "type": "user",
                    "message": {"content": [{"type": "tool_result"}, {"type": "text"}]},
                }
            )
        )
        self.assertFalse(_is_turn_boundary({"type": "user", "message": {}}))

    def test_parse_ts(self):
        self.assertIsNotNone(_parse_ts("2026-06-02T04:45:24.945Z"))
        for bad in (None, "", "not-a-date", 123):
            self.assertIsNone(_parse_ts(bad))

    # --- commit-gate: commit path requirements ---
    def test_commit_gate_explicit_path_allows_active_and_denies_missing(self):
        command = "git commit -m change -- foo.py"
        active = [
            self._user(),
            self._skill("writing-code"),
            self._skill("writing-python"),
        ]
        self.assertIsNone(self._commit_gate(command, entries=active))
        reason = self._reason(self._commit_gate(command, entries=[self._user()]))
        self.assertIn(self.REPO + "/foo.py", reason)
        self.assertIn("writing-code", reason)
        self.assertIn("writing-python", reason)
        self.assertIn("skill を invoke してから commit", reason)
        self.assertIn("subagent や codex", reason)
        self.assertIn("commit を実行する主体自身", reason)
        self.assertNotIn("発注側", reason)
        self.assertIn("hook 自身は file を変更しません", reason)

    def test_commit_gate_allows_skill_less_path(self):
        self.assertIsNone(
            self._commit_gate(
                "git commit -m notes -- notes.txt", entries=[self._user()]
            )
        )

    def test_commit_gate_allows_non_commit_command(self):
        for command in ("git status", "grep 'git commit' foo.md"):
            with self.subTest(command=command):
                self.assertIsNone(self._commit_gate(command, transcript=False))

    def test_commit_gate_checks_payload_with_agent_id(self):
        result = self._commit_gate(
            "git commit -m change -- foo.py",
            entries=[self._user(), self._text(time.time())],
            agent_id="agent-1",
        )
        self.assertIn("writing-python", self._reason(result))

    def test_commit_gate_amend_uses_staged_paths(self):
        from unittest import mock

        root = subprocess.CompletedProcess(
            ["git", "rev-parse", "--show-toplevel"], 0, self.REPO + "\n", ""
        )
        staged = subprocess.CompletedProcess(
            ["git", "diff", "--cached", "--name-only", "-z"], 0, "foo.py\0", ""
        )
        previous = subprocess.CompletedProcess([], 0, "README.md\0", "")
        with mock.patch.object(
            subprocess, "run", side_effect=[root, staged, previous]
        ) as run_mock:
            result = self._commit_gate(
                "git commit --amend --no-edit", entries=[self._user()]
            )
        self.assertIn("writing-python", self._reason(result))
        self.assertEqual(run_mock.call_count, 3)
        run_mock.assert_has_calls(
            [
                mock.call(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=self.REPO,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ),
                mock.call(
                    ["git", "diff", "--cached", "--name-only", "-z"],
                    cwd=self.REPO,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ),
                mock.call(
                    ["git", "show", "--pretty=", "--name-only", "-z", "HEAD"],
                    cwd=self.REPO,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ),
            ]
        )

    def test_commit_gate_amend_always_includes_head_paths(self):
        from unittest import mock

        root = subprocess.CompletedProcess([], 0, self.REPO + "\n", "")
        staged = subprocess.CompletedProcess([], 0, "", "")
        previous = subprocess.CompletedProcess([], 0, "foo.py\0", "")
        with mock.patch.object(
            subprocess, "run", side_effect=[root, staged, previous]
        ) as run_mock:
            result = self._commit_gate(
                "git commit --fixup HEAD", entries=[self._user()]
            )
        self.assertIn("writing-python", self._reason(result))
        self.assertEqual(run_mock.call_count, 3)

    def test_commit_gate_subprocess_failure_is_fail_closed(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        stderr = io.StringIO()
        failure = subprocess.CalledProcessError(1, ["git", "diff"])
        with (
            mock.patch.object(subprocess, "run", side_effect=failure),
            redirect_stderr(stderr),
        ):
            result = self._commit_gate(
                "git commit --squash HEAD", entries=[self._user()]
            )
        self.assertIn("file kind", self._reason(result))
        self.assertIn("deny", stderr.getvalue())

    def test_commit_gate_git_c_global_option_denies(self):
        result = self._commit_gate(
            f"git -C {self.REPO} commit -m change -- foo.py",
            entries=[self._user()],
            cwd="/tmp",
        )
        reason = self._reason(result)
        self.assertIn("writing-python", reason)
        self.assertIn(self.REPO + "/foo.py", reason)

    def test_commit_gate_other_global_options_deny(self):
        commands = (
            "git --no-pager commit -m change -- foo.py",
            "git -c core.pager=cat commit -m change -- foo.py",
        )
        for command in commands:
            with self.subTest(command=command):
                result = self._commit_gate(command, entries=[self._user()])
                self.assertIn("writing-python", self._reason(result))

    def test_commit_gate_directory_pathspec_expands_staged_files(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as repo:
            hook_dir = os.path.join(repo, "claude_managed-hooks")
            os.makedirs(hook_dir)
            path = os.path.join(hook_dir, "guard.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write("pass\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "add", "claude_managed-hooks/guard.py"],
                cwd=repo,
                check=True,
            )
            with mock.patch.object(subprocess, "run", wraps=subprocess.run) as run_mock:
                result = self._commit_gate(
                    "git commit -m change -- claude_managed-hooks",
                    entries=[self._user()],
                    cwd=repo,
                )
            for call in run_mock.call_args_list:
                self.assertEqual(call.kwargs.get("timeout"), 5)
        reason = self._reason(result)
        self.assertIn("guard.py", reason)
        self.assertIn("writing-skills", reason)

    def test_commit_gate_ignores_git_commit_in_heredoc_body(self):
        command = "cat > howto.md <<'EOF'\ngit commit -m msg -- foo.py\nEOF"
        self.assertIsNone(self._commit_gate(command, entries=[self._user()]))
        self.assertIsNone(
            self._commit_gate(
                "git commit -m docs -- notes.txt && echo foo.py",
                entries=[self._user()],
            )
        )

    def test_commit_gate_worktree_only_directory_pathspec_denies(self):
        import tempfile

        with tempfile.TemporaryDirectory() as repo:
            relative = "claude_managed-hooks/guard.py"
            self._init_repo(repo, {relative: "pass\n"})
            with open(os.path.join(repo, relative), "a", encoding="utf-8") as f:
                f.write("changed = True\n")
            result = self._commit_gate(
                "git commit -m change -- claude_managed-hooks",
                entries=[self._user()],
                cwd=repo,
            )
        self.assertIn("writing-skills", self._reason(result))

    def test_commit_gate_partially_staged_directory_pathspec_denies(self):
        import tempfile

        with tempfile.TemporaryDirectory() as repo:
            hook = "claude_managed-hooks/guard.py"
            note = "claude_managed-hooks/notes.txt"
            self._init_repo(repo, {hook: "pass\n", note: "old\n"})
            with open(os.path.join(repo, hook), "a", encoding="utf-8") as f:
                f.write("changed = True\n")
            with open(os.path.join(repo, note), "a", encoding="utf-8") as f:
                f.write("staged\n")
            subprocess.run(["git", "add", note], cwd=repo, check=True)
            result = self._commit_gate(
                "git commit -m change -- claude_managed-hooks",
                entries=[self._user()],
                cwd=repo,
            )
        self.assertIn("writing-skills", self._reason(result))

    def test_commit_gate_quoted_commit_token_is_out_of_scope(self):
        commands = (
            "git 'commit' -m change -- foo.py",
            'git "commit" -m change -- foo.py',
            "git com'mit' -m change -- foo.py",
            "git \\commit -m change -- foo.py",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(self._commit_gate(command, entries=[self._user()]))

    def test_commit_gate_comment_apostrophe_keeps_deny(self):
        for comment in ("Bob's request", "don't"):
            command = f"git commit -m change -- foo.py # {comment}"
            with self.subTest(command=command):
                result = self._commit_gate(command, entries=[self._user()])
                self.assertIn("writing-python", self._reason(result))

    def test_commit_gate_checks_every_commit_line(self):
        result = self._commit_gate(
            "git commit -m docs -- notes.txt\ngit commit -m code -- foo.py",
            entries=[self._user()],
        )
        self.assertIn("writing-python", self._reason(result))

        result = self._commit_gate(
            "git commit -m code -- foo.py\ngit commit -m policy -- SKILL.md",
            entries=[
                self._user(),
                self._skill("writing-code"),
                self._skill("writing-python"),
            ],
        )
        self.assertIn("writing-skills", self._reason(result))

    def test_commit_gate_skips_leading_comment_lines(self):
        comment = "# git commit -m decoy -- foo.py"
        self.assertIsNone(self._commit_gate(comment, entries=[self._user()]))
        result = self._commit_gate(
            f"{comment}\ngit commit -m code -- SKILL.md",
            entries=[self._user()],
        )
        reason = self._reason(result)
        self.assertIn("writing-skills", reason)
        self.assertNotIn("foo.py", reason)

    def test_commit_gate_unbalanced_pathless_command_does_not_blanket_deny(self):
        self.assertIsNone(
            self._commit_gate("git commit -m 'broken", entries=[self._user()])
        )

    def test_commit_gate_strips_line_prefix_wrappers(self):
        commands = (
            "timeout 5 git commit -m change -- foo.py",
            "xargs git commit -m change -- foo.py",
            "(git commit -m change -- foo.py)",
            "GIT_EDITOR=true git commit -m change -- foo.py",
            "env FOO=1 git commit -m change -- foo.py",
        )
        for command in commands:
            with self.subTest(command=command):
                result = self._commit_gate(command, entries=[self._user()])
                self.assertIn("writing-python", self._reason(result))

    def test_commit_gate_documents_unsupported_indirection(self):
        commands = (
            "bash -c 'git commit -m nested -- foo.py'",
            'G="git"; $G commit -m variable -- foo.py',
            "git $(echo commit) -m expanded -- foo.py",
            "git -c alias.ci=commit ci -m alias -- foo.py",
            'python3 -c \'subprocess.run(["git", "commit"])\'',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(self._commit_gate(command, entries=[self._user()]))

    def test_commit_gate_extensionless_shebang_and_plain_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as repo:
            script = "files/run_python"
            plain = "files/plain_data"
            self._init_repo(
                repo,
                {script: "#!/usr/bin/env python3\n", plain: "plain\n"},
            )
            for relative in (script, plain):
                with open(os.path.join(repo, relative), "a", encoding="utf-8") as f:
                    f.write("changed\n")
                subprocess.run(["git", "add", relative], cwd=repo, check=True)
            denied = self._commit_gate(
                f"git commit -m change -- {script}",
                entries=[self._user()],
                cwd=repo,
            )
            allowed = self._commit_gate(
                f"git commit -m change -- {plain}",
                entries=[self._user()],
                cwd=repo,
            )
        self.assertIn("writing-python", self._reason(denied))
        self.assertIsNone(allowed)

    def test_commit_gate_amend_all_with_partial_stage_checks_worktree(self):
        import tempfile

        with tempfile.TemporaryDirectory() as repo:
            self._init_repo(repo, {"doc.md": "old\n", "files/foo.py": "old = 1\n"})
            with open(os.path.join(repo, "doc.md"), "a", encoding="utf-8") as f:
                f.write("staged\n")
            with open(os.path.join(repo, "files/foo.py"), "a", encoding="utf-8") as f:
                f.write("new = 2\n")
            subprocess.run(["git", "add", "doc.md"], cwd=repo, check=True)
            result = self._commit_gate(
                "git commit -a --amend --no-edit",
                entries=[self._user()],
                cwd=repo,
            )
        self.assertIn("writing-python", self._reason(result))

    def test_commit_gate_non_ascii_paths_use_nul_output(self):
        import tempfile

        with tempfile.TemporaryDirectory() as repo:
            relative = "files/日本語.py"
            self._init_repo(repo, {relative: "old = 1\n"})
            with open(os.path.join(repo, relative), "a", encoding="utf-8") as f:
                f.write("new = 2\n")
            subprocess.run(["git", "add", relative], cwd=repo, check=True)
            for pathspec in ("files", relative):
                with self.subTest(pathspec=pathspec):
                    result = self._commit_gate(
                        f"git commit -m change -- {pathspec}",
                        entries=[self._user()],
                        cwd=repo,
                    )
                    self.assertIn("日本語.py", self._reason(result))

    def test_commit_gate_checks_transcript_older_than_freshness_limit(self):
        result = self._commit_gate(
            "git commit -m change -- foo.py",
            entries=[self._user(), self._text(time.time() - 130)],
        )
        self.assertIn("writing-python", self._reason(result))

    def test_commit_gate_checks_stale_transcript_with_agent_id(self):
        # transcript の staleness と agent_id のどちらでも早期 return しない。
        result = self._commit_gate(
            "git commit -m change -- foo.py",
            entries=[self._user(), self._text(time.time() - 720)],
            agent_id="agent-1",
        )
        self.assertIn("writing-python", self._reason(result))

    def test_commit_gate_accepts_skill_from_earlier_in_same_turn(self):
        old = time.time() - 400
        self.assertIsNone(
            self._commit_gate(
                "git commit -m change -- foo.py",
                entries=[
                    self._user(),
                    self._skill("writing-code", old),
                    self._skill("writing-python", old),
                    self._text(time.time()),
                ],
            )
        )

    def test_commit_gate_declare_else_cannot_bypass_extensioned(self):
        import tempfile
        from unittest import mock

        state = tempfile.mkdtemp()
        path = self.REPO + "/generated.py"
        with (
            mock.patch.object(sys.modules[__name__], "STATE_DIR", state),
            mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}),
        ):
            self.assertEqual(self._declare_quiet([path, "else"]), 0)
            reason = self._reason(
                self._commit_gate(
                    "git commit -m change -- generated.py", entries=[self._user()]
                )
            )
        self.assertIn("writing-python", reason)

    def test_commit_gate_declared_else_allows_extensionless(self):
        import tempfile
        from unittest import mock

        with (
            tempfile.TemporaryDirectory() as repo,
            tempfile.TemporaryDirectory() as state,
        ):
            relative = "files/run_python"
            path = os.path.join(repo, relative)
            self._init_repo(repo, {relative: "#!/usr/bin/env python3\n"})
            with open(path, "a", encoding="utf-8") as f:
                f.write("changed\n")
            subprocess.run(["git", "add", relative], cwd=repo, check=True)
            with (
                mock.patch.object(sys.modules[__name__], "STATE_DIR", state),
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s1"}),
            ):
                before = self._commit_gate(
                    f"git commit -m change -- {relative}",
                    entries=[self._user()],
                    cwd=repo,
                )
                self.assertEqual(self._declare_quiet([path, "else"]), 0)
                after = self._commit_gate(
                    f"git commit -m change -- {relative}",
                    entries=[self._user()],
                    cwd=repo,
                )
        self.assertIn("writing-python", self._reason(before))
        self.assertIsNone(after)

    def test_commit_gate_denies_unresolved_extensionless_pathspec(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        stderr = io.StringIO()
        failure = subprocess.CalledProcessError(128, ["git", "rev-parse"])
        with (
            mock.patch.object(subprocess, "run", side_effect=failure),
            redirect_stderr(stderr),
        ):
            result = self._commit_gate(
                "git commit -m change -- claude_managed-hooks",
                entries=[self._user()],
            )
        reason = self._reason(result)
        self.assertIn("pathspec", reason)
        self.assertIn("file kind", reason)
        self.assertIn("commit 対象を明示", reason)

    def test_commit_gate_denies_any_unresolved_pathspec(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        failure = subprocess.CalledProcessError(128, ["git", "rev-parse"])
        with (
            mock.patch.object(subprocess, "run", side_effect=failure),
            redirect_stderr(io.StringIO()),
        ):
            result = self._commit_gate(
                "git commit -m change -- foo.py", entries=[self._user()]
            )
        self.assertIn("foo.py", self._reason(result))

    def test_commit_gate_missing_or_non_string_cwd_does_not_use_process_cwd(self):
        import io
        from contextlib import redirect_stdout

        for cwd in (None, 123):
            payload = {
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -m change -- foo.py"},
                "cwd": cwd,
                "transcript_path": self._transcript([self._user()]),
            }
            output = io.StringIO()
            with redirect_stdout(output):
                cmd_commit_gate(payload)
            self.assertEqual(output.getvalue(), "")

    def test_commit_gate_timeout_is_fail_closed(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        stderr = io.StringIO()
        failure = subprocess.TimeoutExpired(["git", "diff"], 5)
        with (
            mock.patch.object(subprocess, "run", side_effect=failure),
            redirect_stderr(stderr),
        ):
            result = self._commit_gate(
                "git commit --amend --no-edit", entries=[self._user()]
            )
        self.assertIn("file kind", self._reason(result))
        self.assertIn("deny", stderr.getvalue())


if __name__ == "__main__":
    sys.exit(main())
