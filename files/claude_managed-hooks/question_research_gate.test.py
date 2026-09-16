#!/usr/bin/env python3
r"""Acceptance tests for question_research_gate.py, written before the implementation.

Contract: a question put to the user must be preceded, in the same turn, by a search of every
research channel this host actually has. Channels: 教訓 (the lessons clone), issue tracker
(GitHub via `gh` / GitLab via `glab`), docs (`docs/` or a repo-root `README*.md`). A channel that
does not exist here is exempt, so a host with none of them never blocks.

Claims (test_q<N>_*):
  Q1 PreToolUse:AskUserQuestion with no search in the turn -> deny JSON naming every missing channel.
  Q2 every available channel searched -> silent allow.
  Q3 a partially searched turn still denies, and the reason names only what is missing.
  Q4 an unavailable channel is exempt; with none available the gate never fires.
  Q5 Stop whose final text asks the user something -> exit 2 with the reason on stderr.
  Q6 Stop with no question -> silent pass; a question inside a fence is not a question.
  Q7 Stop with stop_hook_active -> pass (one block per turn, no re-block loop).
  Q8 fail-open: a broken payload, missing transcript or unreadable turn never blocks.
  Q9 evidence counts from any tool input in the turn (Bash, Grep, a delegated Agent prompt).
  Q10 evidence from an earlier turn does not count.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "question_research_gate.py"
)
SESSION = "99999999-8888-7777-6666-555555555555"
PROMPT = "この設計の当否を判断してください"
QUESTION = {
    "questions": [{"question": "どの案を採用しますか?", "header": "案", "options": []}]
}


def user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def call(name: str, **tool_input) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": name, "input": tool_input}],
        },
    }


def say(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


class Fixture:
    """A temp host: lessons clone, GitHub remote, `gh` on PATH, docs/ and README.md — each removable."""

    def __init__(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="question-research-")
        self.home = os.path.join(self.tmp, "home")
        self.cwd = os.path.join(self.tmp, "repo")
        self.bin = os.path.join(self.tmp, "bin")
        self.memory = os.path.join(self.tmp, "memory", "claude-lessons-learned")
        for path in (self.home, self.cwd, self.bin, os.path.join(self.memory, "org")):
            os.makedirs(path)
        os.makedirs(os.path.join(self.cwd, "docs"))
        self.write_file("README.md", "# repo\n")
        self.write_file("docs/design.md", "# design\n")
        self.stub("gh")
        os.symlink(shutil.which("git") or "/usr/bin/git", os.path.join(self.bin, "git"))
        self.transcript = os.path.join(self.tmp, "session.jsonl")
        self.turn()
        subprocess.run(["git", "-C", self.cwd, "init", "-q"], check=True)
        self.remote("https://github.com/acme/widgets.git")

    def write_file(self, relative: str, body: str) -> None:
        path = os.path.join(self.cwd, relative)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(body)

    def stub(self, name: str) -> None:
        path = os.path.join(self.bin, name)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)

    def remote(self, url: str | None) -> None:
        subprocess.run(
            ["git", "-C", self.cwd, "remote", "remove", "origin"],
            check=False,
            capture_output=True,
        )
        if url:
            subprocess.run(
                ["git", "-C", self.cwd, "remote", "add", "origin", url], check=True
            )

    def drop_lessons(self) -> None:
        shutil.rmtree(os.path.dirname(self.memory))

    def drop_docs(self) -> None:
        shutil.rmtree(os.path.join(self.cwd, "docs"))
        os.remove(os.path.join(self.cwd, "README.md"))

    def drop_issue_cli(self) -> None:
        os.remove(os.path.join(self.bin, "gh"))

    def turn(self, *entries: dict, before: tuple[dict, ...] = ()) -> None:
        with open(self.transcript, "w", encoding="utf-8") as stream:
            for entry in (*before, user(PROMPT), *entries):
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def run_hook(
    fixture: Fixture, payload: dict, *, raw: str | None = None
) -> subprocess.CompletedProcess:
    body = raw if raw is not None else json.dumps(payload, ensure_ascii=False)
    env = {
        "PATH": fixture.bin,  # 実 host の gh を拾わせない: CLI 有無は stub だけで決まる
        "HOME": fixture.home,
        "LANG": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "QUESTION_RESEARCH_MEMORY_ROOT": fixture.memory,
    }
    return subprocess.run(
        [sys.executable, HOOK],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
    )


def ask(fixture: Fixture) -> dict:
    return {
        "session_id": SESSION,
        "transcript_path": fixture.transcript,
        "cwd": fixture.cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": QUESTION,
    }


def stop(fixture: Fixture, final_text: str, *, active: bool = False) -> dict:
    return {
        "session_id": SESSION,
        "transcript_path": fixture.transcript,
        "cwd": fixture.cwd,
        "hook_event_name": "Stop",
        "stop_hook_active": active,
        "last_assistant_message": final_text,
    }


def deny_reason(proc: subprocess.CompletedProcess) -> str:
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        section = data.get("hookSpecificOutput") or {}
        if section.get("permissionDecision") == "deny":
            return section.get("permissionDecisionReason") or ""
    return ""


LESSON_SEARCH = call(
    "Bash", command='~/.claude/hooks/memory_surface.py --search "質問 前 調査"'
)
ISSUE_SEARCH = call(
    "Bash", command='gh issue list --search "research before asking" --state all'
)
DOCS_SEARCH = call("Grep", pattern="質問", path="docs/")
ALL_SEARCHES = (LESSON_SEARCH, ISSUE_SEARCH, DOCS_SEARCH)


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def assertDenied(self, proc: subprocess.CompletedProcess, *missing: str) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        reason = deny_reason(proc)
        self.assertTrue(reason, proc.stdout)
        for name in missing:
            self.assertIn(name, reason)

    def assertAllowed(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(deny_reason(proc), "", proc.stdout)

    def assertBlocked(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("question-research-gate", proc.stderr)

    def assertPassed(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "", proc.stderr)

    # --- Q1 / Q2 / Q3: the AskUserQuestion door ---

    def test_q1_unresearched_question_is_denied(self):
        self.fx.turn(say("整理しました"))
        proc = run_hook(self.fx, ask(self.fx))
        self.assertDenied(proc, "教訓", "issue", "docs")

    def test_q2_fully_researched_question_is_allowed(self):
        self.fx.turn(*ALL_SEARCHES, say("整理しました"))
        self.assertAllowed(run_hook(self.fx, ask(self.fx)))

    def test_q3_partial_research_denies_and_names_only_what_is_missing(self):
        self.fx.turn(LESSON_SEARCH, DOCS_SEARCH, say("整理しました"))
        proc = run_hook(self.fx, ask(self.fx))
        self.assertDenied(proc, "issue")
        self.assertNotIn("教訓", deny_reason(proc))

    # --- Q4: availability decides what is required ---

    def test_q4_missing_channels_are_exempt(self):
        self.fx.drop_lessons()
        self.fx.turn(ISSUE_SEARCH, DOCS_SEARCH, say("整理しました"))
        self.assertAllowed(run_hook(self.fx, ask(self.fx)))

    def test_q4_non_github_remote_exempts_the_issue_tracker(self):
        self.fx.remote("https://example.com/acme/widgets.git")
        self.fx.turn(LESSON_SEARCH, DOCS_SEARCH, say("整理しました"))
        self.assertAllowed(run_hook(self.fx, ask(self.fx)))

    def test_q4_gitlab_remote_requires_a_gitlab_search(self):
        self.fx.remote("https://gitlab.com/acme/widgets.git")
        self.fx.stub("glab")
        self.fx.turn(LESSON_SEARCH, DOCS_SEARCH, say("整理しました"))
        self.assertDenied(run_hook(self.fx, ask(self.fx)), "issue")
        self.fx.turn(
            LESSON_SEARCH,
            DOCS_SEARCH,
            call("Bash", command="glab issue list"),
            say("整理しました"),
        )
        self.assertAllowed(run_hook(self.fx, ask(self.fx)))

    def test_q4_issue_cli_absent_exempts_the_issue_tracker(self):
        self.fx.drop_issue_cli()
        self.fx.turn(LESSON_SEARCH, DOCS_SEARCH, say("整理しました"))
        self.assertAllowed(run_hook(self.fx, ask(self.fx)))

    def test_q4_no_channel_available_never_fires(self):
        self.fx.drop_lessons()
        self.fx.drop_docs()
        self.fx.drop_issue_cli()
        self.fx.turn(say("整理しました"))
        self.assertAllowed(run_hook(self.fx, ask(self.fx)))
        self.assertPassed(run_hook(self.fx, stop(self.fx, "どの案を採用しますか?")))

    # --- Q5 / Q6 / Q7: the turn-final prose door ---

    def test_q5_unresearched_final_question_blocks(self):
        self.fx.turn(say("整理しました"))
        for text in (
            "🔷 [質問] この方針で進めてよいですか?",
            "どの案が良いでしょうか？",
            "再開しますか",
        ):
            with self.subTest(text=text):
                self.assertBlocked(run_hook(self.fx, stop(self.fx, text)))

    def test_q5_researched_final_question_passes(self):
        self.fx.turn(*ALL_SEARCHES, say("整理しました"))
        self.assertPassed(
            run_hook(self.fx, stop(self.fx, "🔷 [質問] この方針で進めてよいですか?"))
        )

    def test_q6_a_turn_without_a_question_passes(self):
        self.fx.turn(say("整理しました"))
        for text in (
            "🔷 [結論] 修正を commit しました。",
            "```\nどの案にしますか?\n```\n🔷 [結論] 済みです。",
        ):
            with self.subTest(text=text):
                self.assertPassed(run_hook(self.fx, stop(self.fx, text)))

    def test_q7_continuation_stop_does_not_block_again(self):
        self.fx.turn(say("整理しました"))
        self.assertPassed(
            run_hook(self.fx, stop(self.fx, "どの案にしますか?", active=True))
        )

    # --- Q8: fail-open ---

    def test_q8_broken_input_fails_open(self):
        self.fx.turn(say("整理しました"))
        self.assertPassed(run_hook(self.fx, {}, raw="not json"))
        self.assertAllowed(run_hook(self.fx, {}, raw="not json"))
        payload = ask(self.fx)
        payload["transcript_path"] = os.path.join(self.fx.tmp, "missing.jsonl")
        self.assertAllowed(run_hook(self.fx, payload))
        gone = stop(self.fx, "どの案にしますか?")
        gone["transcript_path"] = os.path.join(self.fx.tmp, "missing.jsonl")
        self.assertPassed(run_hook(self.fx, gone))

    def test_q8_other_tools_are_untouched(self):
        self.fx.turn(say("整理しました"))
        payload = ask(self.fx)
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {"command": "ls"}
        self.assertAllowed(run_hook(self.fx, payload))

    # --- Q9 / Q10: what counts as evidence ---

    def test_q9_evidence_from_any_tool_input_counts(self):
        self.fx.turn(
            call("Read", file_path=os.path.join(self.fx.memory, "org", "lesson.md")),
            call("Agent", prompt='gh issue list --search "prior art" で既出を調べて'),
            call("Glob", pattern="docs/**/*.md"),
            say("整理しました"),
        )
        self.assertAllowed(run_hook(self.fx, ask(self.fx)))

    def test_q10_evidence_from_an_earlier_turn_does_not_count(self):
        self.fx.turn(say("整理しました"), before=(user("先に調べて"), *ALL_SEARCHES))
        self.assertDenied(run_hook(self.fx, ask(self.fx)), "教訓", "issue", "docs")


if __name__ == "__main__":
    unittest.main()
