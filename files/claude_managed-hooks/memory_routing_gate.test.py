#!/usr/bin/env python3
"""Acceptance tests for memory_routing_gate.py guard, written by the ordering side before the implementation.

Contract (each claim maps to one test):
  C1  PreToolUse guard: `memory_routing_gate.py guard` reads the payload JSON on stdin and always exits 0;
      deny = one stdout line of JSON {"hookSpecificOutput": {"hookEventName": "PreToolUse",
      "permissionDecision": "deny", "permissionDecisionReason": <non-empty>}}, allow = empty stdout.
      The clone root comes from $CLAUDE_MEMORY_REPO, the sync CLI from $CLAUDE_MEMORY_SYNC_CLI, the grant
      dir and the legacy dirs from $HOME
  C2  out of scope → allow: a path outside the clone, a non-.md path, the index files MEMORY.md /
      OLD-MEMORY.md / README.md, and any edit whose new text contains `memory-guard: allow`
  C3  legacy locations (~/.claude/memory/*.md, ~/.claude/projects/<enc>/memory/*.md) → deny naming the clone
  C4  clone root without .git → deny
  C5  Edit / MultiEdit on an entry → deny, grant or not
  C6  Write on an entry needs the grant file $HOME/.claude/hooks/state/memory-routing/grants/<basename>
      younger than 3600 s: missing or stale → deny naming /memory-routing (a stale grant is removed);
      fresh grant + acceptable content → allow and the grant is consumed
  C7  acceptable content: basename starts with feedback_ or reference_, ≤ 50000 bytes, no oneline_summary:,
      frontmatter has a non-empty reminder: (≤ 150 chars), keywords: with a non-stopword token, models:
      with tags matching [a-z][a-z0-9.-]+; a feedback_ body uses only the h2 理由/対処/事例/関連, in that
      order, at most once each, with 理由 and 事例 present; the body has a YYYY-MM-DD date. Any violation
      → deny and the grant is kept
  C8  org cap: when org/ holds more than ORG_CAP = 60 entries (*.md minus the index files), a Write to a
      path in org/ that does not exist yet → deny (after the grant check, before the content check, grant
      kept); the reason names the cap and lists the org/ lines of `claude_memory_sync --reach` "never:"
      output, at most NEVER_SHOWN = 15 of them, never user/ or project/ lines, and points to `--reach` for
      the rest. Exactly 60 → allow; re-Write of an existing path → allow; new entries in user/ or
      project/ → allow regardless of the org count
  C9  `--reach` unavailable (CLI missing or non-zero exit) → C8 still denies, without a traceback
  C10 fail-open: non-JSON stdin, non-object payload, non-edit tool, missing or unknown subcommand → exit 0,
      empty stdout
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "memory_routing_gate.py"
)

FAKE_SYNC = """#!/usr/bin/env python3
import sys
me = sys.argv[0]
if sys.argv[1:] == ["--reach"]:
    sys.stdout.write(open(me + ".out").read())
    sys.exit(int(open(me + ".rc").read()))
"""
REACH_OUT = (
    "reach[30d]: never=3 hot=0\n"
    "never: org/feedback_never_one.md\n"
    "never: org/feedback_never_two.md\n"
    "never: project/proj-a/feedback_never_proj.md\n"
)
VALID = """---
reminder: 発注の前に契約 test と変異を書け
keywords: memory_routing_gate, org-cap
models: fable-5
---

## 理由

契約が先に無いと変異の生存数を測れない。

## 事例

2026-08-26 に契約を先に書いた。
"""
VALID_REFERENCE = """---
reminder: sync CLI の --reach は never と hot を列挙する
keywords: claude_memory_sync, reach
models: fable-5
---

2026-08-26 確認: never 行は clone 相対 path。
"""


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.home = os.path.join(root, "home")
        self.repo = os.path.join(root, "repo")
        self.grants = os.path.join(
            self.home, ".claude", "hooks", "state", "memory-routing", "grants"
        )
        for sub in (".git", "org", "user/alice", "project/proj-a"):
            os.makedirs(os.path.join(self.repo, sub))
        os.makedirs(self.grants)
        self.sync = os.path.join(root, "claude_memory_sync")
        with open(self.sync, "w") as fh:
            fh.write(FAKE_SYNC)
        self.set_reach(REACH_OUT, 0)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def set_reach(self, out: str, rc: int) -> None:
        with open(self.sync + ".out", "w") as fh:
            fh.write(out)
        with open(self.sync + ".rc", "w") as fh:
            fh.write(str(rc))

    def org(self, name: str) -> str:
        return os.path.join(self.repo, "org", name)

    def fill_org(self, count: int) -> None:
        for i in range(count):
            with open(self.org(f"feedback_f{i:03}.md"), "w") as fh:
                fh.write(VALID)

    def grant(self, path: str, age: float = 0.0) -> str:
        grant = os.path.join(self.grants, os.path.basename(path))
        with open(grant, "w") as fh:
            fh.write(path)
        if age:
            os.utime(grant, (time.time() - age, time.time() - age))
        return grant

    def run_hook(
        self,
        path: str,
        content: str = VALID,
        tool: str = "Write",
        payload: str | None = None,
        argv: list[str] | None = None,
        repo: str | None = None,
        sync: str | None = None,
    ) -> subprocess.CompletedProcess:
        if payload is None:
            if tool == "Write":
                inp = {"file_path": path, "content": content}
            elif tool == "Edit":
                inp = {"file_path": path, "old_string": "x", "new_string": content}
            elif tool == "MultiEdit":
                inp = {
                    "file_path": path,
                    "edits": [{"old_string": "x", "new_string": content}],
                }
            else:
                inp = {"command": content}
            payload = json.dumps(
                {"tool_name": tool, "tool_input": inp, "cwd": self.repo}
            )
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("HOME", "CLAUDE_MEMORY_REPO", "CLAUDE_MEMORY_SYNC_CLI")
        }
        env["HOME"] = self.home
        env["CLAUDE_MEMORY_REPO"] = repo or self.repo
        env["CLAUDE_MEMORY_SYNC_CLI"] = sync or self.sync
        return subprocess.run(
            [sys.executable, HOOK] + (["guard"] if argv is None else argv),
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env=env,
        )

    def deny(self, path: str, **kw) -> str:
        out = self.run_hook(path, **kw)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        lines = out.stdout.strip().splitlines()
        self.assertEqual(
            len(lines), 1, f"{path!r}: expected one JSON line, got {out.stdout!r}"
        )
        spec = json.loads(lines[0])["hookSpecificOutput"]
        self.assertEqual(spec["hookEventName"], "PreToolUse")
        self.assertEqual(spec["permissionDecision"], "deny")
        self.assertTrue(spec["permissionDecisionReason"].strip())
        return spec["permissionDecisionReason"]

    def allow(self, path: str, **kw) -> None:
        out = self.run_hook(path, **kw)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        self.assertEqual(out.stdout.strip(), "", f"{path!r}: {out.stdout}")

    def test_c2_out_of_scope_allows(self) -> None:
        self.allow(os.path.join(self.tmp.name, "notes", "feedback_x.md"))
        self.allow(self.org("feedback_x.txt"))
        for name in ("MEMORY.md", "OLD-MEMORY.md", "README.md"):
            self.allow(self.org(name))
        self.allow(self.org("feedback_x.md"), content="memory-guard: allow\n" + VALID)
        self.allow(
            self.org("feedback_x.md"), content="memory-guard: allow", tool="Edit"
        )

    def test_c3_legacy_locations_redirect(self) -> None:
        for path in (
            os.path.join(self.home, ".claude", "memory", "feedback_x.md"),
            os.path.join(
                self.home, ".claude", "projects", "-home-x", "memory", "feedback_x.md"
            ),
        ):
            reason = self.deny(path)
            self.assertIn(os.path.basename(self.repo), reason)
            self.assertIn("/memory-routing", reason)

    def test_c4_clone_without_git_denies(self) -> None:
        bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(os.path.join(bare, "org"))
        path = os.path.join(bare, "org", "feedback_x.md")
        self.grant(path)
        self.assertIn("clone", self.deny(path, repo=bare))

    def test_c5_edit_on_entry_denies(self) -> None:
        path = self.org("feedback_x.md")
        self.assertIn("Edit", self.deny(path, tool="Edit"))
        self.grant(path)
        self.assertIn("Edit", self.deny(path, tool="Edit"))
        self.assertIn("Edit", self.deny(path, tool="MultiEdit"))

    def test_c6_grant_lifecycle(self) -> None:
        path = self.org("feedback_x.md")
        self.assertIn("/memory-routing", self.deny(path))
        stale = self.grant(path, age=3601)
        self.assertIn("/memory-routing", self.deny(path))
        self.assertFalse(os.path.exists(stale))
        fresh = self.grant(path)
        self.allow(path)
        self.assertFalse(os.path.exists(fresh))
        fresh = self.grant(path, age=3599)
        self.allow(path)
        self.assertFalse(os.path.exists(fresh))

    def test_c7_content_rules(self) -> None:
        path = self.org("feedback_x.md")
        long_reminder = VALID.replace("契約 test と変異を書け", "契約" * 80)
        no_reminder = VALID.replace(
            "reminder: 発注の前に契約 test と変異を書け\n", "reminder:\n"
        )
        no_keywords = VALID.replace("keywords: memory_routing_gate, org-cap\n", "")
        stopword_keywords = VALID.replace(
            "memory_routing_gate, org-cap", "file, error, テスト"
        )
        no_models = VALID.replace("models: fable-5\n", "")
        bad_models = VALID.replace("models: fable-5", "models: Fable_5")
        bad_h2 = VALID.replace("## 理由", "## 背景")
        no_case = VALID.replace("## 事例", "### 事例")
        wrong_order = VALID.replace("## 理由", "## 事例", 1).replace(
            "## 事例\n\n2026", "## 理由\n\n2026"
        )
        no_date = VALID.replace("2026-08-26 に", "昨日")
        huge = VALID + "x" * 50_001
        cases = [
            ("prefix", self.org("project_x.md"), VALID),
            ("oneline", path, VALID.replace("models:", "oneline_summary: y\nmodels:")),
            ("reminder", path, no_reminder),
            ("reminder-150", path, long_reminder),
            ("keywords", path, no_keywords),
            ("stopwords", path, stopword_keywords),
            ("models", path, no_models),
            ("models-tag", path, bad_models),
            ("h2-vocab", path, bad_h2),
            ("h2-required", path, no_case),
            ("h2-order", path, wrong_order),
            ("date", path, no_date),
            ("size", path, huge),
        ]
        for label, target, content in cases:
            grant = self.grant(target)
            self.deny(target, content=content)
            self.assertTrue(os.path.exists(grant), label)
        ref = self.org("reference_x.md")
        grant = self.grant(ref)
        self.allow(ref, content=VALID_REFERENCE)
        self.assertFalse(os.path.exists(grant))

    def test_c8_org_cap_denies_new_org_entry(self) -> None:
        self.fill_org(61)
        path = self.org("feedback_new.md")
        grant = self.grant(path)
        reason = self.deny(path)
        self.assertIn("60", reason)
        self.assertIn("org/feedback_never_one.md", reason)
        self.assertIn("org/feedback_never_two.md", reason)
        self.assertNotIn("proj-a", reason)
        self.assertIn("--reach", reason)
        self.assertTrue(os.path.exists(grant))
        ref = self.org("reference_new.md")
        self.grant(ref)
        self.assertIn("60", self.deny(ref, content=VALID_REFERENCE))

    def test_c8_org_cap_boundary_ignores_index_files(self) -> None:
        self.fill_org(60)
        for name in ("MEMORY.md", "OLD-MEMORY.md", "README.md"):
            with open(self.org(name), "w") as fh:
                fh.write("index\n")
        path = self.org("feedback_new.md")
        self.grant(path)
        self.allow(path)

    def test_c8_org_cap_spares_rewrites_and_other_scopes(self) -> None:
        self.fill_org(61)
        existing = self.org("feedback_f000.md")
        self.grant(existing)
        self.allow(existing)
        for path in (
            os.path.join(self.repo, "user", "alice", "feedback_new.md"),
            os.path.join(self.repo, "project", "proj-a", "feedback_new.md"),
        ):
            grant = self.grant(path)
            self.allow(path)
            self.assertFalse(os.path.exists(grant))

    def test_c8_never_list_is_capped_at_15(self) -> None:
        lines = [f"never: org/feedback_never_{i:02}.md" for i in range(20)]
        lines.append("never: user/alice/feedback_never_user.md")
        self.set_reach("reach[30d]: never=21 hot=0\n" + "\n".join(lines) + "\n", 0)
        self.fill_org(61)
        path = self.org("feedback_new.md")
        self.grant(path)
        reason = self.deny(path)
        self.assertEqual(reason.count("org/feedback_never_"), 15)
        self.assertNotIn("alice", reason)
        self.assertIn("--reach", reason)

    def test_c9_reach_unavailable_still_denies(self) -> None:
        self.fill_org(61)
        path = self.org("feedback_new.md")
        self.grant(path)
        missing = os.path.join(self.tmp.name, "no-such-cli")
        self.assertIn("60", self.deny(path, sync=missing))
        self.set_reach("index: unavailable\n", 1)
        self.assertIn("60", self.deny(path))

    def test_c8_order_grant_then_cap_then_content(self) -> None:
        self.fill_org(61)
        path = self.org("feedback_new.md")
        reason = self.deny(path)
        self.assertIn("/memory-routing", reason)
        self.assertNotIn("--reach", reason)
        grant = self.grant(path)
        no_reminder = VALID.replace(
            "reminder: 発注の前に契約 test と変異を書け\n", "reminder:\n"
        )
        self.assertIn("--reach", self.deny(path, content=no_reminder))
        self.assertTrue(os.path.exists(grant))

    def test_c10_fail_open(self) -> None:
        path = self.org("feedback_x.md")
        for label, out in (
            ("not-json", self.run_hook(path, payload="{not json")),
            ("list", self.run_hook(path, payload="[]")),
            ("null", self.run_hook(path, payload="null")),
            ("bash", self.run_hook(path, tool="Bash", content="ls")),
            ("no-sub", self.run_hook(path, argv=[])),
            ("bogus-sub", self.run_hook(path, argv=["bogus"])),
        ):
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout.strip(), "", label)


if __name__ == "__main__":
    unittest.main()
