#!/usr/bin/env python3
"""Requirement-driven tests for agent_coord, written before the implementation.

Each test names the requirement sentence it pins (REQUIREMENTS_AND_DESIGN.ja.md,
chapter.section or F<n> / V<n>). Unit tests drive the in-process Coordinator with an
injected clock; scenario tests run the daemon, the transport, the hook and MCP
adapters, and fake wake channels, following the workflows of chapter 3 and V1-V13.

Claim map (ID -> requirement):
  C42-1  4.2 memory is the current state; changes persist before the reply; restart rebuilds
  C42-2  4.2 retry with the same request id neither posts nor acquires twice
  C42-3  4.2 a second daemon on the same home fails clearly (non-zero) and keeps one ledger
  C43-1  4.3 connection != session: a dropped connection leaves ownership and cursor alone
  C43-2  4.3 one session, several connections, one cursor that never moves backwards
  F1-1   F1 stable coordinator sid mapped from the native id; pid is never the owner id
  F1-2   F1 read-only use (status / history) creates no session
  F2-1   F2 delivery is per recipient: direct and broadcast are acked independently
  F2-2   F2 catchup pages; unreturned events are not acked; peek/status/watch do not consume
  F2-3   F2 a newcomer gets current state and the last hour of its scopes, not the whole history
  F2-4   F2 a rejoin resumes from its cursor within retention, flagged backfill, no repeats
  F2-5   F2 expiry (24h) never loses ownership / open requests, and reports the gap to the reader
  F2-6   F2 ack is not resolution: requests close only by resolve / cancel
  F2-7   2.1 a display name resolves among present sessions (connected or seen within PRESENCE_TTL)
  F2-8   2.1 all / project / repo reach present sessions only; peers list the same set
  F3-1   F3 unread is announced once per unread range; heartbeats do not wake anyone
  F3-2   F3 no self-notification: own broadcast, own resolve, own release never come back
  F3-3   F3 subscribers and wake pushes happen after commit, outside the lock; rollback pushes nothing
  F3-4   F3 notification state per delivery: pending / pushed / unavailable / pull, and ack removes it
  F3-5   F3 Claude Code sessions are woken through the documented inbox socket found in the registry
  F3-6   F3 Codex sessions are woken with `codex queue --thread <id>`; Antigravity is pull-only
  F4-1   F4 acquire is atomic and exclusive; the conflict answer names owner, purpose, time
  F4-2   F4 release verifies owner and generation; a stale release never frees a newer grant
  F4-3   F4 leave marks held resources unconfirmed, never free; force needs a user action + reason
  F4-4   F4 a forced-out owner cannot re-take the resource until it has read the force notice
  F4-5   F4 resources hand over by transfer -> accept, in one step at accept
  F4-6   F4 a use declaration is recorded without taking the exclusive grant
  F5-1   F5 claim rejects a foreign owner; the same worktree is never owned by two sessions
  F5-2   F5 create plans base and target before running git, refuses a same-named foreign dir
  F5-3   F5 partial failure deletes nothing and is resumable
  F5-4   F5 worktree transfer -> accept flips the owner once; the old owner's late change is refused
  F5-5   F5 the edit gate denies only same-repo foreign checkouts and never guesses a relative path
  F5-6   F5 the enforcement level shown follows the client's verified capability, not the flag
  F6-1   F6 status shows self-report and observation separately, waiters, capabilities, service
  F7-1   F7 a caller acts only as the session it registered on this connection (or by token)
  F7-2   F7 no path / ref passthrough: worktree root is confined, refs go after --
  F7-3   F7 unreachable daemon is diagnosed; no second ledger
  F8-1   F8 hooks: Claude Code and Codex payloads / outputs; Antigravity payloads / outputs
  F8-2   F8 doctor separates CLI/MCP, host/sandbox, notification, enforcement capability
  F8-3   F8 SessionEnd leaves the ledger, so a finished session stops being a name or a recipient
  MCP-1  the stdio adapter never dies on a bad tool call and strips reserved arguments
  MCP-2  a Codex tool call's _meta.threadId binds the adapter to the hook's session, not an anon one
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

SPEC = importlib.util.spec_from_loader(
    "coord",
    importlib.machinery.SourceFileLoader(
        "coord", os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_coord")
    ),
)
assert SPEC and SPEC.loader
coord = importlib.util.module_from_spec(SPEC)
sys.modules["coord"] = coord  # dataclasses resolve annotations through sys.modules
SPEC.loader.exec_module(coord)


def git(*args: str, cwd: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def make_repo(root: Path, name: str, remote: str | None = None) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=str(repo))
    (repo / "README").write_text("x\n")
    git("add", "README", cwd=str(repo))
    git("commit", "-q", "-m", "init", cwd=str(repo))
    if remote:
        git("remote", "add", "origin", remote, cwd=str(repo))
    return repo


class Clock:
    def __init__(self, start: float = 1_800_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class InboxServer:
    """Fake Claude Code inbox socket: records every JSON line a poster sends."""

    def __init__(self, path: Path):
        self.path = path
        self.lines: list[dict] = []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(path))
        self.sock.listen(8)
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def loop(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn, conn.makefile("r", encoding="utf-8") as stream:
                for line in stream:
                    self.lines.append(json.loads(line))

    def close(self) -> None:
        self.sock.close()


def wait_for(predicate: Any, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


class Fixture(unittest.TestCase):
    """Temp home, three repos (main + linked worktree, a clone, a same-named other repo)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="coord-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.clock = Clock()
        self.repo = make_repo(self.tmp, "repo", "https://github.com/example/repo.git")
        self.clone = make_repo(self.tmp, "clone", "git@github.com:example/repo.git")
        self.other = make_repo(self.tmp / "elsewhere", "repo")
        self.wt = self.tmp / "wt" / "repo" / "feature"
        git("worktree", "add", "-q", str(self.wt), "-b", "feature", cwd=str(self.repo))
        self.registry = self.tmp / "claude-sessions"
        self.registry.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.codex_log = self.tmp / "codex.log"
        shim = self.bin / "codex"
        shim.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{self.codex_log}"\n')
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        self.env = {
            "AGENT_COORD_HOME": str(self.home),
            "AGENT_COORD_CLAUDE_REGISTRY": str(self.registry),
            "AGENT_COORD_WORKTREE_ROOT": str(self.tmp / "worktrees"),
            "PATH": f"{self.bin}:{os.environ.get('PATH', '')}",
        }
        self.saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.addCleanup(self.restore_env)

    def restore_env(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def register_claude_session(self, native: str) -> InboxServer:
        """Mimic ~/.claude/sessions/<pid>.json plus a bound inbox socket."""
        sock = self.tmp / f"{native[:6]}.sock"
        server = InboxServer(sock)
        self.addCleanup(server.close)
        pid = 1000 + len(os.listdir(self.registry))
        (self.registry / f"{pid}.abc.key").write_text("tok-" + native)
        (self.registry / f"{pid}.json").write_text(
            json.dumps(
                {
                    "pid": pid,
                    "sessionId": native,
                    "messagingSocketPath": str(sock),
                    "kind": "interactive",
                    "status": "idle",
                }
            )
        )
        return server


class Direct(Fixture):
    """Unit level: the Coordinator in-process, clock injected, one connection id per call."""

    def setUp(self) -> None:
        super().setUp()
        self.co = coord.Coordinator(self.home, clock=self.clock)
        self.addCleanup(lambda: self.co.close())

    def call(self, conn: str, method: str, **params: Any) -> Any:
        return self.co.call(conn, method, params)

    def join(self, sid: str, cwd: Path, client: str = "test", **extra: Any) -> dict:
        return self.call(
            sid, "join", sid=sid, client=client, cwd=str(cwd), native_id=sid, **extra
        )

    def texts(self, sid: str) -> list[str]:
        events = self.call(sid, "catchup", sid=sid)["events"]
        return [e["body"].get("text") or e["kind"] for e in events]


# ------------------------------------------------------------------ 4.x and F1


class LedgerTest(Direct):
    def test_schema_migration_adds_parent_relation_without_losing_old_rows(self):
        legacy = self.tmp / "legacy-ledger.sqlite3"
        db = coord.sqlite3.connect(legacy)
        old_schema = coord.SCHEMA.replace(
            "  edit_worktree TEXT, model TEXT, parent_sid TEXT,\n"
            "  turn_active INTEGER NOT NULL DEFAULT 0, turn_id TEXT,\n"
            "  token TEXT, joined_at REAL, updated_at REAL,",
            "  edit_worktree TEXT, model TEXT, token TEXT, joined_at REAL, updated_at REAL,",
        )
        db.executescript(old_schema)
        db.execute("PRAGMA user_version=1")
        db.execute("INSERT INTO sessions(sid) VALUES('old-session')")
        db.commit()
        db.close()

        journal = coord.Journal(legacy)
        self.addCleanup(journal.close)
        self.assertEqual(
            journal.db.execute("PRAGMA user_version").fetchone()[0],
            coord.DB_SCHEMA_VERSION,
        )
        self.assertEqual(journal.db.execute("PRAGMA auto_vacuum").fetchone()[0], 2)
        columns = {row[1] for row in journal.db.execute("PRAGMA table_info(sessions)")}
        self.assertIn("parent_sid", columns)
        self.assertIn("turn_active", columns)
        self.assertIn("turn_id", columns)
        row = journal.db.execute(
            "SELECT sid, parent_sid, turn_active, turn_id "
            "FROM sessions WHERE sid='old-session'"
        ).fetchone()
        self.assertEqual(tuple(row), ("old-session", None, 0, None))

    def test_unknown_newer_schema_is_refused_before_tables_are_changed(self):
        future = self.tmp / "future-ledger.sqlite3"
        db = coord.sqlite3.connect(future)
        db.execute(f"PRAGMA user_version={coord.DB_SCHEMA_VERSION + 1}")
        db.close()
        with self.assertRaisesRegex(RuntimeError, "newer than supported"):
            coord.Journal(future)
        db = coord.sqlite3.connect(future)
        self.addCleanup(db.close)
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        self.assertEqual(tables, [])

    def test_parent_relation_is_immutable_and_self_parent_is_rejected(self):
        self.join("parent-a", self.repo, client="codex")
        self.join("parent-b", self.repo, client="codex")
        child = self.join("child", self.repo, client="codex", parent_sid="parent-a")[
            "session"
        ]
        self.assertEqual(child["parent_sid"], "parent-a")
        with self.assertRaisesRegex(coord.CoordError, "already owned by parent-a"):
            self.call(
                "other",
                "join",
                sid="child",
                client="codex",
                native_id="child",
                cwd=str(self.repo),
                parent_sid="parent-b",
            )
        with self.assertRaisesRegex(coord.CoordError, "cannot be its own parent"):
            self.call(
                "self-child",
                "join",
                sid="self-child",
                client="codex",
                native_id="self-child",
                cwd=str(self.repo),
                parent_sid="self-child",
            )

    def test_expiry_bounds_abandoned_rows_but_preserves_live_state(self):
        self.assertEqual(
            self.co.journal.db.execute("PRAGMA auto_vacuum").fetchone()[0], 2
        )
        self.join("owner", self.repo)
        self.call("owner", "acquire", sid="owner", key="held")
        self.join("requester", self.repo)
        request = self.call(
            "requester", "request", sid="requester", to="owner", subject="open"
        )
        self.co.disconnect("requester")

        self.join("temporary", self.repo)
        released = self.call("temporary", "acquire", sid="temporary", key="scratch")
        self.call(
            "temporary",
            "release",
            sid="temporary",
            key="scratch",
            generation=released["generation"],
        )
        self.call("temporary", "declare", sid="temporary", key="observation")
        self.call("temporary", "send", sid="temporary", to="self", text="old")
        self.call("temporary", "leave", sid="temporary")
        self.co.disconnect("temporary")

        self.join("resolved", self.repo)
        done = self.call(
            "resolved", "request", sid="resolved", to="owner", subject="done"
        )
        self.call("owner", "resolve", sid="owner", req_id=done["req_id"])
        self.call("resolved", "leave", sid="resolved")
        self.co.disconnect("resolved")

        self.clock.advance(coord.EVENT_TTL + 1)
        self.call("", "status")
        self.assertNotIn("temporary", self.co.ledger.sessions)
        self.assertNotIn("resolved", self.co.ledger.sessions)
        self.assertNotIn("scratch", self.co.ledger.resources)
        self.assertNotIn("observation", self.co.ledger.resources)
        self.assertNotIn(done["req_id"], self.co.ledger.requests)
        self.assertEqual(self.co.ledger.resources["held"]["owner"], "owner")
        self.assertEqual(self.co.ledger.requests[request["req_id"]]["state"], "open")
        self.assertIn("requester", self.co.ledger.sessions)

    def test_open_request_without_a_present_recipient_is_pruned_with_delivery(self):
        self.join("sender", self.repo)
        self.join("target", self.repo)
        request = self.call(
            "sender", "request", sid="sender", to="target", subject="orphan"
        )
        self.assertIn(request["req_id"], self.co.ledger.requests)
        self.assertIn(request["seq"], self.co.ledger.deliveries["target"])

        self.call("target", "leave", sid="target")
        self.co.disconnect("target")
        self.call("", "status")

        self.assertNotIn(request["req_id"], self.co.ledger.requests)
        self.assertNotIn(request["seq"], self.co.ledger.deliveries["target"])

        broadcast = self.call(
            "sender", "request", sid="sender", to="all", subject="nobody"
        )
        self.call("", "status")
        self.assertNotIn(broadcast["req_id"], self.co.ledger.requests)

    def test_c42_1_memory_serves_reads_and_sqlite_persists_before_reply(self):
        self.join("a", self.repo)
        statements: list[str] = []
        self.co.journal.db.set_trace_callback(statements.append)
        self.call("a", "whoami", sid="a")
        self.call("", "status")
        self.co.journal.db.set_trace_callback(None)
        selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        self.assertEqual(selects, [])
        seq = self.call("a", "send", sid="a", to="all", text="hi")["seq"]
        row = self.co.journal.db.execute(
            "SELECT seq FROM events WHERE seq=?", (seq,)
        ).fetchone()
        self.assertEqual(row[0], seq)

    def test_c42_1_restart_rebuilds_ownership_cursor_inbox_and_requests(self):
        """V4: nothing is auto-released and the unread survive a restart."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        grant = self.call("a", "acquire", sid="a", key="rig-1")
        first = self.call("a", "send", sid="a", to="repo", text="one")["seq"]
        self.call("b", "ack", sid="b", through=first)
        self.call("a", "send", sid="a", to="repo", text="two")
        req = self.call("a", "request", sid="a", to="b", subject="please")
        self.co.close()
        self.co = coord.Coordinator(self.home, clock=self.clock)
        self.join("a", self.repo)
        self.join("b", self.wt)
        status = self.call("", "status")
        self.assertEqual(
            [(r["key"], r["owner"], r["generation"]) for r in status["resources"]],
            [("rig-1", "a", grant["generation"])],
        )
        self.assertEqual([t for t in self.texts("b") if t != "request_open"], ["two"])
        self.assertEqual(
            [r["req_id"] for r in self.call("b", "requests", sid="b")["requests"]],
            [req["req_id"]],
        )

    def test_c42_1_restart_preserves_the_exact_running_codex_turn(self):
        self.join("receiver", self.repo, client="codex")
        self.call(
            "receiver",
            "activity",
            sid="receiver",
            active=True,
            turn_id="turn-current",
        )
        self.co.close()
        self.co = coord.Coordinator(self.home, clock=self.clock)
        self.call("receiver", "attach", sid="receiver", native_id="receiver")
        self.assertTrue(
            self.call("receiver", "whoami", sid="receiver")["session"]["turn_active"]
        )
        self.assertEqual(self.co.ledger.sessions["receiver"]["turn_id"], "turn-current")
        self.call("receiver", "activity", sid="receiver", active=True)
        self.assertEqual(self.co.ledger.sessions["receiver"]["turn_id"], "turn-current")
        stale = self.call(
            "receiver",
            "activity",
            sid="receiver",
            active=False,
            turn_id="turn-old",
        )
        self.assertTrue(stale["turn_active"])

    def test_c42_2_retry_is_scoped_to_session_and_method(self):
        """V3: a lost reply is retried with the same id; the id must not leak across methods or sessions."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        first = self.call("a", "send", sid="a", to="repo", text="x", request_id="K")
        again = self.call("a", "send", sid="a", to="repo", text="x", request_id="K")
        self.assertEqual(first, again)
        self.assertEqual(self.texts("b"), ["x"])
        grant = self.call("a", "acquire", sid="a", key="rig", request_id="K")
        self.assertEqual(self.call("", "status")["resources"][0]["owner"], "a")
        self.assertEqual(
            self.call("a", "acquire", sid="a", key="rig", request_id="K"), grant
        )
        with self.assertRaises(coord.CoordError):
            self.call("b", "acquire", sid="b", key="rig", request_id="K")
        gen = grant["generation"]
        released = self.call(
            "a", "release", sid="a", key="rig", generation=gen, request_id="R"
        )
        self.assertEqual(
            self.call(
                "a", "release", sid="a", key="rig", generation=gen, request_id="R"
            ),
            released,
        )

    def test_c42_2_a_stale_acquire_replay_does_not_grant_after_release(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        grant = self.call("a", "acquire", sid="a", key="rig", request_id="K")
        self.call("a", "release", sid="a", key="rig", generation=grant["generation"])
        self.call("b", "acquire", sid="b", key="rig")
        with self.assertRaises(coord.CoordError):
            self.call("a", "acquire", sid="a", key="rig", request_id="K")

    def test_c43_1_a_dropped_connection_keeps_ownership_and_cursor(self):
        self.join("a", self.repo)
        self.call("a", "acquire", sid="a", key="rig")
        self.co.disconnect("a")
        status = self.call("", "status")
        self.assertEqual(status["resources"][0]["owner"], "a")
        self.assertIsNone(status["sessions"][0]["left_at"])

    def test_c43_2_two_connections_share_one_monotonic_cursor(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        seqs = [
            self.call("a", "send", sid="a", to="repo", text=f"m{i}")["seq"]
            for i in range(3)
        ]
        self.call("b2", "attach", sid="b", native_id="b")
        self.call("b2", "ack", sid="b", through=seqs[2])
        self.assertEqual(
            self.call("b", "ack", sid="b", through=seqs[0])["cursor"], seqs[2]
        )
        self.assertEqual(self.call("b", "peek", sid="b")["unread"], 0)

    def test_f1_1_sid_is_derived_from_the_native_id_not_the_pid(self):
        joined = self.call(
            "x", "join", client="claude-code", native_id="N1", cwd=str(self.repo)
        )
        self.assertEqual(joined["session"]["sid"], "cc-N1")
        self.assertEqual(coord.session_id_for("codex", "T9"), "codex-T9")
        self.assertEqual(coord.session_id_for("antigravity", "conv"), "agy-conv")

    def test_f1_2_read_only_calls_create_no_session(self):
        self.join("a", self.repo)
        self.call("", "status")
        self.call("", "history", all=True)
        self.call("", "sessions")
        self.assertEqual(len(self.call("", "status")["sessions"]), 1)


# ------------------------------------------------------------------ F2 delivery


class DeliveryTest(Direct):
    def test_f2_1_direct_and_broadcast_are_acked_independently(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.join("c", self.clone)
        self.join("d", self.other)
        self.call("a", "send", sid="a", to="repo", text="repo only")
        self.call("a", "send", sid="a", to="project", text="project wide")
        self.call("a", "send", sid="a", to="all", text="everyone")
        direct = self.call("a", "send", sid="a", to="c", text="direct")["seq"]
        self.call("c", "ack", sid="c", through=direct)
        self.assertEqual(self.texts("b"), ["repo only", "project wide", "everyone"])
        self.assertEqual(self.texts("c"), [])
        self.assertEqual(self.texts("d"), ["everyone"])
        self.assertEqual(self.texts("a"), [])
        self.call("a", "send", sid="a", to="self", text="note to self")
        self.assertEqual(self.texts("a"), ["note to self"])

    def test_f2_7_display_name_resolves_among_present_sessions_only(self):
        """F2-7: a same-named session that is gone (no connection, silent) is not a candidate."""
        self.join("a", self.repo, name="cc@repo")
        self.join("b", self.wt, name="cc@repo")
        with self.assertRaises(coord.CoordError):
            self.call("a", "send", sid="a", to="cc@repo", text="who?")
        self.co.disconnect("b")
        self.clock.advance(coord.PRESENCE_TTL + 1)
        self.join("c", self.clone, name="sender")
        self.call("c", "send", sid="c", to="cc@repo", text="to the live one")
        self.assertEqual(self.texts("a"), ["to the live one"])
        self.join("d", self.other, name="cc@repo")
        with self.assertRaises(coord.CoordError) as caught:
            self.call("c", "send", sid="c", to="cc@repo", text="ambiguous")
        self.assertNotIn("b", str(caught.exception).split(": ")[-1].split(", "))
        self.call("c", "send", sid="c", to="b", text="sid still addresses it")
        self.call("b", "attach", sid="b", native_id="b")
        self.assertEqual(self.texts("b"), ["sid still addresses it"])

    def test_f2_8_broadcasts_and_peers_cover_present_sessions_only(self):
        """F2-8: `all` means connected (or recently seen) sessions, not everyone who ever joined."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.join("c", self.clone)
        self.co.disconnect("b")
        self.co.disconnect("c")
        self.clock.advance(coord.PRESENCE_TTL - 1)
        self.call("c", "attach", sid="c", native_id="c")
        self.co.disconnect("c")
        self.clock.advance(2)
        self.call("a", "send", sid="a", to="all", text="everyone here")
        self.call("c", "attach", sid="c", native_id="c")
        self.assertEqual(self.texts("c"), ["everyone here"])
        peers = self.join("d", self.other)["peers_same_project"]
        self.assertEqual(sorted(p["sid"] for p in peers), [])
        peers = self.join("e", self.clone)["peers_same_project"]
        self.assertEqual(sorted(p["sid"] for p in peers), ["a", "c"])
        self.call("b", "attach", sid="b", native_id="b")
        self.assertEqual(self.texts("b"), [])

    def test_f2_2_paging_never_acks_unreturned_events_and_viewers_do_not_consume(self):
        """V6 + V7."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        for i in range(5):
            self.call("a", "send", sid="a", to="repo", text=f"m{i}")
        self.assertEqual(self.call("b", "peek", sid="b")["unread"], 5)
        self.call("", "status")
        page = self.call("b", "catchup", sid="b", limit=2)
        self.assertTrue(page["more"])
        self.assertEqual([e["body"]["text"] for e in page["events"]], ["m0", "m1"])
        self.assertEqual(self.call("b", "peek", sid="b")["unread"], 5)
        rest = self.call(
            "b", "catchup", sid="b", limit=10, ack_through=page["last_seq"]
        )
        self.assertEqual(
            [e["body"]["text"] for e in rest["events"]], ["m2", "m3", "m4"]
        )
        self.assertFalse(rest["more"])
        self.call("b", "ack", sid="b", through=rest["last_seq"])
        self.call("b", "ack", sid="b", through=1)
        self.assertEqual(self.call("b", "peek", sid="b")["unread"], 0)

    def test_f2_3_newcomer_sees_state_and_the_last_hour_only(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.call("a", "send", sid="a", to="project", text="old news")
        self.clock.advance(coord.JOIN_BACKFILL + 1)
        self.call("a", "send", sid="a", to="project", text="fresh")
        self.call("a", "send", sid="a", to="b", text="private")
        self.call("a", "acquire", sid="a", key="rig")
        self.call("a", "request", sid="a", to="project", subject="open one")
        joined = self.join("c", self.clone)
        got = [
            (e["body"].get("text") or e["kind"], e.get("backfill"))
            for e in self.call("c", "catchup", sid="c")["events"]
        ]
        self.assertEqual(got, [("fresh", True), ("request_open", True)])
        self.assertEqual([r["key"] for r in joined["resources_held"]], ["rig"])
        self.assertEqual(len(joined["open_requests"]), 1)

    def test_f2_4_rejoin_resumes_from_its_cursor_without_repeats(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        seen = self.call("b", "send", sid="b", to="repo", text="seen")["seq"]
        self.call("a", "ack", sid="a", through=seen)
        self.call("b", "send", sid="b", to="repo", text="pending")
        self.call("a", "leave", sid="a")
        self.clock.advance(2 * coord.JOIN_BACKFILL)
        self.call("b", "send", sid="b", to="repo", text="while away")
        rejoined = self.join("a", self.repo)
        self.assertEqual(rejoined["unread"], 2)
        events = self.call("a", "catchup", sid="a")["events"]
        self.assertEqual(
            [(e["body"]["text"], bool(e.get("backfill"))) for e in events],
            [("pending", False), ("while away", True)],
        )
        self.assertEqual(self.join("a", self.repo)["unread"], 2)
        history = self.call("", "history", all=True)["events"]
        self.assertEqual(
            [e["kind"] for e in history if e["actor"] == "a"], ["join", "leave", "join"]
        )

    def test_f2_5_expiry_keeps_ownership_and_requests_and_reports_the_gap(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.call("a", "acquire", sid="a", key="rig")
        req = self.call("a", "request", sid="a", to="b", subject="stays open")
        self.call("a", "send", sid="a", to="b", text="lost to time")
        last = self.co.ledger.last_seq
        self.clock.advance(coord.EVENT_TTL + 1)
        peek = self.call("b", "peek", sid="b")
        self.assertEqual(peek["unread"], 0)
        self.assertEqual(peek["gap"], {"through": last, "reason": "expired"})
        status = self.call("", "status")
        self.assertEqual(status["resources"][0]["owner"], "a")
        self.assertEqual(status["requests"][0]["req_id"], req["req_id"])
        self.assertEqual(
            self.call("a", "send", sid="a", to="b", text="new")["seq"], last + 1
        )
        self.assertIsNone(self.call("b", "peek", sid="b")["gap"])
        second = self.call("a", "request", sid="a", to="b", subject="second")
        self.assertNotEqual(second["req_id"], req["req_id"])

    def test_f2_6_ack_never_resolves_a_request(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        req = self.call("a", "request", sid="a", to="b", subject="rig?")
        events = self.call("b", "catchup", sid="b")["events"]
        self.call("b", "ack", sid="b", through=events[-1]["seq"])
        self.assertEqual(
            self.call("b", "requests", sid="b")["requests"][0]["state"], "open"
        )
        self.call("b", "resolve", sid="b", req_id=req["req_id"], result="done")
        self.assertEqual(self.call("b", "requests", sid="b")["requests"], [])
        with self.assertRaises(coord.CoordError):
            self.call("a", "cancel", sid="a", req_id=req["req_id"])


# ------------------------------------------------------------------ F3 notification


class NotificationTest(Direct):
    def test_failed_codex_queue_reports_stderr_without_hiding_failure(self):
        adapter = coord.CodexAdapter()
        with (
            patch.object(
                coord.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    [], 1, "", "database is readonly"
                ),
            ),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertFalse(adapter.wake({"native_id": "test"}, "test"))
            self.assertIn("exit 1: database is readonly", err.getvalue())
            self.assertIn("database is readonly", adapter.last_wake_error)
        with patch.object(
            coord.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ):
            self.assertTrue(adapter.wake({"native_id": "test"}, "test"))
            self.assertIsNone(adapter.last_wake_error)

    def test_self_and_historical_messages_do_not_schedule_model_work(self):
        self.co.wakes.put(False)
        self.co.waker.join(5)
        self.join("old", self.repo)
        self.call("old", "send", sid="old", to="repo", text="history")
        self.call("old", "leave", sid="old")
        self.join("only", self.repo, client="codex")
        self.call("only", "send", sid="only", to="self", text="own note")
        self.co._wake_pending()
        self.assertFalse(self.codex_log.exists())
        self.assertIsNone(self.call("only", "nudge", sid="only")["text"])
        result = self.call("only", "catchup", sid="only")
        self.assertEqual(
            [e["body"]["text"] for e in result["events"]], ["history", "own note"]
        )
        queued = self.co.wakes.qsize()
        self.call("only", "ack", sid="only", through=result["last_seq"])
        self.assertEqual(self.co.wakes.qsize(), queued)

    def test_running_codex_turn_is_never_queued_and_injected_unread_stays_unqueued(
        self,
    ):
        self.co.wakes.put(False)
        self.co.waker.join(5)
        self.join("sender", self.repo)
        self.join("receiver", self.repo, client="codex")
        self.call(
            "receiver",
            "activity",
            sid="receiver",
            active=True,
            turn_id="turn-1",
        )
        self.call("sender", "send", sid="sender", to="receiver", text="during turn")
        self.co._wake_pending()
        self.assertFalse(self.codex_log.exists())

        nudge = self.call("receiver", "nudge", sid="receiver")
        self.assertIn("1 unread", nudge["text"])
        self.call(
            "receiver",
            "activity",
            sid="receiver",
            active=False,
            turn_id="turn-1",
        )
        self.co._wake_pending()
        self.assertFalse(self.codex_log.exists())

    def test_turn_end_queues_only_unseen_unread_and_stale_stop_cannot_end_new_turn(
        self,
    ):
        self.co.wakes.put(False)
        self.co.waker.join(5)
        self.join("sender", self.repo)
        self.join("receiver", self.repo, client="codex")
        self.call(
            "receiver",
            "activity",
            sid="receiver",
            active=True,
            turn_id="turn-2",
        )
        self.call("sender", "send", sid="sender", to="receiver", text="late arrival")

        stale = self.call(
            "receiver",
            "activity",
            sid="receiver",
            active=False,
            turn_id="turn-1",
        )
        self.assertTrue(stale["turn_active"])
        self.co._wake_pending()
        self.assertFalse(self.codex_log.exists())

        ended = self.call(
            "receiver",
            "activity",
            sid="receiver",
            active=False,
            turn_id="turn-2",
        )
        self.assertFalse(ended["turn_active"])
        self.co._wake_pending()
        self.assertEqual(self.codex_log.read_text().count("--message "), 1)

    def test_wake_rechecks_each_recipient_after_a_slow_transport(self):
        self.co.wakes.put(False)
        self.co.waker.join(5)
        self.join("sender", self.repo)
        for sid in ("first", "acked", "left"):
            self.join(sid, self.repo, client="codex")
        seq = self.call("sender", "send", sid="sender", to="all", text="pending")["seq"]
        calls = []

        def wake(session, text):
            calls.append(session["sid"])
            if session["sid"] == "first":
                self.call("acked", "ack", sid="acked", through=seq)
                self.call("left", "leave", sid="left")
            return True

        with patch.object(coord.ADAPTERS["codex"], "wake", side_effect=wake):
            self.co._wake_pending()
        self.assertEqual(calls, ["first"])

    def test_state_change_still_wakes_after_its_actor_leaves(self):
        self.co.wakes.put(False)
        self.co.waker.join(5)
        self.join("owner", self.repo)
        self.join("waiter", self.repo, client="codex")
        grant = self.call("owner", "acquire", sid="owner", key="rig")
        with self.assertRaises(coord.CoordError):
            self.call("waiter", "acquire", sid="waiter", key="rig")
        self.call(
            "owner",
            "release",
            sid="owner",
            key="rig",
            generation=grant["generation"],
        )
        self.call("owner", "leave", sid="owner")
        with patch.object(coord.ADAPTERS["codex"], "wake", return_value=True) as wake:
            self.co._wake_pending()
            wake.assert_called_once()
            self.assertIn("1 unread", wake.call_args.args[1])

    def test_final_message_wakes_after_its_sender_leaves(self):
        self.co.wakes.put(False)
        self.co.waker.join(5)
        self.join("sender", self.repo)
        self.join("receiver", self.repo, client="codex")
        self.call("sender", "send", sid="sender", to="receiver", text="final result")
        self.call("sender", "leave", sid="sender")

        with patch.object(coord.ADAPTERS["codex"], "wake", return_value=True) as wake:
            self.co._wake_pending()
            wake.assert_called_once()
            prompt = wake.call_args.args[1]
            self.assertIn("1 unread", prompt)
            self.assertIn("final results", prompt)
            self.assertIn("do not reply to those senders", prompt)

        caught = self.call("receiver", "catchup", sid="receiver")
        self.assertIn("sender offline; no reply expected", coord.render_catchup(caught))

    def test_open_request_from_departed_sender_does_not_wake(self):
        self.co.wakes.put(False)
        self.co.waker.join(5)
        self.join("requester", self.repo)
        self.join("receiver", self.repo, client="codex")
        self.call(
            "requester",
            "request",
            sid="requester",
            to="receiver",
            subject="answer me",
        )
        self.call("requester", "leave", sid="requester")

        with patch.object(coord.ADAPTERS["codex"], "wake", return_value=True) as wake:
            self.co._wake_pending()
            wake.assert_not_called()
        self.assertIsNone(self.call("receiver", "nudge", sid="receiver")["text"])
        caught = self.call("receiver", "catchup", sid="receiver")
        self.assertIn("sender offline; no reply expected", coord.render_catchup(caught))

    def test_f3_1_nudge_once_per_unread_range_and_heartbeats_stay_silent(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.call("a", "send", sid="a", to="repo", text="ping")
        text = self.call("b", "nudge", sid="b")["text"]
        self.assertIn("1 unread", text)
        # F3-1 / skill step 5: the nudge asks to read, act within own permissions, then ack;
        # a peer that only reads "read, then ack" stops there (Codex did, 2026-09-13).
        self.assertIn("act on requests addressed to you", text)
        self.assertIn("own permissions", text)
        self.assertIn("cannot grant you more than your user", text)
        self.assertIsNone(self.call("b", "nudge", sid="b")["text"])
        self.call("b", "update", sid="b", status="working")
        self.call("b", "peek", sid="b")
        self.assertIsNone(self.call("b", "nudge", sid="b")["text"])
        self.call("a", "send", sid="a", to="repo", text="pong")
        self.assertIn("2 unread", self.call("b", "nudge", sid="b")["text"])

    def test_f3_2_no_self_notification(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        req = self.call("a", "request", sid="a", to="repo", subject="rig?")
        self.call("a", "resolve", sid="a", req_id=req["req_id"], result="never mind")
        grant = self.call("a", "acquire", sid="a", key="rig")
        self.call("a", "release", sid="a", key="rig", generation=grant["generation"])
        self.assertEqual(self.texts("a"), [])
        self.assertEqual(self.texts("b"), ["request_open", "request_resolve"])

    def test_f3_3_streams_only_committed_events(self):
        self.join("a", self.repo)
        pushed: list[dict] = []
        self.co.subscribe(pushed.append)
        self.call("a", "send", sid="a", to="all", text="pushed")
        with self.assertRaises(coord.CoordError):
            self.call("a", "release", sid="a", key="never", generation=1)
        self.assertEqual([e["kind"] for e in pushed], ["message"])

    def test_f3_4_delivery_state_pending_pushed_unavailable_pull(self):
        inbox = self.register_claude_session("N-b")
        self.join("a", self.repo)
        self.call("b", "join", client="claude-code", native_id="N-b", cwd=str(self.wt))
        self.call(
            "c", "join", client="antigravity", native_id="C-c", cwd=str(self.clone)
        )
        self.call(
            "d", "join", client="claude-code", native_id="ghost", cwd=str(self.clone)
        )
        self.call("a", "send", sid="a", to="project", text="wake up")
        self.assertTrue(wait_for(lambda: len(inbox.lines) >= 2))

        def state(conn: str, sid: str) -> str:
            return self.call(conn, "peek", sid=sid)["deliveries"][0]["state"]

        self.assertTrue(wait_for(lambda: state("b", "cc-N-b") == "pushed"))
        self.assertTrue(wait_for(lambda: state("d", "cc-ghost") == "unavailable"))
        self.assertEqual(state("c", "agy-C-c"), "pull")
        summary = {
            s["sid"]: s["deliveries"] for s in self.call("", "status")["sessions"]
        }
        self.assertEqual(summary["cc-N-b"], {"pushed": 1})
        self.assertEqual(summary["cc-ghost"], {"unavailable": 1})
        self.assertIn("1 unavailable", coord.render_status(self.call("", "status")))
        self.call("b", "ack", sid="cc-N-b", through=self.co.ledger.last_seq)
        self.assertEqual(self.call("b", "peek", sid="cc-N-b")["deliveries"], [])

    def test_f3_5_claude_code_is_woken_through_its_registered_inbox_socket(self):
        inbox = self.register_claude_session("N-b")
        self.join("a", self.repo)
        self.call("b", "join", client="claude-code", native_id="N-b", cwd=str(self.wt))
        self.call("a", "send", sid="a", to="repo", text="hello b")
        self.assertTrue(wait_for(lambda: len(inbox.lines) >= 2))
        auth, message = inbox.lines[:2]
        self.assertEqual(auth, {"type": "auth", "token": "tok-N-b"})
        self.assertEqual(message["type"], "user")
        self.assertEqual(message["message"]["role"], "user")
        self.assertIn("1 unread", message["message"]["content"])
        self.call("a", "send", sid="a", to="repo", text="again")
        time.sleep(0.3)
        self.assertEqual(len(inbox.lines), 2)  # same unread range: one wake only
        self.call("b", "ack", sid="cc-N-b", through=self.co.ledger.last_seq)
        self.call("a", "send", sid="a", to="repo", text="new range")
        self.assertTrue(wait_for(lambda: len(inbox.lines) >= 4, timeout=10))

    def test_f3_6_codex_is_woken_with_codex_queue_and_antigravity_is_pull_only(self):
        self.join("a", self.repo)
        self.call("b", "join", client="codex", native_id="T-1", cwd=str(self.wt))
        self.call(
            "c", "join", client="antigravity", native_id="C-1", cwd=str(self.clone)
        )
        self.call("a", "send", sid="a", to="project", text="wake")
        self.assertTrue(wait_for(lambda: self.codex_log.exists()))
        line = self.codex_log.read_text().strip()
        self.assertTrue(line.startswith("queue --thread T-1 --message "), line)
        caps = {
            s["sid"]: s["capabilities"] for s in self.call("", "status")["sessions"]
        }
        self.assertEqual(
            caps["codex-T-1"], {"notify": "push", "enforcement": "advisory"}
        )
        self.assertEqual(caps["agy-C-1"], {"notify": "pull", "enforcement": "advisory"})


# ------------------------------------------------------------------ F4 resources


class ResourceTest(Direct):
    def test_f4_1_acquire_is_exclusive_and_the_conflict_names_the_owner(self):
        """V2."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.call("a", "acquire", sid="a", key="rig", purpose="soak")
        with self.assertRaises(coord.CoordError) as ctx:
            self.call("b", "acquire", sid="b", key="rig")
        self.assertEqual(ctx.exception.code, -32010)
        self.assertEqual(ctx.exception.data["owner"], "a")
        self.assertEqual(ctx.exception.data["purpose"], "soak")
        self.assertEqual(
            self.call("", "status")["waiters"], [{"key": "rig", "sid": "b"}]
        )

    def test_f4_2_release_needs_owner_and_generation(self):
        """V3."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        first = self.call("a", "acquire", sid="a", key="rig")
        self.assertEqual(self.call("a", "acquire", sid="a", key="rig"), first)
        with self.assertRaises(coord.CoordError):
            self.call(
                "b", "release", sid="b", key="rig", generation=first["generation"]
            )
        with self.assertRaises(coord.CoordError):
            self.call("a", "release", sid="a", key="rig")
        self.call("a", "release", sid="a", key="rig", generation=first["generation"])
        second = self.call("b", "acquire", sid="b", key="rig")
        with self.assertRaises(coord.CoordError):
            self.call(
                "a", "release", sid="a", key="rig", generation=first["generation"]
            )
        self.assertEqual(
            self.call("", "status")["resources"][0]["generation"], second["generation"]
        )

    def test_f4_3_leave_marks_unconfirmed_and_force_needs_a_user_action(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.call("a", "acquire", sid="a", key="rig")
        self.call("a", "leave", sid="a")
        self.assertEqual(
            self.call("", "status")["resources"][0]["state"], "unconfirmed"
        )
        with self.assertRaises(coord.CoordError):
            self.call("b", "acquire", sid="b", key="rig")
        with self.assertRaises(coord.CoordError):
            self.call("b", "force_release", key="rig", reason="stale")
        with self.assertRaises(coord.CoordError):
            self.call("user", "force_release", key="rig", user_action=True)
        forced = self.call(
            "user", "force_release", key="rig", reason="owner gone", user_action=True
        )
        self.assertEqual(forced["previous_owner"], "a")
        event = self.call("", "history", all=True)["events"][-1]
        self.assertEqual(
            (event["actor"], event["body"]["reason"]), ("user", "owner gone")
        )
        self.call("b", "acquire", sid="b", key="rig")

    def test_f4_4_forced_out_owner_must_read_the_notice_before_retaking(self):
        self.join("a", self.repo)
        self.call("a", "acquire", sid="a", key="rig")
        self.call("user", "force_release", key="rig", reason="stop", user_action=True)
        with self.assertRaises(coord.CoordError):
            self.call("a", "acquire", sid="a", key="rig")
        notice = self.call("a", "catchup", sid="a")["events"][-1]
        self.assertEqual(notice["kind"], "force_release")
        self.call("a", "ack", sid="a", through=notice["seq"])
        self.call("a", "acquire", sid="a", key="rig")

    def test_f4_5_resource_transfer_then_accept_flips_the_owner_once(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.join("c", self.clone)
        grant = self.call("a", "acquire", sid="a", key="rig")
        self.call("a", "resource_transfer", sid="a", key="rig", to="b")
        self.assertEqual(self.call("", "status")["resources"][0]["owner"], "a")
        with self.assertRaises(coord.CoordError):
            self.call("c", "resource_accept", sid="c", key="rig")
        accepted = self.call("b", "resource_accept", sid="b", key="rig")
        self.assertEqual((accepted["owner"], accepted["previous_owner"]), ("b", "a"))
        self.assertGreater(accepted["generation"], grant["generation"])
        with self.assertRaises(coord.CoordError):
            self.call(
                "a", "release", sid="a", key="rig", generation=grant["generation"]
            )
        self.assertEqual(self.texts("b")[-1], "transfer_propose")
        self.assertEqual(self.texts("a")[-1], "transfer_accept")

    def test_f4_6_declaration_is_visible_but_never_blocks_acquire(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.call("a", "declare", sid="a", key="rig", purpose="reading logs")
        listing = self.call("", "resources")["resources"]
        self.assertEqual(
            listing[0]["declared_by"], [{"sid": "a", "purpose": "reading logs"}]
        )
        self.call("b", "acquire", sid="b", key="rig")


# ------------------------------------------------------------------ F5 worktrees


class WorktreeTest(Direct):
    def test_f5_1_claim_is_exclusive_and_membership_checked(self):
        """V8 first half."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.join("d", self.other)
        self.call("a", "worktree_claim", sid="a", path=str(self.wt), enforce=True)
        with self.assertRaises(coord.CoordError):
            self.call("b", "worktree_claim", sid="b", path=str(self.wt))
        with self.assertRaises(coord.CoordError):
            self.call("d", "worktree_claim", sid="d", path=str(self.wt))
        with self.assertRaises(coord.CoordError):
            self.call("a", "worktree_claim", sid="a", path="relative/path")

    def test_f5_2_create_plans_first_and_refuses_a_foreign_dir(self):
        self.join("a", self.repo)
        plan = self.call("a", "worktree_create", sid="a", name="x1", dry_run=True)
        self.assertEqual(plan["target"], str(self.tmp / "worktrees" / "repo" / "x1"))
        self.assertEqual(plan["base"], git("rev-parse", "HEAD", cwd=str(self.repo)))
        self.assertFalse(os.path.exists(plan["target"]))
        created = self.call("a", "worktree_create", sid="a", name="x1")
        self.assertTrue(created["created"])
        self.assertEqual(created["base"], plan["base"])
        self.assertEqual(git("rev-parse", "HEAD", cwd=created["path"]), plan["base"])
        with self.assertRaises(coord.CoordError):
            self.call(
                "a",
                "worktree_create",
                sid="a",
                name="x9",
                root=str(self.tmp / "anywhere"),
            )
        with self.assertRaises(coord.CoordError):
            self.call(
                "a", "worktree_create", sid="a", name="x9", base="--output=/tmp/x"
            )
        foreign = self.tmp / "worktrees" / "repo" / "taken"
        foreign.mkdir(parents=True)
        with self.assertRaises(coord.CoordError):
            self.call("a", "worktree_create", sid="a", name="taken")
        self.assertTrue(foreign.exists())

    def test_f5_2_existing_branch_reports_its_real_tip(self):
        self.join("a", self.repo)
        git("branch", "old", "HEAD", cwd=str(self.repo))
        (self.repo / "later").write_text("y\n")
        git("add", "later", cwd=str(self.repo))
        git("commit", "-q", "-m", "later", cwd=str(self.repo))
        old_tip = git("rev-parse", "old", cwd=str(self.repo))
        with self.assertRaises(coord.CoordError):
            self.call("a", "worktree_create", sid="a", name="old", base="HEAD")
        created = self.call("a", "worktree_create", sid="a", name="old")
        self.assertEqual(created["base"], old_tip)

    def test_f5_3_partial_failure_deletes_nothing_and_resumes(self):
        """V11."""
        self.join("a", self.repo)
        target = self.tmp / "worktrees" / "repo" / "x2"
        git("branch", "x2", cwd=str(self.repo))
        git("worktree", "add", "-q", str(target), "x2", cwd=str(self.repo))
        resumed = self.call("a", "worktree_create", sid="a", name="x2")
        self.assertEqual((resumed["created"], resumed["resumed"]), (False, True))
        self.assertTrue((target / "README").exists())

    def test_f5_4_transfer_accept_flips_once_and_the_old_owner_is_refused(self):
        """V8 second half."""
        self.join("a", self.repo)
        self.join("b", self.wt)
        self.call("a", "worktree_claim", sid="a", path=str(self.wt))
        self.call(
            "a", "worktree_transfer", sid="a", path=str(self.wt), to="b", note="yours"
        )
        self.assertEqual(self.call("", "status")["worktrees"][0]["owner"], "a")
        accepted = self.call("b", "worktree_accept", sid="b", path=str(self.wt))
        self.assertEqual(accepted["previous_owner"], "a")
        with self.assertRaises(coord.CoordError):
            self.call("a", "worktree_release", sid="a", path=str(self.wt))
        self.assertEqual(
            self.call("b", "whoami", sid="b")["session"]["edit_worktree"], str(self.wt)
        )
        self.assertIsNone(self.call("a", "whoami", sid="a")["session"]["edit_worktree"])

    def test_f5_5_edit_gate_denies_same_repo_foreign_checkouts_only(self):
        """V9."""
        self.join("a", self.repo, client="claude-code")
        self.call("a", "worktree_claim", sid="a", path=str(self.wt), enforce=True)

        def allowed(path: str) -> bool:
            return self.call("a", "edit_check", sid="a", path=path)["allow"]

        self.assertFalse(allowed(str(self.repo / "README")))
        self.assertTrue(allowed(str(self.wt / "README")))
        self.assertTrue(allowed("/tmp/scratch.txt"))
        self.assertTrue(allowed(str(self.other / "README")))
        self.assertFalse(allowed("README"))

    def test_f5_6_enforcement_level_follows_the_client_capability(self):
        self.join("a", self.repo, client="claude-code")
        self.join("b", self.wt, client="codex")
        self.call("a", "worktree_claim", sid="a", path=str(self.repo), enforce=True)
        self.call("b", "worktree_claim", sid="b", path=str(self.wt), enforce=True)
        levels = {
            w["owner"]: w["enforcement"] for w in self.call("", "status")["worktrees"]
        }
        self.assertEqual(levels, {"a": "enforced", "b": "advisory"})


# ------------------------------------------------------------------ F6 / F7


class StatusAndBoundaryTest(Direct):
    def test_f6_1_status_separates_report_from_observation_and_lists_waiters(self):
        self.join("a", self.repo, client="claude-code")
        self.call("a", "update", sid="a", status="working", task="soak")
        self.clock.advance(40 * 60)
        self.call("a", "attach", sid="a", native_id="a")
        status = self.call("", "status")
        session = status["sessions"][0]
        self.assertEqual(session["status"], "working")
        self.assertEqual(session["updated_ago"], "40 min")
        self.assertEqual(session["seen_ago"], "0 sec")
        self.assertEqual(
            session["capabilities"], {"notify": "push", "enforcement": "enforced"}
        )
        self.assertEqual(status["service"]["home"], str(self.home))
        self.assertIn("retained", status["service"])
        text = coord.render_status(status)
        self.assertIn("seen", text)
        self.assertIn("enforced", text)

    def test_f7_1_a_caller_acts_only_as_its_registered_session(self):
        self.join("a", self.repo)
        self.join("b", self.wt)
        grant = self.call("a", "acquire", sid="a", key="rig")
        with self.assertRaises(coord.CoordError) as ctx:
            self.call(
                "b", "release", sid="a", key="rig", generation=grant["generation"]
            )
        self.assertEqual(ctx.exception.code, -32001)
        with self.assertRaises(coord.CoordError):
            self.call("x", "leave", sid="a")
        token = self.call("a", "whoami", sid="a")["session"]["token"]
        self.call("x", "attach", sid="a", token=token)
        self.call("x", "release", sid="a", key="rig", generation=grant["generation"])
        with self.assertRaises(coord.CoordError):
            self.call("y", "attach", sid="a", native_id="wrong")

    def test_f7_3_lost_singleton_race_fails_clearly(self):
        """4.2 / V2: the second daemon exits non-zero and never opens a second ledger."""
        daemon = Daemon(self.home)
        self.addCleanup(daemon.stop)
        err = io.StringIO()
        self.assertEqual(coord.serve(self.home, err), 1)
        self.assertIn("another daemon", err.getvalue())


# ------------------------------------------------------------------ scenarios over the wire


class Daemon:
    """In-process daemon on a private home; stop() shuts it down and keeps the ledger."""

    def __init__(self, home: Path):
        self.home = home
        self.log = io.StringIO()
        self.start()

    def start(self) -> None:
        ready = threading.Event()
        self.thread = threading.Thread(
            target=coord.serve, args=(self.home, self.log, ready), daemon=True
        )
        self.thread.start()
        assert ready.wait(5), "daemon did not start"

    def client(self) -> Any:
        return coord.Client(self.home / "coord.sock", autostart=False)

    def stop(self) -> None:
        if not self.thread.is_alive():
            return
        client = self.client()
        client.call("shutdown")
        client.close()
        self.thread.join(5)


class ScenarioTest(Fixture):
    """Chapter 3 workflow and V1 / V5 / V10 / V12 / V13 over the real transport."""

    def setUp(self) -> None:
        super().setUp()
        self.daemon = Daemon(self.home)
        self.addCleanup(self.daemon.stop)

    def join(self, sid: str, cwd: Path, **extra: Any) -> tuple[Any, dict]:
        client = self.daemon.client()
        self.addCleanup(client.close)
        joined = client.call(
            "join", sid=sid, client="test", cwd=str(cwd), native_id=sid, **extra
        )
        return client, joined

    def test_chapter3_workflow_two_sessions_and_a_user(self):
        """3.1-3.6 and V1 / V12: enable, register worktrees, contend for a machine, request, release, catch up, hand over."""
        a, ja = self.join("a", self.repo)
        b, jb = self.join("b", self.wt)
        c, jc = self.join("c", self.clone)
        d, jd = self.join("d", self.other)
        self.assertEqual(ja["session"]["common_dir"], jb["session"]["common_dir"])
        self.assertEqual(ja["session"]["project"], "github.com/example/repo")
        self.assertNotEqual(ja["session"]["common_dir"], jc["session"]["common_dir"])
        self.assertEqual(ja["session"]["project"], jc["session"]["project"])
        self.assertNotEqual(ja["session"]["project"], jd["session"]["project"])
        a.call("update", sid="a", task="soak test")
        a.call("worktree_claim", sid="a", path=str(self.repo))
        b.call("worktree_claim", sid="b", path=str(self.wt), enforce=True)
        user = self.daemon.client()
        self.addCleanup(user.close)
        self.assertEqual(
            {w["owner"] for w in user.call("status")["worktrees"]}, {"a", "b"}
        )
        grant = a.call("acquire", sid="a", key="machine-1", purpose="soak")
        with self.assertRaises(coord.CoordError):
            b.call("acquire", sid="b", key="machine-1")
        req = b.call(
            "request",
            sid="b",
            to="a",
            subject="machine-1 after you",
            resource="machine-1",
        )
        unread = a.call("catchup", sid="a")["events"]
        self.assertEqual(unread[-1]["body"]["req_id"], req["req_id"])
        a.call("release", sid="a", key="machine-1", generation=grant["generation"])
        self.assertIn(
            "release", [e["kind"] for e in b.call("catchup", sid="b")["events"]]
        )
        b.call("acquire", sid="b", key="machine-1")
        a.call("resolve", sid="a", req_id=req["req_id"], result="released")
        self.assertEqual(user.call("status")["resources"][0]["owner"], "b")
        b.call("worktree_transfer", sid="b", path=str(self.wt), to="c")
        c.call("worktree_accept", sid="c", path=str(self.wt))
        owners = {w["path"]: w["owner"] for w in user.call("status")["worktrees"]}
        self.assertEqual(owners[str(self.wt)], "c")

    def test_v5_catchup_recovers_when_the_wake_channel_fails(self):
        """V5: the wake push fails (no registry entry); the unread survive for catchup and ownership ops never wait."""
        a, _ = self.join("a", self.repo)
        b = self.daemon.client()
        self.addCleanup(b.close)
        b.call("join", client="claude-code", native_id="ghost", cwd=str(self.wt))
        a.call("send", sid="a", to="repo", text="nobody home")
        a.call("acquire", sid="a", key="rig")
        events = b.call("catchup", sid="cc-ghost")["events"]
        self.assertEqual(events[-1]["body"]["text"], "nobody home")
        self.assertTrue(
            wait_for(
                lambda: (
                    b.call("peek", sid="cc-ghost")["deliveries"][-1]["state"]
                    == "unavailable"
                )
            )
        )

    def test_v10_unreachable_daemon_is_diagnosed_without_a_second_ledger(self):
        self.daemon.stop()
        with self.assertRaises(coord.CoordError) as ctx:
            coord.Client(self.home / "coord.sock", autostart=False)
        self.assertIn("not running", str(ctx.exception))
        self.assertFalse((self.home / "coord.sock").exists())

    def test_v13_restart_keeps_state_and_reports_version(self):
        a, _ = self.join("a", self.repo)
        a.call("acquire", sid="a", key="rig")
        a.close()
        self.daemon.stop()
        self.daemon.start()
        c = self.daemon.client()
        self.addCleanup(c.close)
        self.assertEqual(c.call("ping")["version"], coord.VERSION)
        self.assertEqual(c.call("status")["resources"][0]["owner"], "a")

    def test_watch_stream_delivers_every_event_in_order(self):
        a, _ = self.join("a", self.repo)
        watcher = self.daemon.client()
        self.addCleanup(watcher.close)
        watcher.call("subscribe")
        for i in range(3):
            a.call("send", sid="a", to="all", text=f"e{i}")
        seen = [
            json.loads(watcher.file.readline())["params"]["body"]["text"]
            for _ in range(3)
        ]
        self.assertEqual(seen, ["e0", "e1", "e2"])


# ------------------------------------------------------------------ adapters: hooks and MCP


class HookTest(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.daemon = Daemon(self.home)
        self.addCleanup(self.daemon.stop)
        os.environ["AGENT_COORD_NO_AUTOSTART"] = "1"
        self.addCleanup(os.environ.pop, "AGENT_COORD_NO_AUTOSTART", None)

    def hook(self, client: str, event: str, payload: dict) -> dict | None:
        out = io.StringIO()
        env = (
            {"CODEX_THREAD_ID": str(payload.get("session_id") or "")}
            if client == "codex"
            else {}
        )
        with patch.dict(os.environ, env):
            rc = coord.hook_main(client, event, io.StringIO(json.dumps(payload)), out)
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue()) if out.getvalue().strip() else None

    def codex_hook_as(
        self, actual_thread: str, event: str, payload: dict
    ) -> dict | None:
        out = io.StringIO()
        with patch.dict(os.environ, {"CODEX_THREAD_ID": actual_thread}):
            rc = coord.hook_main("codex", event, io.StringIO(json.dumps(payload)), out)
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue()) if out.getvalue().strip() else None

    def peer_posts(self, text: str) -> None:
        peer = self.daemon.client()
        self.addCleanup(peer.close)
        peer.call("join", sid="p", client="test", cwd=str(self.repo), native_id="p")
        peer.call("send", sid="p", to="repo", text=text)

    def test_codex_plugin_keeps_the_explicit_trusted_hook_path(self):
        plugin = Path(__file__).resolve().parent / "agent_plugins" / "agent-coord"
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["hooks"], "./hooks/codex.json")
        self.assertEqual(manifest["mcpServers"], "./mcp/codex.json")
        hooks = json.loads((plugin / "hooks" / "codex.json").read_text())["hooks"]
        self.assertIn("UserPromptSubmit", hooks)
        self.assertIn("Stop", hooks)
        self.assertIn("Interrupt", hooks)
        self.assertFalse((plugin / "hooks" / "hooks.json").exists())

    def queued_wake(self):
        self.hook(
            "codex", "SessionStart", {"session_id": "wake-test", "cwd": str(self.wt)}
        )
        me = self.daemon.client()
        self.addCleanup(me.close)
        me.call("attach", sid="codex-wake-test", native_id="wake-test")
        # The fixture's codex executable captures the actual producer command;
        # no real session or model is started by these tests.
        self.peer_posts("please handle this")
        self.assertTrue(
            wait_for(
                lambda: (
                    self.codex_log.exists() and "wake v1" in self.codex_log.read_text()
                )
            )
        )
        self.assertTrue(
            wait_for(
                lambda: (
                    me.call("peek", sid="codex-wake-test")["deliveries"][0]["state"]
                    == "pushed"
                )
            )
        )
        prompt = self.codex_log.read_text().split("--message ", 1)[1].strip()
        seq = me.call("peek", sid="codex-wake-test")["last_seq"]
        return me, prompt, seq

    def submit_wake(self, prompt):
        return self.hook(
            "codex",
            "UserPromptSubmit",
            {"session_id": "wake-test", "cwd": str(self.wt), "prompt": prompt},
        )

    def test_autonomous_wake_is_admitted_once_and_next_new_message_wakes_again(self):
        me, prompt, seq = self.queued_wake()
        self.assertIn(
            "1 unread",
            self.submit_wake(prompt)["hookSpecificOutput"]["additionalContext"],
        )
        self.assertEqual(self.submit_wake(prompt)["decision"], "block")
        me.call("ack", sid="codex-wake-test", through=seq)
        self.hook(
            "codex",
            "Stop",
            {"session_id": "wake-test", "cwd": str(self.wt)},
        )
        self.peer_posts("next task")
        self.assertTrue(
            wait_for(lambda: self.codex_log.read_text().count("--message ") == 2)
        )
        next_prompt = (
            self.codex_log.read_text().splitlines()[-1].split("--message ", 1)[1]
        )
        # Rejecting the old queued prompt must not consume the new notification.
        self.assertEqual(self.submit_wake(prompt)["decision"], "block")
        self.assertIn(
            "1 unread",
            self.submit_wake(next_prompt)["hookSpecificOutput"]["additionalContext"],
        )
        self.assertEqual(
            me.call("whoami", sid="codex-wake-test")["session"]["capabilities"][
                "notify"
            ],
            "push",
        )

    def test_active_turn_uses_hook_context_without_leaving_a_queued_prompt(self):
        self.hook(
            "codex", "SessionStart", {"session_id": "active", "cwd": str(self.wt)}
        )
        me = self.daemon.client()
        self.addCleanup(me.close)
        me.call("attach", sid="codex-active", native_id="active")
        self.assertIsNone(
            self.hook(
                "codex",
                "UserPromptSubmit",
                {
                    "session_id": "active",
                    "cwd": str(self.wt),
                    "turn_id": "turn-active",
                    "prompt": "ordinary user work",
                },
            )
        )
        self.assertTrue(me.call("whoami", sid="codex-active")["session"]["turn_active"])

        self.peer_posts("arrived during the turn")
        self.assertTrue(
            wait_for(
                lambda: (
                    me.call("peek", sid="codex-active")["deliveries"][0]["state"]
                    == "pending"
                )
            )
        )
        self.assertFalse(self.codex_log.exists())
        surfaced = self.hook(
            "codex",
            "PostToolUse",
            {
                "session_id": "active",
                "cwd": str(self.wt),
                "turn_id": "turn-active",
                "tool_name": "Bash",
            },
        )
        self.assertIn("1 unread", surfaced["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(
            self.hook(
                "codex",
                "Stop",
                {
                    "session_id": "active",
                    "cwd": str(self.wt),
                    "turn_id": "turn-active",
                },
            ),
            {"continue": True},
        )
        time.sleep(0.1)
        self.assertFalse(self.codex_log.exists())

    def test_stop_queues_an_event_that_arrived_after_the_last_turn_hook(self):
        self.hook("codex", "SessionStart", {"session_id": "late", "cwd": str(self.wt)})
        me = self.daemon.client()
        self.addCleanup(me.close)
        me.call("attach", sid="codex-late", native_id="late")
        self.hook(
            "codex",
            "UserPromptSubmit",
            {
                "session_id": "late",
                "cwd": str(self.wt),
                "turn_id": "turn-late",
                "prompt": "ordinary user work",
            },
        )
        self.peer_posts("arrived after the last tool")
        time.sleep(0.1)
        self.assertFalse(self.codex_log.exists())
        self.assertEqual(
            self.hook(
                "codex",
                "Stop",
                {
                    "session_id": "late",
                    "cwd": str(self.wt),
                    "turn_id": "turn-late",
                },
            ),
            {"continue": True},
        )
        self.assertTrue(wait_for(lambda: self.codex_log.exists()))
        self.assertEqual(self.codex_log.read_text().count("--message "), 1)

    def test_compaction_keeps_the_turn_active_and_surfaces_unread_without_queueing(
        self,
    ):
        self.hook(
            "codex", "SessionStart", {"session_id": "compact", "cwd": str(self.wt)}
        )
        me = self.daemon.client()
        self.addCleanup(me.close)
        me.call("attach", sid="codex-compact", native_id="compact")
        self.hook(
            "codex",
            "UserPromptSubmit",
            {
                "session_id": "compact",
                "cwd": str(self.wt),
                "turn_id": "turn-compact",
                "prompt": "long running work",
            },
        )
        self.peer_posts("arrived before automatic compaction")
        compact = self.hook(
            "codex",
            "SessionStart",
            {
                "session_id": "compact",
                "cwd": str(self.wt),
                "source": "compact",
            },
        )
        context = compact["hookSpecificOutput"]["additionalContext"]
        self.assertIn("1 unread event", context)
        self.assertTrue(
            me.call("whoami", sid="codex-compact")["session"]["turn_active"]
        )
        self.assertEqual(
            self.hook(
                "codex",
                "Stop",
                {
                    "session_id": "compact",
                    "cwd": str(self.wt),
                    "turn_id": "turn-compact",
                },
            ),
            {"continue": True},
        )
        time.sleep(0.1)
        self.assertFalse(self.codex_log.exists())

    def test_ack_after_enqueue_blocks_empty_catchup_before_model_execution(self):
        me, prompt, seq = self.queued_wake()
        me.call("ack", sid="codex-wake-test", through=seq)
        self.assertEqual(me.call("catchup", sid="codex-wake-test")["events"], [])
        for _ in range(3):
            self.assertEqual(self.submit_wake(prompt)["decision"], "block")
        self.assertEqual(self.codex_log.read_text().count("--message "), 1)

    def test_legacy_queue_backlog_is_blocked_but_quoted_user_text_is_not(self):
        me, prompt, seq = self.queued_wake()
        legacy = coord.WAKE_RE.fullmatch(prompt)[3]
        me.call("ack", sid="codex-wake-test", through=seq)
        self.assertEqual(self.submit_wake(legacy)["decision"], "block")
        self.assertIsNone(self.submit_wake("Explain this notification:\n" + legacy))
        self.assertIsNone(self.submit_wake("continue working"))

    def test_peer_leaves_after_enqueue_dying_message_survives_without_reply(self):
        me, prompt, seq = self.queued_wake()
        peer = self.daemon.client()
        self.addCleanup(peer.close)
        peer.call("attach", sid="p", native_id="p")
        peer.call("leave", sid="p")
        admitted = self.submit_wake(prompt)
        context = admitted["hookSpecificOutput"]["additionalContext"]
        self.assertIn("final results", context)
        self.assertIn("do not reply to those senders", context)
        result = me.call("catchup", sid="codex-wake-test")
        self.assertIn("please handle this", coord.render_catchup(result))
        self.assertIn("no reply expected", coord.render_catchup(result))
        me.call("ack", sid="codex-wake-test", through=seq)
        self.assertEqual(self.codex_log.read_text().count("--message "), 1)

    def test_unverifiable_wake_is_blocked_without_affecting_normal_prompts(self):
        _, prompt, _ = self.queued_wake()
        self.assertEqual(self.submit_wake(prompt + " tampered")["decision"], "block")
        with patch.object(coord, "Client", side_effect=coord.CoordError("offline")):
            self.assertEqual(self.submit_wake(prompt)["decision"], "block")
            self.assertIsNone(self.submit_wake("ordinary user instruction"))

    def test_subagent_hook_uses_child_thread_and_never_consumes_parent_inbox(self):
        parent = self.daemon.client()
        child = self.daemon.client()
        self.addCleanup(parent.close)
        self.addCleanup(child.close)
        parent.call("join", client="codex", native_id="parent", cwd=str(self.repo))
        child.call("join", client="codex", native_id="child", cwd=str(self.repo))
        seq = child.call(
            "send", sid="codex-child", to="codex-parent", text="child result"
        )["seq"]

        # Codex documents that a subagent hook payload reports the parent
        # session_id. Its process environment carries the actual child thread.
        subagent = self.codex_hook_as(
            "child",
            "UserPromptSubmit",
            {
                "session_id": "parent",
                "cwd": str(self.repo),
                "prompt": "ordinary child work",
            },
        )
        self.assertIsNone(subagent)
        self.assertEqual(child.call("peek", sid="codex-child")["unread"], 0)
        self.assertEqual(parent.call("peek", sid="codex-parent")["last_seq"], seq)

        root = self.codex_hook_as(
            "parent",
            "UserPromptSubmit",
            {
                "session_id": "parent",
                "cwd": str(self.repo),
                "prompt": "ordinary root work",
            },
        )
        self.assertIn("1 unread", root["hookSpecificOutput"]["additionalContext"])

    def test_subagent_lifecycle_records_exact_parent_and_stops_exact_child(self):
        for root in ("root-a", "root-b"):
            self.hook(
                "codex",
                "SessionStart",
                {"session_id": root, "cwd": str(self.repo)},
            )

        started = self.hook(
            "codex",
            "SubagentStart",
            {
                "session_id": "root-a",
                "agent_id": "child-a",
                "agent_type": "worker",
                "cwd": str(self.repo),
            },
        )
        self.assertIn(
            "Parent: codex-root-a",
            started["hookSpecificOutput"]["additionalContext"],
        )
        self.hook(
            "codex",
            "SubagentStart",
            {
                "session_id": "root-b",
                "agent_id": "child-b",
                "agent_type": "worker",
                "cwd": str(self.repo),
            },
        )

        observer = self.daemon.client()
        self.addCleanup(observer.close)
        sessions = {s["sid"]: s for s in observer.call("sessions")["sessions"]}
        self.assertEqual(sessions["codex-child-a"]["parent_sid"], "codex-root-a")
        self.assertEqual(sessions["codex-child-b"]["parent_sid"], "codex-root-b")
        with self.assertRaisesRegex(coord.CoordError, "already owned by codex-root-a"):
            observer.call(
                "join",
                client="codex",
                native_id="child-a",
                cwd=str(self.repo),
                parent_sid="codex-root-b",
            )

        child = self.daemon.client()
        parent = self.daemon.client()
        self.addCleanup(child.close)
        self.addCleanup(parent.close)
        child.call("attach", sid="codex-child-a", native_id="child-a")
        parent.call("attach", sid="codex-root-a", native_id="root-a")
        seq = child.call(
            "send",
            sid="codex-child-a",
            to="codex-root-a",
            text="final child result",
        )["seq"]
        self.assertTrue(
            wait_for(
                lambda: (
                    self.codex_log.exists() and "wake v1" in self.codex_log.read_text()
                )
            )
        )
        prompt = self.codex_log.read_text().split("--message ", 1)[1].strip()

        stopped = self.hook(
            "codex",
            "SubagentStop",
            {
                "session_id": "root-a",
                "agent_id": "child-a",
                "agent_type": "worker",
                "cwd": str(self.repo),
            },
        )
        self.assertEqual(stopped, {"continue": True})
        sessions = {s["sid"]: s for s in observer.call("sessions")["sessions"]}
        self.assertIsNotNone(sessions["codex-child-a"]["left_at"])
        self.assertIsNone(sessions["codex-root-a"]["left_at"])

        admitted = self.codex_hook_as(
            "root-a",
            "UserPromptSubmit",
            {
                "session_id": "root-a",
                "cwd": str(self.repo),
                "prompt": prompt,
            },
        )
        context = admitted["hookSpecificOutput"]["additionalContext"]
        self.assertIn("final results", context)
        self.assertIn("do not reply to those senders", context)
        caught = parent.call("catchup", sid="codex-root-a")
        self.assertEqual(caught["last_seq"], seq)
        self.assertIn("sender offline; no reply expected", coord.render_catchup(caught))

    def test_f8_1_claude_code_hooks_join_nudge_and_deny(self):
        start = self.hook(
            "claude-code", "SessionStart", {"session_id": "s1", "cwd": str(self.wt)}
        )
        self.assertIn(
            "joined as cc-s1", start["hookSpecificOutput"]["additionalContext"]
        )
        self.peer_posts("look")
        prompt = self.hook(
            "claude-code", "UserPromptSubmit", {"session_id": "s1", "cwd": str(self.wt)}
        )
        self.assertIn("1 unread", prompt["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.hook("claude-code", "PostToolUse", {"session_id": "s1"}))
        me = self.daemon.client()
        self.addCleanup(me.close)
        me.call("attach", sid="cc-s1", native_id="s1")
        me.call("worktree_claim", sid="cc-s1", path=str(self.wt), enforce=True)
        deny = self.hook(
            "claude-code",
            "PreToolUse",
            {
                "session_id": "s1",
                "tool_name": "Edit",
                "tool_input": {"file_path": str(self.repo / "README")},
            },
        )
        self.assertEqual(deny["hookSpecificOutput"]["permissionDecision"], "deny")
        allow = self.hook(
            "claude-code",
            "PreToolUse",
            {
                "session_id": "s1",
                "tool_name": "Write",
                "tool_input": {"file_path": str(self.wt / "new")},
            },
        )
        self.assertIsNone(allow)
        self.hook("claude-code", "SessionEnd", {"session_id": "s1"})
        gone = [s for s in me.call("status")["sessions"] if s["sid"] == "cc-s1"][0]
        self.assertEqual((gone["status"], gone["left_at"] is not None), ("done", True))

    def test_f8_1_codex_hooks_parse_apply_patch_paths(self):
        self.hook("codex", "SessionStart", {"session_id": "t1", "cwd": str(self.wt)})
        me = self.daemon.client()
        self.addCleanup(me.close)
        me.call("attach", sid="codex-t1", native_id="t1")
        me.call("worktree_claim", sid="codex-t1", path=str(self.wt), enforce=True)
        patch = (
            f"*** Begin Patch\n*** Update File: {self.repo / 'README'}\n@@\n-x\n+y\n"
            "*** End Patch\n"
        )
        deny = self.hook(
            "codex",
            "PreToolUse",
            {
                "session_id": "t1",
                "cwd": str(self.wt),
                "tool_name": "apply_patch",
                "tool_input": {"command": patch},
            },
        )
        self.assertEqual(deny["hookSpecificOutput"]["permissionDecision"], "deny")
        relative = "*** Begin Patch\n*** Add File: notes.md\n+hi\n*** End Patch\n"
        allow = self.hook(
            "codex",
            "PreToolUse",
            {
                "session_id": "t1",
                "cwd": str(self.wt),
                "tool_name": "apply_patch",
                "tool_input": {"command": relative},
            },
        )
        self.assertIsNone(allow)

    def test_f8_1_antigravity_hooks_speak_its_own_schema(self):
        payload = {"conversationId": "c1", "workspacePaths": [str(self.wt)]}
        first = self.hook(
            "antigravity", "PreInvocation", {**payload, "invocationNum": 0}
        )
        self.assertIn("joined as agy-c1", first["injectSteps"][0]["ephemeralMessage"])
        me = self.daemon.client()
        self.addCleanup(me.close)
        me.call("attach", sid="agy-c1", native_id="c1")
        me.call("worktree_claim", sid="agy-c1", path=str(self.wt), enforce=True)
        deny = self.hook(
            "antigravity",
            "PreToolUse",
            {
                **payload,
                "toolCall": {
                    "name": "write_to_file",
                    "args": {"TargetFile": str(self.repo / "README")},
                },
            },
        )
        self.assertEqual(deny["decision"], "deny")
        quiet = self.hook(
            "antigravity", "PreInvocation", {**payload, "invocationNum": 1}
        )
        self.assertEqual(quiet, {})
        self.peer_posts("look")
        nudge = self.hook(
            "antigravity", "PreInvocation", {**payload, "invocationNum": 2}
        )
        self.assertIn("1 unread", nudge["injectSteps"][0]["ephemeralMessage"])


class McpTest(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.daemon = Daemon(self.home)
        self.addCleanup(self.daemon.stop)

    def rpc(
        self, adapter: Any, req_id: int, method: str, params: dict | None = None
    ) -> dict:
        return adapter.dispatch(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        )

    def test_mcp_1_adapter_survives_bad_calls_and_keeps_one_identity(self):
        client = self.daemon.client()
        self.addCleanup(client.close)
        adapter = coord.McpAdapter(
            client, coord.Identity("claude-code", "m1", str(self.wt))
        )
        init = self.rpc(adapter, 1, "initialize", {"protocolVersion": "2025-11-25"})
        self.assertEqual(init["result"]["protocolVersion"], "2025-11-25")
        tools = {
            t["name"] for t in self.rpc(adapter, 2, "tools/list")["result"]["tools"]
        }
        self.assertIn("send", tools)
        self.assertNotIn("force_release", tools)
        who = self.rpc(adapter, 3, "tools/call", {"name": "whoami", "arguments": {}})
        self.assertIn("cc-m1", who["result"]["content"][0]["text"])
        hijack = self.rpc(
            adapter,
            4,
            "tools/call",
            {"name": "update", "arguments": {"sid": "someone-else", "status": "done"}},
        )
        self.assertFalse(hijack["result"]["isError"])
        self.assertEqual(
            client.call("whoami", sid="cc-m1")["session"]["status"], "done"
        )
        bad = self.rpc(
            adapter,
            5,
            "tools/call",
            {
                "name": "worktree",
                "arguments": {"action": "force_release", "path": "/x"},
            },
        )
        self.assertTrue(bad["result"]["isError"])
        odd = self.rpc(
            adapter,
            6,
            "tools/call",
            {"name": "send", "arguments": {"text": ["not", "a", "string"]}},
        )
        self.assertTrue(odd["result"]["isError"])
        self.assertEqual(self.rpc(adapter, 7, "ping")["result"], {})

    def test_mcp_2_codex_tool_call_binds_to_the_hook_thread(self):
        """MCP-2 / openai/codex#19937 + #18093: the Codex MCP subprocess has no thread id in
        its env, so run_mcp must not eager-join an anon session; each tool call's
        _meta.threadId binds it to codex-<thread>, the session its SessionStart hook joined,
        keeping pushes and catchup/ack on one identity."""
        hook_client = self.daemon.client()
        self.addCleanup(hook_client.close)
        hook_client.call("join", client="codex", native_id="th1", cwd=str(self.wt))
        sender = self.daemon.client()
        self.addCleanup(sender.close)
        sender.call(
            "join", sid="peer", client="test", native_id="peer", cwd=str(self.wt)
        )
        seq = sender.call("send", sid="peer", to="codex-th1", text="for the thread")[
            "seq"
        ]
        calls = (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "whoami",
                    "arguments": {},
                    "_meta": {"threadId": "th1"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "catchup",
                    "arguments": {},
                    "_meta": {"threadId": "th1"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "ack",
                    "arguments": {"through": seq},
                    "_meta": {"threadId": "th1"},
                },
            },
        )
        out = io.StringIO()
        with patch.dict(os.environ, {"CODEX_THREAD_ID": ""}):
            coord.run_mcp(
                io.StringIO("\n".join(json.dumps(m) for m in calls) + "\n"),
                out,
                client_name="codex",
            )
        replies = {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}
        self.assertIn("codex-th1", replies[2]["result"]["content"][0]["text"])
        self.assertIn("for the thread", replies[3]["result"]["content"][0]["text"])
        self.assertEqual(hook_client.call("peek", sid="codex-th1")["unread"], 0)
        sids = [s["sid"] for s in hook_client.call("status")["sessions"]]
        self.assertEqual([s for s in sids if s.startswith("anon-")], [])


class DoctorTest(Fixture):
    def test_f8_2_doctor_separates_the_capability_lanes(self):
        daemon = Daemon(self.home)
        self.addCleanup(daemon.stop)
        out = io.StringIO()
        identity = coord.Identity("claude-code", "d1", str(self.repo))
        self.assertEqual(coord.doctor(identity, autostart=False, out=out), 0)
        text = out.getvalue()
        for lane in ("connect:", "session:", "notify:", "enforcement:", "sandbox:"):
            self.assertIn(lane, text)


if __name__ == "__main__":
    unittest.main()
