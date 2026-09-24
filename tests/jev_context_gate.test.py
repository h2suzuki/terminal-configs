#!/usr/bin/env python3
"""Tests for jev_context_gate: the connected jev server calls check() with its own evaluate; throwaway repos provide the commits."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
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
FIT_KEY = re.compile(r"fits_\d+_\d+|style_\d+|placed_\d+")


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
                elif kind == "placed":
                    text = state["new_files"][int(index[0])]["opening"]
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

    def test_gather_prints_exactly_the_requests_check_sends(self):
        """An agent-type hook gathers with `gather`; it must see the same state and questions check() sends."""
        self.add_to_codex_section("MAINTAINER note: keep AGENTS.md in sync.")
        command = 'git commit -m "docs: Add a note" -- README.md'
        self.run_hook(command)
        gathered = subprocess.run(
            [sys.executable, str(ROOT / "files" / "jev_context_gate.py"), "gather",
             "--cwd", str(self.repo), "--command", command],
            capture_output=True, text=True, check=True, env=self.env,
        )  # fmt: skip
        self.assertEqual(json.loads(gathered.stdout)["requests"], self.sent)

    def test_gather_prints_no_requests_for_other_commands(self):
        gathered = subprocess.run(
            [sys.executable, str(ROOT / "files" / "jev_context_gate.py"), "gather",
             "--cwd", str(self.repo), "--command", "git status"],
            capture_output=True, text=True, check=True, env=self.env,
        )  # fmt: skip
        self.assertEqual(json.loads(gathered.stdout), {"requests": []})

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

    def test_heredoc_message_gives_its_text_as_the_background(self):
        """Commit hooks require -m "$(cat <<'EOF' ...)"; unexpanded, the subject was the shell text itself."""
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        for opener in ("<<'EOF'", '<<"EOF"', "<<EOF", "<<-'EOF'"):
            self.sent.clear()
            self.run_hook(
                f'git commit -q -m "$(cat {opener}\ndocs: Add SSH login\n\nExplain SSH login.\nEOF\n)" -- README.md'
            )
            background = self.calls()[0]["state"]["form"]["background_of_change"]
            self.assertEqual(background, "docs: Add SSH login (Explain SSH login.)", opener)
        self.assertEqual(self.records()[-1]["subject"], "docs: Add SSH login")

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
            "a command block, no external links, 0 inline code span(s) (paths, commands, keys).",
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

    def test_new_heading_is_placed_in_the_section_it_joins(self):
        """Backtest: a section moved or inserted elsewhere was asked whether it fits itself, and passed (5 of 5)."""
        self.add_to_codex_section("### Proxy\n\nSet HTTPS_PROXY before signing in.")
        self.run_hook('git commit -m "x" -- README.md')
        hunk = self.only_hunk()
        self.assertTrue(hunk["place_and_its_purpose"].startswith("Tool > Sign in."))
        (piece,) = hunk["pieces"]
        self.assertIn(
            "a new section (heading 'Proxy') placed after the section 'Codex'",
            piece["what_the_edit_adds"],
        )

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
        self.assertTrue(marked[0][0]["place_and_its_purpose"].startswith("Tool > Remote."))
        self.assertIn("new section (heading 'Details')", marked[0][1]["what_the_edit_adds"])
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("Tool > Remote", reason)
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

    def test_definition_nested_in_another_scope_is_named_in_what_the_edit_adds(self):
        """Backtest: new tests moved inside test('PATCH request') passed at 0.53; the nesting was never stated."""
        (self.repo / "loader.py").write_text(CODE)
        self.git("add", "loader.py")
        self.git("commit", "-q", "-m", "code")
        (self.repo / "loader.py").write_text(
            CODE.replace(
                "    return open(path).read()\n",
                "    return open(path).read()\n\n    def save(text):\n        return text\n",
            )
        )
        self.run_hook('git commit -m "x" -- loader.py')
        (piece,) = self.only_hunk()["pieces"]
        self.assertEqual(
            piece["what_the_edit_adds"],
            "2 non-empty line(s) of code, defining `def save(text):` inside `def load(path):`.",
        )

    def test_json_place_is_the_open_key_path(self):
        """Backtest: hooks moved into "permissions" were judged at "(top level of the file)" and passed (4 of 4)."""
        settings = (
            '{\n  "permissions": {\n    "allow": [\n      "Bash(ls)"\n    ],\n    "defaultMode": "auto"\n  },\n'
            '  "hooks": {\n    "Stop": []\n  }\n}\n'
        )
        (self.repo / "settings.json").write_text(settings)
        self.git("add", "settings.json")
        self.git("commit", "-q", "-m", "settings")
        (self.repo / "settings.json").write_text(
            settings.replace('      "Bash(ls)"\n', '      "Bash(ls)",\n      "Bash(pwd)"\n').replace(
                '    "defaultMode": "auto"\n', '    "SessionStart": [],\n    "defaultMode": "auto"\n'
            )
        )
        self.run_hook('git commit -m "x" -- settings.json')
        hunks = [h for c in self.calls() for h in c["state"]["hunks"]]
        self.assertEqual(
            [h["place_and_its_purpose"] for h in hunks],
            ["permissions > allow", "permissions"],
        )
        self.assertEqual(
            hunks[0]["style_of_this_place"],
            "Keys before this change: permissions; permissions > allow; permissions > defaultMode; hooks; hooks > Stop",
        )

    def test_helpers_in_test_files_get_the_code_question(self):
        """Backtest: a cleanup line in setUp scored 0.21 when asked whether it checks what "that test" is about."""
        suite = (
            "import unittest\n\n\nclass Base(unittest.TestCase):\n    def setUp(self):\n        self.tmp = 1\n\n"
            "    def test_value(self):\n        self.assertEqual(self.tmp, 1)\n"
        )
        (self.repo / "suite_test.py").write_text(suite)
        self.git("add", "suite_test.py")
        self.git("commit", "-q", "-m", "tests")
        (self.repo / "suite_test.py").write_text(
            suite.replace("        self.tmp = 1\n", "        self.tmp = 1\n        self.extra = 2\n").replace(
                "self.assertEqual(self.tmp, 1)\n", "self.assertEqual(self.tmp, 1)\n        self.assertTrue(self.extra)\n"
            )
        )
        self.run_hook('git commit -m "x" -- suite_test.py')
        asked = {
            h["place_and_its_purpose"].split(" > ")[-1]: q["instructions"]
            for c in self.calls()
            for i, h in enumerate(c["state"]["hunks"])
            for q in [c["questions"][f"fits_{i}_0"]]
        }
        self.assertIn("responsibility", asked["def setUp(self):"])
        self.assertIn("check what that test is about", asked["def test_value(self):"])

    def test_top_level_code_is_asked_whether_it_belongs_at_the_top_level(self):
        """Asked whether it did the job of the place "(top level of the file)", a needed import line scored 0.09."""
        for name in ("loader.py", "loader_test.py"):
            with self.subTest(name=name):
                self.sent.clear()
                (self.repo / name).write_text(CODE)
                self.git("add", name)
                self.git("commit", "-q", "-m", "code")
                (self.repo / name).write_text(CODE.replace('"""\n\n\n', '"""\n\nimport os\n\n\n'))
                self.run_hook(f'git commit -m "x" -- {name}')
                call = self.calls()[0]
                (hunk,) = call["state"]["hunks"]
                self.assertEqual(hunk["place_and_its_purpose"], "(top level of the file)")
                self.assertIn("top level of this file", call["questions"]["fits_0_0"]["instructions"])

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

    def test_new_code_function_with_blank_lines_is_one_piece(self):
        """Split on blank lines, the tail of a new function was judged alone with no place of its own."""
        (self.repo / "loader.py").write_text(CODE)
        self.git("add", "loader.py")
        self.git("commit", "-q", "-m", "code")
        added = "def save(path, text):\n    handle = open(path, 'w')\n\n    handle.write(text)\n\n    return handle.close()"
        (self.repo / "loader.py").write_text(CODE + "\n\n" + added + "\n")
        self.run_hook('git commit -m "x" -- loader.py')
        hunk = self.only_hunk()
        self.assertEqual([p["added_lines"] for p in hunk["pieces"]], [added])
        self.assertEqual(hunk["place_and_its_purpose"], "(top level of the file)")

    def test_code_hunk_over_the_chunk_limit_is_still_split(self):
        (self.repo / "loader.py").write_text(CODE)
        self.git("add", "loader.py")
        self.git("commit", "-q", "-m", "code")
        body = "\n".join(f"    value_{i} = compute('{'x' * 30}', {i})" for i in range(60))
        (self.repo / "loader.py").write_text(CODE + "\n\ndef build():\n" + body + "\n")
        self.run_hook('git commit -m "x" -- loader.py')
        pieces = [p for c in self.calls() for h in c["state"]["hunks"] for p in h["pieces"]]
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(p["added_lines"]) <= gate.CHUNK_LIMIT for p in pieces))
        self.assertTrue(pieces[0]["added_lines"].startswith("def build():"))
        self.assertTrue(pieces[-1]["added_lines"].endswith(f"value_59 = compute('{'x' * 30}', 59)"))

    def test_code_block_is_judged_with_the_paragraph_that_introduces_it(self):
        """A README example judged apart from its explanation lost what it illustrates."""
        self.add_to_codex_section(
            "Run the login once.\n\n```bash\ncodex login --device-auth\n\ncodex whoami\n```\n\nThen restart."
        )
        self.run_hook('git commit -m "x" -- README.md')
        self.assertEqual(
            [p["added_lines"] for p in self.only_hunk()["pieces"]],
            [
                "Run the login once.\n\n```bash\ncodex login --device-auth\n\ncodex whoami\n```",
                "Then restart.",
            ],
        )

    def test_shape_does_not_count_code_block_contents_as_prose_or_inline_code(self):
        lines = "Run the login once.\n\n```bash\ncodex login --device-auth\n\ncodex whoami\n```".splitlines()
        self.assertEqual(
            gate.shape_sentence(lines),
            "5 non-empty line(s): a command block, 1 prose paragraph(s), longest short (19 characters), "
            "no external links, 0 inline code span(s) (paths, commands, keys).",
        )

    def test_each_file_is_judged_in_its_own_request(self):
        (self.repo / "loader.py").write_text(CODE)
        self.git("add", "loader.py")
        self.git("commit", "-q", "-m", "code")
        (self.repo / "loader.py").write_text(CODE.replace("return 1", "return 2"))
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        self.run_hook('git commit -m "x" -- README.md loader.py')
        files = sorted(call["state"]["document"]["file"] for call in self.calls())
        self.assertEqual(files, ["README.md", "loader.py"])

    def add_new_file(self, name: str, text: str) -> None:
        (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / name).write_text(text)
        self.git("add", name)

    def test_new_file_is_asked_whether_it_belongs_at_its_path(self):
        """N1/N2: a file the commit adds gets one question about its path, filled from the file and its directory."""
        self.add_new_file("NOTES.md", "# Notes\n\nDraft of the design.\n\n- keep it\n")
        self.run_hook('git commit -m "Add design notes" -- NOTES.md')
        (call,) = self.calls()
        self.assertEqual(call["state"]["hunks"], [])
        (new,) = call["state"]["new_files"]
        self.assertEqual(new["path"], "NOTES.md")
        self.assertEqual(new["file_kind_and_role"], "Notes: Draft of the design.")
        text = (self.repo / "NOTES.md").read_text()
        self.assertEqual(new["shape"], gate.shape_sentence(text.splitlines()))
        self.assertEqual(new["opening"], text.rstrip("\n"))
        self.assertEqual(new["directory_neighbors"], ["README.md"])
        background = call["state"]["form"]["background_of_change"]
        self.assertEqual(background, "Add design notes")
        self.assertEqual(list(call["questions"]), ["placed_0"])
        question = call["questions"]["placed_0"]
        self.assertIn("new_files[0].directory_neighbors", question["instructions"])
        self.assertEqual(question["type"], "noul")

    def test_staged_new_file_is_judged_for_a_commit_without_paths(self):
        self.add_new_file("NOTES.md", "# Notes\n\nStaged text.\n")
        (self.repo / "NOTES.md").write_text("# Notes\n\nWorktree text.\n")
        self.run_hook('git commit -m "x"')
        (new,) = self.calls()[0]["state"]["new_files"]
        self.assertIn("Staged text.", new["opening"])

    def test_new_file_neighbors_are_the_entries_of_its_own_directory(self):
        """N2: directories end in a slash; only the directory the file lands in is listed."""
        self.add_new_file("docs/guide.md", "# Guide\n\nRead me.\n")
        self.add_new_file("docs/deep/x.md", "# X\n\nx\n")
        self.git("commit", "-q", "-m", "docs")
        self.add_new_file("docs/plan.md", "# Plan\n\nNext steps.\n")
        self.run_hook('git commit -m "x" -- docs/plan.md')
        (new,) = self.calls()[0]["state"]["new_files"]
        self.assertEqual(new["directory_neighbors"], ["deep/", "guide.md"])
        self.git("reset", "-q", "--", "docs/plan.md")
        self.add_new_file("PLAN.md", "# Plan\n\nNext steps.\n")
        self.sent.clear()
        self.run_hook('git commit -m "x" -- PLAN.md')
        (new,) = self.calls()[0]["state"]["new_files"]
        self.assertEqual(new["directory_neighbors"], ["README.md", "docs/"])

    def test_new_file_in_a_new_directory_lists_the_nearest_existing_parent(self):
        """N2: a new directory has no entries yet, so the question shows its nearest existing parent instead."""
        self.add_new_file("docs/guide.md", "# Guide\n\nRead me.\n")
        self.git("commit", "-q", "-m", "docs")
        self.add_new_file("docs/skills/mytask/SKILL.md", "# Mytask\n\nRecord work.\n")
        self.run_hook('git commit -m "x" -- docs/skills/mytask/SKILL.md')
        (new,) = self.calls()[0]["state"]["new_files"]
        self.assertEqual(new["directory"], "docs")
        self.assertEqual(new["directory_neighbors"], ["guide.md"])
        self.git("reset", "-q", "--", "docs/skills/mytask/SKILL.md")
        self.add_new_file("NOTES.md", "# Notes\n\nx\n")
        self.sent.clear()
        self.run_hook('git commit -m "x" -- NOTES.md')
        (new,) = self.calls()[0]["state"]["new_files"]
        self.assertEqual(new["directory"], "(top level)")

    def test_new_file_neighbors_do_not_depend_on_the_commit_directory(self):
        self.add_new_file("docs/guide.md", "# Guide\n\nRead me.\n")
        self.git("commit", "-q", "-m", "docs")
        self.add_new_file("docs/plan.md", "# Plan\n\nNext steps.\n")
        self.run_hook('git -C docs commit -m "x" -- plan.md')
        (new,) = self.calls()[0]["state"]["new_files"]
        self.assertEqual(new["path"], "docs/plan.md")
        self.assertEqual(new["directory_neighbors"], ["guide.md"])

    def test_new_file_neighbors_and_opening_are_limited(self):
        for i in range(gate.OUTLINE_LIMIT + 5):
            self.add_new_file(f"n{i:02d}.txt", "x\n")
        self.git("commit", "-q", "-m", "many")
        self.add_new_file("LONG.md", "# Long\n\n" + "word " * 2000)
        self.run_hook('git commit -m "x" -- LONG.md')
        (new,) = self.calls()[0]["state"]["new_files"]
        self.assertEqual(len(new["opening"]), gate.OPENING_LIMIT)
        self.assertEqual(len(new["directory_neighbors"]), gate.OUTLINE_LIMIT + 1)
        self.assertEqual(new["directory_neighbors"][-1], "(and 6 more)")

    def test_new_file_that_does_not_belong_is_denied_with_its_first_lines(self):
        """N3: below the threshold the commit is denied, naming the file and the new-file question."""
        self.add_new_file("NOTES.md", "# Notes\n\nDraft of the design.\n")
        output = self.run_hook('git commit -m "x" -- NOTES.md', mode="bad")
        decision = output["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        reason = decision["permissionDecisionReason"]
        self.assertIn("NOTES.md:1", reason)
        self.assertIn(gate.NEW_FILE_MISFIT, reason)
        self.assertIn("+ # Notes", reason)
        self.assertIn("+ Draft of the design.", reason)

    def test_new_file_and_edit_in_one_commit_are_judged_in_their_own_requests(self):
        self.add_new_file("NOTES.md", "# Notes\n\nMAINTAINER draft.\n")
        self.add_to_codex_section("Run `codex login --device-auth` over SSH.")
        output = self.run_hook(
            'git commit -m "x" -- README.md NOTES.md', mode="bad-marked"
        )
        by_file = {c["state"]["document"]["file"]: c for c in self.calls()}
        self.assertEqual(sorted(by_file), ["NOTES.md", "README.md"])
        self.assertNotIn("new_files", by_file["README.md"]["state"])
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("NOTES.md:1", reason)
        self.assertNotIn("README.md:", reason)

    def test_new_file_is_logged_with_its_score(self):
        """N4: the log keeps the new-file judgment beside pieces and new sections."""
        self.add_new_file("NOTES.md", "# Notes\n\nDraft.\n")
        self.run_hook('git commit -m "x" -- NOTES.md')
        (record,) = self.records()
        self.assertEqual(record["outcome"], "allow")
        self.assertEqual(record["pieces"], [])
        self.assertEqual(
            record["new_files"],
            [{"file": "NOTES.md", "line": 1, "place": "(top level)", "placed": 0.9, "failed": False}],
        )  # fmt: skip

    def test_untracked_file_and_deletion_only_changes_are_not_sent(self):
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


def scope_of(source: str, needle: str) -> str:
    lines = source.splitlines()
    index = next(i for i, line in enumerate(lines) if needle in line)
    return gate.code_scope(lines, index)


class ScopeDetectionTest(unittest.TestCase):
    """P1: SCOPE_RE/code_scope must name JS/TS definitions, not fall back to top level."""

    def test_export_function_is_the_place(self):
        src = "export function foo(a) {\n  return a + 1;\n}\n"
        self.assertEqual(scope_of(src, "return a"), "export function foo(a) {")

    def test_export_default_function_is_the_place(self):
        src = "export default function foo(a) {\n  return a + 1;\n}\n"
        self.assertEqual(scope_of(src, "return a"), "export default function foo(a) {")

    def test_export_async_function_is_the_place(self):
        src = "export async function foo(a) {\n  return a + 1;\n}\n"
        self.assertEqual(scope_of(src, "return a"), "export async function foo(a) {")

    def test_bare_async_function_is_the_place(self):
        src = "async function foo(a) {\n  return a + 1;\n}\n"
        self.assertEqual(scope_of(src, "return a"), "async function foo(a) {")

    def test_arrow_function_bound_to_a_name_is_the_place(self):
        src = "const x = (a) => {\n  return a;\n};\n"
        self.assertEqual(scope_of(src, "return a"), "const x = (a) => {")

    def test_async_arrow_function_bound_to_a_name_is_the_place(self):
        src = "const x = async (a) => {\n  return a;\n};\n"
        self.assertEqual(scope_of(src, "return a"), "const x = async (a) => {")

    def test_export_const_arrow_function_is_the_place(self):
        src = "export const x = (a) => {\n  return a;\n};\n"
        self.assertEqual(scope_of(src, "return a"), "export const x = (a) => {")

    def test_class_method_with_arguments_is_the_place(self):
        src = "class Foo {\n  method(a, b) {\n    return a + b;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return a + b"), "class Foo { > method(a, b) {")

    def test_typed_method_and_arrow_are_the_place(self):
        """TS return-type annotations sit between the parameters and `{` or `=>`."""
        src = "class Foo {\n  method(a: number): number {\n    return a;\n  }\n}\n"
        self.assertEqual(
            scope_of(src, "return a"), "class Foo { > method(a: number): number {"
        )
        src = "const f = (a: T): Promise<T> => {\n  return a;\n};\n"
        self.assertEqual(scope_of(src, "return a"), "const f = (a: T): Promise<T> => {")

    def test_async_method_is_the_place(self):
        src = "class Foo {\n  async method(a) {\n    return a;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return a"), "class Foo { > async method(a) {")

    def test_static_method_is_the_place(self):
        src = "class Foo {\n  static method(a) {\n    return a;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return a"), "class Foo { > static method(a) {")

    def test_get_accessor_is_the_place(self):
        src = "class Foo {\n  get value() {\n    return this._v;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return this"), "class Foo { > get value() {")

    def test_set_accessor_is_the_place(self):
        src = "class Foo {\n  set value(v) {\n    this._v = v;\n  }\n}\n"
        self.assertEqual(scope_of(src, "this._v = v"), "class Foo { > set value(v) {")

    def test_describe_it_nesting_chain(self):
        src = (
            "describe('a', () => {\n"
            "  it('b', () => {\n"
            "    expect(1).toBe(1);\n"
            "  });\n"
            "});\n"
        )
        self.assertEqual(
            scope_of(src, "expect(1)"), "describe('a', () => { > it('b', () => {"
        )

    def test_test_block_is_the_place(self):
        src = "test('does x', async t => {\n  t.is(1, 1);\n});\n"
        self.assertEqual(scope_of(src, "t.is(1, 1)"), "test('does x', async t => {")

    def test_if_statement_is_not_a_definition(self):
        src = "function foo() {\n  if (x) {\n    return 1;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return 1"), "function foo() {")

    def test_for_statement_is_not_a_definition(self):
        src = "function foo() {\n  for (let i = 0; i < 1; i++) {\n    return 1;\n  }\n}\n"  # fmt: skip
        self.assertEqual(scope_of(src, "return 1"), "function foo() {")

    def test_while_statement_is_not_a_definition(self):
        src = "function foo() {\n  while (x) {\n    return 1;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return 1"), "function foo() {")

    def test_switch_statement_is_not_a_definition(self):
        src = "function foo() {\n  switch (x) {\n    return 1;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return 1"), "function foo() {")

    def test_catch_clause_is_not_a_definition(self):
        src = "function foo() {\n  catch (e) {\n    return 1;\n  }\n}\n"
        self.assertEqual(scope_of(src, "return 1"), "function foo() {")

    def test_plain_call_statement_does_not_match_scope_re(self):
        self.assertIsNone(gate.SCOPE_RE.match("foo(a);"))

    def test_access_modifiers_and_private_names_are_the_place(self):
        """Backtest: lines inside `protected _stream(...)` and `async #parseJson(...)` were placed in the constructor."""
        for header in (
            "protected _stream(response: Response) {",
            "async #parseJson(text: string): Promise<unknown> {",
            "private static helper(): void {",
            "public readonly get size(): number {",
            "#decorate(response) {",
        ):
            with self.subTest(header=header):
                src = f"class Ky {{\n  constructor() {{\n    this.a = 1;\n  }}\n\n  {header}\n    return 1;\n  }}\n}}\n"
                self.assertEqual(scope_of(src, "return 1"), f"class Ky {{ > {header}")

    def test_test_modifier_calls_are_the_place(self):
        for call in ("test.serial", "test.failing", "it.only", "describe.skip"):
            with self.subTest(call=call):
                src = f"{call}('works', async t => {{\n  const b = 2;\n}});\n"
                self.assertEqual(scope_of(src, "const b"), f"{call}('works', async t => {{")

    def test_unrecognized_block_hides_the_sibling_above_it(self):
        """A header the gate cannot name must not let the previous sibling method pass for the enclosing one."""
        src = "class A {\n  constructor() {\n    this.a = 1;\n  }\n\n  *gen() {\n    yield 1;\n  }\n}\n"
        self.assertEqual(scope_of(src, "yield 1"), "class A {")

    def test_type_declarations_are_the_place(self):
        """Backtest: a doc comment inside an exported hooks interface was judged as top-level code (0.49)."""
        for header in (
            "export interface Hooks {",
            "interface Options extends Base {",
            "export type Options = {",
            "type State<T> = {",
            "export enum Kind {",
            "declare module 'ky' {",
            "namespace Ky {",
        ):
            with self.subTest(header=header):
                src = f"{header}\n  beforeRetry: Hook[];\n}}\n"
                self.assertEqual(scope_of(src, "beforeRetry"), header)

    def test_multi_line_python_signature_still_names_the_function(self):
        src = "def f(\n    a,\n    b,\n):\n    return a\n"
        self.assertEqual(scope_of(src, "return a"), "def f(")


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

    def test_agent_hook_probe_runs_only_on_its_marker_and_never_judges_without_jev(self):
        """The subagent-type trial gathers with the deployed module, asks the connected Jev, and passes when Jev is unreachable."""
        settings = json.loads((ROOT / "files" / "claude_managed-extensions.json").read_text())
        hooks = [h for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        (probe,) = [h for h in hooks if h.get("type") == "agent"]
        self.assertEqual(probe["if"], "Bash(git -c jev.probe=1 *)")
        prompt = probe["prompt"]
        self.assertIn("$ARGUMENTS", prompt)
        self.assertIn("python3 /usr/local/lib/jev/jev_context_gate.py gather", prompt)
        self.assertIn("mcp__jev__evaluate", prompt)
        self.assertIn("Never judge the text yourself", prompt)
        # The if filter still fires on any command with $VAR or $(), so other commands must pass at once.
        self.assertIn('Unless tool_input.command contains the exact text `git -c jev.probe=1 commit`, answer {"ok": true} at once', prompt)
        allow = settings["permissions"]["allow"]
        self.assertIn("mcp__jev__evaluate", allow)
        self.assertIn("Bash(python3 /usr/local/lib/jev/jev_context_gate.py gather *)", allow)

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
