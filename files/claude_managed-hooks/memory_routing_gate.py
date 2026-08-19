#!/usr/bin/env python3
r"""
Memory-entry write enforcement hook for Claude Code.

Purpose
=======
memory entry (共有 clone /var/lib/claude-rag-memory/claude-lessons-learned 配下の
org/*.md, user/<login>/*.md, project/<enc>/*.md) への書込を /memory-routing
skill 経由に強制する決定論的 gate。retrieval 層 (memory_surface.py の
reminder/keywords surface) の上に乗る hard 層で、skill 非発火でも format /
keyword 品質 / DB 同期 / git commit+push を担保する。旧 location
(~/.claude/memory, ~/.claude/projects/<enc>/memory) への書込は clone への
redirect deny、clone 不在/破損時は閉塞 deny (installer 再実行が復旧手順)。

なぜ skill 強制か: /memory-routing は routing 判断・正書式 (reminder:/keywords:)・
FTS DB 同期 (--upsert) を 1 単位で行う。直接 Write はこれらを欠く。本 hook は
「skill を通ったか」を gate にし、通らなければ deny する。

検出機構: capability grant (skill が mint・hook が consume)
==========================================================
turn 概念 / 時刻 window / turn_counter には依存しない。/memory-routing が entry P
の Write 直前に grant ~/.claude/hooks/state/memory-routing/grants/<basename(P)>
を mint し、本 hook はその存在 (+ 鮮度) を skill 経由の証跡とする。

  - 1 turn 複数 entry: entry ごとに固有 grant → 各 Write が独立に通る。
  - 乱数不要: grant 名を対象 path の basename に束ねる (LLM が Bash 無しで組める)。
  - grant を作らないほど従わない LLM は本文も不備 → 内容 check で捕捉 (二重の網)。

grant content には P の絶対パスを書く (audit 用)。判定は basename 一致 + 鮮度。

処理 flow (PreToolUse: guard / PostToolUse: sync)
=================================================
PreToolUse `^(Edit|Write|MultiEdit)$` → guard:
  対象外 (memory entry でない / index file MEMORY.md・OLD-MEMORY.md) → 素通り。
  opt-out: 対象 content に `memory-guard: allow` を含む → 素通り。
  Edit / MultiEdit on entry:
    → 無条件 deny。差分編集は最終 format を gate できず、skill 経由に一本化する
      ため。「/memory-routing 経由で full content を Write」へ誘導。
  Write on entry:
    1. grant 不在 (or 鮮度切れ) → deny「/memory-routing を使え」。
    2. 内容不備 (下記) → deny (具体的是正指示)。grant は残す (直して再 Write が
       そのまま通る = 一発 Write の趣旨)。warn は出さない (Edit を塞いだ以上、
       warn は「直す→Edit→denied」の詰みになるため、受理できる内容まで deny)。
    3. 両方 OK → allow (silent) + grant を consume (削除)。

  内容不備の判定 (memory_surface._parse_entry / _build_query と同契約):
    - content が MAX_ENTRY_SIZE 超 → memory_surface が index しない。
    - basename が feedback_ / reference_ で始まらない (type 体系外)。
    - `oneline_summary:` (廃止形式) を含む。
    - frontmatter に非空の `reminder:` 行が無い (^reminder:[ \t]*(.+)$ MULTILINE)。
    - frontmatter に非空の `keywords:` 行が無い。
    - keywords が FTS token を 1 つも産まない / 一般語 (STOPWORDS) のみ = 無効/広すぎ。
    - frontmatter に非空の `models:` 行が無い / tag 書式不正 (観測 model の tag、例 fable-5)。
    - feedback: h2 が Why/How/事例/Related の固定語彙・固定順・各 1 回でない、
      または ## Why / ## 事例 が無い (## How / ## Related は任意。自由見出しは h3)。
    - 本文に絶対日付 (YYYY-MM-DD) が 1 つも無い。
  旧形式 (3 field が本文先頭) の既存 entry は再 Write する機会に新書式へ引き上げる。

PostToolUse `^Write$` → sync:
  entry の Write 成功後に claude_memory_sync --commit <abspath> を呼び、
  index upsert (scope は path から CLI が導出) + git commit + detached push
  を self-heal する (skill の同期漏れ保険)。

deny 方式・fail-open
====================
deny は JSON `permissionDecision: "deny"` (exit 0) — read_before_edit.py と同じく
hook bug が誤って tool を block しないため (deny は exit code でなく JSON で伝える)。guard/sync とも全例外を
握り潰し exit 0 (fail-open): hook 不具合が prompt/turn を壊さない。sync は
PostToolUse ゆえそもそも block 不能。

canonical source: files/claude_managed-hooks/memory_routing_gate.py
deploy: /etc/claude-code/hooks/  両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "hooks", "state")
GRANTS_DIR = os.path.join(STATE_DIR, "memory-routing", "grants")
MEMORY_REPO_DIR = "/var/lib/claude-rag-memory/claude-lessons-learned"
SYNC_CLI = "/usr/local/bin/claude_memory_sync"
# Legacy pre-clone locations: writes there get a redirect deny.
LEGACY_USER_MEM_DIR = os.path.join(HOME, ".claude", "memory")
_LEGACY_PROJ_MEM_RE = re.compile(r".*/\.claude/projects/([^/]+)/memory/[^/]+\.md$")

MAX_ENTRY_SIZE = 50_000  # memory_surface._parse_entry と一致
GRANT_STALE_SECONDS = 3600  # 放置 grant を無効化 + 掃除する閾値
SYNC_TIMEOUT_SECONDS = 20  # index upsert + local git commit (push は detached)
INDEX_NAMES = {"MEMORY.md", "OLD-MEMORY.md", "README.md"}
OPT_OUT = "memory-guard: allow"

# memory_surface._build_query と同じトークナイザ (CJK 3+, ASCII 4+)
_CJK_RE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]{3,}")
_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")

ENTRY_PREFIXES = ("feedback_", "reference_")  # 行動是正の教訓 / 外部仕様の調査 snapshot
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# 一般語 (=match に効かず context を flood する語; CJK 3+/ASCII 4+ のみ列挙) を deny する閾値判定用。保守的に
# 「これらだけ」弾く: 1 つでも固有語があれば通す。tunable。
STOPWORDS = {
    # JA (katakana / 3+ char generics)
    "ファイル",
    "エラー",
    "コード",
    "テスト",
    "データ",
    "メモリ",
    "ください",
    "できる",
    "される",
    "について",
    "における",
    # EN (4+ char generics)
    "file",
    "files",
    "error",
    "errors",
    "code",
    "test",
    "tests",
    "data",
    "this",
    "that",
    "when",
    "with",
    "from",
    "your",
    "have",
    "will",
    "into",
    "thing",
    "things",
    "stuff",
    "issue",
    "change",
    "update",
    "value",
    "true",
    "false",
    "none",
    "null",
}


def _canonical(raw_path: str, cwd: str) -> str:
    if not isinstance(raw_path, str) or not raw_path:
        return ""
    expanded = os.path.expanduser(raw_path)
    if not os.path.isabs(expanded):
        base = cwd if cwd else os.getcwd()
        expanded = os.path.join(base, expanded)
    return os.path.realpath(expanded)


def _is_entry_name(path: str) -> bool:
    base = os.path.basename(path)
    return base.endswith(".md") and base not in INDEX_NAMES


def _repo_rel(path: str) -> str | None:
    """Repo-relative path, or None when outside the clone."""
    rel = os.path.relpath(path, os.path.realpath(MEMORY_REPO_DIR))
    return None if rel.startswith("..") else rel


def _is_memory_entry(path: str) -> bool:
    if not path or not _is_entry_name(path):
        return False
    rel = _repo_rel(path)
    if rel is None:
        return False
    parts = rel.split(os.sep)
    return (len(parts) == 2 and parts[0] == "org") or (
        len(parts) == 3 and parts[0] in ("user", "project")
    )


def _is_legacy_entry(path: str) -> bool:
    if not path or not _is_entry_name(path):
        return False
    if os.path.dirname(path) == os.path.realpath(LEGACY_USER_MEM_DIR):
        return True
    return bool(_LEGACY_PROJ_MEM_RE.match(path))


def _grant_path(path: str) -> str:
    return os.path.join(GRANTS_DIR, os.path.basename(path))


def _grant_valid(grant: str) -> bool:
    """grant が在り、鮮度内なら True。stale なら掃除して False。"""
    try:
        age = time.time() - os.path.getmtime(grant)
    except OSError:
        return False
    if age < GRANT_STALE_SECONDS:
        return True
    try:
        os.remove(grant)
    except OSError:
        pass
    return False


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter 内側, body) を返す。frontmatter が無ければ ("", text)。"""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 4)
            body = text[nl + 1 :] if nl != -1 else ""
            return text[text.find("\n") + 1 : end], body
    return "", text


def _content_problem(path: str, content: str) -> str | None:
    """受理できない内容なら是正指示文字列、OK なら None。"""
    if len(content.encode("utf-8")) > MAX_ENTRY_SIZE:
        return (
            f"entry が {MAX_ENTRY_SIZE} byte 超で memory_surface が index "
            "しません。 短くしてから Write してください。"
        )
    base = os.path.basename(path)
    if not base.startswith(ENTRY_PREFIXES):
        return (
            "entry の file 名は feedback_* (行動是正の教訓) か reference_* "
            "(外部仕様の調査 snapshot) で始めてください。 旧 prefix (project_* 等) "
            "の entry は再 Write する機会に feedback_* へ rename します。"
        )
    if re.search(r"^oneline_summary:", content, flags=re.MULTILINE):
        return (
            "oneline_summary: は廃止形式 (read されません)。 reminder: と "
            "keywords: の 2 行に置き換えてください。"
        )
    fm, body = _split_frontmatter(content)
    # [ \t]*: \s は改行を跨ぎ次行を値と誤認する (memory_surface._parse_entry と同契約)
    m = re.search(r"^reminder:[ \t]*(.+)$", fm, flags=re.MULTILINE)
    if not (m and m.group(1).strip()):
        return (
            "frontmatter 内に reminder: 行 (1 文の是正指示) が必要です。 本文でなく "
            "frontmatter (--- で挟まれた区画) に置いてください。 旧形式 (本文先頭) の "
            "entry を更新する時も frontmatter へ移してから Write してください。"
        )
    if len(m.group(1).strip()) > 150:
        return (
            "reminder が 150 字を超えています (1 文・150 字以内)。 surface 時の "
            "injection が verbose になり無視されます。 具体事案名や jargon は "
            "behavioral nudge に効かないので避け、 一般的な是正指示 1 文に縮めて "
            "ください (個別事案・事例は entry 本文に書く)。"
        )
    mk = re.search(r"^keywords:[ \t]*(.+)$", fm, flags=re.MULTILINE)
    if not (mk and mk.group(1).strip()):
        return (
            "frontmatter 内に keywords: 行 (選択的な match 語) が必要です。 "
            "/memory-routing の書式に従ってください。"
        )
    keywords = mk.group(1)
    tokens = _CJK_RE.findall(keywords) + _ASCII_RE.findall(keywords)
    meaningful = [t for t in tokens if t.lower() not in STOPWORDS]
    if not meaningful:
        return (
            "keywords が FTS で match しません (3+ 字 CJK / 4+ 字 ASCII の "
            "固有語が無い、 または一般語のみ)。 tool 名・path・error code・"
            "固有名詞など選択的な語を入れてください。"
        )
    mm = re.search(r"^models:[ \t]*(.+)$", fm, flags=re.MULTILINE)
    if not (mm and mm.group(1).strip()):
        return (
            "frontmatter 内に models: 行 (この教訓を観測した model の tag) が必要です。 "
            "実行中の自分の model を短形式で記入してください (例 models: fable-5、 "
            "複数は space 区切り)。 /memory-routing の書式に従ってください。"
        )
    tags = [t for t in re.split(r"[\s,・]+", mm.group(1).strip()) if t]
    if not all(re.fullmatch(r"[a-z][a-z0-9.-]+", t) for t in tags):
        return (
            "models: の tag 書式が不正です (小文字英数と . - のみ、 例 opus-4.8 / "
            "fable-5)。 モデル ID 全体 (claude-fable-5) でも可 (index 時に正規化)。"
        )
    if base.startswith("feedback_"):
        # fence 内の見出し様行を除外 (check_skill_writing と同じ手当て)
        prose = re.sub(
            r"^```[^\n]*\n.*?^```[ \t]*$", "", body, flags=re.MULTILINE | re.DOTALL
        )
        h2s = re.findall(r"^## (.+?)[ \t]*$", prose, flags=re.MULTILINE)
        canon = ["Why", "How", "事例", "Related"]
        bad = [h for h in h2s if h not in canon]
        if bad:
            return (
                "feedback 本文の h2 は Why / How / 事例 / Related の 4 語彙に固定です "
                f"(規約外: {', '.join(bad[:3])})。 自由な見出し (日付つき事案・深掘り) は "
                "該当 h2 の下の ### に置いてください。"
            )
        if "Why" not in h2s or "事例" not in h2s:
            return (
                "feedback entry の本文には ## Why (原因/機序) と ## 事例 (絶対日付つきの "
                "発生事例) の見出しが必要です (## How / ## Related は任意)。 "
                "/memory-routing の本文構成に従ってください。"
            )
        idx = [canon.index(h) for h in h2s]
        if idx != sorted(idx) or len(set(h2s)) != len(h2s):
            return (
                "feedback 本文の h2 は Why → How → 事例 → Related の順・各 1 回です。 "
                "並べ替えるか、 重複分を ### に格下げしてください。"
            )
    if not _DATE_RE.search(body):
        return (
            "本文に絶対日付 (YYYY-MM-DD) がありません。 feedback は事例の発生日、 "
            "reference は情報の確認日を書いてください (相対表現は session 境界で "
            "意味を失います)。"
        )
    return None


def _edit_content(tool: str, inp: dict) -> str:
    """opt-out 走査用に Write/Edit/MultiEdit の投入テキストを連結。"""
    if tool == "Write":
        return inp.get("content") or ""
    if tool == "Edit":
        return inp.get("new_string") or ""
    if tool == "MultiEdit":
        edits = inp.get("edits") or []
        return "\n".join(
            e.get("new_string", "") or "" for e in edits if isinstance(e, dict)
        )
    return ""


def cmd_guard(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    tool = payload.get("tool_name") or ""
    if tool not in ("Write", "Edit", "MultiEdit"):
        return
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        return
    cwd = payload.get("cwd") or ""
    path = _canonical(inp.get("file_path") or "", cwd)
    is_repo_entry = _is_memory_entry(path)
    if not is_repo_entry and not _is_legacy_entry(path):
        return
    if OPT_OUT in _edit_content(tool, inp):
        return
    if not is_repo_entry:
        _emit_deny(
            "memory entry は git 管理の共有 clone へ移設されました。 この旧 path "
            "ではなく "
            f"{MEMORY_REPO_DIR}/user/<login>/ (user scope) または "
            f"{MEMORY_REPO_DIR}/project/<encoded-cwd>/ (project scope) に "
            "/memory-routing 経由で Write してください。"
        )
        return
    if not os.path.isdir(os.path.join(MEMORY_REPO_DIR, ".git")):
        _emit_deny(
            "memory clone が不在/破損のため書込を閉塞しています。 "
            "install_claude_extensions を再実行して clone を復旧してから "
            "Write してください (復旧までは entry 化を保留し、教訓は "
            "chat/todos.md に一時記録)。"
        )
        return

    if tool in ("Edit", "MultiEdit"):
        _emit_deny(
            "memory entry の差分編集 (Edit/MultiEdit) は不可です。 "
            "/memory-routing を経由し、 full content で Write し直してください "
            "(skill が書込前に grant を mint します)。"
        )
        return

    # tool == "Write"
    grant = _grant_path(path)
    if not _grant_valid(grant):
        _emit_deny(
            "この memory entry は /memory-routing skill を経由して書いてください。 "
            "skill が書込直前に grant を mint し、 routing 判断・正書式・DB 同期を "
            "一括で担保します (直接 Write は grant 不在で deny されます)。"
        )
        return

    problem = _content_problem(path, inp.get("content") or "")
    if problem:
        _emit_deny(problem)  # grant は残す: 直して再 Write がそのまま通る
        return

    # allow: silent。grant を consume。
    try:
        os.remove(grant)
    except OSError:
        pass


def cmd_sync(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Write":
        return
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        return
    path = _canonical(inp.get("file_path") or "", payload.get("cwd") or "")
    if not _is_memory_entry(path) or not os.path.exists(SYNC_CLI):
        return
    try:
        subprocess.run(
            [sys.executable, SYNC_CLI, "--commit", path],
            timeout=SYNC_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    sub = sys.argv[1]
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        if sub == "guard":
            cmd_guard(payload)
        elif sub == "sync":
            cmd_sync(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
