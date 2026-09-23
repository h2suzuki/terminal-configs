#!/usr/bin/env python3
"""Point real user prompts to the shared mytask skill; never block a turn.

Only model-facing UserPromptSubmit additionalContext is emitted. Empty prompts
and synthetic task notifications stay silent. Claude's native-task feature gate
does not disable the reminder: the skill also covers the mytask MCP fallback.

A second line is appended when the session's ledger has gone stale: the create
side is nudged every prompt, so without it memo-style Tasks pile up open until
wind-down. Any failure while reading the ledger drops that line only.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from unittest import mock

PURPOSE = "依頼を記録し、大きな作業を分解し、自分の計画を依頼に照らして見直すため、"
NUDGE = (
    "mytask: "
    + PURPOSE
    + "未読なら mytask Skill（~/.claude/skills/mytask/SKILL.md）を読み、その手順に従う。"
    "読込済みなら今回の依頼・追加・訂正を反映する。"
)
CODEX_NUDGE = (
    "mytask: "
    + PURPOSE
    + "未読なら /etc/codex/skills/mytask/SKILL.md を読み、その手順に従う。"
    "読込済みなら今回の依頼・追加・訂正を反映する。"
)
SYNTHETIC_PREFIX = "<task-notification>"

TIME_FORMAT = "%Y-%m-%d %H:%M"  # mytask CLI の created / updated と同じ書式
CLOSED_STATUSES = frozenset({"completed", "cancelled"})
STALE_STATUSES = frozenset({"pending", "in_progress"})
STALE_SECONDS = 30 * 60
STALE_LABEL = "30 分以上更新なし"
OPEN_TASK_CAP = 10  # 放置が無くてもこの件数を超えたら整理を促す
STALE_ID_CAP = 5
THROTTLE_SECONDS = 600
STAMP_TTL_SECONDS = 7 * 24 * 3600
CLOSE_ADVICE = "終わった項目は completed に、不要な項目は cancelled にする"


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
    """stop_checks.py と同じ 2 つの store を読む: native Task と mytask ledger。"""
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return []
    records: list[dict] = []
    native = os.path.join(os.environ.get("HOME", ""), ".claude", "tasks", session)
    try:
        names = sorted(os.listdir(native))
    except OSError:
        names = []
    for name in names:
        value = (
            _load_json(os.path.join(native, name)) if name.endswith(".json") else None
        )
        if isinstance(value, dict):
            records.append(value)
    roots: list[str] = []
    for root in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if isinstance(root, str) and root and root not in roots:
            roots.append(root)
    for root in roots:
        value = _load_json(os.path.join(root, "drafts", "tasks", session + ".json"))
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    return records


def _is_stale(task: dict, now: datetime) -> bool:
    for key in ("updated", "created"):
        value = task.get(key)
        if isinstance(value, str) and value:
            try:
                touched = datetime.strptime(value, TIME_FORMAT)
            except ValueError:
                return False
            return (now - touched).total_seconds() > STALE_SECONDS
    return False


def _close_message(payload: dict, now: datetime) -> str | None:
    opened = [
        task
        for task in _session_tasks(payload)
        if str(task.get("status", "")).lower() not in CLOSED_STATUSES
    ]
    if not opened:
        return None
    stale = [
        task
        for task in opened
        if str(task.get("status", "")).lower() in STALE_STATUSES
        and _is_stale(task, now)
    ]
    if not stale and len(opened) <= OPEN_TASK_CAP:
        return None
    detail = ""
    if stale:
        ids = ", ".join(f"#{task.get('id', '?')}" for task in stale[:STALE_ID_CAP])
        detail = f" (うち {STALE_LABEL} {len(stale)} 件: {ids})"
    return f"mytask: open Task {len(opened)} 件{detail}。{CLOSE_ADVICE}"


def _stamp_path(payload: dict) -> str | None:
    session = payload.get("session_id")
    home = os.environ.get("HOME")
    if not home or not isinstance(session, str) or not session:
        return None
    if "/" in session or session in {".", ".."}:
        return None
    return os.path.join(
        home, ".claude", "hooks", "state", "mytask_close_nudge", session
    )


def _throttled(path: str, now_ts: float) -> bool:
    try:
        with open(path, encoding="utf-8") as stream:
            last = float(stream.read().strip())
    except (OSError, ValueError):
        return False
    return now_ts - last < THROTTLE_SECONDS


def _record_emit(path: str, now_ts: float) -> None:
    directory = os.path.dirname(path)
    try:
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(str(now_ts))
    except OSError:
        return
    _prune_stamps(directory, now_ts)


def _prune_stamps(directory: str, now_ts: float) -> None:
    """SessionEnd を経ずに終わった session の stamp を落とす (無ければ何もしない)。"""
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        stale = os.path.join(directory, name)
        try:
            if now_ts - os.path.getmtime(stale) > STAMP_TTL_SECONDS:
                os.remove(stale)
        except OSError:
            pass


def _close_nudge(payload: dict) -> str | None:
    """Stale な open Task を畳むよう促す 1 行。 読めない / 節目でなければ None。"""
    try:
        path = _stamp_path(payload)
        if path is None:
            return None
        now_ts = time.time()
        if _throttled(path, now_ts):
            return None
        message = _close_message(payload, datetime.now())
        if message is None:
            return None
        _record_emit(path, now_ts)
        return message
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
        close = _close_nudge(payload)
        _emit_context(f"{message}\n{close}" if close else message)
    return 0


def main() -> int:
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

    def task(self, task_id: str, minutes_ago: int, status: str = "pending") -> dict:
        touched = datetime.fromtimestamp(time.time() - minutes_ago * 60)
        return {
            "id": task_id,
            "content": "覚え書きの Task",
            "status": status,
            "created": touched.strftime(TIME_FORMAT),
            "updated": touched.strftime(TIME_FORMAT),
        }

    def test_stale_open_task_is_nudged_with_ids(self):
        self.ledger(
            [
                self.task("1", 90, status="in_progress"),
                self.task("2-3", 45),
                self.task("3", 1),
            ]
        )
        message = _close_nudge(self.payload)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("open Task 3 件", message)
        self.assertIn(f"{STALE_LABEL} 2 件: #1, #2-3", message)
        self.assertIn(CLOSE_ADVICE, message)

    def test_fresh_and_few_open_tasks_stay_silent(self):
        self.ledger([self.task(str(index), 1) for index in range(1, 11)])
        self.assertIsNone(_close_nudge(self.payload))

    def test_more_than_ten_open_tasks_are_nudged_without_stale_detail(self):
        self.ledger([self.task(str(index), 1) for index in range(1, 12)])
        message = _close_nudge(self.payload)
        self.assertEqual(message, f"mytask: open Task 11 件。{CLOSE_ADVICE}")

    def test_second_call_within_the_window_stays_silent(self):
        self.ledger([self.task("1", 90)])
        self.assertIsNotNone(_close_nudge(self.payload))
        self.assertIsNone(_close_nudge(self.payload))

    def test_stamps_older_than_the_ttl_are_pruned(self):
        self.ledger([self.task("1", 90)])
        self.assertIsNotNone(_close_nudge(self.payload))
        stamp = _stamp_path(self.payload)
        assert stamp is not None
        orphan = os.path.join(os.path.dirname(stamp), "gone-session")
        open(orphan, "w").close()
        os.utime(orphan, (0, time.time() - STAMP_TTL_SECONDS - 60))
        os.remove(stamp)
        self.assertIsNotNone(_close_nudge(self.payload))
        self.assertFalse(os.path.exists(orphan))

    def test_missing_ledger_and_closed_tasks_stay_silent(self):
        self.assertIsNone(_close_nudge(self.payload))
        self.ledger([self.task("1", 90, status="completed")])
        self.assertIsNone(_close_nudge(self.payload))
        self.assertIsNone(_close_nudge({"prompt": "session_id なし"}))

    def test_nudge_rides_the_skill_reminder_as_a_second_line(self):
        self.ledger([self.task("1", 90)])
        with mock.patch.object(sys.modules[__name__], "_emit_context") as emit:
            _run({**self.payload, "prompt": "続きをお願いします"})
        emitted = emit.call_args[0][0]
        self.assertTrue(emitted.startswith(NUDGE + "\n"))
        self.assertIn("open Task 1 件", emitted)


if __name__ == "__main__":
    sys.exit(main())
