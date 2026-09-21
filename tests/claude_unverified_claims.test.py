#!/usr/bin/env python3
"""Acceptance tests for `claude_unverified_claims`, written before the baseline run.

Contract (each claim maps to one test, IDs are the CLI docstring's D1-D6):
  D1  one `~/.claude/projects/*/*.jsonl` file = one session; its start is the
      first record's timestamp; a subagent transcript one dir deeper is not one
  D2  a turn ends at the next human prompt, so a later turn's tool_use does not
      absolve an earlier turn's claim
  D3  isMeta / isSidechain / tool_result / `<local-command-*>` /
      `<task-notification>` records do not start a turn; a `<command-name>`
      slash-command record does
  D4  an assistant text block after a tool_use in the same turn is verified;
      before one it is unverified; `thinking` counts as neither
  D5  fenced code and `[推測]` / `[推論]` sentences are not assertions
  D6  the table reports assertions / unverified / ratio per session plus a TOTAL
  Options: --since, --project, --json, --top; exit 1 on an unreadable dir
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files")
CLI = os.path.join(HERE, "claude_unverified_claims")
TS = "2026-09-01T10:00:00.000Z"


def user(text: str, **extra) -> dict:
    return {"type": "user", "timestamp": TS, "message": {"content": text}, **extra}


def tool_result(tool_id: str = "t1") -> dict:
    return {
        "type": "user",
        "timestamp": TS,
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}
            ]
        },
    }


def assistant(*blocks: dict) -> dict:
    return {"type": "assistant", "timestamp": TS, "message": {"content": list(blocks)}}


def text(body: str) -> dict:
    return {"type": "text", "text": body}


def tool_use() -> dict:
    return {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}


def thinking(body: str) -> dict:
    return {"type": "thinking", "thinking": body}


class ScannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects = os.path.join(self.tmp.name, "projects")

    def write(self, project: str, session: str, records: list[dict]) -> str:
        path = os.path.join(self.projects, project)
        os.makedirs(path, exist_ok=True)
        target = os.path.join(path, session + ".jsonl")
        with open(target, "w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return target

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, CLI, "--projects-dir", self.projects, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def counts(self, *args: str) -> list[dict]:
        out = self.run_cli("--json", *args)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def one(self, records: list[dict], *args: str) -> dict:
        self.write("proj", "s0000000-aaaa", records)
        rows = self.counts(*args)
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    # --- D4: the pre-investigation window ---

    def test_d4_claim_before_any_tool_is_unverified(self) -> None:
        row = self.one([user("直して"), assistant(text("該当なし"))])
        self.assertEqual((row["assertions"], row["unverified"]), (1, 1))

    def test_d4_claim_after_a_tool_is_verified(self) -> None:
        row = self.one(
            [
                user("直して"),
                assistant(tool_use()),
                tool_result(),
                assistant(text("該当なし")),
            ]
        )
        self.assertEqual((row["assertions"], row["unverified"]), (1, 0))

    def test_d4_tool_use_later_in_the_same_block_does_not_absolve(self) -> None:
        row = self.one([user("直して"), assistant(text("該当なし"), tool_use())])
        self.assertEqual((row["assertions"], row["unverified"]), (1, 1))

    def test_d4_thinking_is_neither_text_nor_investigation(self) -> None:
        row = self.one(
            [
                user("直して"),
                assistant(thinking("該当なし")),
                assistant(text("該当なし")),
            ]
        )
        self.assertEqual((row["assertions"], row["unverified"]), (1, 1))

    def test_d2_next_turn_resets_the_window(self) -> None:
        row = self.one(
            [
                user("一つ目"),
                assistant(tool_use()),
                tool_result(),
                assistant(text("問題ありません")),
                user("二つ目"),
                assistant(text("該当なし")),
            ]
        )
        self.assertEqual((row["assertions"], row["unverified"]), (2, 1))

    def test_d4_text_before_the_first_prompt_is_not_counted(self) -> None:
        row = self.one([assistant(text("該当なし")), user("直して")])
        self.assertEqual((row["assertions"], row["unverified"]), (0, 0))

    # --- D3: what does not start a turn ---

    def test_d3_meta_sidechain_and_plumbing_do_not_start_a_turn(self) -> None:
        for label, record in (
            ("meta", user("skill body", isMeta=True)),
            ("sidechain", user("subagent prompt", isSidechain=True)),
            ("stdout", user("<local-command-stdout>done</local-command-stdout>")),
            ("notification", user("<task-notification>\n<task-id>x</task-id>")),
            ("tool_result", tool_result()),
        ):
            with self.subTest(label=label):
                self.write(
                    label,
                    "s0000000-" + label,
                    [
                        user("直して"),
                        assistant(tool_use()),
                        record,
                        assistant(text("該当なし")),
                    ],
                )
                rows = self.counts("--project", label)
                self.assertEqual(len(rows), 1, rows)
                self.assertEqual((rows[0]["assertions"], rows[0]["unverified"]), (1, 0))

    def test_d3_slash_command_starts_a_turn(self) -> None:
        """A /goal-driven session has no other prompt record, so the echo must count."""
        row = self.one(
            [
                user(
                    "<command-name>/goal</command-name>\n<command-args>todos.md</command-args>"
                ),
                assistant(text("該当なし")),
            ]
        )
        self.assertEqual((row["assertions"], row["unverified"]), (1, 1))

    def test_d3_text_block_prompt_starts_a_turn(self) -> None:
        prompt = {
            "type": "user",
            "timestamp": TS,
            "message": {"content": [{"type": "text", "text": "調べて"}]},
        }
        row = self.one([prompt, assistant(text("できません"))])
        self.assertEqual((row["assertions"], row["unverified"]), (1, 1))

    # --- D5: sentence extraction ---

    def test_d5_fenced_code_and_hedges_are_dropped(self) -> None:
        body = (
            "```\n該当なし\n該当なし\n```\n"
            "[推測] 該当なし\n"
            "これは 該当なし です。次の文は 存在しない ものです。"
        )
        row = self.one([user("直して"), assistant(text(body))])
        self.assertEqual((row["assertions"], row["unverified"]), (2, 2))

    def test_d5_plain_prose_is_not_an_assertion(self) -> None:
        row = self.one(
            [user("直して"), assistant(text("todos.md を上から順に進めます。"))]
        )
        self.assertEqual((row["assertions"], row["unverified"]), (0, 0))

    # --- D1 / D6 / options ---

    def test_d1_subagent_transcript_is_not_a_session(self) -> None:
        self.write(
            "proj", "s0000000-aaaa", [user("直して"), assistant(text("該当なし"))]
        )
        nested = os.path.join(self.projects, "proj", "s0000000-aaaa", "subagents")
        os.makedirs(nested)
        with open(os.path.join(nested, "agent-1.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(user("直して")) + "\n")
            fh.write(json.dumps(assistant(text("該当なし"))) + "\n")
        rows = self.counts()
        self.assertEqual([r["session"] for r in rows], ["s0000000-aaaa"])

    def test_d6_table_reports_per_session_and_totals(self) -> None:
        self.write(
            "proj-a",
            "aaaaaaaa-1111",
            [user("直して"), assistant(text("該当なし。存在しない。"))],
        )
        self.write(
            "proj-b",
            "bbbbbbbb-2222",
            [
                {
                    "type": "user",
                    "timestamp": "2026-09-05T00:00:00Z",
                    "message": {"content": "後の session"},
                },
                assistant(tool_use()),
                assistant(text("問題ありません")),
            ],
        )
        out = self.run_cli()
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        self.assertEqual(lines[1].split()[:2], ["aaaaaaaa", "2026-09-01"])
        self.assertEqual(lines[1].split()[-3:], ["2", "2", "1.00"])
        self.assertEqual(lines[2].split()[-3:], ["1", "0", "0.00"])
        self.assertEqual(lines[3].split()[0], "TOTAL")
        self.assertEqual(lines[3].split()[-3:], ["3", "2", "0.67"])

    def test_option_since_filters_by_session_start(self) -> None:
        self.write("proj", "aaaaaaaa-1111", [user("古い"), assistant(text("該当なし"))])
        self.write(
            "proj",
            "bbbbbbbb-2222",
            [
                {
                    "type": "user",
                    "timestamp": "2026-09-05T00:00:00Z",
                    "message": {"content": "新しい"},
                },
                assistant(text("該当なし")),
            ],
        )
        rows = self.counts("--since", "2026-09-05")
        self.assertEqual([r["session"] for r in rows], ["bbbbbbbb-2222"])

    def test_option_project_filters_by_subdir(self) -> None:
        self.write("proj-a", "aaaaaaaa-1111", [user("a"), assistant(text("該当なし"))])
        self.write("proj-b", "bbbbbbbb-2222", [user("b"), assistant(text("該当なし"))])
        rows = self.counts("--project", "proj-b")
        self.assertEqual([r["project"] for r in rows], ["proj-b"])

    def test_option_top_keeps_the_worst_sessions_only(self) -> None:
        self.write(
            "proj",
            "aaaaaaaa-1111",
            [user("a"), assistant(text("該当なし。存在しない。"))],
        )
        self.write("proj", "bbbbbbbb-2222", [user("b"), assistant(text("該当なし"))])
        rows = self.counts("--top", "1")
        self.assertEqual([r["session"] for r in rows], ["aaaaaaaa-1111"])

    def test_option_json_carries_the_ratio(self) -> None:
        row = self.one([user("直して"), assistant(text("該当なし"))])
        self.assertEqual(row["ratio"], 1.0)
        self.assertEqual(row["project"], "proj")
        self.assertEqual(row["start"], TS)

    # --- error surfaces ---

    def test_unreadable_projects_dir_exits_1(self) -> None:
        out = self.run_cli()
        self.assertEqual(out.returncode, 1)
        self.assertIn("not a readable directory", out.stderr)

    def test_unparsable_record_is_reported_not_swallowed(self) -> None:
        path = self.write(
            "proj", "aaaaaaaa-1111", [user("直して"), assistant(text("該当なし"))]
        )
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        out = self.run_cli("--json")
        self.assertEqual(out.returncode, 0)
        self.assertIn("skipped unparsable record", out.stderr)
        self.assertEqual(json.loads(out.stdout)[0]["unverified"], 1)

    def test_empty_scan_says_so(self) -> None:
        os.makedirs(self.projects)
        out = self.run_cli()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "no sessions matched")

    def test_bad_since_is_rejected(self) -> None:
        os.makedirs(self.projects)
        out = self.run_cli("--since", "2026-13-99")
        self.assertEqual(out.returncode, 2)


if __name__ == "__main__":
    unittest.main()
