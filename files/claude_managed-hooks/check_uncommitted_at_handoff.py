#!/usr/bin/env python3
"""
UserPromptSubmit hook: on session wind-down phrase (handoff / お疲れさま /
終わります / sign off 等), inject additionalContext for two end-of-session
invariants: uncommitted changes (commit-discipline) and open Task items
(handoff skill Task 残処理 — carry-overs move to todos.md, the rest close).

Why UserPromptSubmit (not Stop): end-intent is detected from the user's own
message; Stop fires after every turn, so checking end-state there is noisy.
The blocking backstop is stop_checks.py (open-tasks-at-wind-down family),
which imports HANDOFF_RE / open_tasks from this module.

Stdin: UserPromptSubmit payload JSON (`prompt`, `cwd`, `session_id`, `transcript_path`).
Stdout: hookSpecificOutput additionalContext only when a wind-down phrase AND
(uncommitted changes OR open tasks) hold; else empty.

Exit:
  0: always. This hook only injects context, never blocks; exits 0 on any
     parse / IO error (fail-open).
"""

from __future__ import annotations

import glob
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# Case-insensitive for `Handoff` / `Sign Off` etc.
# `本日はこれで` requires これで to avoid matching neutral `本日は…` (e.g. 本日は晴天なり).
HANDOFF_RE = re.compile(
    r"handoff|セッション(終了|リセット)|お疲れさま(でし)?(た)?|終わります|またね|sign\s?off|本日はこれで",
    re.IGNORECASE,
)

MAX_FILES_LISTED = 20
MAX_TASKS_LISTED = 10

NATIVE_TASKS_DIR = os.path.expanduser("~/.claude/tasks")
OPEN_STATUSES = ("pending", "in_progress", "blocked")


# sandbox が書き込み禁止 path へ被せる stub の実測 roster。 未収載の stub は従来通り報告する
# (取りこぼしは偽陽性で済むが、 roster 無しの type 判定だけでは実 file を落としうる)。
MASK_STUB_PATHS = frozenset(
    {
        ".bash_profile",
        ".bashrc",
        ".claude/agents",
        ".claude/commands",
        ".claude/hooks",
        ".claude/launch.json",
        ".claude/loop.md",
        ".claude/output-styles",
        ".claude/routines",
        ".claude/scheduled_tasks.json",
        ".claude/settings.json",
        ".claude/skills",
        ".claude/workflows",
        ".gitconfig",
        ".gitmodules",
        ".idea",
        ".mcp.json",
        ".profile",
        ".ripgreprc",
        ".vscode",
        ".zprofile",
        ".zshrc",
    }
)


def _is_mask_stub(cwd: str, rel: str) -> bool:
    """True only when known-masked path AND non-regular node AND zero size all hold."""
    if rel not in MASK_STUB_PATHS:
        return False
    try:
        st = os.lstat(os.path.join(cwd, rel))
    except OSError:
        return False  # 消えた path は削除された tracked file — 正当な未コミット変更ゆえ残す
    is_node = not (
        stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)
    )
    return is_node and st.st_size == 0


def _git_uncommitted(cwd: str) -> list[str]:
    """Return uncommitted paths via `git status --porcelain`; empty list on any error (fail-open)."""
    if not cwd or not os.path.isdir(cwd):
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        # porcelain v1 is `XY<space>path...`, so col 3+ is the path;
        # strip is good-enough for the user-facing rename-arrow case.
        if len(line) < 4:
            continue
        path_part = line[3:].strip()
        if path_part and not _is_mask_stub(cwd, path_part):
            files.append(path_part)
    return files


def _native_open_tasks(session_id: str) -> list[str]:
    """Open items from the native Task store (~/.claude/tasks/<sid>/<N>.json)."""
    items: list[str] = []
    for path in sorted(glob.glob(os.path.join(NATIVE_TASKS_DIR, session_id, "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                task = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(task, dict) and task.get("status") in OPEN_STATUSES:
            items.append(f"#{task.get('id', '?')} {task.get('subject', '')}".strip())
    return items


def _mytask_open_tasks(session_id: str, cwd: str) -> list[str]:
    """Open items from the mytask MCP store (<cwd>/drafts/tasks/<sid>.json)."""
    path = os.path.join(cwd, "drafts", "tasks", f"{session_id}.json")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    return [
        f"#{task.get('id', '?')} {task.get('content', '')}".strip()
        for task in raw
        if isinstance(task, dict) and task.get("status") in OPEN_STATUSES
    ]


def open_tasks(session_id: str, cwd: str) -> list[str]:
    """All open work items for the session across both task stores; [] on any error (fail-open)."""
    if not session_id:
        return []
    try:
        return _native_open_tasks(session_id) + _mytask_open_tasks(session_id, cwd)
    except Exception:
        return []


def _listing(items: list[str], limit: int) -> str:
    head = "\n".join(f"  - {i}" for i in items[:limit])
    more = f"\n  ... 他 {len(items) - limit} 件" if len(items) > limit else ""
    return head + more


def _emit_context(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return 0
    if not HANDOFF_RE.search(prompt):
        return 0
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    sections: list[str] = []
    files = _git_uncommitted(cwd)
    if files:
        sections.append(
            f"未コミット変更が {len(files)} 件あります:\n{_listing(files, MAX_FILES_LISTED)}\n\n"
            "セッション終了示唆 (handoff / お疲れさま / 終わります 等) を検出。 "
            "commit-discipline skill 「session wind-down 時に未コミットを残さない」 "
            "規約に従い、 整理して commit を済ませてください。"
        )
    tasks = open_tasks(str(payload.get("session_id") or ""), cwd)
    if tasks:
        sections.append(
            f"open な Task が {len(tasks)} 件残っています:\n{_listing(tasks, MAX_TASKS_LISTED)}\n\n"
            "セッション終了示唆を検出。 handoff skill の Task 残処理に従い、 "
            "次 session へ持ち越す項目は todos.md の parent block へ転記 "
            "(詳細があれば handoff doc も更新) し、 全 open Task を close してください。"
        )
    if not sections:
        return 0
    _emit_context("\n\n".join(sections))
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        return _run(payload)
    except Exception:
        return 0


class OpenTasksTest(unittest.TestCase):
    """open_tasks: 両 store の open 抽出と fail-open。 Run: python3 -m unittest check_uncommitted_at_handoff"""

    SID = "sid-test"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cwd = tmp.name
        self.native = os.path.join(tmp.name, "native-tasks")
        patcher = mock.patch.object(
            sys.modules[__name__], "NATIVE_TASKS_DIR", self.native
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _native(self, tid: str, status: str, subject: str = "work") -> None:
        d = os.path.join(self.native, self.SID)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{tid}.json"), "w", encoding="utf-8") as f:
            json.dump({"id": tid, "subject": subject, "status": status}, f)

    def _mytask(self, items: list) -> None:
        d = os.path.join(self.cwd, "drafts", "tasks")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{self.SID}.json"), "w", encoding="utf-8") as f:
            json.dump(items, f)

    def test_native_filters_by_status(self):
        self._native("1", "pending", "a")
        self._native("2", "completed", "b")
        self._native("3", "in_progress", "c")
        self.assertEqual(open_tasks(self.SID, self.cwd), ["#1 a", "#3 c"])

    def test_mytask_filters_by_status(self):
        self._mytask(
            [
                {"id": "1", "content": "x", "status": "blocked"},
                {"id": "2", "content": "y", "status": "completed"},
            ]
        )
        self.assertEqual(open_tasks(self.SID, self.cwd), ["#1 x"])

    def test_both_stores_concatenate(self):
        self._native("1", "pending", "a")
        self._mytask([{"id": "1", "content": "x", "status": "pending"}])
        self.assertEqual(open_tasks(self.SID, self.cwd), ["#1 a", "#1 x"])

    def test_missing_stores_and_empty_sid(self):
        self.assertEqual(open_tasks(self.SID, self.cwd), [])
        self.assertEqual(open_tasks("", self.cwd), [])

    def test_malformed_store_files_ignored(self):
        d = os.path.join(self.native, self.SID)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "1.json"), "w", encoding="utf-8") as f:
            f.write("not json")
        self._mytask([{"id": "1", "status": "pending"}, "not a dict"])
        self.assertEqual(open_tasks(self.SID, self.cwd), ["#1"])


class GitUncommittedTest(unittest.TestCase):
    """_git_uncommitted: sandbox mask stub を落とし、 実 path と削除は残す。
    出所: 2026-08-07 実機 — sandbox 内で走らせると write-deny path の device stub が
    untracked 22 件として報告された (実在の untracked file は regular と判定)。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cwd = tmp.name

    def _status(self, *lines: str) -> list[str]:
        completed = subprocess.CompletedProcess(
            [], 0, stdout="\n".join(lines), stderr=""
        )
        with mock.patch.object(subprocess, "run", lambda *a, **k: completed):
            return _git_uncommitted(self.cwd)

    def _node(self, rel: str) -> None:
        # chardev の作成には root 権限が要るので FIFO で代替する
        os.makedirs(os.path.dirname(os.path.join(self.cwd, rel)), exist_ok=True)
        os.mkfifo(os.path.join(self.cwd, rel))

    def test_masked_path_with_empty_node_dropped(self):
        self._node(".bashrc")
        self._node(".claude/settings.json")
        self.assertEqual(self._status("?? .bashrc", "?? .claude/settings.json"), [])

    def test_unlisted_path_with_empty_node_kept(self):
        self._node("odd.pipe")
        self.assertEqual(self._status("?? odd.pipe"), ["odd.pipe"])

    def test_masked_path_with_regular_file_kept(self):
        open(os.path.join(self.cwd, ".bashrc"), "w").close()
        self.assertEqual(self._status("?? .bashrc"), [".bashrc"])

    def test_masked_node_with_size_kept(self):
        self._node(".bashrc")
        sized = os.stat_result((stat.S_IFCHR | 0o666, 4, 6, 1, 0, 0, 1, 0, 0, 0))
        with mock.patch.object(os, "lstat", lambda p: sized):
            self.assertEqual(self._status("?? .bashrc"), [".bashrc"])

    def test_regular_dir_and_symlink_kept(self):
        open(os.path.join(self.cwd, "a.py"), "w").close()
        os.mkdir(os.path.join(self.cwd, "sub"))
        os.symlink("a.py", os.path.join(self.cwd, "link"))
        self.assertEqual(
            self._status("?? a.py", "?? sub", "?? link"), ["a.py", "sub", "link"]
        )

    def test_deleted_path_kept(self):
        self.assertEqual(self._status(" D gone.py"), ["gone.py"])

    def test_git_failure_stays_fail_open(self):
        completed = subprocess.CompletedProcess([], 1, stdout="?? a.py", stderr="boom")
        with mock.patch.object(subprocess, "run", lambda *a, **k: completed):
            self.assertEqual(_git_uncommitted(self.cwd), [])


class RunTest(unittest.TestCase):
    """_run: wind-down 検出時のみ、 uncommitted / open Task の各節を injection。"""

    def _emit(self, prompt: str, files: list[str], tasks: list[str]) -> list[str]:
        sent: list[str] = []
        module = sys.modules[__name__]
        with (
            mock.patch.object(module, "_git_uncommitted", lambda cwd: files),
            mock.patch.object(module, "open_tasks", lambda sid, cwd: tasks),
            mock.patch.object(module, "_emit_context", sent.append),
        ):
            _run({"prompt": prompt, "cwd": "/tmp", "session_id": "s"})
        return sent

    def test_wind_down_with_tasks_only(self):
        out = self._emit("お疲れさまでした", [], ["#1 a"])
        self.assertEqual(len(out), 1)
        self.assertIn("open な Task が 1 件", out[0])
        self.assertNotIn("未コミット", out[0])

    def test_wind_down_with_both_sections(self):
        out = self._emit("これで handoff します", ["f.py"], ["#1 a"])
        self.assertEqual(len(out), 1)
        self.assertIn("未コミット変更が 1 件", out[0])
        self.assertIn("open な Task が 1 件", out[0])

    def test_wind_down_clean_state_silent(self):
        self.assertEqual(self._emit("お疲れさまでした", [], []), [])

    def test_no_wind_down_silent(self):
        self.assertEqual(self._emit("次の実装をお願いします", ["f.py"], ["#1 a"]), [])


if __name__ == "__main__":
    sys.exit(main())
