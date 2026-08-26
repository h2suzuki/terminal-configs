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

本 module は handoff 観測の単一 source を兼ねる: doc path 判定 (is_handoff_doc /
handoff_docs / mentions_handoff_doc / writes_handoff_doc) と完了 marker 判定
(has_handoff_marker) を stop_checks / session_resume_context / skill_reminder_gate が
import する。 言及の観測は mentions_、 書込の判定は writes_ と分ける。

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
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# Case-insensitive for `Handoff` / `Sign Off` etc.
# `本日はこれで` requires これで to avoid matching neutral `本日は…` (e.g. 本日は晴天なり).
# `handoff` は依頼形か単独発話のみ。 裸で拾うと doc 名や話題語での言及に発火する。
HANDOFF_RE = re.compile(
    r"(?:^|[\s。、「『(])handoff(?:\s*doc)?\s*(?:を)?\s*"
    r"(?:お願い|おねがい|よろしく|して|しといて|しよう|しましょう|します|する)"
    r"|^\s*handoff\s*[!！。.]*\s*$"
    r"|(?<!前回)(?<!前回の)(?<!前の)セッション(終了|リセット|を?閉じ)(?!時)"
    r"|お疲れさま(でし)?(た)?|終わります|またね"
    r"|sign\s?off|本日はこれで",
    re.IGNORECASE,
)

MAX_FILES_LISTED = 20
MAX_TASKS_LISTED = 10

NATIVE_TASKS_DIR = os.path.expanduser("~/.claude/tasks")
OPEN_STATUSES = ("pending", "in_progress", "blocked")

# Stop payload は prompt を含まないので、 wind-down 判定は prompt を受け取れる本 hook が下し、
# 結果だけを session 単位で残す (Stop 側が transcript を遡ると harness entry と読取幅に潰される)。
WIND_DOWN_STATE_DIR = os.path.expanduser("~/.claude/hooks/state/wind_down_signal")


def _signal_path(session_id: str) -> str:
    return os.path.join(WIND_DOWN_STATE_DIR, session_id)


def _sticky_path(session_id: str) -> str:
    return _signal_path(session_id) + ".sticky"


def record_wind_down(session_id: str, signalled: bool) -> None:
    """最新 prompt の wind-down 判定を session state へ上書き記録 (IO 失敗は無視 = fail-open)。"""
    if not session_id:
        return
    try:
        os.makedirs(WIND_DOWN_STATE_DIR, exist_ok=True)
        with open(_signal_path(session_id), "w", encoding="utf-8") as f:
            f.write("1" if signalled else "0")
        if signalled:  # 宣言は session 内で不可逆 (完了側の判定は marker が担う)
            open(_sticky_path(session_id), "w").close()
    except OSError:
        pass


def wind_down_signalled(session_id: str) -> bool:
    """直近 prompt が wind-down だったか。 未記録 / 読取不能は False (fail-open)。"""
    if not session_id:
        return False
    try:
        with open(_signal_path(session_id), encoding="utf-8") as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def wind_down_declared(session_id: str) -> bool:
    """session 内で一度でも wind-down 宣言があったか (sticky。 後続 prompt で消えない)。"""
    return bool(session_id) and os.path.exists(_sticky_path(session_id))


TAIL_SCAN_BYTES = 128 * 1024  # marker / doc token の後方走査幅 (数 turn を覆う)


def tail_text(path: str, nbytes: int = TAIL_SCAN_BYTES) -> str:
    """Last nbytes of the file, utf-8 decoded lossily; '' on error."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - nbytes))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


# --- handoff 実体観測 (doc path / 完了 marker) の単一 source。 consumer: stop_checks /
# session_resume_context / skill_reminder_gate。 代理指標 (open Task / wind-down 語) でなく実体を見る。

# handoff skill 規約の doc 置き場 (repo top と drafts/)。
HANDOFF_DOC_GLOBS = ("*handoff.md", os.path.join("drafts", "*handoff.md"))

# text / Bash command 中の doc path token 抽出 (経路不問の loose 観測)。
HANDOFF_DOC_TOKEN_RE = re.compile(r"[\w./-]*handoff\.md", re.IGNORECASE)

# handoff skill が session-end message 冒頭に出す marker (~~~~ … Handoff (<sid>) ~~~~)。
MARKER_RE = re.compile(r"~{4,}[^\n]*\bHandoff\b[^\n]*~{2,}", re.IGNORECASE)


def is_handoff_doc(path: str) -> bool:
    """basename が handoff doc 形 (handoff.md / *-handoff.md / *_handoff.md) か。"""
    low = os.path.basename(path).lower()
    return low == "handoff.md" or low.endswith(("-handoff.md", "_handoff.md"))


def handoff_docs(cwd: str) -> list[str]:
    """規約置き場に実在する handoff doc の path 一覧 (sorted)。 cwd 不正は []。"""
    if not cwd or not os.path.isdir(cwd):
        return []
    found: list[str] = []
    for pattern in HANDOFF_DOC_GLOBS:
        found.extend(
            p for p in glob.glob(os.path.join(cwd, pattern)) if is_handoff_doc(p)
        )
    return sorted(found)


def mentions_handoff_doc(text: str) -> bool:
    """text (Bash command / transcript 断片) が handoff doc path token を含むか。"""
    return any(
        is_handoff_doc(m.group()) for m in HANDOFF_DOC_TOKEN_RE.finditer(text or "")
    )


# 書込語だけを列挙する。 読取語は列挙しない — 未知の command は読取へ倒すのが誤 deny を生まない側。
WRITE_COMMANDS = frozenset(
    {
        "cp",
        "dd",
        "ed",
        "emacs",
        "install",
        "ln",
        "mv",
        "nano",
        "nvim",
        "patch",
        "rsync",
        "shred",
        "sponge",
        "tee",
        "touch",
        "truncate",
        "vi",
        "vim",
    }
)
# 中身を読めない実行系。 argv の先にある書込を見られないので書込側へ倒す。
OPAQUE_RUNNERS = frozenset(
    {"bash", "node", "perl", "python", "python3", "ruby", "sh", "zsh"}
)
SEGMENT_BREAKS = frozenset({";", "&&", "||", "|", "&", "(", ")", "{", "}"})
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def writes_handoff_doc(text: str) -> bool:
    """command が handoff doc へ書くか。 言及しただけの読取と区別する。
    出所 2026-08-24: mention 判定が `ls` / `cat` を deny していた。"""
    if not mentions_handoff_doc(text):
        return False
    if "<<" in text:  # heredoc の中身は読めない
        return True
    # punctuation_chars=True は `<` `>` を切り出す (codex_worktree_gate の roster は redirect 非対象)。
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:  # 引用が壊れた塊は読めない
        return True
    leading = ""
    previous = ""
    for token in tokens:
        if token in SEGMENT_BREAKS:
            leading, previous = "", token
            continue
        if not leading and not token.startswith("-") and not ASSIGNMENT_RE.match(token):
            leading = os.path.basename(token)
        if mentions_handoff_doc(token) and (
            previous.startswith(">")
            or leading in WRITE_COMMANDS
            or leading in OPAQUE_RUNNERS
            or (leading == "sed" and any(t.startswith("-i") for t in tokens))
        ):
            return True
        previous = token
    return False


def has_handoff_marker(text: str, sid: str) -> bool:
    """full sid 入り handoff marker の有無 (sid 無しの template / 省略引用は不採用)。"""
    return bool(sid) and any(sid in m.group() for m in MARKER_RE.finditer(text))


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
    """True only when known-masked path AND zero size AND stub shape (non-regular node, or read-only regular file)."""
    if rel not in MASK_STUB_PATHS:
        return False
    try:
        st = os.lstat(os.path.join(cwd, rel))
    except OSError:
        return False  # 消えた path は削除された tracked file — 正当な未コミット変更ゆえ残す
    if st.st_size != 0:
        return False
    if stat.S_ISREG(st.st_mode):
        # leak した stub は 0444 の regular file として実体化する (2026-08-17 実測)。
        return not st.st_mode & stat.S_IWUSR
    return not (stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode))


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
    session_id = str(payload.get("session_id") or "")
    signalled = bool(HANDOFF_RE.search(prompt))
    record_wind_down(session_id, signalled)  # 毎 prompt 上書き = 最新 turn の判定が残る
    if not signalled:
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
    tasks = open_tasks(session_id, cwd)
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

    def test_masked_readonly_empty_regular_dropped(self):
        # 出所: 2026-08-17 実機 — mask leak が 0-byte 0444 の regular file として実体化した。
        path = os.path.join(self.cwd, ".bashrc")
        open(path, "w").close()
        os.chmod(path, 0o444)
        self.assertEqual(self._status("?? .bashrc"), [])

    def test_masked_readonly_regular_with_content_kept(self):
        path = os.path.join(self.cwd, ".bashrc")
        with open(path, "w") as f:
            f.write("x")
        os.chmod(path, 0o444)
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


class HandoffObservablesTest(unittest.TestCase):
    """is_handoff_doc / has_handoff_marker: handoff 実体観測の単一 source (stop_checks / session_resume_context が import)。
    出所: 2026-06-08 実機 — template marker (placeholder sid) と省略引用が sid anchor 無しで誤検出。
    2026-08-20 実機 — skill 不発動のまま handoff doc が 3 回編集され素通り (doc path 観測が不在だった)。"""

    SID = "5262c4b2-7933-4f6b-893f-35405925375c"

    def test_canonical_doc_paths_detected(self):
        for path in (
            "last-session-handoff.md",
            "/repo/drafts/rebuild-handoff.md",
            "/repo/handoff.md",
            "/repo/my_handoff.md",
            "/repo/drafts/Feature-X-Handoff.md",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_handoff_doc(path))

    def test_non_doc_paths_ignored(self):
        for path in ("/repo/handoff-notes.md", "/repo/todos.md", "/repo/handoff.py"):
            with self.subTest(path=path):
                self.assertFalse(is_handoff_doc(path))

    def test_handoff_docs_lists_conventional_locations(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "drafts"))
            expected = [
                os.path.join(d, "drafts", "rebuild-handoff.md"),
                os.path.join(d, "last-session-handoff.md"),
            ]
            for p in expected + [
                os.path.join(d, "handoff-notes.md"),
                os.path.join(d, "drafts", "misc.md"),
            ]:
                open(p, "w").close()
            self.assertEqual(handoff_docs(d), sorted(expected))
        self.assertEqual(handoff_docs(""), [])
        self.assertEqual(handoff_docs("/nonexistent-dir"), [])

    def test_mentions_handoff_doc_in_command_text(self):
        cmd = "python3 - <<'EOF'\nopen('drafts/rebuild-handoff.md','w')\nEOF"
        self.assertTrue(mentions_handoff_doc(cmd))
        self.assertTrue(mentions_handoff_doc("cat last-session-handoff.md"))
        self.assertFalse(mentions_handoff_doc("grep handoff-notes.md; ls todos.md"))
        self.assertFalse(mentions_handoff_doc("echo check_uncommitted_at_handoff.py"))

    def test_sid_marker_detected(self):
        text = f"wind-down\n\n~~~~~~~~ Monday Handoff ({self.SID}) ~~~~~~\n## 本体"
        self.assertTrue(has_handoff_marker(text, self.SID))

    def test_template_marker_without_sid_ignored(self):
        self.assertFalse(
            has_handoff_marker("例: ~~~~ Monday Handoff (session ID) ~~~~", self.SID)
        )

    def test_abbreviated_body_quote_ignored(self):
        self.assertFalse(
            has_handoff_marker("(~~~~ … Handoff (5262c4b2…) ~~~~)", self.SID)
        )

    def test_no_marker_or_empty_sid(self):
        self.assertFalse(has_handoff_marker("ただの会話", self.SID))
        self.assertFalse(has_handoff_marker(f"~~~~ Handoff ({self.SID}) ~~~~", ""))


class HandoffWriteIntentTest(unittest.TestCase):
    """writes_handoff_doc: 読むだけの command を書込と取り違えない。
    出所: 2026-08-24 実機 — `ls -la last-session-handoff.md drafts/` が deny され、
    状況確認の一覧表示が止まった。mention だけでは読取と書込を分けられない。"""

    READS = (
        "ls -la last-session-handoff.md drafts/",
        "cat last-session-handoff.md",
        "grep -n Status drafts/rebuild-handoff.md",
        "head -20 handoff.md",
        "wc -l last-session-handoff.md",
        "diff a-handoff.md b-handoff.md",
        "sed -n '1,10p' last-session-handoff.md",
        "git log --oneline -- last-session-handoff.md",
        "echo a && cat drafts/rebuild-handoff.md",
    )

    WRITES = (
        "echo x > last-session-handoff.md",
        "echo x >> last-session-handoff.md",
        "echo x>last-session-handoff.md",
        "echo x | tee last-session-handoff.md",
        "cp draft.md last-session-handoff.md",
        "mv draft.md last-session-handoff.md",
        "install -m 644 a.md drafts/rebuild-handoff.md",
        "sed -i 's/a/b/' last-session-handoff.md",
        "vim last-session-handoff.md",
        "python3 -c \"open('handoff.md','w')\"",
        "python3 - <<'EOF'\nopen('drafts/rebuild-handoff.md','w')\nEOF",
    )

    def test_read_only_commands_are_not_writes(self):
        for command in self.READS:
            with self.subTest(command=command):
                self.assertFalse(writes_handoff_doc(command))

    def test_write_commands_are_writes(self):
        for command in self.WRITES:
            with self.subTest(command=command):
                self.assertTrue(writes_handoff_doc(command))

    def test_commands_without_a_doc_are_not_writes(self):
        self.assertFalse(writes_handoff_doc("ls drafts/"))
        self.assertFalse(writes_handoff_doc("echo x > handoff-notes.md"))
        self.assertFalse(writes_handoff_doc(""))

    def test_unparsable_command_counts_as_write(self):
        self.assertTrue(writes_handoff_doc("echo 'x last-session-handoff.md"))


class HandoffPhraseTest(unittest.TestCase):
    """HANDOFF_RE: 終了示唆だけを拾い、 同語の別用途は拾わない。
    出所: 2026-08-08 実機 — 「セッションを閉じます」が未収載で取りこぼした。 2026-08-27 実機 — 「前回セッション終了時に」を終了示唆と誤検出。"""

    def test_wind_down_phrases_match(self):
        for text in (
            "セッションを閉じます",
            "セッション閉じますね",
            "セッション終了です",
            "お疲れさまでした",
            "これで終わります",
            "handoff お願いします",
            "handoff をお願いします",
            "handoff して",
            "handoff",
        ):
            with self.subTest(text=text):
                self.assertTrue(HANDOFF_RE.search(text))

    def test_closing_something_else_does_not_match(self):
        for text in (
            "この項目を閉じます",
            "前回セッション終了時にエラーがでていた",
            "前回のセッション終了でエラーが出た",
            "セッション終了時に handoff を書く仕組み",
            "issue を閉じました",
            "次の実装をお願いします",
            # 2026-08-23 実機: doc 名と話題語での言及が終了示唆として拾われた。
            "last-session-handoff.md を削除してよいか",
            "handoff protocol / hook の強化が必要?",
            "handoff doc が stale だね",
            "handoff.md を消して",
        ):
            with self.subTest(text=text):
                self.assertIsNone(HANDOFF_RE.search(text))


class WindDownSignalTest(unittest.TestCase):
    """wind-down 判定を prompt 受領時に記録し Stop 側へ渡す (transcript を読ませない)。
    出所: 2026-08-08 実機 — Stop payload に prompt が無く、 transcript 走査は harness entry と
    読取幅に潰されて block が不発だった。"""

    SID = "sid-signal"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(
            sys.modules[__name__], "WIND_DOWN_STATE_DIR", tmp.name
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _submit(self, prompt: str) -> None:
        module = sys.modules[__name__]
        with (
            mock.patch.object(module, "_git_uncommitted", lambda cwd: []),
            mock.patch.object(module, "open_tasks", lambda sid, cwd: []),
            mock.patch.object(module, "_emit_context", lambda msg: None),
        ):
            _run({"prompt": prompt, "cwd": "/tmp", "session_id": self.SID})

    def test_unrecorded_session_is_not_signalled(self):
        self.assertFalse(wind_down_signalled(self.SID))
        self.assertFalse(wind_down_signalled(""))

    def test_wind_down_prompt_records_signal(self):
        self._submit("お疲れさまでした")
        self.assertTrue(wind_down_signalled(self.SID))

    def test_later_ordinary_prompt_clears_signal(self):
        self._submit("お疲れさまでした")
        self._submit("次の実装をお願いします")
        self.assertFalse(wind_down_signalled(self.SID))

    def test_declaration_is_sticky_across_prompts(self):
        self.assertFalse(wind_down_declared(self.SID))
        self._submit("セッションリセット後に取り組みます")
        self._submit("次の実装をお願いします")
        self.assertFalse(wind_down_signalled(self.SID))
        self.assertTrue(wind_down_declared(self.SID))
        self.assertFalse(wind_down_declared(""))

    def test_unwritable_state_dir_fails_open(self):
        with mock.patch.object(
            sys.modules[__name__], "WIND_DOWN_STATE_DIR", "/proc/nonexistent/x"
        ):
            record_wind_down(self.SID, True)
            self.assertFalse(wind_down_signalled(self.SID))


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
