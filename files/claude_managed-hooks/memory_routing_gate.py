#!/usr/bin/env python3
r"""
Memory-entry write enforcement hook for Claude Code.

Purpose
=======
memory entry (~/.claude/memory/*.md, ~/.claude/projects/<enc>/memory/*.md)
への書込を /memory-routing skill 経由に強制する決定論的 gate。retrieval 層
(memory_surface.py の reminder/keywords surface) の上に乗る hard 層で、skill
非発火でも format / keyword 品質 / DB 同期を担保する。

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
    - body に `oneline_summary:` (廃止形式) を含む。
    - body に非空の `reminder:` 行が無い (^reminder:\s*(.+)$ MULTILINE)。
    - body に非空の `keywords:` 行が無い。
    - keywords が FTS token を 1 つも産まない / 一般語 (STOPWORDS) のみ = 無効/広すぎ。

PostToolUse `^Write$` → sync:
  entry の Write 成功後に memory_surface.py --upsert <abspath> [project_id] を
  呼び DB を self-heal (skill の upsert 漏れ保険)。project_id は path から導出
  (projects/<enc>/memory → <enc>、user memory → なし)。

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
SURFACE_HOOK = os.path.join(HOME, ".claude", "hooks", "memory_surface.py")
USER_MEM_DIR = os.path.join(HOME, ".claude", "memory")

MAX_ENTRY_SIZE = 50_000  # memory_surface._parse_entry と一致
GRANT_STALE_SECONDS = 3600  # 放置 grant を無効化 + 掃除する閾値
SYNC_TIMEOUT_SECONDS = 10
INDEX_NAMES = {"MEMORY.md", "OLD-MEMORY.md"}
OPT_OUT = "memory-guard: allow"

# projects/<enc>/memory/<name>.md を判定 (basename は別途 index 除外)
_PROJ_MEM_RE = re.compile(r".*/\.claude/projects/([^/]+)/memory/[^/]+\.md$")

# memory_surface._build_query と同じトークナイザ (CJK 3+, ASCII 4+)
_CJK_RE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]{3,}")
_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")

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


def _is_memory_entry(path: str) -> bool:
    if not path:
        return False
    base = os.path.basename(path)
    if base in INDEX_NAMES or not base.endswith(".md"):
        return False
    if os.path.dirname(path) == os.path.realpath(USER_MEM_DIR):
        return True
    return bool(_PROJ_MEM_RE.match(path))


def _project_id_for(path: str) -> str | None:
    m = _PROJ_MEM_RE.match(path)
    return m.group(1) if m else None


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


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 4)
            return text[nl + 1 :] if nl != -1 else ""
    return text


def _content_problem(content: str) -> str | None:
    """受理できない内容なら是正指示文字列、OK なら None。"""
    if len(content.encode("utf-8")) > MAX_ENTRY_SIZE:
        return (
            f"entry が {MAX_ENTRY_SIZE} byte 超で memory_surface が index "
            "しません。 短くしてから Write してください。"
        )
    body = _strip_frontmatter(content)
    if re.search(r"^oneline_summary:", body, flags=re.MULTILINE):
        return (
            "oneline_summary: は廃止形式 (read されません)。 reminder: と "
            "keywords: の 2 行に置き換えてください。"
        )
    m = re.search(r"^reminder:\s*(.+)$", body, flags=re.MULTILINE)
    if not (m and m.group(1).strip()):
        return (
            "本文先頭に reminder: 行 (1 文の是正指示) が必要です。 "
            "/memory-routing の書式に従ってください。"
        )
    if len(m.group(1).strip()) > 150:
        return (
            "reminder が 150 字を超えています (1 文・150 字以内)。 surface 時の "
            "injection が verbose になり無視されます。 具体事案名や jargon は "
            "behavioral nudge に効かないので避け、 一般的な是正指示 1 文に縮めて "
            "ください (個別事案・事例は entry 本文に書く)。"
        )
    mk = re.search(r"^keywords:\s*(.+)$", body, flags=re.MULTILINE)
    if not (mk and mk.group(1).strip()):
        return (
            "本文に keywords: 行 (選択的な match 語) が必要です。 "
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
    if not _is_memory_entry(path):
        return
    if OPT_OUT in _edit_content(tool, inp):
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

    problem = _content_problem(inp.get("content") or "")
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
    if not _is_memory_entry(path) or not os.path.exists(SURFACE_HOOK):
        return
    args = [sys.executable, SURFACE_HOOK, "--upsert", path]
    pid = _project_id_for(path)
    if pid:
        args.append(pid)
    try:
        subprocess.run(
            args,
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
