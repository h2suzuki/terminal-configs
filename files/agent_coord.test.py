#!/usr/bin/env python3
"""Verification scenarios V1-V11 of the coordinator design doc, run against agent_coord."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import sqlite3
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

SPEC = importlib.util.spec_from_loader(
    "agent_coord",
    importlib.machinery.SourceFileLoader(
        "agent_coord", str(Path(__file__).with_name("agent_coord"))
    ),
)
assert SPEC is not None and SPEC.loader is not None
coord = importlib.util.module_from_spec(SPEC)
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
        client = self.client()
        client.call("shutdown")
        client.close()
        self.thread.join(5)


class CoordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="coord-test-"))
        self.home = self.tmp / "home"
        self.daemon = Daemon(self.home)
        self.addCleanup(self.cleanup)
        self.repo = make_repo(self.tmp, "repo", "https://github.com/example/repo.git")
        self.clone = make_repo(self.tmp, "clone", "git@github.com:example/repo.git")
        self.other = make_repo(self.tmp / "elsewhere", "repo")
        self.wt = self.tmp / "wt" / "repo" / "feature"
        git("worktree", "add", "-q", str(self.wt), "-b", "feature", cwd=str(self.repo))

    def cleanup(self):
        if self.daemon.thread.is_alive():
            self.daemon.stop()

    def join(self, sid: str, cwd: Path, **extra) -> tuple[Any, dict]:
        client = self.daemon.client()
        self.addCleanup(client.close)
        return client, client.call(
            "join", sid=sid, client="test", cwd=str(cwd), **extra
        )

    def unread_texts(self, client: Any, sid: str) -> list[str]:
        return [
            e["body"].get("text") or e["kind"]
            for e in client.call("catchup", sid=sid)["events"]
        ]

    def test_identity_groups_worktrees_by_common_dir_and_clones_by_project(self):
        """V1: main checkout + linked worktree share one repo key; clones share the project key; a same-named other repo stays apart."""
        _, main = self.join("a", self.repo)
        _, wt = self.join("b", self.wt)
        _, clone = self.join("c", self.clone)
        _, other = self.join("d", self.other)
        self.assertEqual(main["session"]["common_dir"], wt["session"]["common_dir"])
        self.assertEqual(wt["session"]["branch"], "feature")
        self.assertEqual(main["session"]["project"], "github.com/example/repo")
        self.assertEqual(clone["session"]["project"], "github.com/example/repo")
        self.assertNotEqual(
            clone["session"]["common_dir"], main["session"]["common_dir"]
        )
        self.assertNotEqual(other["session"]["project"], main["session"]["project"])
        self.assertEqual(os.path.basename(other["session"]["repo_top"]), "repo")
        self.assertEqual({p["sid"] for p in clone["peers_same_project"]}, {"a", "b"})

    def test_scopes_limit_who_reads_a_message(self):
        """Broadcast scope (repo / project / all / session) decides visibility; own broadcasts are not redelivered, self-addressed ones are."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        c, _ = self.join("c", self.clone)
        d, _ = self.join("d", self.other)
        a.call("send", sid="a", to="repo", text="repo only")
        a.call("send", sid="a", to="project", text="project wide")
        a.call("send", sid="a", to="all", text="everyone")
        a.call("send", sid="a", to="c", text="direct")
        self.assertEqual(
            self.unread_texts(b, "b"), ["repo only", "project wide", "everyone"]
        )
        self.assertEqual(
            self.unread_texts(c, "c"), ["project wide", "everyone", "direct"]
        )
        self.assertEqual(self.unread_texts(d, "d"), ["everyone"])
        self.assertEqual(self.unread_texts(a, "a"), [])
        a.call("send", sid="a", to="self", text="note to self")
        self.assertEqual(self.unread_texts(a, "a"), ["note to self"])

    def test_acquire_is_exclusive_release_checks_owner_and_generation(self):
        """V2 + V3: one winner per key, idempotent retry, stale-generation and foreign release rejected, waiter notified."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.clone)
        first = a.call(
            "acquire", sid="a", key="rig-1", purpose="flash", request_id="k1"
        )
        self.assertEqual(first["generation"], 1)
        self.assertEqual(
            a.call("acquire", sid="a", key="rig-1", purpose="flash", request_id="k1"),
            first,
        )
        self.assertEqual(
            [e["kind"] for e in a.call("history", sid="a", all=True)["events"]],
            ["join", "join", "acquire"],
        )
        with self.assertRaises(coord.CoordError) as ctx:
            b.call("acquire", sid="b", key="rig-1", purpose="test")
        self.assertEqual(ctx.exception.code, -32010)
        self.assertEqual(ctx.exception.data["owner"], "a")
        with self.assertRaises(coord.CoordError):
            b.call("release", sid="b", key="rig-1")
        with self.assertRaises(coord.CoordError):
            a.call("release", sid="a", key="rig-1", generation=0)
        a.call("release", sid="a", key="rig-1", generation=1)
        self.assertEqual(
            [e["kind"] for e in b.call("catchup", sid="b")["events"]], ["release"]
        )
        self.assertEqual(b.call("acquire", sid="b", key="rig-1")["generation"], 2)
        with self.assertRaises(coord.CoordError):
            a.call("release", sid="a", key="rig-1")

    def test_restart_keeps_ownership_cursor_and_unread(self):
        """V4: after a daemon restart ownership, cursors and unread events survive; nothing is auto-released."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        a.call("acquire", sid="a", key="rig-1")
        a.call("send", sid="a", to="repo", text="one")
        first = b.call("catchup", sid="b")
        b.call("ack", sid="b", through=first["last_seq"])
        a.call("send", sid="a", to="repo", text="two")
        a.close()
        b.close()
        self.daemon.stop()
        self.daemon.start()
        c = self.daemon.client()
        self.addCleanup(c.close)
        status = c.call("status")
        self.assertEqual(
            [(r["key"], r["owner"]) for r in status["resources"]], [("rig-1", "a")]
        )
        self.assertEqual(self.unread_texts(c, "b"), ["two"])
        self.assertEqual(c.call("peek", sid="b")["cursor"], first["last_seq"])

    def test_memory_is_the_current_state_and_sqlite_only_persists(self):
        """4.2: reads are answered from memory (no SQL), writes reach SQLite before the reply, a rollback reloads memory."""
        store = coord.Store(self.tmp / "direct" / "ledger.sqlite3")
        store.transact(
            store.join, {"sid": "a", "client": "test", "cwd": str(self.repo)}
        )
        store.transact(store.send, {"sid": "a", "to": "all", "text": "hello"})
        statements: list[str] = []
        store.db.set_trace_callback(statements.append)
        status = store.transact(store.status, {})
        verdict = store.transact(store.edit_check, {"sid": "a", "path": str(self.repo)})
        store.db.set_trace_callback(None)
        self.assertEqual((status["service"]["events"], verdict["allow"]), (2, True))
        self.assertFalse(
            [q for q in statements if q.lstrip().upper().startswith("SELECT")],
            statements,
        )
        durable = store.db.execute(
            "SELECT cursor FROM sessions WHERE sid='a'"
        ).fetchone()[0]
        self.assertEqual(durable, store.session("a")["cursor"])

        def failing_save(table: str, row: dict) -> None:
            raise sqlite3.OperationalError("disk gone")

        store._save = failing_save  # type: ignore[method-assign]
        with self.assertRaises(sqlite3.OperationalError):
            store.transact(store.ack, {"sid": "a", "through": 2})
        self.assertEqual(
            store.session("a")["cursor"], durable
        )  # memory rolled back with the transaction

    def test_delivery_is_per_recipient_not_a_shared_cursor(self):
        """F2/F3: a direct message and a broadcast are acked independently; nobody's inbox depends on another session's ack."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        c, _ = self.join("c", self.clone)
        a.call("send", sid="a", to="repo", text="for b")
        direct = a.call("send", sid="a", to="c", text="for c")
        c.call("ack", sid="c", through=direct["seq"])
        self.assertEqual(self.unread_texts(c, "c"), [])
        self.assertEqual(self.unread_texts(b, "b"), ["for b"])
        self.assertEqual(b.call("peek", sid="b")["unread"], 1)

    def test_events_expire_after_ttl_and_newcomers_get_the_last_hour(self):
        """F2 (use case): undelivered talk lives EVENT_TTL; a newcomer is seeded with JOIN_BACKFILL of its scopes only."""
        store = coord.Store(self.tmp / "direct" / "ledger.sqlite3")
        call = lambda method, **p: store.transact(getattr(store, method), p)  # noqa: E731
        call("join", sid="a", client="test", cwd=str(self.repo))
        call("join", sid="b", client="test", cwd=str(self.wt))
        stale = call("send", sid="a", to="project", text="old news")["seq"]
        call("send", sid="a", to="project", text="fresh")
        call("send", sid="a", to="b", text="private to b")
        store._by_seq[stale]["ts"] -= coord.JOIN_BACKFILL + 1
        call("join", sid="c", client="test", cwd=str(self.clone))
        self.assertEqual(
            [e["body"]["text"] for e in call("catchup", sid="c")["events"]], ["fresh"]
        )
        self.assertEqual(len(call("catchup", sid="b")["events"]), 3)
        for event in store._events:
            event["ts"] -= coord.EVENT_TTL + 1
        last_seq = store._last_seq
        self.assertEqual(call("peek", sid="b")["unread"], 0)
        self.assertEqual(call("status")["service"]["retained"], 0)
        self.assertEqual(
            store.db.execute("SELECT count(*) FROM inbox").fetchone()[0], 0
        )
        self.assertEqual(
            call("send", sid="a", to="repo", text="later")["seq"], last_seq + 1
        )

    def test_backfill_never_repeats_a_delivery_and_is_marked(self):
        """F2 (use case): a rejoin gets the last hour it missed while away, flagged backfill; acked and pending entries are not delivered twice."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        seen = b.call("send", sid="b", to="repo", text="seen before leaving")["seq"]
        a.call("ack", sid="a", through=seen)
        b.call("send", sid="b", to="repo", text="pending when leaving")
        a.call("leave", sid="a")
        b.call("send", sid="b", to="repo", text="posted while away")
        _, rejoined = self.join("a", self.repo)
        self.assertEqual(rejoined["unread"], 2)
        events = a.call("catchup", sid="a")["events"]
        self.assertEqual(
            [(e["body"]["text"], e.get("backfill", False)) for e in events],
            [("pending when leaving", False), ("posted while away", True)],
        )
        _, again = self.join("a", self.repo)  # a second join adds nothing
        self.assertEqual(again["unread"], 2)
        a.call("ack", sid="a", through=events[-1]["seq"])
        self.assertEqual(a.call("peek", sid="a")["unread"], 0)
        history = self.daemon.client().call("history", all=True)["events"]
        self.assertEqual(
            [e["kind"] for e in history if e["actor"] == "a"],
            [
                "join",
                "leave",
                "join",
            ],  # the rejoin is announced once; the idle re-join is not
        )

    def test_resolving_your_own_request_does_not_notify_yourself(self):
        """F3: the requester's own resolve goes to the request's addressees, never back to the requester."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        req = a.call("request", sid="a", to="repo", subject="rig?")
        a.call("resolve", sid="a", req_id=req["req_id"], result="never mind")
        self.assertEqual(self.unread_texts(a, "a"), [])
        self.assertEqual(self.unread_texts(b, "b"), ["request_open", "request_resolve"])

    def test_subscribers_see_committed_events_only_after_commit(self):
        """F3/V5: a watch subscriber gets each committed event pushed once; a refused acquire that rolls back pushes nothing."""
        a, _ = self.join("a", self.repo)
        watcher = self.daemon.client()
        self.addCleanup(watcher.close)
        self.assertTrue(watcher.call("subscribe")["subscribed"])
        watcher.sock.settimeout(5)
        a.call("send", sid="a", to="repo", text="pushed")
        pushed = json.loads(watcher.file.readline())
        self.assertEqual(
            (pushed["method"], pushed["params"]["body"]["text"]), ("event", "pushed")
        )
        with self.assertRaises(coord.CoordError):
            a.call("release", sid="a", key="never-held")  # rolls back, no event
        a.call("acquire", sid="a", key="rig")
        self.assertEqual(
            json.loads(watcher.file.readline())["params"]["kind"], "acquire"
        )

    def test_catchup_pages_peek_and_status_do_not_consume(self):
        """V6 + V7: paging never drops events, peek/status leave the cursor alone, ack only moves forward."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        for i in range(5):
            a.call("send", sid="a", to="repo", text=f"m{i}")
        self.assertEqual(b.call("peek", sid="b")["unread"], 5)
        b.call("status")
        page = b.call("catchup", sid="b", limit=2)
        self.assertTrue(page["more"])
        self.assertEqual([e["body"]["text"] for e in page["events"]], ["m0", "m1"])
        self.assertEqual(b.call("peek", sid="b")["unread"], 5)
        rest = b.call("catchup", sid="b", limit=10, ack_through=page["last_seq"])
        self.assertEqual(
            [e["body"]["text"] for e in rest["events"]], ["m2", "m3", "m4"]
        )
        self.assertFalse(rest["more"])
        b.call("ack", sid="b", through=rest["last_seq"])
        b.call("ack", sid="b", through=1)
        self.assertEqual(b.call("peek", sid="b")["unread"], 0)
        self.assertIsNone(b.call("nudge", sid="b")["text"])

    def test_nudge_once_per_unread_range(self):
        """V6: the same unread range is announced once; a new event re-arms the nudge."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        a.call("send", sid="a", to="repo", text="ping")
        self.assertIn("1 unread", b.call("nudge", sid="b")["text"])
        self.assertIsNone(b.call("nudge", sid="b")["text"])
        a.call("send", sid="a", to="repo", text="pong")
        self.assertIn("2 unread", b.call("nudge", sid="b")["text"])

    def test_requests_resolve_and_cancel_are_explicit(self):
        """V12 (request part): release does not resolve a request; only requester cancels; resolution is a separate event."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.clone)
        b.call("acquire", sid="b", key="rig-1")
        req = a.call(
            "request",
            sid="a",
            to="b",
            subject="please release rig-1",
            resource="rig-1",
            request_id="r1",
        )
        self.assertEqual(
            a.call(
                "request",
                sid="a",
                to="b",
                subject="please release rig-1",
                request_id="r1",
            ),
            req,
        )
        seen = b.call("catchup", sid="b")["events"]
        self.assertEqual(seen[0]["body"]["req_id"], req["req_id"])
        self.assertEqual(
            [r["req_id"] for r in b.call("whoami", sid="b")["open_requests"]],
            [req["req_id"]],
        )
        with self.assertRaises(coord.CoordError):
            b.call("cancel", sid="b", req_id=req["req_id"])
        b.call("release", sid="b", key="rig-1")
        self.assertEqual(
            [r["req_id"] for r in a.call("requests", sid="a")["requests"]],
            [req["req_id"]],
        )
        b.call("resolve", sid="b", req_id=req["req_id"], result="released")
        self.assertEqual(
            [e["kind"] for e in a.call("catchup", sid="a")["events"]],
            ["release", "request_resolve"],
        )
        with self.assertRaises(coord.CoordError):
            a.call("cancel", sid="a", req_id=req["req_id"])

    def test_leave_marks_resources_unconfirmed_and_force_release_needs_reason(self):
        """F4: leaving never frees a resource; a user force-release must carry a reason."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.wt)
        a.call("acquire", sid="a", key="rig-1")
        self.assertEqual(a.call("leave", sid="a")["resources_marked_unconfirmed"], 1)
        with self.assertRaises(coord.CoordError) as ctx:
            b.call("acquire", sid="b", key="rig-1")
        self.assertEqual(ctx.exception.data["state"], "unconfirmed")
        with self.assertRaises(coord.CoordError):
            b.call("force_release", key="rig-1")
        b.call("force_release", key="rig-1", reason="owner gone, rig idle")
        self.assertEqual(b.call("acquire", sid="b", key="rig-1")["generation"], 2)

    def test_worktree_claim_transfer_and_enforcement(self):
        """V8 + V9: one owner per worktree, two-phase transfer, stale owner rejected, enforced edits stay inside the worktree."""
        a, _ = self.join("a", self.repo)
        b, _ = self.join("b", self.repo)
        claim = a.call("worktree_claim", sid="a", path=str(self.wt), enforce=True)
        self.assertEqual(claim["generation"], 1)
        with self.assertRaises(coord.CoordError) as ctx:
            b.call("worktree_claim", sid="b", path=str(self.wt))
        self.assertEqual(ctx.exception.code, -32010)
        with self.assertRaises(coord.CoordError):
            a.call("worktree_claim", sid="a", path=str(self.other))
        self.assertFalse(
            a.call("edit_check", sid="a", path=str(self.repo / "README"))["allow"]
        )
        self.assertTrue(
            a.call("edit_check", sid="a", path=str(self.wt / "new.py"))["allow"]
        )
        self.assertTrue(
            a.call("edit_check", sid="a", path="/tmp/elsewhere.txt")["allow"]
        )
        self.assertTrue(
            b.call("edit_check", sid="b", path=str(self.repo / "README"))["allow"]
        )
        a.call("worktree_transfer", sid="a", path=str(self.wt), to="b")
        self.assertEqual(
            b.call("catchup", sid="b")["events"][0]["kind"], "transfer_propose"
        )
        owner = next(
            w["owner"]
            for w in a.call("status")["worktrees"]
            if w["path"] == str(self.wt.resolve())
        )
        self.assertEqual(owner, "a")
        with self.assertRaises(coord.CoordError):
            b.call("worktree_accept", sid="b", path=str(self.other))
        accepted = b.call("worktree_accept", sid="b", path=str(self.wt))
        self.assertEqual(accepted["previous_owner"], "a")
        with self.assertRaises(coord.CoordError):
            a.call("worktree_release", sid="a", path=str(self.wt))
        with self.assertRaises(coord.CoordError):
            a.call("worktree_transfer", sid="a", path=str(self.wt), to="b")
        self.assertEqual(
            a.call("catchup", sid="a")["events"][-1]["kind"], "transfer_accept"
        )
        self.assertTrue(
            a.call("edit_check", sid="a", path=str(self.repo / "README"))["allow"]
        )

    def test_worktree_create_resume_and_collision(self):
        """V8 + V11: create claims the new worktree, re-create resumes it, bad names / refs / foreign dirs are refused."""
        a, _ = self.join("a", self.repo)
        root = self.tmp / "wtroot"
        created = a.call(
            "worktree_create", sid="a", name="issue-1", root=str(root), enforce=True
        )
        self.assertTrue(created["created"])
        self.assertTrue((root / "repo" / "issue-1" / "README").exists())
        self.assertEqual(
            git(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=str(root / "repo" / "issue-1")
            ),
            "issue-1",
        )
        resumed = a.call("worktree_create", sid="a", name="issue-1", root=str(root))
        self.assertTrue(resumed["resumed"])
        self.assertEqual(resumed["generation"], 2)
        with self.assertRaises(coord.CoordError):
            a.call("worktree_create", sid="a", name="../evil", root=str(root))
        with self.assertRaises(coord.CoordError):
            a.call(
                "worktree_create",
                sid="a",
                name="issue-2",
                base="no-such-ref",
                root=str(root),
            )
        o, _ = self.join("o", self.other)
        with self.assertRaises(coord.CoordError) as ctx:
            o.call("worktree_create", sid="o", name="issue-1", root=str(root))
        self.assertEqual(ctx.exception.code, -32012)

    def test_mcp_adapter_joins_and_forwards_tools(self):
        """F8: the stdio adapter keeps no ledger of its own; every tool call lands in the daemon as one session."""
        client = self.daemon.client()
        self.addCleanup(client.close)
        adapter = coord.McpAdapter(client, "mcp-1", str(self.repo))
        init = adapter.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            }
        )
        self.assertEqual(init["result"]["serverInfo"]["name"], "agent-coord")
        names = {
            t["name"]
            for t in adapter.dispatch(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
            )["result"]["tools"]
        }
        self.assertIn("catchup", names)
        self.assertIsNone(
            adapter.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        sent = adapter.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "send",
                    "arguments": {"text": "hi me", "to": "self"},
                },
            }
        )
        self.assertFalse(sent["result"]["isError"])
        got = adapter.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "catchup", "arguments": {}},
            }
        )
        self.assertIn("hi me", got["result"]["content"][0]["text"])
        bad = adapter.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "worktree",
                    "arguments": {"action": "claim", "path": "/nowhere"},
                },
            }
        )
        self.assertTrue(bad["result"]["isError"])
        self.assertEqual(client.call("sessions")["sessions"][0]["sid"], "mcp-1")

    def test_hooks_join_nudge_and_deny_edits_outside_worktree(self):
        """F3 + V9 (Claude Code path): SessionStart joins, prompt/tool hooks nudge once, PreToolUse denies edits outside the enforced worktree."""
        os.environ["AGENT_COORD_HOME"] = str(self.home)
        os.environ["AGENT_COORD_NO_AUTOSTART"] = "1"
        self.addCleanup(os.environ.pop, "AGENT_COORD_HOME")
        self.addCleanup(os.environ.pop, "AGENT_COORD_NO_AUTOSTART")
        out = io.StringIO()
        coord.hook_main(
            "SessionStart",
            io.StringIO(json.dumps({"session_id": "s1", "cwd": str(self.wt)})),
            out,
        )
        self.assertIn(
            "joined as cc-s1",
            json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"],
        )
        a, _ = self.join("a", self.repo)
        a.call("send", sid="a", to="repo", text="look")
        out = io.StringIO()
        coord.hook_main(
            "UserPromptSubmit", io.StringIO(json.dumps({"session_id": "s1"})), out
        )
        self.assertIn("1 unread", out.getvalue())
        out = io.StringIO()
        coord.hook_main(
            "PostToolUse", io.StringIO(json.dumps({"session_id": "s1"})), out
        )
        self.assertEqual(out.getvalue(), "")
        a.call("worktree_claim", sid="cc-s1", path=str(self.wt), enforce=True)
        out = io.StringIO()
        coord.hook_main(
            "PreToolUse",
            io.StringIO(
                json.dumps(
                    {
                        "session_id": "s1",
                        "tool_name": "Edit",
                        "tool_input": {"file_path": str(self.repo / "README")},
                    }
                )
            ),
            out,
        )
        self.assertEqual(
            json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        out = io.StringIO()
        coord.hook_main(
            "PreToolUse",
            io.StringIO(
                json.dumps(
                    {
                        "session_id": "s1",
                        "tool_name": "Edit",
                        "tool_input": {"file_path": str(self.wt / "x")},
                    }
                )
            ),
            out,
        )
        self.assertEqual(out.getvalue(), "")

    def test_second_daemon_on_same_home_refuses(self):
        """V2 (singleton): a second daemon on the same home exits without serving; the first keeps answering."""
        err = io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            self.assertEqual(coord.serve(self.home, io.StringIO()), 0)
        finally:
            sys.stderr = old
        self.assertIn("another daemon", err.getvalue())
        self.assertTrue(self.daemon.client().call("ping")["pong"])

    def test_global_flags_parse_from_anywhere(self):
        """CLI ergonomics: --json / --as / --no-autostart work before or after the subcommand."""
        after = coord.parse_cli(["status", "--json", "--as", "x", "--no-autostart"])
        before = coord.parse_cli(["--json", "--as=x", "--no-autostart", "status"])
        for args in (after, before):
            self.assertEqual(
                (args.sid, args.json, args.no_autostart), ("x", True, True)
            )
        plain = coord.parse_cli(["send", "hi", "--to", "all"])
        self.assertEqual(
            (plain.sid, plain.json, plain.no_autostart), (None, False, False)
        )
        self.assertEqual(plain.to, "all")

    def test_remote_normalization(self):
        """Project key ignores scheme, user, case of host and the .git suffix."""
        cases = {
            "https://github.com/H2suzuki/terminal-configs.git": "github.com/H2suzuki/terminal-configs",
            "git@github.com:h2suzuki/terminal-configs.git": "github.com/h2suzuki/terminal-configs",
            "ssh://git@GitHub.com/h2suzuki/x/": "github.com/h2suzuki/x",
            "/srv/git/repo.git": "/srv/git/repo",
        }
        for url, expected in cases.items():
            self.assertEqual(coord.normalize_remote(url), expected, url)


if __name__ == "__main__":
    unittest.main()
