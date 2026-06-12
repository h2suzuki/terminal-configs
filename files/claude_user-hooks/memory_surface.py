#!/usr/bin/env python3
# dangling-ref-check: allow (this hook's function is to scan that path).
"""UserPromptSubmit hook surfacing the best-matching memory entry via hybrid retrieval.

Modes:

- (no argv) — UserPromptSubmit handler. Hybrid score = weighted fusion of
  FTS5 BM25 and dense cosine (static embeddings served from a local SQLite
  vocab table; stdlib-only at query time). Top-1 (plus a 2nd only if it
  clears a strong bar), confidence floor + per-session throttle (15 min
  same-entry suppression). Falls back to BM25-only floors when the embed
  model DB is absent. Fail-open: any error exits 0 with no output so a hook
  bug never blocks the prompt.

- `--upsert <abs_path> [project_id]` — replace one entry. Called by
  /memory-routing after writing a feedback file. Exit 1 on error so the
  skill can surface the failure.

- `--delete <abs_path> [project_id]` — remove one entry. Called when
  /memory-routing retires an entry to OLD-MEMORY.md.

- `--rebuild [memory_dir [project_id]]` — bulk re-index files referenced by
  `<memory_dir>/MEMORY.md` (initial population / disaster recovery). Defaults
  to user memory.

The embed model DB (vocab token -> fp16 vector) is built once by the
standalone stdlib-only builder CLI that the installer deploys to
/usr/local/bin; every mode here is stdlib-only too.

The query mode does NOT scan the filesystem — the DB is the source of truth,
maintained by /memory-routing via --upsert / --delete.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import struct
import sys
import time
import unicodedata
import unittest


HOME = os.path.expanduser("~")
USER_MEMORY_DIR = os.path.join(HOME, ".claude", "memory")
DB_PATH = os.path.join(HOME, ".claude", "hooks", "state", "memory_index.sqlite3")
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

# --- hybrid RAG: dense embeddings (model2vec static vectors in SQLite) ---
MODEL_DB_PATH = os.path.join(
    HOME, ".claude", "hooks", "state", "memory_embed_model.sqlite3"
)
EMBED_MAX_CHARS = 2000  # prompt cap before normalization (mean-pool dilutes anyway)
EMBED_MAX_NORM_CHARS = 3000  # cap after punct spacing inflates length
# h = alpha*min(1,-bm25/DIV) + (1-alpha)*cos。 transcript 評価で BM25 単独比
# recall 同等以上・surface 数 6 割減・MRR 0.75→0.91 を確認した動作点
HYBRID_ALPHA = 0.5
BM25_NORM_DIV = 10.0
HYBRID_FLOOR = 0.40
HYBRID_STRONG_FLOOR = 0.50
# hybrid 全滅時の救済: lexical 無 match でも cos がこれ以上なら top-1 を surface
# (評価で recall +6pt / precision 不変)
DENSE_RESCUE_FLOOR = 0.55
BM25_CANDIDATES = 10
_UNK_ID = 1
_VITERBI_UNK_SCORE = -20.0  # below any real token score; spm uses min_score - 10
_SQL_VAR_CHUNK = 500

# --- L4: concern / correction injector (UserPromptSubmit) ---
# Raises (not enforces) illuminate-not-reassure / memory-routing via tight prompt phrases (precision>recall — noisy L4 is net-negative; per-channel throttle).
# 間違 INTENTIONALLY excluded: fires on generic "X is wrong" (code bugs / rule-authoring prose), not assistant-correction — dominant FP.
_L4_CONCERN_KEY = "<L4-concern>"
_L4_CORRECTION_KEY = "<L4-correction>"
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


def _connect() -> sqlite3.Connection | None:
    """Open DB, ensure schema, run idempotent migrations."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        con = sqlite3.connect(DB_PATH, timeout=2.0)
    except sqlite3.Error:
        return None
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
        # Idempotent migration for DBs created before session_id column existed.
        try:
            con.execute("ALTER TABLE inject_log ADD COLUMN session_id TEXT")
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


def _encoded_project_id(cwd: str) -> str:
    """Match Claude Code's projects/<encoded-cwd>/ form: '/' -> '-'."""
    return cwd.replace("/", "-")


def _parse_entry(file_path: str) -> tuple[str, str, str] | None:
    """Return (reminder, keywords, body_for_search); strips YAML frontmatter. FTS5 matches
    `keywords`; `reminder` is the actionable past-mistake reminder (written to prevent repeat, not a summary) — kept separate so it need not be keyword-stuffed."""
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
    m = re.search(r"^reminder:\s*(.+)$", body, flags=re.MULTILINE)
    reminder = m.group(1).strip() if m else ""
    mk = re.search(r"^keywords:\s*(.+)$", body, flags=re.MULTILINE)
    keywords = mk.group(1).strip() if mk else ""
    if not reminder:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("reminder:", "keywords:")):
                reminder = stripped
                break
    return reminder, keywords, body


def _upsert_entry(
    con: sqlite3.Connection,
    file_path: str,
    project_id: str | None,
) -> int:
    """Replace one entry in entries_fts. Returns 0 on success, 1 on error."""
    parsed = _parse_entry(file_path)
    if parsed is None:
        return 1
    reminder, keywords, body = parsed
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
    """Remove one entry from entries_fts (e.g., retired to OLD-MEMORY.md)."""
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
        con.commit()
    except sqlite3.Error:
        return 1
    return 0


def _list_active_entries(memory_dir: str) -> list[str]:
    """Used by --rebuild only: read MEMORY.md, extract feedback*.md paths."""
    index_path = os.path.join(memory_dir, "MEMORY.md")
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    # title can contain `]` (e.g. backtick-wrapped `[skip-semantic]`);
    # greedy `.+` extends to the last `](` on the line, capturing the link target.
    slugs = re.findall(r"^- \[.+\]\(([^)]+\.md)\)", text, flags=re.MULTILINE)
    paths: list[str] = []
    for slug in slugs:
        abs_path = os.path.normpath(os.path.join(memory_dir, slug))
        if not abs_path.startswith(memory_dir + os.sep):
            continue
        if os.path.exists(abs_path):
            paths.append(abs_path)
    return paths


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


def _model_open() -> tuple[sqlite3.Connection, int, int] | None:
    """Read-only open of the embed model DB; None when absent/invalid (BM25 fallback)."""
    if not os.path.exists(MODEL_DB_PATH):
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % MODEL_DB_PATH, uri=True, timeout=2.0)
        meta = dict(con.execute("SELECT key, value FROM meta"))
        return con, int(meta["dim"]), int(meta["max_token_len"])
    except (sqlite3.Error, KeyError, ValueError):
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
) -> bool:
    """True iff this entry was injected in the same session within THROTTLE_SECONDS."""
    row = con.execute(
        "SELECT MAX(ts) FROM inject_log "
        "WHERE file_path = ? AND coalesce(session_id, '') = coalesce(?, '')",
        (file_path, session_id),
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
) -> None:
    con.execute(
        "INSERT INTO inject_log(file_path, project_id, session_id, "
        "ts, score, query_excerpt) VALUES (?, ?, ?, ?, ?, ?)",
        (file_path, project_id, session_id, ts, score, prompt[:QUERY_EXCERPT_LEN]),
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


def _memory_surface(payload: dict) -> str | None:
    # Top-1 FTS5 BM25 match (global + current project), session-throttled.
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
        query = _build_query(prompt)
        if query is None:
            return None
        try:
            rows = con.execute(
                f"SELECT file_path, reminder, bm25(entries_fts, 0, 0, 0, 1.0, {BM25_BODY_WEIGHT}, 0) "
                "FROM entries_fts WHERE entries_fts MATCH ? "
                "AND (project_id IS NULL OR project_id = ?) "
                f"ORDER BY bm25(entries_fts, 0, 0, 0, 1.0, {BM25_BODY_WEIGHT}, 0) "
                f"LIMIT {BM25_CANDIDATES}",
                (query, project_id),
            ).fetchall()
        except sqlite3.Error:
            return None
        picks = _hybrid_picks(con, prompt, project_id, rows)
        if picks is None:
            # legacy BM25-only floors (embed model DB 不在 / embed 失敗)
            picks = []
            for rank, (file_path, reminder, score) in enumerate(rows[:2]):
                floor = BM25_SURFACE_FLOOR if rank == 0 else BM25_STRONG_FLOOR
                if score is None or score > floor:
                    continue
                picks.append((file_path, reminder, score))
        now = time.time()
        blocks = []
        for file_path, reminder, score in picks:
            if _throttle_check(con, file_path, session_id, now):
                continue
            _record_inject(con, file_path, project_id, session_id, now, score, prompt)
            display = reminder or "(reminder 未設定)"
            blocks.append(
                f"<memory-surface>\n{display} 詳細: {file_path}\n</memory-surface>"
            )
        return "\n".join(blocks) if blocks else None
    finally:
        con.close()


def _hybrid_picks(
    con: sqlite3.Connection,
    prompt: str,
    project_id: str,
    bm_rows: list,
) -> list[tuple[str, str, float]] | None:
    """Fuse BM25 + cosine into surface picks; None -> caller falls back to BM25-only."""
    model = _model_open()
    if model is None:
        return None
    mcon, dim, max_len = model
    try:
        qvec = _embed(mcon, dim, max_len, prompt)
    except Exception:
        qvec = None
    finally:
        mcon.close()
    if qvec is None:
        return None
    bm_by_path = {fp: s for fp, _r, s in bm_rows if s is not None}
    reminders = {fp: r for fp, r, _s in bm_rows}
    try:
        vrows = con.execute(
            "SELECT file_path, vec FROM entries_vec "
            "WHERE project_id IS NULL OR project_id = ?",
            (project_id,),
        ).fetchall()
    except sqlite3.Error:
        vrows = []
    scored: dict[str, float] = {}
    cos_by_path: dict[str, float] = {}
    for fp, blob in vrows:
        try:
            ev = struct.unpack("<%de" % dim, blob)
        except struct.error:
            continue
        cos_by_path[fp] = sum(x * y for x, y in zip(qvec, ev, strict=True))
        scored[fp] = _fuse(bm_by_path.get(fp), cos_by_path[fp])
    for fp, s in bm_by_path.items():
        scored.setdefault(fp, _fuse(s, 0.0))  # entry without vec: BM25 part only
    picks: list[tuple[str, str, float]] = []
    for fp, h in _select_picks(scored, cos_by_path):
        reminder = reminders.get(fp)
        if reminder is None:
            try:
                row = con.execute(
                    "SELECT reminder FROM entries_fts WHERE file_path = ? "
                    "AND (project_id IS NULL OR project_id = ?) LIMIT 1",
                    (fp, project_id),
                ).fetchone()
            except sqlite3.Error:
                row = None
            reminder = row[0] if row else ""
        picks.append((fp, reminder, h))
    return picks


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


def _concern_inject(payload: dict) -> str | None:
    # Raise the two user-prompt-triggered skills; throttled per channel sentinel.
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
            _record_inject(con, key, None, session_id, now, 0.0, prompt)
            out.append(reminder)
        return "\n".join(out) if out else None
    finally:
        con.close()


def _main_query() -> int:
    """UserPromptSubmit handler — always exit 0 (fail-open). Turn marker + memory entry ride BOTH channels (TUI may drop UPS systemMessage, an undocumented CC gap, so additionalContext is the reliable copy); L4 concern/correction rides additionalContext only — a private model nudge."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        marker = _turn_marker(payload)
    except Exception:
        marker = None
    try:
        additional = _memory_surface(payload)
    except Exception:
        additional = None
    try:
        concern = _concern_inject(payload)
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


def _main_upsert(argv: list[str]) -> int:
    if len(argv) < 1:
        sys.stderr.write("usage: --upsert <abs_path> [project_id]\n")
        return 1
    file_path = os.path.abspath(argv[0])
    project_id = argv[1] if len(argv) > 1 else None
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
    con = _connect()
    if con is None:
        return 1
    try:
        return _delete_entry(con, file_path, project_id)
    finally:
        con.close()


def _main_rebuild(argv: list[str]) -> int:
    memory_dir = os.path.abspath(argv[0]) if argv else USER_MEMORY_DIR
    project_id = argv[1] if len(argv) > 1 else None
    con = _connect()
    if con is None:
        return 1
    try:
        paths = _list_active_entries(memory_dir)
        # Wipe existing entries for this project_id scope first.
        try:
            con.execute(
                "DELETE FROM entries_fts WHERE coalesce(project_id, '') = "
                "coalesce(?, '')",
                (project_id,),
            )
            con.execute(
                "DELETE FROM entries_vec WHERE coalesce(project_id, '') = "
                "coalesce(?, '')",
                (project_id,),
            )
        except sqlite3.Error:
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
            _select_picks({"a": 0.55, "b": 0.52, "c": 0.1}, {}),
            [("a", 0.55), ("b", 0.52)],
        )
        # rank1 は strong floor (0.50) 未満なので落ちる
        self.assertEqual(_select_picks({"a": 0.45, "b": 0.46}, {}), [("b", 0.46)])

    def test_select_picks_dense_rescue_when_below_floor(self):
        scored = {"a": 0.30, "b": 0.20}
        self.assertEqual(_select_picks(scored, {"a": 0.62, "b": 0.40}), [("a", 0.62)])
        self.assertEqual(_select_picks(scored, {"a": 0.50}), [])

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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open last-line-of-defense for the hook path. Admin paths' non-zero
        # exits would be hidden here, so admin callers rely on explicit returns above.
        sys.exit(0)
