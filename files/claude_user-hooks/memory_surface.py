#!/usr/bin/env python3
# dangling-ref-check: allow (this hook's function is to scan that path).
"""UserPromptSubmit hook surfacing top-1 memory entry via SQLite FTS5 BM25.

Modes:

- (no argv) — UserPromptSubmit handler. Reads stdin JSON envelope, runs
  FTS5 BM25 against the user prompt, picks top-1, applies a per-session
  throttle (15 min same-entry suppression), and prints the entry's
  oneline_summary as additional context. Fail-open: any error exits 0
  with no output so a hook bug never blocks the prompt.

- `--upsert <abs_path> [project_id]` — replace one entry in entries_fts.
  Called by /memory-routing after writing a memory feedback file. Exit 1
  on error so the skill can surface the failure.

- `--delete <abs_path> [project_id]` — remove one entry from entries_fts.
  Called when /memory-routing retires an entry to OLD-MEMORY.md.

- `--rebuild [memory_dir [project_id]]` — bulk re-index every active
  feedback file referenced by `<memory_dir>/MEMORY.md`. Useful for
  initial population and disaster recovery. Defaults to user memory.

The query mode does NOT scan the filesystem — the DB is the source of
truth, maintained by /memory-routing via --upsert / --delete.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time


HOME = os.path.expanduser("~")
USER_MEMORY_DIR = os.path.join(HOME, ".claude", "memory")
DB_PATH = os.path.join(HOME, ".claude", "hooks", "state", "memory_index.sqlite3")
THROTTLE_SECONDS = 900  # 15 min per (file_path, session_id)
MIN_ASCII_LEN = 4
MIN_CJK_RUN = 3
QUERY_EXCERPT_LEN = 200
MAX_ENTRY_SIZE = 50_000  # skip absurdly large feedback files


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
            "oneline_summary, body, "
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


def _parse_entry(file_path: str) -> tuple[str, str] | None:
    """Return (oneline_summary, body_for_search). Strips YAML frontmatter."""
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return None
    if size > MAX_ENTRY_SIZE:
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 4)
            body = text[nl + 1:] if nl != -1 else ""
    summary_match = re.search(
        r"^oneline_summary:\s*(.+)$", body, flags=re.MULTILINE,
    )
    if summary_match:
        oneline = summary_match.group(1).strip()
    else:
        oneline = ""
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("oneline_summary:"):
                oneline = stripped
                break
    return oneline, body


def _upsert_entry(
    con: sqlite3.Connection,
    file_path: str,
    project_id: str | None,
) -> int:
    """Replace one entry in entries_fts. Returns 0 on success, 1 on error."""
    parsed = _parse_entry(file_path)
    if parsed is None:
        return 1
    oneline, body = parsed
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
            "oneline_summary, body, last_modified) VALUES (?, ?, ?, ?, ?)",
            (file_path, project_id, oneline, body, mtime),
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
        with open(index_path, "r", encoding="utf-8") as f:
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
        rf"[A-Za-z][A-Za-z0-9_-]{{{MIN_ASCII_LEN - 1},}}", prompt,
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


def _main_query() -> int:
    """UserPromptSubmit handler — always exit 0 (fail-open)."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    prompt = payload.get("prompt") or ""
    if not isinstance(prompt, str) or not prompt.strip():
        return 0
    session_id = payload.get("session_id") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        cwd = os.getcwd()
    project_id = _encoded_project_id(cwd)
    con = _connect()
    if con is None:
        return 0
    try:
        query = _build_query(prompt)
        if query is None:
            return 0
        try:
            row = con.execute(
                "SELECT file_path, oneline_summary, bm25(entries_fts) "
                "FROM entries_fts WHERE entries_fts MATCH ? "
                "AND (project_id IS NULL OR project_id = ?) "
                "ORDER BY bm25(entries_fts) LIMIT 1",
                (query, project_id),
            ).fetchone()
        except sqlite3.Error:
            return 0
        if not row:
            return 0
        file_path, oneline, score = row
        now = time.time()
        if _throttle_check(con, file_path, session_id, now):
            return 0
        _record_inject(con, file_path, project_id, session_id, now, score, prompt)
        display = (oneline or "(oneline_summary 未設定)").rstrip("。．.!?！？ \t")
        sys.stdout.write(
            "<global-memory-surface>\n"
            f"過去にこんな事例あり: {display}。 詳細: {file_path}\n"
            "</global-memory-surface>\n"
        )
    finally:
        con.close()
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open for hook (query) path; non-zero exit for admin paths
        # would be hidden under this catch, so admin callers should rely
        # on the explicit return codes above (this catch is the last line
        # of defense against unexpected exceptions in the hook context).
        sys.exit(0)
