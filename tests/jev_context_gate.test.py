#!/usr/bin/env python3
"""Tests for jev_context_gate: the connected jev server calls check() with its own evaluate; throwaway repos provide the commits."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "jev_context_gate", ROOT / "files" / "jev_context_gate.py"
)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
REAL_POPEN = subprocess.Popen

README = (
    "# Tool\n\nTool sets up coding agents on a workstation.\n\n## Sign in\n\nSign in to each CLI once.\n\n"
    "### Codex\n\n```bash\ncodex login\n```\n\n## Updating\n\nPull and rerun.\n"
)
CODE = '"""Loader for agent settings files."""\n\n\ndef load(path):\n    return open(path).read()\n\n\ndef helper():\n    return 1\n'
FIT_KEY = re.compile(r"fits_\d+_\d+|style_\d+")


class JevContextGateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.sent: list[dict] = []
        self.spawned: list[list[str]] = []
        self.noul = 0.1
        self.gate_log = root / "state" / "log.jsonl"
        self.log_path = self.gate_log
        self.home = root / "home"
        self.home.mkdir()
        self.repo = root / "repo"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.git("init", "-q", "-b", "main", str(self.repo), cwd=root)
        (self.repo / "README.md").write_text(README)
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "init")

    def git(self, *args: str, cwd: Path | None = None) -> None:
        subprocess.run(
            ["git", "-C", str(cwd or self.repo), *args],
            check=True,
            env=self.env,
            capture_output=True,
        )

    def add_to_codex_section(self, text: str) -> None:
        readme = (self.repo / "README.md").read_text()
        (self.repo / "README.md").write_text(
            readme.replace("```\n\n## Updating", f"```\n\n{text}\n\n## Updating")
        )

    def evaluate(self, mode: str):
        def answer(state: dict, questions: dict, timeout: float) -> dict:
            self.assertGreater(timeout, 0)
            self.sent.append(json.loads(json.dumps({"state": state, "questions": questions})))
            if mode == "error":
                raise gate.Skip("No API key configured. Run jev api-key set.")
            answers = {}
            for key in questions:
                kind, *index = key.split("_")
                if kind == "fits":
                    text = state["hunks"][int(index[0])]["pieces"][int(index[1])]["added_lines"]
                else:
                    assert state["new_sections"][int(index[0])]["new_section"]["text"]
                    text = ""
                bad = mode == "bad" or (mode == "bad-marked" and "MAINTAINER" in text)
                bad = bad or (mode == "bad-style" and kind == "style")
                answers[key] = {"type": "noul", "noul": self.noul if bad else 0.9}
            return {"answers": answers, "model": "stub-jev", "usage": {"input_tokens": 7}}

        return answer

    def spy(self, *args, **kwargs):
        argv = args[0] if args else kwargs["args"]
        self.spawned.append([str(a) for a in argv])
        return REAL_POPEN(*args, **kwargs)

    def run_hook(self, command: str, mode: str = "good", codex: bool = False) -> dict:
        payload: dict = (
            {"tool_name": "Bash", "tool_input": {"cmd": command, "workdir": str(self.repo)}, "cwd": "/"}
            if codex
            else {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.repo)}
        )  # fmt: skip
        payload["session_id"] = "sess-1"
        with (
            mock.patch.dict(os.environ, self.env, clear=True),
            mock.patch.object(gate, "LOG", str(self.log_path)),
            mock.patch.object(subprocess, "Popen", side_effect=self.spy),
        ):
            output = gate.check({"hook_event_name": "PreToolUse", **payload}, self.evaluate(mode))
        # The check runs inside the connected jev server: it may run git, never start a process of its own.
        self.assertEqual({argv[0] for argv in self.spawned} - {"git"}, set())
        return output

    def calls(self) -> list[dict]:
        return self.sent

    def records(self) -> list[dict]:
        return (
            [json.loads(line) for line in self.gate_log.read_text().splitlines()]
            if self.gate_log.exists()
            else []
        )

    def only_hunk(self) -> dict:
        (call,) = self.calls()
        (hunk,) = call["state"]["hunks"]
        return hunk

    def test_non_commit_command_is_ignored(self):
        self.add_to_codex_section("MAINTAINER note")
        self.assertEqual(self.run_hook("git status", mode="bad"), {})
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.records(), [])

    def test_fitting_hunk_passes_silently_with_the_form_state_shape(self):
        """State is form + document + hunks[place, style, pieces]; nothing else is sent."""
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.assertEqual(self.run_hook('git commit -m "x" -- README.md'), {})
        state = self.calls()[0]["state"]
        self.assertEqual(set(state), {"form", "document", "hunks"})
        self.assertEqual(
            set(state["form"]), {"background_of_change", "file_kind_and_role"}
        )
        self.assertEqual(set(state["document"]), {"file", "file_role"})
        self.assertEqual(state["document"]["file"], "README.md")
        (hunk,) = state["hunks"]
        self.assertEqual(
            set(hunk), {"place_and_its_purpose", "style_of_this_place", "pieces"}
        )
        (piece,) = hunk["pieces"]
        self.assertEqual(
            set(piece),
            {"what_the_edit_adds", "lines_before", "added_lines", "lines_after"},
        )
        self.assertEqual(
            piece["added_lines"], "Run `codex login --device-auth` over SSH."
        )
        self.assertEqual(piece["lines_before"][-2:], ["```", ""])
        self.assertEqual(
            piece["lines_after"], ["", "## Updating", "", "Pull and rerun."]
        )

    def test_context_lines_are_limited_to_six_on_each_side(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.run_hook('git commit -m "x" -- README.md')
        (piece,) = self.only_hunk()["pieces"]
        self.assertEqual(len(piece["lines_before"]), 6)
        self.assertEqual(piece["lines_before"][0], "### Codex")

    def test_placement_misfit_is_denied_with_location_score_and_text(self):
        self.add_to_codex_section(
            "MAINTAINER note: keep AGENTS.md in sync and run the test."
        )
        output = self.run_hook('git commit -m "x" -- README.md', mode="bad")[
            "hookSpecificOutput"
        ]
        self.assertEqual(output["permissionDecision"], "deny")
        reason = output["permissionDecisionReason"]
        (line,) = [x for x in reason.splitlines() if x.startswith("- README.md:15 ")]
        self.assertIn("Tool > Sign in > Codex", line)
        self.assertIn("置いた場所", line)
        self.assertNotIn("書きぶり", line)
        self.assertIn("0.10", line)
        self.assertIn("MAINTAINER note", reason)

    def test_staged_changes_are_judged_for_a_commit_without_paths(self):
        self.add_to_codex_section("MAINTAINER note")
        self.git("add", "README.md")
        output = self.run_hook('git commit -m "x"', mode="bad")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_all_tracked_flag_judges_worktree_changes(self):
        self.add_to_codex_section("MAINTAINER note")
        output = self.run_hook('git commit -am "x"', mode="bad")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_codex_payload_is_judged_the_same_way(self):
        self.add_to_codex_section("MAINTAINER note")
        output = self.run_hook('git commit -m "x" -- README.md', mode="bad", codex=True)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_key_error_skips_and_tells_the_user(self):
        self.add_to_codex_section("MAINTAINER note")
        output = self.run_hook('git commit -m "x" -- README.md', mode="error")
        self.assertNotIn("hookSpecificOutput", output)
        self.assertIn("Jev", output["systemMessage"])
        self.assertIn("No API key", output["systemMessage"])

    def test_pieces_of_one_hunk_are_sent_together(self):
        """A piece judged alone lost its neighbours' context and scored lower, so one place stays in one request."""
        self.add_to_codex_section("Run `a`.\n\nRun `b`.\n\nRun `c`.")
        self.run_hook('git commit -m "x" -- README.md')
        call = self.calls()[0]
        self.assertEqual(len(self.calls()), 1)
        (hunk,) = call["state"]["hunks"]
        self.assertEqual(
            [p["added_lines"] for p in hunk["pieces"]],
            ["Run `a`.", "Run `b`.", "Run `c`."],
        )
        self.assertEqual(set(call["questions"]), {"fits_0_0", "fits_0_1", "fits_0_2"})
        self.assertIn(
            "hunks[0].pieces[2].added_lines",
            call["questions"]["fits_0_2"]["instructions"],
        )

    def test_hunks_that_do_not_fit_together_go_whole_into_separate_requests(self):
        steps = "\n\n".join(f"Codex step {i}: " + "word " * 60 for i in range(4))
        self.add_to_codex_section(steps)
        readme = (self.repo / "README.md").read_text()
        more = "\n\n".join(f"Update step {i}: " + "word " * 60 for i in range(4))
        (self.repo / "README.md").write_text(readme + f"\n{more}\n")
        self.run_hook('git commit -m "x" -- README.md')
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        for call, place in zip(
            calls, ["Tool > Sign in > Codex", "Tool > Updating"], strict=True
        ):
            (hunk,) = call["state"]["hunks"]
            self.assertTrue(hunk["place_and_its_purpose"].startswith(place))
            self.assertEqual(len(hunk["pieces"]), 4)
            self.assertLessEqual(
                len(json.dumps(call["state"], ensure_ascii=False)), 12000
            )

    def test_large_change_is_split_into_requests_that_all_get_judged(self):
        paragraphs = "\n\n".join(f"Step {i}: " + "detail " * 40 for i in range(120))
        self.add_to_codex_section(paragraphs + "\n\nMAINTAINER note at the end.")
        output = self.run_hook('git commit -m "x" -- README.md', mode="bad-marked")
        calls = self.calls()
        self.assertGreater(len(calls), 1)
        for call in calls:
            self.assertLessEqual(
                len(json.dumps(call["state"], ensure_ascii=False)), 16000
            )
        judged = "".join(
            p["added_lines"]
            for call in calls
            for h in call["state"]["hunks"]
            for p in h["pieces"]
        )
        self.assertIn("Step 0:", judged)
        self.assertIn("Step 119:", judged)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_only_placement_and_style_questions_are_asked(self):
        """The commit-reason and choice questions are gone; every question is a noul."""
        self.add_to_codex_section("## Remote\n\nUse the app.")
        self.run_hook(
            'git commit -m "docs: Record the AGENTS.md sync rule" -m "Refs #12" -- README.md'
        )
        call = self.calls()[0]
        self.assertNotIn("commit", call["state"])
        self.assertTrue(call["questions"])
        for key, question in call["questions"].items():
            self.assertRegex(key, FIT_KEY)
            self.assertEqual(question["type"], "noul")

    def test_background_of_change_carries_the_commit_subject_and_body(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        body = "Explain SSH login. " * 30
        self.run_hook(f'git commit -m "docs: Add SSH login" -m "{body}" -- README.md')
        background = self.calls()[0]["state"]["form"]["background_of_change"]
        self.assertEqual(background, f"docs: Add SSH login ({body.strip()[:300]})")

    def test_commit_without_a_message_has_an_empty_background(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.assertEqual(self.run_hook("git commit -- README.md"), {})
        self.assertEqual(self.calls()[0]["state"]["form"]["background_of_change"], "")

    def test_file_kind_and_role_is_title_intro_and_whole_document_shape(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.run_hook('git commit -m "x" -- README.md')
        state = self.calls()[0]["state"]
        role = state["form"]["file_kind_and_role"]
        self.assertTrue(
            role.startswith("Tool: Tool sets up coding agents on a workstation.")
        )
        self.assertIn("Whole document: 10 non-empty line(s)", role)
        self.assertIn("a command block", role)
        self.assertEqual(
            state["document"]["file_role"],
            "Tool: Tool sets up coding agents on a workstation.",
        )

    def test_place_and_its_purpose_is_heading_chain_and_section_intros(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.run_hook('git commit -m "x" -- README.md')
        place = self.only_hunk()["place_and_its_purpose"]
        self.assertEqual(
            place,
            "Tool > Sign in > Codex. Section 'Sign in: Sign in to each CLI once.' "
            "Section 'Codex: ```bash codex login ```'",
        )

    def test_style_of_this_place_describes_the_section_before_the_change(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.run_hook('git commit -m "x" -- README.md')
        self.assertEqual(
            self.only_hunk()["style_of_this_place"],
            "Existing content of the section 'Codex' before this change: 3 non-empty line(s): "
            "a command block, no external links, 1 inline code span(s) (paths, commands, keys).",
        )

    def test_amend_takes_the_style_from_the_parent_commit(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.git("commit", "-q", "-am", "first")
        self.add_to_codex_section("Run `codex logout` to sign out.")
        self.run_hook('git commit --amend -m "x" -- README.md')
        style = self.only_hunk()["style_of_this_place"]
        self.assertIn("'Codex' before this change: 3 non-empty line(s)", style)

    def test_what_the_edit_adds_is_the_shape_of_the_added_lines(self):
        self.add_to_codex_section(
            "Run `codex login --device-auth` over [SSH](https://example.com)."
        )
        self.run_hook('git commit -m "x" -- README.md')
        (piece,) = self.only_hunk()["pieces"]
        self.assertEqual(
            piece["what_the_edit_adds"],
            "1 non-empty line(s): 1 prose paragraph(s), longest short (64 characters), "
            "1 external link(s), 1 inline code span(s) (paths, commands, keys).",
        )

    def test_no_heading_added_means_no_style_question(self):
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.run_hook('git commit -m "x" -- README.md')
        call = self.calls()[0]
        self.assertNotIn("new_sections", call["state"])
        self.assertEqual(set(call["questions"]), {"fits_0_0"})

    def test_new_top_level_section_is_compared_with_its_siblings(self):
        self.add_to_codex_section(
            "## Remote\n\nUse the [app](https://example.com).\n\n### Details\n\nMore."
        )
        self.run_hook('git commit -m "x" -- README.md')
        call = self.calls()[0]
        (section,) = call["state"]["new_sections"]
        self.assertEqual(section["heading"], "Remote")
        self.assertEqual(
            section["new_section"],
            {
                "lines": 4, "paragraphs": 4, "table_rows": 0, "code_blocks": 0,
                "external_links": 1, "subheadings": 2,
                "text": "## Remote\n\nUse the [app](https://example.com).\n\n### Details\n\nMore.\n",
            },
        )  # fmt: skip
        siblings = section["sibling_sections"]
        self.assertEqual([s["heading"] for s in siblings], ["Sign in", "Updating"])
        self.assertEqual(siblings[1]["text"], "## Updating\n\nPull and rerun.")
        self.assertEqual(siblings[0]["code_blocks"], 1)
        self.assertEqual(
            [k for k in call["questions"] if k.startswith("style_")], ["style_0"]
        )
        self.assertIn(
            "new_sections[0].sibling_sections",
            call["questions"]["style_0"]["instructions"],
        )

    def test_new_section_and_sibling_text_are_truncated(self):
        readme = (self.repo / "README.md").read_text()
        (self.repo / "README.md").write_text(
            readme.replace("Pull and rerun.", "Pull. " * 400)
        )
        self.git("commit", "-q", "-am", "long sibling")
        self.add_to_codex_section("## Remote\n\n" + "Long text. " * 800)
        self.run_hook('git commit -m "x" -- README.md')
        (section,) = [
            s for c in self.calls() for s in c["state"].get("new_sections", [])
        ]
        self.assertEqual(len(section["new_section"]["text"]), 5000)
        self.assertEqual(section["new_section"]["lines"], 2)
        self.assertEqual(len(section["sibling_sections"][1]["text"]), 1200)

    def test_new_section_style_misfit_is_denied(self):
        self.add_to_codex_section("## Remote\n\nUse the app.")
        output = self.run_hook('git commit -m "x" -- README.md', mode="bad-style")
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        (line,) = [x for x in reason.splitlines() if x.startswith("- README.md:")]
        self.assertTrue(line.startswith("- README.md:15 "))
        self.assertIn("Tool > Remote", line)
        self.assertIn("書きぶり", line)
        self.assertNotIn("置いた場所", line)
        self.assertIn("## Remote", reason)

    def test_new_section_paragraphs_are_judged_one_by_one_under_their_own_heading(self):
        self.add_to_codex_section(
            "## Remote\n\nUse the app.\n\n### Details\n\nMAINTAINER evidence link."
        )
        output = self.run_hook('git commit -m "x" -- README.md', mode="bad-marked")
        hunks = [h for call in self.calls() for h in call["state"]["hunks"]]
        marked = [
            (h, p)
            for h in hunks
            for p in h["pieces"]
            if "MAINTAINER" in p["added_lines"]
        ]
        self.assertEqual(len(marked), 1)
        self.assertNotIn("Use the app.", marked[0][1]["added_lines"])
        self.assertTrue(
            marked[0][0]["place_and_its_purpose"].startswith("Tool > Remote > Details.")
        )
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("Remote > Details", reason)
        self.assertNotIn("Use the app.", reason)

    def test_threshold_denies_below_one_half_only(self):
        self.add_to_codex_section("MAINTAINER note")
        self.noul = 0.45
        denied = self.run_hook('git commit -m "x" -- README.md', mode="bad")
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.noul = 0.55
        self.assertEqual(
            self.run_hook('git commit -m "x" -- README.md', mode="bad"), {}
        )

    def test_code_piece_maps_scope_and_docstring_into_the_same_slots(self):
        (self.repo / "loader.py").write_text(CODE)
        self.git("add", "loader.py")
        self.git("commit", "-q", "-m", "code")
        (self.repo / "loader.py").write_text(
            CODE.replace(
                "    return open(path).read()",
                "    text = open(path).read()\n    return text",
            )
        )
        self.run_hook('git commit -m "x" -- loader.py')
        call = self.calls()[0]
        self.assertIn(
            "Loader for agent settings files.",
            call["state"]["form"]["file_kind_and_role"],
        )
        (hunk,) = call["state"]["hunks"]
        self.assertEqual(hunk["place_and_its_purpose"], "def load(path):")
        self.assertIn("def helper():", hunk["style_of_this_place"])
        self.assertIn("responsibility", call["questions"]["fits_0_0"]["instructions"])

    def test_each_file_is_judged_in_its_own_request(self):
        (self.repo / "loader.py").write_text(CODE)
        self.git("add", "loader.py")
        self.git("commit", "-q", "-m", "code")
        (self.repo / "loader.py").write_text(CODE.replace("return 1", "return 2"))
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.run_hook('git commit -m "x" -- README.md loader.py')
        files = sorted(call["state"]["document"]["file"] for call in self.calls())
        self.assertEqual(files, ["README.md", "loader.py"])

    def test_new_file_and_deletion_only_changes_are_not_sent(self):
        (self.repo / "NEW.md").write_text("# New\n\nMAINTAINER note\n")
        readme = (self.repo / "README.md").read_text()
        (self.repo / "README.md").write_text(readme.replace("Pull and rerun.\n", ""))
        self.assertEqual(
            self.run_hook('git commit -m "x" -- NEW.md README.md', mode="bad"), {}
        )
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.records(), [])

    def test_deny_is_logged_with_the_scores_of_each_piece(self):
        """A later analysis joins denies with follow-up commits, so each run keeps what was judged and how."""
        added = "MAINTAINER note: keep AGENTS.md in sync."
        self.add_to_codex_section(added)
        self.run_hook(
            'git commit -m "docs: Add note" -m "Body." -- README.md', mode="bad"
        )
        (record,) = self.records()
        self.assertEqual(record["outcome"], "deny")
        self.assertIsNone(record["skip_reason"])
        self.assertEqual(record["session_id"], "sess-1")
        self.assertEqual(record["subject"], "docs: Add note")
        self.assertEqual(os.path.realpath(record["repo"]), os.path.realpath(self.repo))
        self.assertEqual(os.path.realpath(record["cwd"]), os.path.realpath(self.repo))
        self.assertEqual(record["threshold"], 0.5)
        self.assertTrue(record["question_version"])
        self.assertRegex(record["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        self.assertEqual(record["model"], "stub-jev")
        self.assertEqual(record["input_tokens"], 7)
        self.assertEqual(len(record["request_latency_ms"]), 1)
        self.assertEqual(record["server_pid"], os.getpid())
        self.assertGreaterEqual(record["latency_ms"], record["request_latency_ms"][0])
        self.assertEqual(
            record["pieces"],
            [{
                "file": "README.md", "line": 15, "kind": "docs", "place": "Tool > Sign in > Codex",
                "what_the_edit_adds": self.calls()[0]["state"]["hunks"][0]["pieces"][0]["what_the_edit_adds"],
                "added_sha256": hashlib.sha256(added.encode()).hexdigest(), "added_head": added,
                "fit": 0.1, "failed": True,
            }],
        )  # fmt: skip
        self.assertEqual(record["new_sections"], [])

    def test_allow_is_logged_with_new_section_style_scores(self):
        self.add_to_codex_section("## Remote\n\n" + "Use the app. " * 30)
        self.assertEqual(self.run_hook("git commit -- README.md"), {})
        (record,) = self.records()
        self.assertEqual(record["outcome"], "allow")
        self.assertEqual(record["subject"], "")
        self.assertEqual(len(record["pieces"][0]["added_head"]), 200)
        self.assertEqual([p["failed"] for p in record["pieces"]], [False])
        self.assertEqual(
            record["new_sections"],
            [{"file": "README.md", "line": 15, "place": "Tool > Remote", "heading": "Remote",
              "style": 0.9, "failed": False}],
        )  # fmt: skip

    def test_skip_is_logged_with_its_reason(self):
        self.add_to_codex_section("MAINTAINER note")
        self.run_hook('git commit -m "x" -- README.md', mode="error")
        (record,) = self.records()
        self.assertEqual(record["outcome"], "skip")
        self.assertIn("No API key", record["skip_reason"])
        self.assertIsNone(record["pieces"][0]["fit"])

    def test_unwritable_log_path_leaves_the_output_unchanged(self):
        self.add_to_codex_section("MAINTAINER note")
        expected = self.run_hook('git commit -m "x" -- README.md', mode="bad")
        blocker = self.gate_log.parent.parent / "blocker"
        blocker.write_text("")
        self.log_path = blocker / "log.jsonl"
        self.assertEqual(
            self.run_hook('git commit -m "x" -- README.md', mode="bad"), expected
        )



class RegistrationTest(unittest.TestCase):
    """Both clients hand the commit to the connected jev server; no hook starts a process to judge it."""

    # Claude Code documents substitution into string values only, so it passes the command string.
    CLAUDE_INPUT = {"command": "${tool_input.command}", "cwd": "${cwd}", "session_id": "${session_id}"}
    CODEX_INPUT = {"tool_input": "${tool_input}", "cwd": "${cwd}", "session_id": "${session_id}"}

    def test_claude_code_calls_the_connected_jev_server(self):
        settings = json.loads((ROOT / "files" / "claude_managed-extensions.json").read_text())
        hooks = [h for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertFalse([h for h in hooks if "jev_context_gate" in h.get("command", "")])
        (hook,) = [h for h in hooks if h.get("type") == "mcp_tool" and h.get("server") == "jev"]
        self.assertEqual(hook["tool"], "context_gate")
        self.assertEqual(hook["if"], "Bash(git *)")
        self.assertEqual(hook["input"], self.CLAUDE_INPUT)

    def test_codex_calls_the_connected_jev_server(self):
        config = tomllib.loads((ROOT / "files" / "codex_config.toml").read_text())
        hooks = [h for g in config["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertFalse([h for h in hooks if "jev_context_gate" in h.get("command", "")])
        (hook,) = [h for h in hooks if h.get("type") == "mcp_tool" and h.get("server") == "jev"]
        self.assertEqual(hook["tool"], "context_gate")
        self.assertEqual(hook["input"], self.CODEX_INPUT)

    def test_the_module_ships_with_the_jev_runtime_not_as_a_hook(self):
        self.assertFalse((ROOT / "files" / "shared_hooks" / "jev_context_gate.py").exists())
        for script in ("debian12.sh", "ubuntu2404-wsl.sh"):
            text = (ROOT / script).read_text()
            copied = re.search(r"^copy jev_context_gate\.py +/usr/local/lib/jev/jev_context_gate\.py", text, re.M)
            self.assertTrue(copied, f"{script} does not ship the module with the jev runtime")


if __name__ == "__main__":
    unittest.main()
