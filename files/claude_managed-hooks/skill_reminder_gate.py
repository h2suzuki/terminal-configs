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
2 mode (argv[1] で dispatch):

  gate    PreToolUse(^(Edit|Write|MultiEdit)$) hook。下記 flow で allow/deny。
  declare model が Bash で実行する CLI:
            skill_reminder_gate.py declare <ABS-path> <kind>[,<kind>...]
          拡張子なし file の kind 真実源を session state に記録。sid は env
          $CLAUDE_CODE_SESSION_ID (== payload session_id) から取る。path は
          **絶対 path 必須** — gate は payload.cwd、 declare は shell cwd で
          解決するため、 相対だと cwd drift 時に hash 不一致で永久 deny loop。
          同じ絶対 path を後続 Edit でも使う。

gate flow:
  declared(sid, path) あり:
      拡張子あり → required = relevant_skills(path) ∪ ∪(宣言 kind の skill)
                   (declare は **追加のみ**。 auto-detect を下回れない —
                    .py を else 宣言で gating 無効化する穴を塞ぐ)
      拡張子なし → required = ∪(宣言 kind の skill)  (declare が唯一の真実源)
  elif 拡張子あり → required = relevant_skills(path)
  else (拡張子なし・未宣言) → DENY「絶対 path で kind を declare せよ」; return
  required が空            → ALLOW (skill-less file。transcript 非読込)
  active = 現 turn かつ直近 5 分以内の Skill invoke 集合 (現 turn を後方 1 つ読み ts で drop)
  active 判定不能 (corrupted) → ALLOW (fail-open)
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

skill-active 窓 (現 turn かつ直近 SKILL_WINDOW_SECONDS=5 分以内) の根拠
================================================================
現 turn を後方 1 つだけ読み (_load_tail、boundary は positional ゆえ ts 単調性に
非依存で sound)、その中で直近 5 分以内に invoke された skill のみ active とみなす
(5 分以上前は drop)。5 分は長い作業中の再 invoke friction 抑制と、無関係に古い
invoke が通るリスク回避の折衷。現 turn のみ読むため cross-turn の recency は無い。

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

residual (閉じない・既知)
=========================
- 拡張子なし file の kind 語彙選択は model 判断 (bash を else 誤宣言ですり抜け)。
  detour deny で declare は強制できるが語彙は model が選ぶ。
- 未収載の exotic 言語拡張子 (CODE_EXTENSIONS 外) は skill-less 扱い。
- .j2/.in/.tmpl 等 templating 拡張子は config 多数ゆえ skill-less 許容 (.bak/
  .orig/.swp/~ の backup/swap は元拡張子を復元して gate)。
- symlink: _canonical の realpath が skill/hook-dir segment を解決し分類が変わり
  得る (現 deploy の symlink は分類保存、 SKILL.md は basename 判定で不変 = 現状
  未発火。latent)。

canonical source: files/claude_managed-hooks/skill_reminder_gate.py
deploy: /etc/claude-code/hooks/ (copy_dir で自動)。両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "hooks", "state", "skill_reminder")
DECL_STALE_SECONDS = 7 * 24 * 3600  # 放置宣言 session dir の自己掃除閾値
SKILL_WINDOW_SECONDS = 300  # skill-active 窓 (現 turn ∪ 直近 5 分。H.S. 指定)
GATE_TOOLS = ("Edit", "Write", "MultiEdit")

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


def _active_skills(entries: list[dict], now: float, window_s: int) -> set[str] | None:
    """invoke 済 skill 集合 = 現 turn のうち直近 window_s 秒以内 (それより前は drop)。boundary 不在は None (fail-open)。"""
    start_idx = -1
    for i in range(len(entries) - 1, -1, -1):
        if _is_turn_boundary(entries[i]):
            start_idx = i + 1
            break
    if start_idx == -1:
        return None

    cutoff = now - window_s
    active: set[str] = set()
    for idx, obj in enumerate(entries):
        if obj.get("type") != "assistant":
            continue
        if idx < start_idx:
            continue  # 現 turn 外
        ep = _parse_ts(obj.get("timestamp"))
        if ep is not None and ep < cutoff:
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


# --- modes ---


def cmd_gate(payload: dict) -> None:
    if not isinstance(payload, dict):
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
        declared_skills: set[str] = set()
        for k in declared:
            declared_skills |= KIND_SKILLS.get(k, set())
        # 拡張子あり: declare は追加のみ (auto-detect を下回れない)。なし: declare が唯一源。
        if _has_extension(path):
            required = relevant_skills(path) | declared_skills
        else:
            required = declared_skills
    elif _has_extension(path):
        required = relevant_skills(path)
    else:
        _deny_declare(os.path.basename(path))
        return

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
    active = _active_skills(entries, now, SKILL_WINDOW_SECONDS)
    if active is None:
        return  # fail-open: boundary 不在

    missing = required - active
    if missing:
        _deny_missing(missing)


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
