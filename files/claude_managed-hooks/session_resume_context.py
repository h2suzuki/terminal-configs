#!/usr/bin/env python3
"""SessionStart hook: point at possibly-interrupted prior sessions instead of injecting their tail (startup / clear only; fail-open).

対象 = 直近 1 日以内に終了 ∧ handoff marker 無し ∧ (open Task 残 ∨ handoff doc
言及) の dead session。 正規の再開路 (resume / handoff doc) が無い中断だけを
pointer で提示し、 読むかどうかは最初の user prompt を見て agent が判断する
(tail 本文は注入しない)。 marker / doc / open-task の観測は sibling hook
check_uncommitted_at_handoff が単一 source。
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
WINDOW_SECONDS = 24 * 3600  # 「中断されたかもしれない」とみなす終了からの窓
MAX_SESSIONS = 3
MAX_SUBJECTS = 3

# open-task / marker / doc reader は sibling UserPromptSubmit hook が単一 source
# (same deployed dir; absent/broken hook → 本 hook は沈黙 = fail-open)。
try:
    import check_uncommitted_at_handoff as _handoff_mod
except Exception:
    _handoff_mod = None  # fail-open sentinel, guarded by `is not None`


def _encoded_project_id(cwd: str) -> str:
    """Match Claude Code's projects/<encoded-cwd>/ form: '/' -> '-'."""
    return cwd.replace("/", "-")


AGENTS_TIMEOUT = 5  # `claude agents --json` の上限 (startup blocking ゆえ短く)


def _live_session_ids() -> set[str] | None:
    """`claude agents --json` が報告する live session の sid 集合。 取得失敗時 None。"""
    try:
        r = subprocess.run(
            ["claude", "agents", "--json"],
            capture_output=True,
            text=True,
            timeout=AGENTS_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    return {a["sessionId"] for a in data if isinstance(a, dict) and a.get("sessionId")}


def _open_tasks(session_id: str, cwd: str) -> list[str]:
    if _handoff_mod is None:
        return []
    return _handoff_mod.open_tasks(session_id, cwd)


def _interrupted_sessions(
    cwd: str, current_sid: str, now: float
) -> list[tuple[str, float, list[str], bool]]:
    """(jsonl path, age sec, open subjects, doc 言及) — 窓内・非 live・marker 無しの候補。"""
    if _handoff_mod is None:
        return []
    project_dir = os.path.join(PROJECTS_DIR, _encoded_project_id(cwd))
    if not os.path.isdir(project_dir):
        return []
    files = glob.glob(os.path.join(project_dir, "*.jsonl"))
    files.sort(key=os.path.getmtime, reverse=True)
    live = _live_session_ids()
    out: list[tuple[str, float, list[str], bool]] = []
    for f in files:
        sid = os.path.basename(f).rsplit(".", 1)[0]
        if sid == current_sid or (live is not None and sid in live):
            continue
        try:
            age = now - os.path.getmtime(f)
        except OSError:
            continue
        if age > WINDOW_SECONDS:
            break  # mtime 降順ゆえ以降は全て窓外
        tail = _handoff_mod.tail_text(f)
        if _handoff_mod.has_handoff_marker(tail, sid):
            continue
        subjects = _open_tasks(sid, cwd)
        doc_touch = _handoff_mod.mentions_handoff_doc(tail)
        if not subjects and not doc_touch:
            continue
        out.append((f, age, subjects, doc_touch))
        if len(out) >= MAX_SESSIONS:
            break
    return out


def _age_label(age: float) -> str:
    minutes = int(age // 60)
    return f"{minutes} 分" if minutes < 60 else f"{minutes // 60} 時間"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("source") not in ("startup", "clear"):
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return 0
    hits = _interrupted_sessions(cwd, payload.get("session_id") or "", time.time())
    if not hits:
        return 0
    lines: list[str] = []
    for path, age, subjects, _doc_touch in hits:
        if subjects:
            shown = " / ".join(subjects[:MAX_SUBJECTS])
            more = (
                f" 他{len(subjects) - MAX_SUBJECTS}件"
                if len(subjects) > MAX_SUBJECTS
                else ""
            )
            detail = f"open {len(subjects)} 件: {shown}{more}"
        else:
            detail = "handoff doc に言及・完了 marker 無し"
        lines.append(f"- `{path}` ({_age_label(age)}前に終了, {detail})")
    ctx = (
        "## 中断された可能性のある直前 session (pointer)\n\n"
        "直近 1 日以内に終了し、 handoff 完了 marker が無いまま open Task か "
        "handoff doc への言及が残っている session:\n\n"
        + "\n".join(lines)
        + "\n\nresume でも handoff 由来でもない再開 (例: 「接続が切れたので再開します」) "
        "の時だけ関係します。 最初の user prompt がそれを示す場合のみ該当 jsonl を "
        "Read で確認してください (それ以外は無視してよい)。"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }
    json.dump(out, sys.stdout)
    return 0


class InterruptedSessionsTest(unittest.TestCase):
    """_interrupted_sessions: 窓内・非 live・marker 無し・(open Task 残 ∨ doc 言及) の filter。
    marker / doc 判定の単体回帰は check_uncommitted_at_handoff の HandoffObservablesTest が持つ。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cwd = os.path.join(tmp.name, "proj")
        os.makedirs(self.cwd)
        self.project_dir = os.path.join(
            tmp.name, "projects", _encoded_project_id(self.cwd)
        )
        os.makedirs(self.project_dir)
        self.now = 1_000_000_000.0
        self.open_map: dict[str, list[str]] = {}
        module = sys.modules[__name__]
        for target, repl in (
            ("PROJECTS_DIR", os.path.join(tmp.name, "projects")),
            ("_live_session_ids", lambda: set()),
            ("_open_tasks", lambda sid, cwd: self.open_map.get(sid, [])),
        ):
            patcher = mock.patch.object(module, target, repl)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _session(
        self, sid: str, age: float, text: str = "log", tasks: list | None = None
    ):
        path = os.path.join(self.project_dir, f"{sid}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        os.utime(path, (self.now - age, self.now - age))
        if tasks is not None:
            self.open_map[sid] = tasks
        return path

    def _hits(self, current_sid: str = "cur"):
        return _interrupted_sessions(self.cwd, current_sid, self.now)

    def test_open_tasks_without_marker_listed(self):
        p = self._session("a", 3600, tasks=["#1 x"])
        self.assertEqual(self._hits(), [(p, 3600, ["#1 x"], False)])

    def test_doc_mention_without_tasks_listed(self):
        p = self._session("a", 3600, text='{"command": "cat drafts/x-handoff.md"}')
        self.assertEqual(self._hits(), [(p, 3600, [], True)])

    def test_handoff_marker_excluded(self):
        self._session("a", 3600, text="~~~~ Mon Handoff (a) ~~~~\n本体", tasks=["#1 x"])
        self.assertEqual(self._hits(), [])

    def test_no_open_tasks_excluded(self):
        self._session("a", 3600)
        self.assertEqual(self._hits(), [])

    def test_outside_window_excluded(self):
        self._session("a", WINDOW_SECONDS + 60, tasks=["#1 x"])
        self.assertEqual(self._hits(), [])

    def test_current_and_live_excluded(self):
        self._session("cur", 60, tasks=["#1 x"])
        self._session("lv", 60, tasks=["#1 x"])
        with mock.patch.object(
            sys.modules[__name__], "_live_session_ids", lambda: {"lv"}
        ):
            self.assertEqual(self._hits(), [])

    def test_capped_and_newest_first(self):
        for i in range(5):
            self._session(f"s{i}", 100 * (i + 1), tasks=[f"#{i}"])
        hits = self._hits()
        self.assertEqual(len(hits), MAX_SESSIONS)
        self.assertEqual([h[2] for h in hits], [["#0"], ["#1"], ["#2"]])

    def test_age_label(self):
        self.assertEqual(_age_label(59 * 60), "59 分")
        self.assertEqual(_age_label(2 * 3600 + 100), "2 時間")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
