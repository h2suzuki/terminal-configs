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
      certain = type が code 言語 (明示的 code 検索宣言)
      symbol -> codegraph_search / codegraph_explore、 call -> codegraph_callers /
      codegraph_callees / codegraph_impact へ誘導
  code signal あり ＆ pattern が symbol/call ＆ suspected      -> ADVISORY
      suspected = glob/path だけが code を示し type 明示なし

Read (v1 は advisory のみ。 deny 基準「確実な symbol/call-tree 検索」に Read は
非該当ゆえ。 cold-vs-targeted を効かせた Read-deny は v2 候補):
  code file (CODE_EXTENSIONS) ＆ 除外 dir 外                   -> ADVISORY (codegraph_explore)
  非 code / 除外 dir                                            -> ALLOW

advise-once detour (per-operation・loop-safe・retry passes)
==========================================================
gate した (tool, target) を session-state file に時刻付きで記録し、 同一操作が
ADVISE_WINDOW_SECONDS 以内に再来したら ALLOW (read -> deny -> 再 read -> allow)。
操作単位ゆえ別操作の gate は互いに干渉しない。 transcript の substring scan は hook
file の Read 等で `[codegraph-first]` を誤検出するため不採用 (codex adversarial review)。

emit / fail-open
================
DENY は permissionDecision: deny、 ADVISORY は additionalContext (tool は走る)。
全例外を握り潰し exit 0 (fail-open) — gate bug が tool を止めない。 state file が
読めなければ retry 追跡を諦め gate は通常 emit (single deny は loop しない)。

canonical source: files/claude_managed-hooks/codegraph_first_gate.py
deploy: /etc/claude-code/hooks/ (copy_dir で自動)。 両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
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

# 呼出 (callers) 検索とみなさない制御構文等の keyword (`if (` を call 誤検出しない)。
CONTROL_KW: set[str] = {
    "if",
    "elif",
    "else",
    "for",
    "while",
    "switch",
    "case",
    "catch",
    "return",
    "with",
    "do",
    "when",
    "foreach",
    "sizeof",
    "typeof",
    "defer",
    "go",
    "match",
    "yield",
    "await",
    "assert",
    "del",
    "raise",
    "in",
    "and",
    "or",
    "not",
}
# 識別子 + 開き括弧 = 呼出。 識別子を捕捉して制御 keyword を除外する。
CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\\?\(")


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower() if isinstance(path, str) else ""


def _glob_exts(glob: str) -> list[str]:
    """glob から拡張子群を抽出 (`*.py` / brace の `**/*.{ts,tsx}` 両対応)。"""
    if not isinstance(glob, str):
        return []
    exts: list[str] = []
    for tok in re.findall(r"\.(\{[^}]*\}|[A-Za-z0-9]+)", glob):
        if tok.startswith("{"):
            exts.extend(e.strip() for e in tok[1:-1].split(",") if e.strip())
        else:
            exts.append(tok)
    return ["." + e.lower() for e in exts]


def _is_symbol_pattern(pat: str) -> bool:
    """anchor / word-boundary を剥がすと単一の識別子か (= symbol 検索)。 `$store` / `@ivar`
    / `foo?` / `foo!` / Unicode 識別子も拾う (codex review)。 def 系 keyword 句 ('type
    error' 等) は誤検出するため signal にしない。 kebab (`my-fn`) は text FP 回避で非対象。"""
    if not isinstance(pat, str):
        return False
    core = re.sub(r"^\^|\$$|\\b", "", pat.strip())
    return bool(re.fullmatch(r"[$@]?[^\W\d][\w$]*[?!]?", core))


def _is_call_pattern(pat: str) -> bool:
    """識別子 + 開き括弧。 制御構文 keyword (`if (` / `for (` 等) は呼出でない。"""
    if not isinstance(pat, str):
        return False
    m = CALL_RE.search(pat)
    return bool(m) and m.group(1).lower() not in CONTROL_KW


def _grep_code_signal(inp: dict) -> str | None:
    """type / glob / path のどれが code を指すか。 非 code 明示 / 無 signal / scope 外 は None。"""
    t = (inp.get("type") or "").strip().lower()
    if t in CODE_RG_TYPES:
        return "type"
    glob = inp.get("glob") or ""
    if isinstance(glob, str) and EXCLUDE_DIR_RE.search(glob):
        return None  # 依存・生成物を指す glob は scope 外
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


# --- advise-once state (per-operation, session-keyed, time-windowed) ---

STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "codegraph_first"
)
ADVISE_WINDOW_SECONDS = 300  # 同一操作の retry を通す窓 (これ以降は再 gate)
_STALE_SESSION_SECONDS = 7 * 24 * 3600


def _op_key(tool: str, inp: dict) -> str:
    """(tool, target) の安定 hash。 Grep は pattern/path/glob/type、 Read は file_path。"""
    if tool == "Grep":
        target = "\x00".join(
            str(inp.get(k) or "") for k in ("pattern", "path", "glob", "type")
        )
    else:
        target = str(inp.get("file_path") or "")
    return hashlib.sha256((tool + "\x00" + target).encode("utf-8")).hexdigest()[:16]


def _state_path(sid: str) -> str:
    return os.path.join(STATE_DIR, sid)


def _load_state(sid: str) -> dict:
    try:
        with open(_state_path(sid), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _recently_gated(sid: str, key: str, now: float) -> bool:
    """この (tool, target) を直近 ADVISE_WINDOW_SECONDS 以内に gate 済か (= retry)。"""
    if not sid:
        return False
    ts = _load_state(sid).get(key)
    return isinstance(ts, (int, float)) and (now - ts) < ADVISE_WINDOW_SECONDS


def _record_gated(sid: str, key: str, now: float) -> None:
    """gate した op を記録。 書込失敗は retry 追跡を諦めるだけ (gate 自体は emit 済)。"""
    if not sid:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        cutoff = now - ADVISE_WINDOW_SECONDS
        state = {
            k: v
            for k, v in _load_state(sid).items()
            if isinstance(v, (int, float)) and v >= cutoff
        }
        state[key] = now
        with open(_state_path(sid), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass
    _prune_old_sessions(now)


def _prune_old_sessions(now: float) -> None:
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return
    for name in names:
        p = os.path.join(STATE_DIR, name)
        try:
            if now - os.path.getmtime(p) > _STALE_SESSION_SECONDS:
                os.remove(p)
        except OSError:
            pass


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
    tool = payload.get("tool_name")
    if tool not in GATE_TOOLS:
        return
    inp = payload.get("tool_input")
    if not isinstance(inp, dict):
        return

    sid = payload.get("session_id") or ""
    now = time.time()
    key = _op_key(tool, inp)
    if _recently_gated(sid, key, now):
        return  # 同一操作の retry -> ALLOW (1 度案内したら通す)

    if tool == "Grep":
        sig = _grep_code_signal(inp)
        if sig is None:
            return
        pat = inp.get("pattern") or ""
        symbol = _is_symbol_pattern(pat)
        call = _is_call_pattern(pat)
        if not (symbol or call):
            return  # text 検索は grep の領分
        _record_gated(sid, key, now)
        if sig == "type":  # type 明示 = code 検索宣言 (certain)。 def keyword は FP 多
            _deny_call() if (call and not symbol) else _deny_symbol()
        else:
            _advisory_grep()
        return

    # Read (v1 は advisory のみ)
    fp = inp.get("file_path") or ""
    if _ext(fp) in CODE_EXTENSIONS and not EXCLUDE_DIR_RE.search(fp):
        _record_gated(sid, key, now)
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
    def _run(tool, tool_input, sid=""):
        import io
        from contextlib import redirect_stdout

        payload = {"tool_name": tool, "tool_input": tool_input, "session_id": sid}
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
        self.assertTrue(_is_symbol_pattern(r"\bMyType\b"))
        self.assertTrue(_is_symbol_pattern("$store"))  # JS
        self.assertTrue(_is_symbol_pattern("@ivar"))  # Ruby ivar
        self.assertTrue(_is_symbol_pattern("valid?"))  # Ruby predicate
        self.assertTrue(_is_symbol_pattern("save!"))  # Ruby bang
        self.assertTrue(_is_symbol_pattern("名前"))  # Unicode
        self.assertFalse(_is_symbol_pattern("123abc"))  # 数字始まりは識別子でない
        self.assertFalse(_is_symbol_pattern("^class Foo"))  # 2-token 句は symbol でない
        self.assertFalse(
            _is_symbol_pattern("type error")
        )  # def keyword 句を誤検出しない
        self.assertFalse(_is_symbol_pattern("TODO: fix this"))
        self.assertTrue(_is_call_pattern("parseConfig("))
        self.assertTrue(_is_call_pattern(r"render\("))
        self.assertFalse(_is_call_pattern("if ("))  # 制御構文は call でない
        self.assertFalse(_is_call_pattern("for ("))
        self.assertFalse(_is_call_pattern("just text"))

    def test_code_signal(self):
        self.assertEqual(_grep_code_signal({"type": "py"}), "type")
        self.assertEqual(_grep_code_signal({"glob": "**/*.ts"}), "glob")
        self.assertEqual(_grep_code_signal({"glob": "**/*.{ts,tsx}"}), "glob")  # brace
        self.assertEqual(_grep_code_signal({"path": "src/app.go"}), "path")
        self.assertEqual(_grep_code_signal({"path": "src/"}), "path")  # dir
        self.assertIsNone(_grep_code_signal({"glob": "**/*.md"}))
        self.assertIsNone(
            _grep_code_signal({"glob": "**/*.{json,yaml}"})
        )  # brace noncode
        self.assertIsNone(
            _grep_code_signal({"glob": "node_modules/**/*.ts"})
        )  # exclude glob
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

    # --- Grep FP regression (codex adversarial review) ---
    def test_grep_allow_def_keyword_phrase(self):
        # 'type error' は def keyword を含むが text 検索 -> ALLOW (誤 deny しない)。
        self.assertIsNone(self._run("Grep", {"pattern": "type error", "type": "ts"}))

    def test_grep_allow_control_flow_call(self):
        # 'if (' は呼出でなく制御構文 -> ALLOW。
        self.assertIsNone(self._run("Grep", {"pattern": "if (", "type": "py"}))

    def test_grep_brace_glob_signal(self):
        # brace glob でも code signal を取り symbol は advisory (type 明示なし)。
        a = self._adv(
            self._run("Grep", {"pattern": "parseConfig", "glob": "**/*.{ts,tsx}"})
        )
        self.assertIn("codegraph", a)

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

    # --- advise-once detour (state-file, per-operation) ---
    def test_advise_once_state_suppresses_retry(self):
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        op = ("Grep", {"pattern": "parseConfig", "type": "py"})
        with mock.patch.object(sys.modules[__name__], "STATE_DIR", d):
            self._deny(self._run(*op, sid="s1"))  # 1 回目 -> deny + 記録
            self.assertIsNone(self._run(*op, sid="s1"))  # 同一操作 retry -> ALLOW
            # 別操作 (Read) は干渉しない (cross-suppression なし)
            self._adv(self._run("Read", {"file_path": "/r/app.py"}, sid="s1"))
            # session 違いは独立
            self._deny(self._run(*op, sid="s2"))

    def test_no_sid_gates_without_state(self):
        # session_id 無し -> state 追跡なしだが gate は通常 emit。
        self._deny(self._run("Grep", {"pattern": "parseConfig", "type": "py"}))

    def test_non_gate_tool(self):
        self.assertIsNone(self._run("Bash", {"command": "ls"}))


if __name__ == "__main__":
    sys.exit(main())
