#!/usr/bin/env python3
# dangling-ref-check: allow (this hook's function is to scan that path).
"""UserPromptSubmit hook surfacing the best-matching memory entry via hybrid retrieval.

Modes:

- (no argv) — UserPromptSubmit handler. Hybrid score = weighted fusion of
  FTS5 BM25 and dense cosine (static embeddings served from a local SQLite
  vocab table; stdlib-only at query time). Top-1 (plus a 2nd only if it
  clears a strong bar), confidence floor + per-session throttle (15 min
  same-entry suppression). Falls back to BM25-only floors when the embed
  model DB is absent. Entries are model-scoped: only entries whose models:
  tags include the running model surface (untagged = opus-4.8); would-be
  picks for other models are logged as kind='mismatch' for tag-propagation
  stats. Fail-open: any error exits 0 with no output so a hook bug never
  blocks the prompt.

- `--upsert <abs_path> [project_id]` — replace one entry. Called by
  /memory-routing after writing a feedback file. Exit 1 on error so the
  skill can surface the failure.

- `--delete <abs_path> [project_id]` — remove one entry. Called when an
  entry is retired (file deleted from the clone; git history is the archive).

- `--rebuild [memory_dir [project_id]]` — bulk re-index every entry *.md
  under memory_dir (initial population / disaster recovery). Defaults to own
  user memory in the shared clone.

- `--wipe-scope [project_id]` — drop every entry in one scope (no arg = the
  NULL/org scope). Used by the git-sync CLI before a full rebuild so scopes
  that vanished from the clone (or legacy pre-clone rows) do not linger.

- `--project-id [dir]` — print the scope id for dir (default cwd): normalized
  origin URL, cwd-encode fallback. Entry writers use it to pick the project dir.
- `--search <text> [project_id]` — cross-model ranked lookup for
  /memory-routing (no model filter, no throttle, no inject_log rows).
  Prints `score<TAB>models<TAB>path<TAB>reminder` per hit.

Besides the CLI modes, `surface_for_text()` is importable so other hooks (e.g. the
Stop hook) run the same hybrid retrieval against an arbitrary text source, not just
the prompt. `search_unfiltered()` is the same for the `--search` path — the Stop hook
uses it to report entries the model filter would have muted.

The embed model DB (vocab token -> fp16 vector) is built once by the
standalone stdlib-only builder CLI that the installer deploys to
/usr/local/bin; every mode here is stdlib-only too.

The query mode does NOT scan the filesystem — the DB is the source of truth,
maintained by /memory-routing via --upsert / --delete.
"""

from __future__ import annotations

import contextlib
import fcntl
import getpass
import json
import math
import os
import re
import sqlite3
import struct
import subprocess
import sys
import time
import unicodedata
import unittest


HOME = os.path.expanduser("~")


def _login() -> str:
    try:
        return getpass.getuser()
    except Exception:  # uid without passwd entry — keep the hook fail-open
        return str(os.getuid())


# Canonical entry store = shared git clone; the GitHub repo is the source of truth.
MEMORY_REPO_DIR = "/var/lib/claude-rag-memory/claude-lessons-learned"
USER_MEMORY_DIR = os.path.join(MEMORY_REPO_DIR, "user", _login())
# project_id scopes: NULL = org (shared) / user-<login> = own user / <encoded-cwd> = project
USER_SCOPE = "user-" + _login()
SCOPE_PRED = "(project_id IS NULL OR project_id = ? OR project_id = ?)"
# Shared root+login-user store (installer makes it root:login-group 2775 setgid);
# per-user fallback keeps standalone / non-deployed runs working.
SHARED_STATE_DIR = "/var/lib/claude-rag-memory"


def _state_path(filename: str) -> str:
    if os.path.isdir(SHARED_STATE_DIR):
        return os.path.join(SHARED_STATE_DIR, filename)
    return os.path.join(HOME, ".claude", "hooks", "state", filename)


DB_PATH = _state_path("memory_index.sqlite3")
THROTTLE_SECONDS = 900  # 15 min per (file_path, session_id)
# top-1 を surface する floor (負が深いほど良 match、 ~0 は弱 noise)
BM25_SURFACE_FLOOR = -2.0
# 2 件目は強候補 (bm25 <= これ) の時だけ追加。 大抵は top-1 のみ
BM25_STRONG_FLOOR = -3.0
# body 列を keywords より下げ、 lesson 本文の汎用語が無関係 prompt に誤マッチするのを抑える
BM25_BODY_WEIGHT = 0.3
MIN_ASCII_LEN = 4
MIN_CJK_RUN = 3
QUERY_EXCERPT_LEN = 200
MAX_ENTRY_SIZE = 50_000  # skip absurdly large feedback files
# タグ無し entry の既定 tag (タグ導入前の全 entry = opus-4.8 世代、 意図的 reset)
MODELS_DEFAULT = "opus-4.8"
# 1m 等の context-window 表記だけを落とす。 中身を問わず bracket を捨てると、
# 将来の別 variant (safety-eval 等) まで同じ model へ潰してしまう。
CONTEXT_WINDOW_SUFFIX = re.compile(r"\[\d+[kmg]\]")
SEARCH_LIMIT = 8
TRANSCRIPT_TAIL_BYTES = 65536

# --- hybrid RAG: dense embeddings (model2vec static vectors in SQLite) ---
MODEL_DB_PATH = _state_path("memory_embed_model.sqlite3")
EMBED_MAX_CHARS = 2000  # prompt cap before normalization (mean-pool dilutes anyway)
EMBED_MAX_NORM_CHARS = 3000  # cap after punct spacing inflates length
# h = alpha*min(1,-bm25/DIV) + (1-alpha)*cos。 transcript 評価で BM25 単独比
# recall 同等以上・surface 数 6 割減・MRR 0.75→0.91 を確認した動作点
HYBRID_ALPHA = 0.5
BM25_NORM_DIV = 10.0
HYBRID_FLOOR = 0.45
HYBRID_STRONG_FLOOR = 0.55
# hybrid 全滅時の救済: lexical 無 match でも cos がこれ以上なら top-1 を surface
# (評価で recall +6pt / precision 不変)
DENSE_RESCUE_FLOOR = 0.60
BM25_CANDIDATES = 10
_UNK_ID = 1
_VITERBI_UNK_SCORE = -20.0  # below any real token score; spm uses min_score - 10
_SQL_VAR_CHUNK = 500

# --- L4: concern / correction / pixel injector (UserPromptSubmit) ---
# Raises (not enforces) illuminate-not-reassure / memory-routing / pixel-diff via tight prompt phrases (precision>recall — noisy L4 is net-negative; per-channel throttle).
# 間違 INTENTIONALLY excluded: fires on generic "X is wrong" (code bugs / rule-authoring prose), not assistant-correction — dominant FP.
_L4_CONCERN_KEY = "<L4-concern>"
_L4_CORRECTION_KEY = "<L4-correction>"
_L4_PIXEL_KEY = "<L4-pixel-diff>"
_CONCERN_REMINDER = (
    "<concern-detected>懸念/不安が表明された可能性。 illuminate-not-reassure: "
    "「大丈夫/安全」で覆わず、 (1)核心を言い直し (2)起こり得る可能性を本気で深掘り "
    "(3)実機構/state を中立に晒す。 結論は実態提示の後に 1 度だけ。</concern-detected>"
)
_CORRECTION_REMINDER = (
    "<correction-detected>訂正/feedback が出た可能性。 memory-routing: 同じ指摘の "
    "再発なら memory entry 化を検討 (user vs project-local を判断)。</correction-detected>"
)
_CONCERN_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"心配",
        r"気がかり",
        r"懸念(?!\s*もう少し)",
        r"大丈夫(?:[?？]|なの|ですか|だろうか|でしょうか|かな)",
        r"(?:壊れ|崩れ|破綻|消え|漏れ|デグレ|退行|regress).{0,8}(?:ない|しない)(?:か|の)?[?？]",
        r"(?:恐れ|危険)が(?:ある|あり|高)",
        r"(?:本当に|ほんとに|ちゃんと).{0,12}(?:動く|大丈夫|問題ない|いける)(?:の)?[?？]",
    )
]
_CORRECTION_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"じゃなくて",
        r"(?:そう|それ)じゃ(?:なく|ない)",
        r"勝手に",
        r"(?:前|さっき|何度|毎回|以前)(?:に)?も(?:言|いっ|指摘|伝え)",
    )
]
_PIXEL_REMINDER = (
    "<pixel-diff-detected>1px/見た目ずれの可能性。 個別修正でなく mock/実装両方の "
    "computed style を機械 dump して diff、再 dump 0 件で収束証明。 詳細: "
    f"{USER_MEMORY_DIR}/feedback_pixel_perfect_computed_style_diff.md</pixel-diff-detected>"
)
_PIXEL_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"(?<!\d)1\s?px(?![a-z0-9])",  # 11px/21px/1pxel は除外、和文接続 (1pxずれ) は許可
        r"ピクセル(?:パーフェクト)?",
        r"ずれて(?:い|る|ます)",
        r"見た目が(?:ずれ|違|ちが)",  # §C-5 明記 trigger「見た目がずれ」(語尾なし) を含む
    )
]


@contextlib.contextmanager
def _write_lock():
    # flock the DB file itself: no sidecar lock file, independent of SQLite's fcntl
    # locks, and it follows DB_PATH patches so tests never take the live lock.
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    fd = os.open(DB_PATH, os.O_CREAT | os.O_RDWR, 0o666)
    with contextlib.suppress(OSError):  # umask strips o+w at creation
        os.fchmod(fd, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _connect() -> sqlite3.Connection | None:
    """Open DB, ensure schema, run idempotent migrations."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        con = sqlite3.connect(DB_PATH, timeout=2.0)
    except sqlite3.Error:
        return None
    # SQLite hardcodes 0644 (umask can't add bits); open to all trusted users BEFORE
    # WAL so -wal/-shm inherit it. O_NOFOLLOW: never chmod a swapped-in symlink.
    with contextlib.suppress(OSError):
        fd = os.open(DB_PATH, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fchmod(fd, 0o666)
        finally:
            os.close(fd)
    try:
        con.execute("PRAGMA journal_mode = WAL")
        con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5("
            "file_path UNINDEXED, project_id UNINDEXED, "
            "reminder UNINDEXED, keywords, body, "
            "last_modified UNINDEXED, "
            "tokenize='trigram')"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS inject_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "file_path TEXT NOT NULL, project_id TEXT, "
            "session_id TEXT, "
            "ts REAL NOT NULL, score REAL, query_excerpt TEXT)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS entries_vec ("
            "file_path TEXT NOT NULL, project_id TEXT, "
            "vec BLOB NOT NULL, last_modified REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS entry_models ("
            "file_path TEXT NOT NULL, project_id TEXT, "
            "models TEXT NOT NULL, last_modified REAL)"
        )
        # Idempotent migrations for DBs created before these columns existed.
        for column in ("session_id", "model", "kind"):
            try:
                con.execute(f"ALTER TABLE inject_log ADD COLUMN {column} TEXT")
            except sqlite3.OperationalError:
                pass
        con.execute(
            "CREATE INDEX IF NOT EXISTS inject_log_file_session_ts "
            "ON inject_log(file_path, session_id, ts DESC)"
        )
        con.commit()
    except sqlite3.Error:
        con.close()
        return None
    return con


def _origin_url(cwd: str) -> str:
    """origin remote URL of the repo containing cwd; '' when absent (fail-open)."""
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _normalize_origin(url: str) -> str:
    """User/checkout/protocol-independent slug, e.g. github.com-<owner>-<repo>."""
    u = url.strip()
    head, _, tail = u.partition("://")
    u = tail or head
    first = u.split("/", 1)[0]
    if "@" in first and ":" in first.split("@", 1)[1]:
        u = u.replace(":", "/", 1)  # scp form git@host:path -> git@host/path
    first = u.split("/", 1)[0]
    if "@" in first:
        u = u.split("@", 1)[1]
    host, _, path = u.partition("/")
    u = (host.lower() + "/" + path).rstrip("/").removesuffix(".git")
    return u.replace("/", "-").replace(":", "-")


def _encoded_project_id(cwd: str) -> str:
    """Normalized origin URL (same repo = same scope for every user/checkout);
    falls back to the legacy cwd '/' -> '-' encode when there is no origin."""
    url = _origin_url(cwd)
    return _normalize_origin(url) if url else cwd.replace("/", "-")


def _main_project_id(args: list[str]) -> int:
    """--project-id [dir]: print the scope id entry writers must use for dir/cwd."""
    print(_encoded_project_id(os.path.abspath(args[0]) if args else os.getcwd()))
    return 0


def _normalize_model(model_id: str) -> str:
    """claude-opus-4-8 / claude-opus-5[1m] -> opus-4.8 / opus-5 (idempotent)."""
    m = model_id.strip().lower().removeprefix("claude-")
    m = CONTEXT_WINDOW_SUFFIX.sub("", m)  # 同一モデルの context-window 表記違い
    m = re.sub(r"-\d{8}$", "", m)
    return re.sub(r"-(\d+)-(\d+)$", r"-\1.\2", m)


def _statusline_model(session_id) -> str | None:
    """Model id from the statusline stdin dump cache (absent in headless runs)."""
    if not isinstance(session_id, str) or not session_id:
        return None
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(cache, "claude-tui-statusline", session_id + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mid = ((data.get("stdin") or {}).get("model") or {}).get("id")
    except Exception:
        return None
    return mid if isinstance(mid, str) and mid else None


def _transcript_model(transcript_path) -> str | None:
    """Latest assistant-message model from the transcript tail (headless fallback)."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"model"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue  # the byte cut may truncate the oldest line
        if not isinstance(obj, dict) or obj.get("type") != "assistant":
            continue
        msg = obj.get("message")
        model = msg.get("model") if isinstance(msg, dict) else None
        # claude- prefix 必須: alias 行 (sonnet 等) と <synthetic> を除外
        if isinstance(model, str) and model.startswith("claude-"):
            return model
    return None


def _resolve_model(payload: dict) -> str | None:
    """Running model's short id; None -> caller surfaces unfiltered (fail-open)."""
    raw = _statusline_model(payload.get("session_id")) or _transcript_model(
        payload.get("transcript_path")
    )
    return _normalize_model(raw) if raw else None


def _model_pred(con: sqlite3.Connection, project_id: str, model: str):
    """Predicate: does this entry's tag set (default MODELS_DEFAULT) include model?"""
    try:
        rows = con.execute(
            "SELECT file_path, models FROM entry_models WHERE " + SCOPE_PRED,
            (project_id, USER_SCOPE),
        ).fetchall()
    except sqlite3.Error:
        rows = []
    # 保存済み tag も引く側で正規化する — 旧形式 (opus-5[1m] 等) の row は
    # entry を書き直すまで DB に残るため、query 時に揃えないと mute が続く。
    tags = {fp: {_normalize_model(t) for t in m.split()} for fp, m in rows if m}

    def ok(file_path: str) -> bool:
        return model in tags.get(file_path, {MODELS_DEFAULT})

    return ok


def _entry_tags(con: sqlite3.Connection, project_id: str) -> dict[str, str]:
    """file_path -> space-joined tags for display (--search); missing = default."""
    try:
        rows = con.execute(
            "SELECT file_path, models FROM entry_models WHERE " + SCOPE_PRED,
            (project_id, USER_SCOPE),
        ).fetchall()
    except sqlite3.Error:
        rows = []
    return {fp: " ".join(_normalize_model(t) for t in m.split()) for fp, m in rows if m}


def _parse_entry(file_path: str) -> tuple[str, str, str, str] | None:
    """Return (reminder, keywords, body_for_search, models); the 3 fields are dual-read from frontmatter (canonical) or body (legacy), body_for_search excludes frontmatter. FTS5 matches
    `keywords`; `reminder` is the actionable past-mistake reminder (written to prevent repeat, not a summary) — kept separate so it need not be keyword-stuffed. `models` is the normalized space-joined tag list ('' = untagged -> MODELS_DEFAULT at query time)."""
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return None
    if size > MAX_ENTRY_SIZE:
        return None
    try:
        with open(file_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 4)
            body = text[nl + 1 :] if nl != -1 else ""
    # text 全域 = frontmatter (正書式) / 本文 (旧形式) の両位置読み; [ \t]* は次行の値誤認防止 (gate と同契約)
    m = re.search(r"^reminder:[ \t]*(.+)$", text, flags=re.MULTILINE)
    reminder = m.group(1).strip() if m else ""
    mk = re.search(r"^keywords:[ \t]*(.+)$", text, flags=re.MULTILINE)
    keywords = mk.group(1).strip() if mk else ""
    mm = re.search(r"^models:[ \t]*(.+)$", text, flags=re.MULTILINE)
    models = (
        " ".join(_normalize_model(t) for t in re.split(r"[\s,・]+", mm.group(1)) if t)
        if mm
        else ""
    )
    if not reminder:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(
                ("reminder:", "keywords:", "models:")
            ):
                reminder = stripped
                break
    return reminder, keywords, body, models


def _upsert_entry(
    con: sqlite3.Connection,
    file_path: str,
    project_id: str | None,
) -> int:
    """Replace one entry in entries_fts. Returns 0 on success, 1 on error."""
    parsed = _parse_entry(file_path)
    if parsed is None:
        return 1
    reminder, keywords, body, models = parsed
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        return 1
    try:
        con.execute(
            "DELETE FROM entries_fts WHERE file_path = ? "
            "AND coalesce(project_id, '') = coalesce(?, '')",
            (file_path, project_id),
        )
        con.execute(
            "INSERT INTO entries_fts(file_path, project_id, "
            "reminder, keywords, body, last_modified) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_path, project_id, reminder, keywords, body, mtime),
        )
        con.execute(
            "DELETE FROM entries_vec WHERE file_path = ? "
            "AND coalesce(project_id, '') = coalesce(?, '')",
            (file_path, project_id),
        )
        con.execute(
            "DELETE FROM entry_models WHERE file_path = ? "
            "AND coalesce(project_id, '') = coalesce(?, '')",
            (file_path, project_id),
        )
        if models:
            con.execute(
                "INSERT INTO entry_models(file_path, project_id, models, "
                "last_modified) VALUES (?, ?, ?, ?)",
                (file_path, project_id, models, mtime),
            )
        model = _model_open()
        if model is not None:
            mcon, dim, max_len = model
            try:
                vec = _embed(mcon, dim, max_len, _embed_entry_text(reminder, keywords))
            finally:
                mcon.close()
            if vec is not None:
                con.execute(
                    "INSERT INTO entries_vec(file_path, project_id, vec, "
                    "last_modified) VALUES (?, ?, ?, ?)",
                    (file_path, project_id, struct.pack("<%de" % dim, *vec), mtime),
                )
        con.commit()
    except sqlite3.Error:
        return 1
    return 0


def _delete_entry(
    con: sqlite3.Connection,
    file_path: str,
    project_id: str | None,
) -> int:
    """Remove one entry from entries_fts (e.g., retired = entry file deleted)."""
    try:
        con.execute(
            "DELETE FROM entries_fts WHERE file_path = ? "
            "AND coalesce(project_id, '') = coalesce(?, '')",
            (file_path, project_id),
        )
        con.execute(
            "DELETE FROM entries_vec WHERE file_path = ? "
            "AND coalesce(project_id, '') = coalesce(?, '')",
            (file_path, project_id),
        )
        con.execute(
            "DELETE FROM entry_models WHERE file_path = ? "
            "AND coalesce(project_id, '') = coalesce(?, '')",
            (file_path, project_id),
        )
        con.commit()
    except sqlite3.Error:
        return 1
    return 0


# Non-entry .md files an entry dir may carry (legacy rosters + repo docs).
NON_ENTRY_MD = {"MEMORY.md", "OLD-MEMORY.md", "README.md"}


def _list_active_entries(memory_dir: str) -> list[str]:
    """--rebuild enumeration: every *.md on disk = active (retired files are deleted)."""
    try:
        names = os.listdir(memory_dir)
    except OSError:
        return []
    return sorted(
        os.path.join(memory_dir, name)
        for name in names
        if name.endswith(".md") and name not in NON_ENTRY_MD
    )


def _build_query(prompt: str) -> str | None:
    """Extract 3+ char CJK runs and 4+ char ASCII tokens; OR-join for FTS5."""
    cjk = re.findall(r"[぀-ゟ゠-ヿ一-鿿]{3,}", prompt)
    ascii_tokens = re.findall(
        rf"[A-Za-z][A-Za-z0-9_-]{{{MIN_ASCII_LEN - 1},}}",
        prompt,
    )
    terms: list[str] = []
    seen: set[str] = set()
    for token in cjk:
        if token not in seen:
            seen.add(token)
            terms.append(f'"{token}"')
    for token in ascii_tokens:
        low = token.lower()
        if low not in seen:
            seen.add(low)
            terms.append(f'"{low}"')
    if not terms:
        return None
    return " OR ".join(terms)


# --- dense encoder: mirrors model2vec encode for the bundled Unigram tokenizer ---
# (NFKC ~ precompiled charsmap, then the model's own punct-spacing Replace chain)
_EMBED_PUNCT_RE = re.compile(
    "([" + re.escape("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~") + "])"
)
_EMBED_WS_RE = re.compile(r"\s+")
_EMBED_MULTISPACE_RE = re.compile(" {2,}")
_EMBED_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮﻿]")


def _embed_normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _EMBED_CTRL_RE.sub(" ", text)
    text = _EMBED_MULTISPACE_RE.sub(" ", text)
    text = _EMBED_PUNCT_RE.sub(r" \1 ", text)
    text = _EMBED_WS_RE.sub(" ", text)
    return text.strip()


def _viterbi_ids(
    text: str, vocab: dict[str, tuple[int, float]], max_len: int
) -> list[int]:
    """Unigram segmentation maximizing sum of log-probs; OOV chars become UNK."""
    n = len(text)
    neg = -math.inf
    best = [neg] * (n + 1)
    back: list[tuple[int, int] | None] = [None] * (n + 1)  # (start, token_id)
    best[0] = 0.0
    for i in range(n):
        if best[i] == neg:
            continue
        for j in range(i + 1, min(i + max_len, n) + 1):
            hit = vocab.get(text[i:j])
            if hit is None:
                continue
            score = best[i] + hit[1]
            if score > best[j]:
                best[j] = score
                back[j] = (i, hit[0])
        if back[i + 1] is None and best[i] + _VITERBI_UNK_SCORE > best[i + 1]:
            best[i + 1] = best[i] + _VITERBI_UNK_SCORE
            back[i + 1] = (i, _UNK_ID)
    ids: list[int] = []
    pos = n
    while pos > 0:
        step = back[pos]
        if step is None:
            return []
        ids.append(step[1])
        pos = step[0]
    ids.reverse()
    return ids


EMBED_WARN_INTERVAL_SECONDS = 3600


def _warn_degraded(reason: str) -> None:
    """劣化を hot path から報告する — 黙って BM25 に落ちると誰も気付けない。"""
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    marker = os.path.join(cache, "claude-memory-surface", "embed-degraded.stamp")
    try:
        if time.time() - os.path.getmtime(marker) < EMBED_WARN_INTERVAL_SECONDS:
            return
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as stream:
            stream.write(reason + "\n")
    except OSError:
        pass
    sys.stderr.write(
        f"memory-surface: {reason}; falling back to BM25 only, so hybrid scores and "
        f"the muted-memory floor no longer hold. Rebuild with claude_rag_memory_builder.\n"
    )


def _model_open() -> tuple[sqlite3.Connection, int, int] | None:
    """Read-only open of the embed model DB; None when absent/invalid (BM25 fallback)."""
    if not os.path.exists(MODEL_DB_PATH):
        _warn_degraded(f"embed model DB missing at {MODEL_DB_PATH}")
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % MODEL_DB_PATH, uri=True, timeout=2.0)
        meta = dict(con.execute("SELECT key, value FROM meta"))
        return con, int(meta["dim"]), int(meta["max_token_len"])
    except (sqlite3.Error, KeyError, ValueError) as exc:
        _warn_degraded(f"embed model DB unreadable at {MODEL_DB_PATH}: {exc}")
        return None


def _embed(
    mcon: sqlite3.Connection, dim: int, max_len: int, text: str
) -> list[float] | None:
    """Unit-norm mean of token vectors, or None when nothing tokenizes."""
    norm = _embed_normalize(text[:EMBED_MAX_CHARS])[:EMBED_MAX_NORM_CHARS]
    if not norm:
        return None
    seq = "▁" + norm.replace(" ", "▁")  # Metaspace pre-tokenizer
    subs: set[str] = set()
    for i in range(len(seq)):
        for j in range(i + 1, min(i + max_len, len(seq)) + 1):
            subs.add(seq[i:j])
    vocab: dict[str, tuple[int, float]] = {}
    sub_list = list(subs)
    for k in range(0, len(sub_list), _SQL_VAR_CHUNK):
        chunk = sub_list[k : k + _SQL_VAR_CHUNK]
        rows = mcon.execute(
            "SELECT token, id, score FROM vocab WHERE token IN (%s)"
            % ",".join("?" * len(chunk)),
            chunk,
        ).fetchall()
        for tok, tid, score in rows:
            vocab[tok] = (tid, score)
    ids = [i for i in _viterbi_ids(seq, vocab, max_len) if i != _UNK_ID]
    if not ids:
        return None
    uniq = sorted(set(ids))
    vecs: dict[int, tuple[float, ...]] = {}
    for k in range(0, len(uniq), _SQL_VAR_CHUNK):
        chunk = uniq[k : k + _SQL_VAR_CHUNK]
        rows = mcon.execute(
            "SELECT id, vec FROM vocab WHERE id IN (%s)" % ",".join("?" * len(chunk)),
            chunk,
        ).fetchall()
        for tid, blob in rows:
            vecs[tid] = struct.unpack("<%de" % dim, blob)
    acc = [0.0] * dim
    n = 0
    for tid in ids:
        v = vecs.get(tid)
        if v is None:
            continue
        n += 1
        for d in range(dim):
            acc[d] += v[d]
    if n == 0:
        return None
    norm2 = math.sqrt(sum(x * x for x in acc)) + 1e-32
    return [x / norm2 for x in acc]


def _embed_entry_text(reminder: str, keywords: str) -> str:
    # 評価で body 込みより reminder+keywords が一貫して高精度だった
    return ("%s %s" % (reminder, keywords)).strip()


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # both unit-norm


def _throttle_check(
    con: sqlite3.Connection,
    file_path: str,
    session_id: str,
    now: float,
    kind: str = "emit",
) -> bool:
    """True iff this entry was logged under `kind` in the same session within THROTTLE_SECONDS.

    Kept per kind: a mismatch row records that the model filter muted an entry,
    not that anything was shown, so counting it against emits hides the entry for
    15 minutes exactly when a fresh tag should make it appear.
    """
    row = con.execute(
        "SELECT MAX(ts) FROM inject_log "
        "WHERE file_path = ? AND coalesce(session_id, '') = coalesce(?, '') "
        "AND coalesce(kind, 'emit') = ?",
        (file_path, session_id, kind),
    ).fetchone()
    if not row or row[0] is None:
        return False
    return (now - row[0]) < THROTTLE_SECONDS


def _record_inject(
    con: sqlite3.Connection,
    file_path: str,
    project_id: str | None,
    session_id: str,
    ts: float,
    score: float,
    prompt: str,
    model: str | None = None,
    kind: str = "emit",
) -> None:
    con.execute(
        "INSERT INTO inject_log(file_path, project_id, session_id, "
        "ts, score, query_excerpt, model, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            file_path,
            project_id,
            session_id,
            ts,
            score,
            prompt[:QUERY_EXCERPT_LEN],
            model,
            kind,
        ),
    )
    con.commit()


def _gap(elapsed: int) -> str:
    if elapsed >= 3600:
        return "%d hr %d min" % (elapsed // 3600, (elapsed % 3600) // 60)
    if elapsed >= 60:
        return "%d min" % (elapsed // 60)
    return "%d sec" % elapsed


def _counter_path(payload: dict) -> str | None:
    # Mirror stop_checks.py:_counter_path so we read the SAME file Stop writes.
    # Read-only here — Stop owns the increment, so we never double-count.
    transcript = payload.get("transcript_path") or ""
    if transcript:
        base = transcript[:-6] if transcript.endswith(".jsonl") else transcript
        return base + ".turns"
    session_id = payload.get("session_id") or ""
    if not session_id:
        return None
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "claude-turn-counter", session_id + ".turns")


def _turn_marker(payload: dict) -> str | None:
    # Skip synthetic re-entry prompts: a dynamic-workflow completion injects a
    # <task-notification> through the prompt path, which is not a real turn.
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt.lstrip().startswith("<task-notification>"):
        return None
    # Read-only view of Stop-owned counter: file holds prev turn's (count, last-stop), so starting=count+1, idle gap=now-last-stop.
    # We never write — Stop owns count + last-stop epoch.
    path = _counter_path(payload)
    if not path:
        return None
    count = last = 0
    try:
        with open(path, encoding="utf-8") as f:
            parts = f.read().split()
        if len(parts) >= 2:
            count, last = int(parts[0]), int(parts[1])
    except (OSError, ValueError):
        count = last = 0
    now = int(time.time())
    out = [
        time.strftime("%H:%M:%S", time.localtime(now)),
        "Turn #%d starting" % (count + 1),
    ]
    if last > 0:
        out.append("(%s passed since the last stop)" % _gap(now - last))
    else:
        out.append("(session start)")
    return " ".join(out)


def _bm_candidates(con: sqlite3.Connection, query: str, project_id: str) -> list:
    return con.execute(
        f"SELECT file_path, reminder, bm25(entries_fts, 0, 0, 0, 1.0, {BM25_BODY_WEIGHT}, 0) "
        "FROM entries_fts WHERE entries_fts MATCH ? "
        f"AND {SCOPE_PRED} "
        f"ORDER BY bm25(entries_fts, 0, 0, 0, 1.0, {BM25_BODY_WEIGHT}, 0) "
        f"LIMIT {BM25_CANDIDATES}",
        (query, project_id, USER_SCOPE),
    ).fetchall()


def _bm25_picks(rows: list) -> list[tuple[str, str, float]]:
    """Legacy BM25-only floors (embed model DB 不在 / embed 失敗)."""
    picks: list[tuple[str, str, float]] = []
    for rank, (file_path, reminder, score) in enumerate(rows[:2]):
        floor = BM25_SURFACE_FLOOR if rank == 0 else BM25_STRONG_FLOOR
        if score is None or score > floor:
            continue
        picks.append((file_path, reminder, score))
    return picks


def _surface_core(
    con: sqlite3.Connection,
    query_text: str,
    session_id: str,
    project_id: str,
    now: float,
    max_emit: int,
    model: str | None = None,
) -> list[tuple[str, str, float]]:
    """Hybrid-retrieve → model-filter → floor-gate → throttle-dedup → record up to max_emit picks; shared by _memory_surface (UPS) and surface_for_text (Stop). Recording an inject row is what makes the per-(file,session) throttle suppress a repeat — incl. an entry already surfaced this turn at UPS — within THROTTLE_SECONDS. Would-be picks whose tags exclude model are logged kind='mismatch' (tag-propagation stats), then selection reruns on the matching subset so a muted top-1 can't shadow a valid lower candidate."""
    query = _build_query(query_text)
    if query is None:
        return []
    try:
        rows = _bm_candidates(con, query, project_id)
    except sqlite3.Error:
        return []
    picks = _hybrid_picks(con, query_text, project_id, rows)
    if picks is None:
        picks = _bm25_picks(rows)
    if model is not None:
        ok = _model_pred(con, project_id, model)
        mismatches = [p for p in picks if not ok(p[0])]
        if mismatches:
            rows_ok = [r for r in rows if ok(r[0])]
            picks = _hybrid_picks(con, query_text, project_id, rows_ok, ok)
            if picks is None:
                picks = _bm25_picks(rows_ok)
            picks = [p for p in picks if ok(p[0])]
            for file_path, _reminder, score in mismatches:
                if _throttle_check(con, file_path, session_id, now, "mismatch"):
                    continue
                _record_inject(
                    con,
                    file_path,
                    project_id,
                    session_id,
                    now,
                    score,
                    query_text,
                    model,
                    "mismatch",
                )
    out: list[tuple[str, str, float]] = []
    for file_path, reminder, score in picks:
        if len(out) >= max_emit:
            break
        if _throttle_check(con, file_path, session_id, now):
            continue
        _record_inject(
            con, file_path, project_id, session_id, now, score, query_text, model
        )
        out.append((file_path, reminder, score))
    return out


def surface_for_text(
    query_text: str,
    session_id: str,
    project_id: str,
    max_emit: int = 1,
    model: str | None = None,
) -> list[tuple[str, str, float]]:
    """Importable retrieval for non-UPS callers (e.g. the Stop hook): up to max_emit throttle-deduped (file_path, reminder, score) picks, [] when the DB is unavailable so the caller fails open. `model` accepts a raw id (normalized here); None surfaces unfiltered."""
    if not query_text or not query_text.strip():
        return []
    con = _connect()
    if con is None:
        return []
    try:
        return _surface_core(
            con,
            query_text,
            session_id,
            project_id,
            time.time(),
            max_emit,
            _normalize_model(model) if model else None,
        )
    finally:
        con.close()


def _memory_surface(payload: dict, model: str | None = None) -> str | None:
    # UserPromptSubmit: top hybrid match(es) for the prompt, session-throttled.
    prompt = payload.get("prompt") or ""
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    # Skip synthetic re-entry prompts (task-notification / compaction continuation).
    if prompt.lstrip().startswith(
        ("<task-notification>", "This session is being continued")
    ):
        return None
    session_id = payload.get("session_id") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        cwd = os.getcwd()
    project_id = _encoded_project_id(cwd)
    con = _connect()
    if con is None:
        return None
    try:
        picks = _surface_core(
            con, prompt, session_id, project_id, time.time(), 2, model
        )
    finally:
        con.close()
    blocks = [
        f"<memory-surface>\n{reminder or '(reminder 未設定)'} 詳細: {file_path}\n</memory-surface>"
        for file_path, reminder, _score in picks
    ]
    return "\n".join(blocks) if blocks else None


def _hybrid_scored(
    con: sqlite3.Connection,
    prompt: str,
    project_id: str,
    bm_rows: list,
    ok=None,
) -> tuple[dict[str, float], dict[str, float]] | None:
    """Fused scores + cosines over candidates passing `ok`; None -> BM25-only fallback."""
    embed_db = _model_open()
    if embed_db is None:
        return None
    mcon, dim, max_len = embed_db
    try:
        qvec = _embed(mcon, dim, max_len, prompt)
    except Exception:
        qvec = None
    finally:
        mcon.close()
    if qvec is None:
        return None
    bm_by_path = {fp: s for fp, _r, s in bm_rows if s is not None}
    try:
        vrows = con.execute(
            "SELECT file_path, vec FROM entries_vec WHERE " + SCOPE_PRED,
            (project_id, USER_SCOPE),
        ).fetchall()
    except sqlite3.Error:
        vrows = []
    scored: dict[str, float] = {}
    cos_by_path: dict[str, float] = {}
    for fp, blob in vrows:
        if ok is not None and not ok(fp):
            continue
        try:
            ev = struct.unpack("<%de" % dim, blob)
        except struct.error:
            continue
        cos_by_path[fp] = sum(x * y for x, y in zip(qvec, ev, strict=True))
        scored[fp] = _fuse(bm_by_path.get(fp), cos_by_path[fp])
    for fp, s in bm_by_path.items():
        if ok is not None and not ok(fp):
            continue
        scored.setdefault(fp, _fuse(s, 0.0))  # entry without vec: BM25 part only
    return scored, cos_by_path


def _lookup_reminder(
    con: sqlite3.Connection, project_id: str, fp: str, reminders: dict
) -> str:
    reminder = reminders.get(fp)
    if reminder is not None:
        return reminder
    try:
        row = con.execute(
            "SELECT reminder FROM entries_fts WHERE file_path = ? "
            f"AND {SCOPE_PRED} LIMIT 1",
            (fp, project_id, USER_SCOPE),
        ).fetchone()
    except sqlite3.Error:
        row = None
    return row[0] if row else ""


def _hybrid_picks(
    con: sqlite3.Connection,
    prompt: str,
    project_id: str,
    bm_rows: list,
    ok=None,
) -> list[tuple[str, str, float]] | None:
    """Fuse BM25 + cosine into surface picks; None -> caller falls back to BM25-only."""
    both = _hybrid_scored(con, prompt, project_id, bm_rows, ok)
    if both is None:
        return None
    scored, cos_by_path = both
    reminders = {fp: r for fp, r, _s in bm_rows}
    return [
        (fp, _lookup_reminder(con, project_id, fp, reminders), h)
        for fp, h in _select_picks(scored, cos_by_path)
    ]


def _select_picks(
    scored: dict[str, float], cos_by_path: dict[str, float]
) -> list[tuple[str, float]]:
    """Floor-gated top-2 by hybrid score; dense-only rescue when nothing clears."""
    ranked = sorted(scored.items(), key=lambda kv: -kv[1])[:2]
    picks = [
        (fp, h)
        for rank, (fp, h) in enumerate(ranked)
        if h >= (HYBRID_FLOOR if rank == 0 else HYBRID_STRONG_FLOOR)
    ]
    if not picks and cos_by_path:
        fp, cos = max(cos_by_path.items(), key=lambda kv: kv[1])
        if cos >= DENSE_RESCUE_FLOOR:
            picks = [(fp, cos)]
    return picks


def _fuse(bm_score: float | None, cos: float) -> float:
    bm_part = 0.0 if bm_score is None else min(1.0, max(0.0, -bm_score / BM25_NORM_DIV))
    return HYBRID_ALPHA * bm_part + (1.0 - HYBRID_ALPHA) * cos


def _concern_inject(payload: dict, model: str | None = None) -> str | None:
    # Raise the three prompt-triggered channels (concern/correction/pixel); throttled per channel sentinel.
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    # Skip synthetic re-entry prompts (task-notification / compaction continuation).
    if prompt.lstrip().startswith(
        ("<task-notification>", "This session is being continued")
    ):
        return None
    hits = []
    if any(r.search(prompt) for r in _CONCERN_RES):
        hits.append((_L4_CONCERN_KEY, _CONCERN_REMINDER))
    if any(r.search(prompt) for r in _CORRECTION_RES):
        hits.append((_L4_CORRECTION_KEY, _CORRECTION_REMINDER))
    if any(r.search(prompt) for r in _PIXEL_RES):
        hits.append((_L4_PIXEL_KEY, _PIXEL_REMINDER))
    if not hits:
        return None
    try:
        con = _connect()
    except Exception:
        con = None
    if con is None:
        return (
            None  # DB unavailable → drop (match _memory_surface; no unthrottled spam)
        )
    try:
        session_id = payload.get("session_id") or ""
        now = time.time()
        out = []
        for key, reminder in hits:
            if _throttle_check(con, key, session_id, now):
                continue
            _record_inject(con, key, None, session_id, now, 0.0, prompt, model)
            out.append(reminder)
        return "\n".join(out) if out else None
    finally:
        con.close()


def _main_query() -> int:
    """UserPromptSubmit handler — always exit 0 (fail-open). Turn marker + memory entry ride BOTH channels (TUI may drop UPS systemMessage, an undocumented CC gap, so additionalContext is the reliable copy); L4 concern/correction/pixel rides additionalContext only — a private model nudge."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        marker = _turn_marker(payload)
    except Exception:
        marker = None
    try:
        model = _resolve_model(payload)
    except Exception:
        model = None
    try:
        additional = _memory_surface(payload, model)
    except Exception:
        additional = None
    try:
        concern = _concern_inject(payload, model)
    except Exception:
        concern = None
    out: dict = {}
    ctx_parts = [p for p in (marker, additional, concern) if p]
    if ctx_parts:
        out["hookSpecificOutput"] = {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(ctx_parts),
        }
    # memory-surface も systemMessage に出して user に見せる (concern/L4 は model 限定の nudge ゆえ additionalContext のみ)。
    sys_parts = [p for p in (marker, additional) if p]
    if sys_parts:
        out["systemMessage"] = "\n".join(sys_parts)
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0


def search_unfiltered(
    text: str, project_id: str = ""
) -> list[tuple[float, str, str, str]] | None:
    """Cross-model ranked hits (score, models, path, reminder) desc; None = DB 不在, [] = hit ゼロ."""
    query = _build_query(text)
    if query is None:
        return []
    con = _connect()
    if con is None:
        return None
    try:
        rows = _bm_candidates(con, query, project_id)
        both = _hybrid_scored(con, text, project_id, rows)
        if both is not None:
            scored = both[0]
        else:
            scored = {fp: _fuse(s, 0.0) for fp, _r, s in rows if s is not None}
        tags = _entry_tags(con, project_id)
        reminders = {fp: r for fp, r, _s in rows}
        return [
            (
                score,
                tags.get(fp, MODELS_DEFAULT),
                fp,
                _lookup_reminder(con, project_id, fp, reminders),
            )
            for fp, score in sorted(scored.items(), key=lambda kv: -kv[1])[
                :SEARCH_LIMIT
            ]
        ]
    finally:
        con.close()


def _main_search(argv: list[str]) -> int:
    """Cross-model ranked lookup for /memory-routing: no filter, no throttle, no logging."""
    if not argv:
        sys.stderr.write("usage: --search <text> [project_id]\n")
        return 1
    if _build_query(argv[0]) is None:
        sys.stderr.write("no searchable tokens in text\n")
        return 1
    try:
        hits = search_unfiltered(argv[0], argv[1] if len(argv) > 1 else "")
    except sqlite3.Error as e:
        sys.stderr.write("search failed: %s\n" % e)
        return 1
    if hits is None:
        return 1
    for row in hits:
        sys.stdout.write("%.3f\t%s\t%s\t%s\n" % row)
    return 0


def _main_upsert(argv: list[str]) -> int:
    if len(argv) < 1:
        sys.stderr.write("usage: --upsert <abs_path> [project_id]\n")
        return 1
    file_path = os.path.abspath(argv[0])
    project_id = argv[1] if len(argv) > 1 else None
    with _write_lock():
        con = _connect()
        if con is None:
            return 1
        try:
            return _upsert_entry(con, file_path, project_id)
        finally:
            con.close()


def _main_delete(argv: list[str]) -> int:
    if len(argv) < 1:
        sys.stderr.write("usage: --delete <abs_path> [project_id]\n")
        return 1
    file_path = os.path.abspath(argv[0])
    project_id = argv[1] if len(argv) > 1 else None
    with _write_lock():
        con = _connect()
        if con is None:
            return 1
        try:
            return _delete_entry(con, file_path, project_id)
        finally:
            con.close()


def _wipe_scope(con: sqlite3.Connection, project_id: str | None) -> int:
    try:
        for table in ("entries_fts", "entries_vec", "entry_models"):
            con.execute(
                f"DELETE FROM {table} WHERE coalesce(project_id, '') = coalesce(?, '')",
                (project_id,),
            )
        con.commit()
    except sqlite3.Error:
        return 1
    return 0


def _main_wipe_scope(argv: list[str]) -> int:
    project_id = argv[0] if argv else None
    with _write_lock():
        con = _connect()
        if con is None:
            return 1
        try:
            return _wipe_scope(con, project_id)
        finally:
            con.close()


def _main_rebuild(argv: list[str]) -> int:
    memory_dir = os.path.abspath(argv[0]) if argv else USER_MEMORY_DIR
    # no args = own user scope; an explicit dir must bring its own scope id
    project_id = argv[1] if len(argv) > 1 else (None if argv else USER_SCOPE)
    with _write_lock():
        con = _connect()
        if con is None:
            return 1
        try:
            paths = _list_active_entries(memory_dir)
            if not paths:
                # Empty source must not wipe the now-shared scope (cross-user data loss).
                sys.stderr.write(
                    f"no active entries under {memory_dir}; skip wipe (use --upsert/--delete)\n"
                )
                return 0
            # Wipe existing entries for this project_id scope first.
            if _wipe_scope(con, project_id) != 0:
                return 1
            errs = 0
            for fp in paths:
                if _upsert_entry(con, fp, project_id) != 0:
                    errs += 1
            sys.stderr.write(
                f"rebuilt {len(paths) - errs}/{len(paths)} entries from {memory_dir}\n"
            )
            return 1 if errs else 0
        finally:
            con.close()


def main() -> int:
    os.umask(0o002)  # explicit 0666 fchmods do the sharing; umask just avoids 077 homes
    argv = sys.argv[1:]
    if not argv:
        return _main_query()
    cmd = argv[0]
    if cmd == "--upsert":
        return _main_upsert(argv[1:])
    if cmd == "--delete":
        return _main_delete(argv[1:])
    if cmd == "--rebuild":
        return _main_rebuild(argv[1:])
    if cmd == "--wipe-scope":
        return _main_wipe_scope(argv[1:])
    if cmd == "--search":
        return _main_search(argv[1:])
    if cmd == "--project-id":
        return _main_project_id(argv[1:])
    sys.stderr.write(f"unknown command: {cmd}\n")
    return 1


class TurnMarkerTest(unittest.TestCase):
    """UserPromptSubmit turn-marker tests. Run: python3 -m unittest memory_surface"""

    @staticmethod
    def _with_turns(count, last):
        # Seed .turns as the Stop hook writes it ("count last_stop").
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "s.jsonl")
        open(p, "w").close()
        payload = {"transcript_path": p, "prompt": "next q"}
        cp = _counter_path(payload)
        assert cp is not None
        with open(cp, "w", encoding="utf-8") as f:
            f.write("%d %d\n" % (count, last))
        return payload

    def test_idle_gap_since_last_stop(self):
        from unittest import mock

        payload = self._with_turns(1, 2_000_000)
        with mock.patch.object(time, "time", lambda: 2_000_300):
            msg = _turn_marker(payload)
        assert msg is not None
        self.assertIn("Turn #2 starting", msg)
        self.assertIn("5 min passed since the last stop", msg)

    def test_session_start_when_no_counter(self):
        import tempfile
        from unittest import mock

        p = os.path.join(tempfile.mkdtemp(), "fresh.jsonl")
        open(p, "w").close()
        with mock.patch.object(time, "time", lambda: 1000):
            msg = _turn_marker({"transcript_path": p, "prompt": "q"})
        assert msg is not None
        self.assertIn("Turn #1 starting", msg)
        self.assertIn("session start", msg)

    def test_read_only_never_writes(self):
        # Invariant: UPS reads the Stop-owned counter, never writes it.
        from unittest import mock

        payload = self._with_turns(3, 5_000_000)
        cp = _counter_path(payload)
        assert cp is not None
        with open(cp) as f:
            before = f.read()
        with mock.patch.object(time, "time", lambda: 5_000_100):
            _turn_marker(payload)
        with open(cp) as f:
            self.assertEqual(f.read(), before)

    def test_synthetic_prompt_skipped(self):
        self.assertIsNone(
            _turn_marker({"prompt": "<task-notification> x", "transcript_path": "/x"})
        )


class EmbedDbDegradationTest(unittest.TestCase):
    """embed model DB 喪失は黙って BM25 に落ちず報告する。 Run: python3 -m unittest memory_surface"""

    def setUp(self):
        import tempfile
        from unittest import mock

        cache = mock.patch.dict(
            os.environ, {"XDG_CACHE_HOME": tempfile.mkdtemp(prefix="embed-warn-")}
        )
        cache.start()
        self.addCleanup(cache.stop)

    @staticmethod
    def _open(path):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        err = io.StringIO()
        with mock.patch(f"{__name__}.MODEL_DB_PATH", path), redirect_stderr(err):
            con = _model_open()
        if con is not None:
            con[0].close()
        return con, err.getvalue()

    def test_missing_db_is_reported_not_silent(self):
        con, err = self._open("/nonexistent/embed.sqlite3")
        self.assertIsNone(con)
        self.assertIn("missing", err)

    def test_unreadable_db_is_reported_as_distinct_from_missing(self):
        """不在と破損は別の事故 — 復旧手順が違うので文面で区別する。"""
        import tempfile

        path = os.path.join(tempfile.mkdtemp(), "broken.sqlite3")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not a database")
        con, err = self._open(path)
        self.assertIsNone(con)
        self.assertIn("unreadable", err)
        self.assertNotIn("missing", err)

    def test_repeat_within_window_reports_once(self):
        _con, first = self._open("/nonexistent/embed.sqlite3")
        _con2, second = self._open("/nonexistent/embed.sqlite3")
        self.assertIn("missing", first)
        self.assertEqual("", second)

    def test_healthy_db_says_nothing(self):
        if not os.path.exists(MODEL_DB_PATH):
            self.skipTest("embed model DB not built")
        _con, err = self._open(MODEL_DB_PATH)
        self.assertEqual("", err)


class HybridEncoderTest(unittest.TestCase):
    """Dense-encoder + fusion tests. Run: python3 -m unittest memory_surface"""

    def test_normalize_spaces_punct_and_collapses_ws(self):
        self.assertEqual(_embed_normalize("a,b  c\nd"), "a , b c d")

    def test_normalize_nfkc_fullwidth(self):
        self.assertEqual(_embed_normalize("ＡＢ１"), "AB1")

    def test_viterbi_prefers_higher_logprob_segmentation(self):
        vocab = {"ab": (7, -1.0), "a": (8, -3.0), "b": (9, -3.0)}
        self.assertEqual(_viterbi_ids("ab", vocab, 24), [7])

    def test_viterbi_unk_fallback_for_oov_char(self):
        vocab = {"a": (8, -3.0)}
        self.assertEqual(_viterbi_ids("aXa", vocab, 24), [8, _UNK_ID, 8])

    def test_fp16_blob_roundtrip(self):
        vec = [0.5, -0.25, 0.125]
        blob = struct.pack("<3e", *vec)
        self.assertEqual(list(struct.unpack("<3e", blob)), vec)

    def test_fuse_combines_bm25_and_cosine(self):
        self.assertAlmostEqual(_fuse(-10.0, 0.6), 0.5 * 1.0 + 0.5 * 0.6)
        self.assertAlmostEqual(_fuse(None, 0.6), 0.5 * 0.6)
        self.assertAlmostEqual(_fuse(-5.0, 0.0), 0.25)

    def test_select_picks_floor_gate_and_second(self):
        self.assertEqual(
            _select_picks({"a": 0.60, "b": 0.56, "c": 0.1}, {}),
            [("a", 0.60), ("b", 0.56)],
        )
        # rank1 は strong floor (0.55) 未満なので落ちる
        self.assertEqual(_select_picks({"a": 0.50, "b": 0.51}, {}), [("b", 0.51)])

    def test_select_picks_dense_rescue_when_below_floor(self):
        scored = {"a": 0.30, "b": 0.20}
        self.assertEqual(_select_picks(scored, {"a": 0.65, "b": 0.40}), [("a", 0.65)])
        self.assertEqual(_select_picks(scored, {"a": 0.55}), [])

    def test_model_open_none_when_db_missing(self):
        from unittest import mock

        with mock.patch(f"{__name__}.MODEL_DB_PATH", "/nonexistent/model.sqlite3"):
            self.assertIsNone(_model_open())

    @unittest.skipUnless(os.path.exists(MODEL_DB_PATH), "embed model DB not built")
    def test_embed_separates_paraphrase_from_unrelated(self):
        model = _model_open()
        assert model is not None
        mcon, dim, max_len = model
        try:
            a = _embed(mcon, dim, max_len, "push する前にユーザーの許可を取る")
            b = _embed(mcon, dim, max_len, "勝手に push しないでと言ったよね")
            c = _embed(mcon, dim, max_len, "今日の天気は晴れです")
        finally:
            mcon.close()
        assert a and b and c
        self.assertGreater(_cosine(a, b), _cosine(a, c) + 0.15)


class SurfaceCoreTest(unittest.TestCase):
    """_surface_core / surface_for_text throttle + max_emit. Run: python3 -m unittest memory_surface"""

    @staticmethod
    def _tmp_db():
        import tempfile

        return os.path.join(tempfile.mkdtemp(), "idx.sqlite3")

    def test_dedup_and_max_emit(self):
        from unittest import mock

        db = self._tmp_db()
        picks = [("/m/a.md", "lesson A", -6.0), ("/m/b.md", "lesson B", -4.0)]
        mod = sys.modules[__name__]
        with (
            mock.patch.object(mod, "DB_PATH", db),
            mock.patch.object(mod, "_hybrid_picks", lambda *a: list(picks)),
        ):
            con = _connect()
            assert con is not None
            try:
                now = 1_000_000.0
                first = _surface_core(con, "deploy repo 放置", "s1", "proj", now, 2)
                self.assertEqual([p[0] for p in first], ["/m/a.md", "/m/b.md"])
                # same session within THROTTLE_SECONDS -> both deduped
                self.assertEqual(
                    _surface_core(con, "deploy repo 放置", "s1", "proj", now + 60, 2),
                    [],
                )
                # max_emit caps; a fresh session is not throttled
                self.assertEqual(
                    len(_surface_core(con, "deploy repo 放置", "s2", "proj", now, 1)), 1
                )
            finally:
                con.close()

    def test_a_mismatch_row_does_not_throttle_a_later_emit(self):
        """mute の記録は inject ではない — 同じ 15 分の抑止を食うと tag 追記直後の確認が空振りする。"""
        from unittest import mock

        db = self._tmp_db()
        mod = sys.modules[__name__]
        with (
            mock.patch.object(mod, "DB_PATH", db),
            mock.patch.object(
                mod, "_hybrid_picks", lambda *a: [("/m/a.md", "lesson A", -6.0)]
            ),
        ):
            con = _connect()
            assert con is not None
            try:
                now = 1_000_000.0
                _record_inject(
                    con, "/m/a.md", "proj", "s1", now, 0.9, "q", "opus-5", "mismatch"
                )
                picks = _surface_core(con, "deploy 放置", "s1", "proj", now + 60, 1)
                self.assertEqual([p[0] for p in picks], ["/m/a.md"])
            finally:
                con.close()

    def test_surface_for_text_blank_and_wrapper(self):
        from unittest import mock

        db = self._tmp_db()
        picks = [("/m/a.md", "lesson A", -6.0)]
        mod = sys.modules[__name__]
        with (
            mock.patch.object(mod, "DB_PATH", db),
            mock.patch.object(mod, "_hybrid_picks", lambda *a: list(picks)),
        ):
            self.assertEqual(surface_for_text("", "s", "proj"), [])
            out = surface_for_text("deploy repo 放置", "s", "proj", 1)
            self.assertEqual([p[0] for p in out], ["/m/a.md"])


class ModelTagTest(unittest.TestCase):
    """Model tag filter / detection / --search. Run: python3 -m unittest memory_surface"""

    @staticmethod
    def _tmp_db():
        import tempfile

        return os.path.join(tempfile.mkdtemp(), "idx.sqlite3")

    def test_normalize_model(self):
        cases = {
            "claude-opus-4-8": "opus-4.8",
            "claude-fable-5": "fable-5",
            "claude-haiku-4-5-20251001": "haiku-4.5",
            "claude-opus-5[1m]": "opus-5",
            "claude-opus-4-8[1m]": "opus-4.8",
            "claude-haiku-4-5[1m]-20251001": "haiku-4.5",  # 順序が逆でも畳む
            "claude-opus-5[safety-eval]": "opus-5[safety-eval]",  # 別 variant は潰さない
            "opus-4.8": "opus-4.8",  # idempotent
        }
        for raw, expect in cases.items():
            self.assertEqual(_normalize_model(raw), expect, raw)

    def test_parse_entry_models_line(self):
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "e.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(
                "reminder: r\nkeywords: k\nmodels: claude-fable-5・opus-4-8\n\nbody\n"
            )
        parsed = _parse_entry(p)
        assert parsed is not None
        self.assertEqual(parsed[3], "fable-5 opus-4.8")
        with open(p, "w", encoding="utf-8") as f:
            f.write("reminder: r\nkeywords: k\n\nbody\n")
        parsed = _parse_entry(p)
        assert parsed is not None
        self.assertEqual(parsed[3], "")
        with open(p, "w", encoding="utf-8") as f:
            f.write("reminder: r\nkeywords: k\nmodels:   \n\nbody\n")
        parsed = _parse_entry(p)
        assert parsed is not None
        self.assertEqual(parsed[3], "")  # 空 models: 行が次行 body を値に拾わない
        with open(p, "w", encoding="utf-8") as f:
            f.write("reminder:\n実際の指示\nkeywords:   \nmodels: fable-5\n\nbody\n")
        parsed = _parse_entry(p)
        assert parsed is not None
        self.assertEqual(parsed[0], "実際の指示")  # 跨ぎ拾いせず fallback
        self.assertEqual(parsed[1], "")  # 空 keywords: は空のまま

    def test_statusline_model_reads_cache(self):
        import tempfile
        from unittest import mock

        cache = tempfile.mkdtemp()
        sid = "sess-1"
        os.makedirs(os.path.join(cache, "claude-tui-statusline"))
        with open(
            os.path.join(cache, "claude-tui-statusline", sid + ".json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"stdin": {"model": {"id": "claude-fable-5"}}}, f)
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}):
            self.assertEqual(_statusline_model(sid), "claude-fable-5")
            self.assertIsNone(_statusline_model("missing-sess"))

    def test_transcript_model_tail(self):
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        lines = [
            {"type": "user", "message": {"content": "q"}},
            {"type": "assistant", "message": {"model": "claude-opus-4-8"}},
            {"type": "assistant", "message": {"model": "<synthetic>"}},
            {"type": "assistant", "message": {"model": "sonnet"}},
        ]
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        self.assertEqual(_transcript_model(p), "claude-opus-4-8")
        self.assertIsNone(_transcript_model(p + ".nope"))

    def _seed_tags(self, con, rows):
        for fp, models in rows:
            con.execute(
                "INSERT INTO entry_models(file_path, project_id, models, "
                "last_modified) VALUES (?, NULL, ?, 0)",
                (fp, models),
            )
        con.commit()

    def test_legacy_bracket_tag_still_matches(self):
        """DB に残る旧形式 tag (opus-5[1m]) は entry を書き直さずとも引く側で揃える。"""
        from unittest import mock

        db = self._tmp_db()
        with mock.patch.object(sys.modules[__name__], "DB_PATH", db):
            con = _connect()
            assert con is not None
            try:
                self._seed_tags(con, [("/m/legacy.md", "opus-5[1m]")])
                self.assertTrue(_model_pred(con, "proj", "opus-5")("/m/legacy.md"))
                self.assertEqual(_entry_tags(con, "proj")["/m/legacy.md"], "opus-5")
            finally:
                con.close()

    def test_filter_emits_match_and_logs_mismatch(self):
        from unittest import mock

        db = self._tmp_db()
        picks = [("/m/a.md", "lesson A", -6.0), ("/m/b.md", "lesson B", -4.0)]
        mod = sys.modules[__name__]
        with (
            mock.patch.object(mod, "DB_PATH", db),
            mock.patch.object(mod, "_hybrid_picks", lambda *a: list(picks)),
        ):
            con = _connect()
            assert con is not None
            try:
                self._seed_tags(con, [("/m/a.md", "fable-5")])  # b は未タグ
                out = _surface_core(
                    con, "deploy repo 放置", "s1", "proj", 1_000_000.0, 2, "fable-5"
                )
                self.assertEqual([p[0] for p in out], ["/m/a.md"])
                rows = con.execute(
                    "SELECT file_path, model, kind FROM inject_log ORDER BY file_path"
                ).fetchall()
            finally:
                con.close()
        self.assertEqual(
            rows,
            [("/m/a.md", "fable-5", "emit"), ("/m/b.md", "fable-5", "mismatch")],
        )

    def test_untagged_defaults_to_opus(self):
        from unittest import mock

        db = self._tmp_db()
        picks = [("/m/a.md", "lesson A", -6.0), ("/m/b.md", "lesson B", -4.0)]
        mod = sys.modules[__name__]
        with (
            mock.patch.object(mod, "DB_PATH", db),
            mock.patch.object(mod, "_hybrid_picks", lambda *a: list(picks)),
        ):
            con = _connect()
            assert con is not None
            try:
                out = _surface_core(
                    con, "deploy repo 放置", "s1", "proj", 1_000_000.0, 2, "opus-4.8"
                )
                self.assertEqual([p[0] for p in out], ["/m/a.md", "/m/b.md"])
                kinds = [
                    k for (k,) in con.execute("SELECT kind FROM inject_log").fetchall()
                ]
            finally:
                con.close()
        self.assertEqual(kinds, ["emit", "emit"])

    def test_model_none_surfaces_unfiltered(self):
        from unittest import mock

        db = self._tmp_db()
        picks = [("/m/a.md", "lesson A", -6.0)]
        mod = sys.modules[__name__]
        with (
            mock.patch.object(mod, "DB_PATH", db),
            mock.patch.object(mod, "_hybrid_picks", lambda *a: list(picks)),
        ):
            con = _connect()
            assert con is not None
            try:
                self._seed_tags(con, [("/m/a.md", "fable-5")])
                out = _surface_core(
                    con, "deploy repo 放置", "s1", "proj", 1_000_000.0, 2
                )
                self.assertEqual([p[0] for p in out], ["/m/a.md"])
            finally:
                con.close()

    def test_search_prints_without_logging(self):
        import io
        import tempfile
        from unittest import mock

        db = self._tmp_db()
        entry = os.path.join(tempfile.mkdtemp(), "feedback_x.md")
        with open(entry, "w", encoding="utf-8") as f:
            f.write(
                "reminder: deploy 前に repo を確認せよ\n"
                "keywords: deploy repo 放置問題\nmodels: fable-5\n\nbody\n"
            )
        mod = sys.modules[__name__]
        with mock.patch.object(mod, "DB_PATH", db):
            with _write_lock():
                con = _connect()
                assert con is not None
                try:
                    self.assertEqual(_upsert_entry(con, entry, None), 0)
                finally:
                    con.close()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(_main_search(["deploy repo 放置問題"]), 0)
            self.assertIn(entry, buf.getvalue())
            self.assertIn("fable-5", buf.getvalue())
            con = _connect()
            assert con is not None
            try:
                n = con.execute("SELECT COUNT(*) FROM inject_log").fetchone()[0]
            finally:
                con.close()
        self.assertEqual(n, 0)

    def _seed(self, entries):
        """entries: [(basename, models line, keywords)] -> {basename: abs path}"""
        import tempfile

        root = tempfile.mkdtemp()
        paths = {}
        for name, models, keywords in entries:
            p = os.path.join(root, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    f"reminder: {name} の教訓\nkeywords: {keywords}\n"
                    f"models: {models}\n\nbody\n"
                )
            paths[name] = p
        with _write_lock():
            con = _connect()
            assert con is not None
            try:
                for p in paths.values():
                    self.assertEqual(_upsert_entry(con, p, None), 0)
            finally:
                con.close()
        return paths

    def test_search_unfiltered_ranks_and_defaults_untagged(self):
        """search_unfiltered は (score, models, path, reminder) を降順で返し、models: 無しは MODELS_DEFAULT 表示。"""
        from unittest import mock

        db = self._tmp_db()
        with mock.patch.object(sys.modules[__name__], "DB_PATH", db):
            paths = self._seed(
                [
                    ("tagged.md", "fable-5", "deploy repo 放置問題"),
                    ("untagged.md", "", "deploy repo 放置問題 sandbox 除外設定"),
                ]
            )
            hits = search_unfiltered("deploy repo 放置問題")
        assert hits is not None
        self.assertEqual(
            [h[0] for h in hits], sorted((h[0] for h in hits), reverse=True)
        )
        by_path = {h[2]: h for h in hits}
        self.assertEqual(by_path[paths["tagged.md"]][1], "fable-5")
        self.assertEqual(by_path[paths["untagged.md"]][1], MODELS_DEFAULT)
        self.assertIn("tagged.md の教訓", by_path[paths["tagged.md"]][3])

    def test_search_unfiltered_none_when_db_unavailable(self):
        """DB 不在は None (hit ゼロの [] と区別され、CLI が exit 1 を保てる)。"""
        from unittest import mock

        with mock.patch.object(sys.modules[__name__], "_connect", lambda: None):
            self.assertIsNone(search_unfiltered("deploy repo 放置問題"))

    def test_search_unfiltered_empty_on_untokenizable_text(self):
        """検索語を作れない text は [] (None ではない) — 呼び手が DB 障害と区別できる。"""
        self.assertEqual(search_unfiltered("   "), [])


class PixelL4InjectTest(unittest.TestCase):
    """_concern_inject pixel channel: fire / throttle / no-fire. Run: python3 -m unittest memory_surface"""

    @staticmethod
    def _tmp_db():
        import tempfile

        return os.path.join(tempfile.mkdtemp(), "idx.sqlite3")

    # §C-5 明記 trigger 全部 + regex 各 branch (table-driven)
    _POSITIVE = (
        "1pxずれの知見についても気をつけましょう",
        "1px 問題かも",
        "1 px の差があります",
        "見た目がずれ",
        "見た目が違う気がします",
        "ピクセルパーフェクトにしたい",
        "ピクセル単位で確認して",
        "ヘッダーがずれています",
    )
    # 数値部分一致 (11px/21px)・英字連結・無関係 prompt は非発火
    _NEGATIVE = (
        "margin を 11px にしてください",
        "padding: 21px で統一",
        "1pxel という単語",
        "テストを追加してください",
    )

    def test_fires_on_all_spec_triggers(self):
        from unittest import mock

        mod = sys.modules[__name__]
        for i, prompt in enumerate(self._POSITIVE):
            with mock.patch.object(mod, "DB_PATH", self._tmp_db()):
                out = _concern_inject({"prompt": prompt, "session_id": "s%d" % i})
                assert out is not None, prompt
                self.assertIn("pixel-diff-detected", out)

    def test_no_fire_on_negatives(self):
        from unittest import mock

        mod = sys.modules[__name__]
        with mock.patch.object(mod, "DB_PATH", self._tmp_db()):
            for prompt in self._NEGATIVE:
                self.assertIsNone(
                    _concern_inject({"prompt": prompt, "session_id": "s1"}), prompt
                )

    def test_throttled_same_session_and_sentinel_logged(self):
        from unittest import mock

        mod = sys.modules[__name__]
        with mock.patch.object(mod, "DB_PATH", self._tmp_db()):
            payload = {"prompt": "見た目がずれています", "session_id": "s1"}
            self.assertIsNotNone(_concern_inject(payload))
            self.assertIsNone(_concern_inject(payload))  # same-session throttle
            con = _connect()
            assert con is not None
            try:
                rows = con.execute(
                    "SELECT file_path, session_id FROM inject_log"
                ).fetchall()
            finally:
                con.close()
            self.assertEqual(rows, [(_L4_PIXEL_KEY, "s1")])  # sentinel key 記録

    def test_channels_are_independent(self):
        from unittest import mock

        mod = sys.modules[__name__]
        with mock.patch.object(mod, "DB_PATH", self._tmp_db()):
            # pixel-only prompt は concern/correction を出さない
            out = _concern_inject({"prompt": "1px 問題かも", "session_id": "s1"})
            assert out is not None
            self.assertNotIn("concern-detected", out)
            self.assertNotIn("correction-detected", out)
            # pixel throttle 後も concern channel は独立に発火する
            out2 = _concern_inject({"prompt": "この変更、心配です", "session_id": "s1"})
            assert out2 is not None
            self.assertIn("concern-detected", out2)
            self.assertNotIn("pixel-diff-detected", out2)


class RebuildEnumerationTest(unittest.TestCase):
    """--rebuild は disk の entry *.md 全件を active とみなす (roster 廃止、退役 = file 削除)。 Run: python3 -m unittest memory_surface"""

    @staticmethod
    def _memory_dir(on_disk=()):
        import tempfile

        d = tempfile.mkdtemp(prefix="mem-rebuild-")
        for name in on_disk:
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write("reminder: r\nkeywords: k\n\nbody\n")
        return d

    def _names(self, d):
        return sorted(os.path.basename(p) for p in _list_active_entries(d))

    def test_every_disk_entry_is_active(self):
        """feedback_ 以外の prefix (reference_ / project_ 等) も entry として拾う。"""
        d = self._memory_dir(on_disk=["feedback_a.md", "reference_b.md"])
        self.assertEqual(["feedback_a.md", "reference_b.md"], self._names(d))

    def test_index_and_non_md_files_are_ignored(self):
        d = self._memory_dir(
            on_disk=["feedback_a.md", "MEMORY.md", "OLD-MEMORY.md", "README.md"]
        )
        with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("x\n")
        self.assertEqual(["feedback_a.md"], self._names(d))

    def test_missing_dir_returns_empty(self):
        self.assertEqual([], _list_active_entries("/nonexistent/memdir"))

    def test_rebuild_indexes_every_disk_entry_under_given_scope(self):
        import io
        import tempfile
        from contextlib import redirect_stderr
        from unittest import mock

        d = self._memory_dir(on_disk=["feedback_a.md", "reference_c.md"])
        db = os.path.join(tempfile.mkdtemp(), "idx.sqlite3")
        with mock.patch(f"{__name__}.DB_PATH", db), redirect_stderr(io.StringIO()):
            self.assertEqual(_main_rebuild([d, "scope-x"]), 0)
            con = _connect()
            assert con is not None
            try:
                rows = con.execute(
                    "SELECT file_path FROM entries_fts WHERE project_id = 'scope-x'"
                ).fetchall()
            finally:
                con.close()
        self.assertEqual(
            ["feedback_a.md", "reference_c.md"],
            sorted(os.path.basename(fp) for (fp,) in rows),
        )


class ProjectIdTest(unittest.TestCase):
    """project id = 正規化 remote URL (user/checkout path 非依存、2026-08-19 裁定)。repo/remote 無しは cwd encode に fallback。"""

    def test_https_url_with_git_suffix(self):
        self.assertEqual(
            _normalize_origin("https://github.com/h2suzuki/terminal-configs.git"),
            "github.com-h2suzuki-terminal-configs",
        )

    def test_scp_form_equals_https_form(self):
        self.assertEqual(
            _normalize_origin("git@github.com:h2suzuki/terminal-configs.git"),
            _normalize_origin("https://github.com/h2suzuki/terminal-configs"),
        )

    def test_scheme_credentials_and_trailing_slash_stripped(self):
        self.assertEqual(
            _normalize_origin("ssh://git@example.com/a/b.git"), "example.com-a-b"
        )
        self.assertEqual(
            _normalize_origin("https://user:tok@example.com/a/b/"), "example.com-a-b"
        )

    def test_host_lowercased_path_case_kept(self):
        self.assertEqual(
            _normalize_origin("https://GitHub.COM/Ab/Cd"), "github.com-Ab-Cd"
        )

    def test_non_git_dir_falls_back_to_cwd_encode(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_encoded_project_id(d), d.replace("/", "-"))

    def test_git_repo_without_origin_falls_back(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], capture_output=True, check=True)
            self.assertEqual(_encoded_project_id(d), d.replace("/", "-"))

    def test_git_repo_with_origin_uses_normalized_url(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], capture_output=True, check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    d,
                    "remote",
                    "add",
                    "origin",
                    "git@github.com:alice/proj.git",
                ],
                capture_output=True,
                check=True,
            )
            self.assertEqual(_encoded_project_id(d), "github.com-alice-proj")

    def test_cli_project_id_prints_id_for_cwd_and_explicit_dir(self):
        import io
        import tempfile
        from contextlib import redirect_stdout

        with io.StringIO() as buf, redirect_stdout(buf):
            self.assertEqual(_main_project_id([]), 0)
            self.assertEqual(buf.getvalue().strip(), _encoded_project_id(os.getcwd()))
        with tempfile.TemporaryDirectory() as d, io.StringIO() as buf:
            with redirect_stdout(buf):
                self.assertEqual(_main_project_id([d]), 0)
            self.assertEqual(buf.getvalue().strip(), d.replace("/", "-"))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open last-line-of-defense for the hook path. Admin paths' non-zero
        # exits would be hidden here, so admin callers rely on explicit returns above.
        sys.exit(0)
