#!/usr/bin/env python3
r"""
codegraph-first gate (PreToolUse: Grep / Read) for org-managed Claude Code.

Purpose
=======
codegraph MCP (`mcp__codegraph__*`) は symbol / call-tree / impact を verbatim
source 付きで返すが、 server instructions の「grep より codegraph 優先」は
self-judgment 依存で発火率が低い。 本 hook は Grep / Read を **構造 signal**
(ripgrep の type / glob / path) で判別し、 codegraph が確実に上回る検索だけ
deny / advisory で誘導する。 freshness は見ない (codegraph は OS file-watcher で
継続 index・"stays fresh as you code")。

判定 (構造 signal 主軸・pattern は補助。 意味解析は lossy ゆえ deny の決め手にしない)
====================================================================
Grep:
  code signal 無し (type/glob/path が code を指さない)        -> ALLOW
  code signal あり ＆ pattern が text 検索                     -> ALLOW (grep の領分)
  code signal あり ＆ pattern が symbol/call ＆ certain        -> DENY
      certain = type が code 言語 (明示的 code 検索宣言) or pattern に def 系 keyword
      symbol -> codegraph_search / codegraph_explore、 call -> codegraph_callers /
      codegraph_callees / codegraph_impact へ誘導
  code signal あり ＆ pattern が symbol/call ＆ suspected      -> ADVISORY
      suspected = glob/path だけが code を示し type 明示なし

Read (v1 は advisory のみ。 H.S. の deny 基準「確実な symbol/call-tree 検索」に Read は
非該当ゆえ。 cold-vs-targeted を効かせた Read-deny は v2 候補):
  code file (CODE_EXTENSIONS) ＆ 除外 dir 外                   -> ADVISORY (codegraph_explore)
  非 code / 除外 dir                                            -> ALLOW

advise-once detour (loop-safe・retry passes)
============================================
deny / advisory 文面 1 行目に sentinel `[codegraph-first]` を置く。 当 turn の
transcript に sentinel が既出なら以後 ALLOW。 = 1 turn 1 回だけ案内し、 同じ操作を
再実行すれば通る (read -> deny -> 再 read -> allow)。 sentinel は固定文字列ゆえ現在の
tool 引数とは衝突せず self-match しない。

emit / fail-open
================
DENY は permissionDecision: deny、 ADVISORY は additionalContext (tool は走る)。
全例外を握り潰し exit 0 (fail-open) — gate bug が tool を止めない。 transcript が
読めなければ advise-once 判定不能ゆえ ALLOW に倒す。

canonical source: files/claude_managed-hooks/codegraph_first_gate.py
deploy: /etc/claude-code/hooks/ (copy_dir で自動)。 両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

GATE_TOOLS = ("Grep", "Read")
SENTINEL = "[codegraph-first]"

# ripgrep の --type 名のうち code 言語 (Grep tool の type に渡る)。 explicit code 検索宣言。
CODE_RG_TYPES: set[str] = {
    "py",
    "python",
    "rust",
    "js",
    "javascript",
    "jsx",
    "ts",
    "typescript",
    "tsx",
    "go",
    "c",
    "cpp",
    "cc",
    "h",
    "hpp",
    "java",
    "ruby",
    "rb",
    "php",
    "cs",
    "csharp",
    "swift",
    "kotlin",
    "kt",
    "scala",
    "lua",
    "clojure",
    "clj",
    "elixir",
    "erlang",
    "haskell",
    "ocaml",
    "nim",
    "zig",
    "dart",
    "r",
    "julia",
    "perl",
    "sql",
    "vue",
    "svelte",
    "objc",
    "groovy",
    "fsharp",
}

# code file 拡張子 (glob / path / Read file_path の判定用)。 広めに列挙。
CODE_EXTENSIONS: set[str] = {
    ".py",
    ".pyi",
    ".pyw",
    ".rs",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".cts",
    ".mts",
    ".go",
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
    ".clj",
    ".cljs",
    ".cljc",
    ".cs",
    ".fs",
    ".fsx",
    ".vb",
    ".swift",
    ".dart",
    ".rb",
    ".rake",
    ".php",
    ".pl",
    ".pm",
    ".lua",
    ".ex",
    ".exs",
    ".erl",
    ".hrl",
    ".hs",
    ".ml",
    ".mli",
    ".nim",
    ".zig",
    ".jl",
    ".r",
    ".sql",
    ".vue",
    ".svelte",
    ".astro",
}

# 明示的に非 code の拡張子 (glob / path がこれなら gate しない)。
NONCODE_EXTENSIONS: set[str] = {
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".lock",
    ".log",
    ".csv",
    ".tsv",
    ".xml",
    ".env",
    ".properties",
}

# 検索 scope 外 (依存・生成物)。 path がここを指せば gate しない。
EXCLUDE_DIR_RE = re.compile(
    r"(^|/)(node_modules|\.git|dist|build|out|vendor|\.next|target|"
    r"__pycache__|\.venv|venv|site-packages|\.tox|coverage|\.cache)(/|$)"
)

# 定義系 keyword を含む pattern は code symbol 検索と確信できる。
DEF_KEYWORD_RE = re.compile(
    r"\b(def|class|func|fn|function|interface|struct|impl|trait|enum|"
    r"type|module|package|fun|sub|method|proc)\b"
)
# 識別子の直後に開き括弧 = 呼出 (callers) 検索。
CALL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\\?\(")


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower() if isinstance(path, str) else ""


def _glob_exts(glob: str) -> list[str]:
    """glob から拡張子群を抽出 (`**/*.{ts,tsx}` / `*.py` 等)。"""
    if not isinstance(glob, str):
        return []
    return ["." + e.lower() for e in re.findall(r"\.([A-Za-z0-9]+)", glob)]


def _is_symbol_pattern(pat: str) -> bool:
    """pattern が定義系 keyword か、 anchor / word-boundary を剥がすと裸の識別子か。"""
    if not isinstance(pat, str):
        return False
    s = pat.strip()
    if DEF_KEYWORD_RE.search(s):
        return True
    core = re.sub(r"^\^|\$$|\\b", "", s)
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", core))


def _is_call_pattern(pat: str) -> bool:
    return isinstance(pat, str) and bool(CALL_RE.search(pat))


def _grep_code_signal(inp: dict) -> str | None:
    """type / glob / path のどれが code を指すか。 非 code 明示 / 無 signal は None。"""
    t = (inp.get("type") or "").strip().lower()
    if t in CODE_RG_TYPES:
        return "type"
    glob = inp.get("glob") or ""
    exts = _glob_exts(glob)
    if exts:
        if any(e in CODE_EXTENSIONS for e in exts):
            return "glob"
        if all(e in NONCODE_EXTENSIONS for e in exts):
            return None  # 非 code glob を明示
    path = inp.get("path") or ""
    if isinstance(path, str) and path:
        if EXCLUDE_DIR_RE.search(path):
            return None
        e = _ext(path)
        if e in CODE_EXTENSIONS:
            return "path"
        if e in NONCODE_EXTENSIONS:
            return None
        if not e:
            return "path"  # 拡張子なし = dir 検索、 repo code とみなす (deny は別途 certain 要)
    return None


# --- current-turn scan (advise-once) ---

_TAIL_BUFSIZE = 128 * 1024


def _is_turn_boundary(obj: dict) -> bool:
    """human-input turn の起点か (isMeta / tool_result 継続は起点でない)。"""
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


def _load_tail(path: str, bufsize: int = _TAIL_BUFSIZE) -> list[dict]:
    """末尾から直近 1 turn boundary を含むまで後方読み (boundary 不在なら全件)。"""
    try:
        with open(path, "rb") as f:
            pos = f.seek(0, os.SEEK_END)
            pending = b""
            tail: list[dict] = []
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
                        tail.reverse()
                        return tail
            line = pending.strip()
            if line:
                try:
                    tail.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            tail.reverse()
            return tail
    except OSError:
        return []


def _sentinel_seen(transcript_path) -> bool | None:
    """当 turn の transcript に sentinel が既出か。 読めなければ None (fail-open)。"""
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    entries = _load_tail(transcript_path)
    if not entries:
        return None
    start = 0
    for i in range(len(entries) - 1, -1, -1):
        if _is_turn_boundary(entries[i]):
            start = i
            break
    blob = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries[start:])
    return SENTINEL in blob


# --- emit ---


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


def _emit_advisory(context: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
        + "\n"
    )


# deny / advisory 文面は意図的に冗長 (de-escalation 条件 + 代替 tool を内面化させる)。 trim 禁止。
def _deny_symbol() -> None:
    _emit_deny(
        f"{SENTINEL} この Grep は code の symbol / 定義検索に見えます (type/glob/path が "
        f"code を指し、 pattern が識別子・定義形)。 codegraph は定義を verbatim source "
        f"付きで返すので、 `mcp__codegraph__codegraph_search` (位置) か "
        f"`mcp__codegraph__codegraph_explore` (関連 source 群) を使ってください。 "
        f"literal text の検索だった / codegraph が未 index の repo なら、 同じ Grep を "
        f"そのまま再実行すれば通ります (本 gate は 1 turn に 1 回だけ案内します)。"
    )


def _deny_call() -> None:
    _emit_deny(
        f"{SENTINEL} この Grep は呼出箇所 (call) の検索に見えます (識別子 + 開き括弧)。 "
        f"codegraph は呼出関係を辿れるので、 `mcp__codegraph__codegraph_callers` "
        f"(呼出元) / `codegraph_callees` (呼出先) / `codegraph_impact` (変更波及) を "
        f"使ってください。 単なる文字列検索だった / codegraph が未 index なら、 同じ "
        f"Grep をそのまま再実行すれば通ります (本 gate は 1 turn に 1 回だけ案内します)。"
    )


def _advisory_grep() -> None:
    _emit_advisory(
        f"{SENTINEL} この Grep は code symbol 検索の可能性があります (glob/path が code)。 "
        f"Grep はこのまま実行されますが、 定義・呼出を辿るなら "
        f"`mcp__codegraph__codegraph_explore` / `codegraph_search` の方が verbatim "
        f"source を絞って返します。 次回の探索で検討してください。"
    )


def _advisory_read() -> None:
    _emit_advisory(
        f"{SENTINEL} code file の Read です。 特定 symbol の理解が目的なら "
        f"`mcp__codegraph__codegraph_explore` が関連定義を verbatim source で絞って "
        f"返し、 file 全体を読むより効率的です。 Read はこのまま実行されます "
        f"(本 gate は 1 turn に 1 回だけ案内します)。"
    )


# --- gate ---


def cmd_gate(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("tool_name") not in GATE_TOOLS:
        return
    inp = payload.get("tool_input")
    if not isinstance(inp, dict):
        return

    seen = _sentinel_seen(payload.get("transcript_path"))
    if seen or seen is None:
        return  # advise-once 既出、 または判定不能 -> ALLOW (fail-open)

    if payload.get("tool_name") == "Grep":
        sig = _grep_code_signal(inp)
        if sig is None:
            return
        pat = inp.get("pattern") or ""
        symbol = _is_symbol_pattern(pat)
        call = _is_call_pattern(pat)
        if not (symbol or call):
            return  # text 検索は grep の領分
        certain = sig == "type" or bool(DEF_KEYWORD_RE.search(pat))
        if certain:
            _deny_call() if (call and not symbol) else _deny_symbol()
        else:
            _advisory_grep()
        return

    # Read
    fp = inp.get("file_path") or ""
    if _ext(fp) in CODE_EXTENSIONS and not EXCLUDE_DIR_RE.search(fp):
        _advisory_read()


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        cmd_gate(payload)
    except Exception:
        pass  # fail-open: gate bug が tool を止めない
    return 0


class GateTest(unittest.TestCase):
    """emit-vs-comply + 分類 branch。 Run: python3 -m unittest codegraph_first_gate"""

    @staticmethod
    def _run(tool, tool_input, entries=None, transcript=True):
        import io
        import tempfile
        from contextlib import redirect_stdout

        payload = {"tool_name": tool, "tool_input": tool_input}
        if transcript:
            p = os.path.join(tempfile.mkdtemp(), "t.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                for e in entries or [{"type": "user", "message": {"content": "go"}}]:
                    f.write(json.dumps(e) + "\n")
            payload["transcript_path"] = p
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_gate(payload)
        out = buf.getvalue().strip()
        return json.loads(out)["hookSpecificOutput"] if out else None

    def _deny(self, out):
        self.assertIsNotNone(out)
        self.assertEqual(out["permissionDecision"], "deny")
        return out["permissionDecisionReason"]

    def _adv(self, out):
        self.assertIsNotNone(out)
        return out["additionalContext"]

    # --- classification helpers ---
    def test_symbol_and_call_detection(self):
        self.assertTrue(_is_symbol_pattern("parseConfig"))
        self.assertTrue(_is_symbol_pattern("^class Foo"))
        self.assertTrue(_is_symbol_pattern(r"\bMyType\b"))
        self.assertFalse(_is_symbol_pattern("TODO: fix this"))
        self.assertTrue(_is_call_pattern("parseConfig("))
        self.assertTrue(_is_call_pattern(r"render\("))
        self.assertFalse(_is_call_pattern("just text"))

    def test_code_signal(self):
        self.assertEqual(_grep_code_signal({"type": "py"}), "type")
        self.assertEqual(_grep_code_signal({"glob": "**/*.ts"}), "glob")
        self.assertEqual(_grep_code_signal({"path": "src/app.go"}), "path")
        self.assertEqual(_grep_code_signal({"path": "src/"}), "path")  # dir
        self.assertIsNone(_grep_code_signal({"glob": "**/*.md"}))
        self.assertIsNone(_grep_code_signal({"path": "README.md"}))
        self.assertIsNone(_grep_code_signal({"path": "node_modules/x.js"}))
        self.assertIsNone(_grep_code_signal({"pattern": "x"}))  # no signal

    # --- Grep deny (certain) ---
    def test_grep_deny_symbol_with_type(self):
        r = self._deny(self._run("Grep", {"pattern": "parseConfig", "type": "py"}))
        self.assertIn("codegraph_search", r)
        self.assertIn(SENTINEL, r)

    def test_grep_deny_call_with_type(self):
        r = self._deny(self._run("Grep", {"pattern": "render(", "type": "ts"}))
        self.assertIn("codegraph_callers", r)

    def test_grep_deny_def_keyword_via_glob(self):
        # glob だけだが def keyword で certain。
        r = self._deny(self._run("Grep", {"pattern": "def handle", "glob": "**/*.py"}))
        self.assertIn("codegraph", r)

    # --- Grep advisory (suspected) ---
    def test_grep_advisory_symbol_via_glob(self):
        a = self._adv(self._run("Grep", {"pattern": "parseConfig", "glob": "**/*.ts"}))
        self.assertIn("codegraph_explore", a)
        self.assertIn(SENTINEL, a)

    # --- Grep allow ---
    def test_grep_allow_text_over_code(self):
        self.assertIsNone(self._run("Grep", {"pattern": "TODO fix", "type": "py"}))

    def test_grep_allow_no_signal(self):
        self.assertIsNone(self._run("Grep", {"pattern": "parseConfig"}))

    def test_grep_allow_noncode(self):
        self.assertIsNone(self._run("Grep", {"pattern": "title", "glob": "**/*.md"}))

    # --- Read advisory / allow ---
    def test_read_advisory_code_file(self):
        a = self._adv(self._run("Read", {"file_path": "/repo/src/app.py"}))
        self.assertIn("codegraph_explore", a)

    def test_read_allow_noncode(self):
        self.assertIsNone(self._run("Read", {"file_path": "/repo/README.md"}))

    def test_read_allow_excluded_dir(self):
        self.assertIsNone(
            self._run("Read", {"file_path": "/repo/node_modules/x/index.js"})
        )

    # --- advise-once detour ---
    def test_advise_once_suppresses_second(self):
        # 当 turn に sentinel 既出 -> ALLOW (retry passes)。
        prior_deny = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "content": f"{SENTINEL} use codegraph"}
                ]
            },
        }
        entries = [{"type": "user", "message": {"content": "go"}}, prior_deny]
        self.assertIsNone(
            self._run("Grep", {"pattern": "parseConfig", "type": "py"}, entries=entries)
        )

    def test_failopen_no_transcript(self):
        # transcript 読めず -> advise-once 判定不能 -> ALLOW。
        self.assertIsNone(
            self._run("Grep", {"pattern": "x", "type": "py"}, transcript=False)
        )

    def test_non_gate_tool(self):
        self.assertIsNone(self._run("Bash", {"command": "ls"}))


if __name__ == "__main__":
    sys.exit(main())
