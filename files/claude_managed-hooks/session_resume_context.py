#!/usr/bin/env python3
"""SessionStart hook: point at possibly-interrupted prior sessions instead of injecting their tail (startup / clear only; fail-open).

対象 = 直近 1 日以内に終了 ∧ handoff marker 無し ∧ open Task 残 の dead session。
正規の再開路 (resume / handoff doc) が無い中断だけを pointer で提示し、 読むか
どうかは最初の user prompt を見て agent が判断する (tail 本文は注入しない)。
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
WINDOW_SECONDS = 24 * 3600  # 「中断されたかもしれない」とみなす終了からの窓
TAIL_SCAN_BYTES = 128 * 1024  # marker 検出の後方走査幅 (wind-down 数 turn を覆う)
MAX_SESSIONS = 3
MAX_SUBJECTS = 3

# open-task reader は sibling UserPromptSubmit hook が単一 source
# (same deployed dir; absent/broken hook → 本 hook は沈黙 = fail-open)。
try:
    import check_uncommitted_at_handoff as _handoff_mod
except Exception:
    _handoff_mod = None  # ty: ignore[invalid-assignment] — fail-open sentinel, guarded by `is not None`


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


# /handoff skill が chat 出力冒頭に出す区切りマーカー (~~~~ … Handoff (<sid>) … ~~~~)。
# SKILL.md の例・body 抜粋・過去 handoff も同形ゆえ、 当該 session の full sid を含む marker のみ採用。
_MARKER_RE = re.compile(r"~{4,}[^\n]*\bHandoff\b[^\n]*~{2,}", re.IGNORECASE)


def _tail_text(path: str, nbytes: int = TAIL_SCAN_BYTES) -> str:
    """Last nbytes of the file, utf-8 decoded lossily; '' on error."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - nbytes))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _has_handoff_marker(text: str, sid: str) -> bool:
    """full sid 入り handoff marker の有無 (sid 無しの template / 省略引用は不採用)。"""
    return bool(sid) and any(sid in m.group() for m in _MARKER_RE.finditer(text))


def _open_tasks(session_id: str, cwd: str) -> list[str]:
    if _handoff_mod is None:
        return []
    return _handoff_mod.open_tasks(session_id, cwd)


def _interrupted_sessions(
    cwd: str, current_sid: str, now: float
) -> list[tuple[str, float, list[str]]]:
    """(jsonl path, age sec, open subjects) — 窓内・非 live・marker 無し・open Task 残のみ。"""
    project_dir = os.path.join(PROJECTS_DIR, _encoded_project_id(cwd))
    if not os.path.isdir(project_dir):
        return []
    files = glob.glob(os.path.join(project_dir, "*.jsonl"))
    files.sort(key=os.path.getmtime, reverse=True)
    live = _live_session_ids()
    out: list[tuple[str, float, list[str]]] = []
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
        if _has_handoff_marker(_tail_text(f), sid):
            continue
        subjects = _open_tasks(sid, cwd)
        if not subjects:
            continue
        out.append((f, age, subjects))
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
    for path, age, subjects in hits:
        shown = " / ".join(subjects[:MAX_SUBJECTS])
        more = (
            f" 他{len(subjects) - MAX_SUBJECTS}件"
            if len(subjects) > MAX_SUBJECTS
            else ""
        )
        lines.append(
            f"- `{path}` ({_age_label(age)}前に終了, open {len(subjects)} 件: {shown}{more})"
        )
    ctx = (
        "## 中断された可能性のある直前 session (pointer)\n\n"
        "直近 1 日以内に終了し、 handoff 無しで open Task が残っている session:\n\n"
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


class HandoffMarkerTest(unittest.TestCase):
    """_has_handoff_marker の sid-anchor 回帰 (handoff skill: marker は full session id を埋める)。
    出所: 2026-06-08 実機 — SKILL.md template marker (placeholder sid) と body 内省略引用が
    本物 marker と同形で混入し、 sid anchor 無しでは誤検出した。 Run: python3 -m unittest session_resume_context"""

    SID = "5262c4b2-7933-4f6b-893f-35405925375c"

    def test_sid_marker_detected(self):
        text = f"wind-down\n\n~~~~~~~~ Monday Handoff ({self.SID}) ~~~~~~\n## 本体"
        self.assertTrue(_has_handoff_marker(text, self.SID))

    def test_template_marker_without_sid_ignored(self):
        self.assertFalse(
            _has_handoff_marker("例: ~~~~ Monday Handoff (session ID) ~~~~", self.SID)
        )

    def test_abbreviated_body_quote_ignored(self):
        self.assertFalse(
            _has_handoff_marker("(~~~~ … Handoff (5262c4b2…) ~~~~)", self.SID)
        )

    def test_no_marker_or_empty_sid(self):
        self.assertFalse(_has_handoff_marker("ただの会話", self.SID))
        self.assertFalse(_has_handoff_marker(f"~~~~ Handoff ({self.SID}) ~~~~", ""))


class InterruptedSessionsTest(unittest.TestCase):
    """_interrupted_sessions: 窓内・非 live・marker 無し・open Task 残 の AND filter。"""

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
        self.assertEqual(self._hits(), [(p, 3600, ["#1 x"])])

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
