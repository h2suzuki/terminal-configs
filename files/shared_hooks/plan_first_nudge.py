#!/usr/bin/env python3
"""Point real user prompts to the shared mytask skill; never block a turn.

Only model-facing UserPromptSubmit additionalContext is emitted. Empty prompts
and synthetic task notifications stay silent.

The reminder pushes work into the ledger every prompt but nothing pushed it
back out, so finished items piled up open. When the session holds open Tasks
the reminder also prints them as a parent/child tree and asks for the closable
ones to be closed. Any failure while reading the ledger drops that part only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

PURPOSE = "依頼を記録し、大きな作業を分解し、自分の計画を依頼に照らして見直すため、"
NUDGE = (
    "mytask: "
    + PURPOSE
    + "未読なら mytask Skill（~/.claude/skills/mytask/SKILL.md）を Skill ツールか Read で単独に読み、"
    "作業 tool より先に依頼を登録する。"
    "読込済みなら今回の依頼・追加・訂正を反映する。"
)
CODEX_NUDGE = (
    "mytask: "
    + PURPOSE
    + "未読なら /etc/codex/skills/mytask/SKILL.md を読み、その手順に従う。"
    "読込済みなら今回の依頼・追加・訂正を反映する。"
)
SYNTHETIC_PREFIX = "<task-notification>"

CLOSE_NUDGE = "mytask: 終わった項目は completed に、不要な項目は cancelled に、理由があって実施しない項目は skipped にする"
CLOSED_STATUSES = frozenset({"completed", "cancelled", "skipped", "deleted"})
STATUS_EMOJI = {
    "pending": "◻️",
    "in_progress": "▶️",
    "delegated": "🤖",
    "blocked": "🚧",
}
DEFAULT_EMOJI = "◻️"
TASK_BODY_CHARS = 60
NUMERIC_ID = re.compile(r"[0-9]+(?:-[0-9]+)*")


def _emit_context(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_json(path: str) -> object:
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _session_tasks(payload: dict) -> list[dict]:
    """stop_checks.py と同じ mytask ledger を読む。"""
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return []
    records: list[dict] = []
    roots: list[str] = []
    for root in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if isinstance(root, str) and root and root not in roots:
            roots.append(root)
    for root in roots:
        value = _load_json(os.path.join(root, "drafts", "tasks", session + ".json"))
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    return records


def _open_tasks(tasks: list[dict]) -> list[dict]:
    return [
        task
        for task in tasks
        if str(task.get("status", "")).lower() not in CLOSED_STATUSES
    ]


def _ancestry(task: dict, by_id: dict[str, dict]) -> list[str]:
    """root から自身までの id。 数字 id は `-` 区切り、他は台帳の parent 欄をたどる。"""
    task_id = str(task.get("id", ""))
    if NUMERIC_ID.fullmatch(task_id):
        parts = task_id.split("-")
        return ["-".join(parts[: depth + 1]) for depth in range(len(parts))]
    chain = [task_id]
    parent = task.get("parent")
    while isinstance(parent, str) and parent in by_id and parent not in chain:
        chain.append(parent)
        parent = by_id[parent].get("parent")
    chain.reverse()
    return chain


def _tree_key(chain: list[str]) -> tuple:
    leaf = chain[-1] if chain else ""
    if NUMERIC_ID.fullmatch(leaf):
        return (0, tuple(int(part) for part in leaf.split("-")), ())
    return (1, (), tuple(chain))


def _task_body(task: dict) -> str:
    for key in ("content", "subject", "activeForm", "name"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            text = " ".join(value.split())
            return (
                text if len(text) <= TASK_BODY_CHARS else text[:TASK_BODY_CHARS] + "…"
            )
    return "(本文なし)"


def _task_tree(tasks: list[dict]) -> list[str]:
    """mytask の TaskList と同じ id / 状態 / 本文を、子は 2 字下げで親の下に並べる。"""
    by_id = {str(task.get("id", "")): task for task in tasks}
    rows = []
    for task in tasks:
        chain = _ancestry(task, by_id)
        rows.append((_tree_key(chain), len(chain) - 1, task))
    rows.sort(key=lambda row: row[0])
    lines = []
    for _key, depth, task in rows:
        status = str(task.get("status", "")).lower()
        emoji = STATUS_EMOJI.get(status, DEFAULT_EMOJI)
        body = _task_body(task)
        owner = task.get("owner")
        if status == "delegated" and isinstance(owner, str) and owner:
            body += f" [{owner}]"
        lines.append(f"{'  ' * depth}{task.get('id', '?')} {emoji} {body}")
    return lines


def _close_block(payload: dict) -> str | None:
    """open Task のツリーとクローズ依頼。 0 件 / 台帳が読めない場合は None。"""
    try:
        opened = _open_tasks(_session_tasks(payload))
        if not opened:
            return None
        return "\n".join(_task_tree(opened) + [CLOSE_NUDGE])
    except Exception:
        return None


def _run(payload: object, *, codex: bool = False) -> int:
    if not isinstance(payload, dict):
        return 0
    prompt = payload.get("prompt")
    if (
        isinstance(prompt, str)
        and prompt.strip()
        and not prompt.lstrip().startswith(SYNTHETIC_PREFIX)
    ):
        message = CODEX_NUDGE if codex else NUDGE
        close = _close_block(payload)
        _emit_context(f"{message}\n{close}" if close else message)
    return 0


def main() -> int:
    if os.environ.get("CLAUDE_HOOK_CHILD"):
        return 0  # a one-off session spawned by another hook runs no session hooks
    try:
        return _run(
            json.loads(sys.stdin.read() or "{}"), codex="--codex" in sys.argv[1:]
        )
    except Exception:
        return 0


class NudgeTest(unittest.TestCase):
    def test_client_specific_skill_reference(self):
        for codex, expected in ((False, NUDGE), (True, CODEX_NUDGE)):
            with (
                self.subTest(codex=codex),
                mock.patch.object(sys.modules[__name__], "_emit_context") as emit,
            ):
                self.assertEqual(_run({"prompt": "追加の依頼です"}, codex=codex), 0)
                emit.assert_called_once_with(expected)

    def test_empty_and_synthetic_prompts_are_silent(self):
        with mock.patch.object(sys.modules[__name__], "_emit_context") as emit:
            for codex in (False, True):
                for prompt in (None, "", "  ", SYNTHETIC_PREFIX + "done"):
                    _run({"prompt": prompt}, codex=codex)
                _run([], codex=codex)
            emit.assert_not_called()

    def test_only_model_context_is_emitted(self):
        for codex in (False, True):
            output = []
            with mock.patch.object(sys, "stdout", mock.Mock(write=output.append)):
                _run({"prompt": "作業を再開して"}, codex=codex)
            result = json.loads("".join(output))
            self.assertEqual(set(result), {"hookSpecificOutput"})
            self.assertEqual(
                result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
            )
            self.assertNotIn("ToolSearch", CODEX_NUDGE)


class CloseNudgeTest(unittest.TestCase):
    SESSION = "close-nudge-session"

    def setUp(self):
        self.temp_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            mock.patch.dict(
                os.environ,
                {"HOME": self.temp_dir, "CLAUDE_PROJECT_DIR": self.temp_dir},
                clear=False,
            )
        )
        self.payload = {"session_id": self.SESSION, "cwd": self.temp_dir}

    def ledger(self, tasks: list[dict]) -> None:
        directory = os.path.join(self.temp_dir, "drafts", "tasks")
        os.makedirs(directory, exist_ok=True)
        with open(
            os.path.join(directory, self.SESSION + ".json"), "w", encoding="utf-8"
        ) as stream:
            json.dump(tasks, stream, ensure_ascii=False)

    def task(self, task_id: str, status: str = "pending", **extra) -> dict:
        return {"id": task_id, "content": "覚え書き", "status": status, **extra}

    def test_open_tasks_add_the_tree_and_the_close_line(self):
        self.ledger([self.task("1", "in_progress"), self.task("2", "completed")])
        block = _close_block(self.payload)
        self.assertEqual(block, f"1 ▶️ 覚え書き\n{CLOSE_NUDGE}")

    def test_blocked_tasks_count_as_open(self):
        self.ledger([self.task("1", "blocked"), self.task("2", "cancelled")])
        block = _close_block(self.payload)
        self.assertEqual(block, f"1 🚧 覚え書き\n{CLOSE_NUDGE}")

    def test_delegated_tasks_show_their_owner(self):
        self.ledger(
            [
                self.task("1", "in_progress"),
                self.task("2", "delegated", owner="agent-a"),
                self.task("3", "delegated"),
            ]
        )
        block = _close_block(self.payload)
        self.assertEqual(
            block,
            f"1 ▶️ 覚え書き\n2 🤖 覚え書き [agent-a]\n3 🤖 覚え書き\n{CLOSE_NUDGE}",
        )

    def test_children_are_indented_under_their_parent(self):
        self.ledger(
            [
                self.task(task_id)
                for task_id in ("4-10", "4-1-10", "5", "4-1-2", "4-1", "4", "4-2")
            ]
        )
        block = _close_block(self.payload)
        assert block is not None
        self.assertEqual(
            block.splitlines()[:-1],
            [
                "4 ◻️ 覚え書き",
                "  4-1 ◻️ 覚え書き",
                "    4-1-2 ◻️ 覚え書き",
                "    4-1-10 ◻️ 覚え書き",
                "  4-2 ◻️ 覚え書き",
                "  4-10 ◻️ 覚え書き",
                "5 ◻️ 覚え書き",
            ],
        )

    def test_parent_field_builds_the_tree_for_non_numeric_ids(self):
        self.ledger(
            [
                self.task("child", parent="root"),
                self.task("root"),
                self.task("grandchild", parent="child"),
            ]
        )
        block = _close_block(self.payload)
        assert block is not None
        self.assertEqual(
            block.splitlines()[:-1],
            ["root ◻️ 覚え書き", "  child ◻️ 覚え書き", "    grandchild ◻️ 覚え書き"],
        )

    def test_long_bodies_are_cut_to_one_line(self):
        self.ledger([{"id": "1", "content": "詳細" * 80, "status": "pending"}])
        block = _close_block(self.payload)
        assert block is not None
        line = block.splitlines()[0]
        self.assertEqual(len(block.splitlines()), 2)
        self.assertEqual(line, "1 ◻️ " + "詳細" * (TASK_BODY_CHARS // 2) + "…")

    def test_closed_ledger_and_missing_session_add_nothing(self):
        self.assertIsNone(_close_block(self.payload))
        self.ledger(
            [
                self.task("1", "completed"),
                self.task("2", "cancelled"),
                self.task("3", "skipped"),
            ]
        )
        self.assertIsNone(_close_block(self.payload))
        self.assertIsNone(_close_block({"prompt": "session_id なし"}))

    def test_tree_rides_the_skill_reminder(self):
        self.ledger([self.task("1")])
        with mock.patch.object(sys.modules[__name__], "_emit_context") as emit:
            _run({**self.payload, "prompt": "続きをお願いします"})
        emitted = emit.call_args[0][0]
        self.assertEqual(emitted.splitlines(), [NUDGE, "1 ◻️ 覚え書き", CLOSE_NUDGE])


if __name__ == "__main__":
    sys.exit(main())
