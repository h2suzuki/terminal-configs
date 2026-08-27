#!/usr/bin/env python3
r"""Acceptance tests for the skill_reminder_gate.py rewrite (contract: skill_reminder_gate-contract-draft.md).

Written by the ordering side before the implementation. Black box: the hook is started as a subprocess
(`skill_reminder_gate.py <mode>`, payload JSON on stdin) and only stdout, stderr and the exit code are
read; the hook is never imported. Every fixture (HOME, state root, repo dir, transcript, PATH with a git
shim) lives in a temp dir, so no real transcript, no real state and no real memory clone is touched.

Contract (claims are verbatim from the draft; each maps to the tests named test_c<N>_*):

    name    skill_reminder_gate.py  (mode = gate | commit-gate | record-skill)
    in      argv[1] = mode、stdin = Claude Code hook payload の JSON 1 個
    out     allow = stdout 空。deny = stdout に JSON 1 行 (PreToolUse deny)。exit は常に 0
    state   <root>/active/<session_id>/main.json
            = {"<skill>": {"ts": <float>, "prompt_id": <any>}}
            <root> = $SKILL_REMINDER_STATE_DIR (設定済み かつ 非空のとき)
                   = $HOME/.claude/hooks/state/skill_reminder (既定、決裁 4)
            root は process 起動時の環境変数から読む。他の env は読まない
    own     この hook だけが上記 state を書く。file / git / transcript は一切書かない・読まない
            (例外: handoff doc 判定は sibling module check_uncommitted_at_handoff に委譲)
            読み手は codex_delegation_gate (既定 root だけを読む)
    inv1    gate が deny するのは、required が非空 かつ state が読めて かつ missing が非空 のときだけ
    inv2    active 窓は「prompt_id 一致」または「now - ts <= 1800」の論理和 (D1)
    inv3    agent_id が非空なら常に allow (D3 の subagent 免除)
    inv4    state が corrupt/unreadable なら allow (fail-open)、state が未生成なら deny (fail-safe)
    inv5    例外・payload 不正・mode 不一致は allow (exit 0, stdout 空, stderr 1 行まで)
    inv6    deny 文面は 1 行。`<prefix><label>: <skill 群> を invoke してから書き直せ` (D4)
    inv7    commit-gate は handoff 規則を先に評価し、deny ならそこで終わる。次に
            `git commit` の literal pathspec を評価する。git は一度も起動しない (決裁 1)
    inv8    state の更新は同 dir の一時 file へ書いて os.replace で置換する。lock は使わない。
            置換後の main.json は常に有効な JSON dict (決裁 6)
    inv9    session_id に `/` または `..` を含む payload は state path を持たない = 書かず、allow

- **C1 出力形と fail-open**
  入力: 空 stdin / 壊れた JSON / 非 dict payload / 想定外 `hook_event_name` / 内部例外を
  起こす payload。出力: exit 0、stdout 空、stderr は 1 行以内。deny 時のみ stdout に
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
  "permissionDecisionReason": "..."}}` を 1 行。
  test 方針: 各不正入力を stdin に流し、returncode 0 かつ stdout 空を assert。

- **C2 gate の対象 tool と path 解決**
  入力: `tool_name` が Write / Edit / MultiEdit / NotebookEdit の payload。path は
  `tool_input.file_path`、無ければ `tool_input.notebook_path`。相対なら payload `cwd` で
  絶対化し realpath。出力: それ以外の `tool_name` (Bash / Read / Grep など) と path 欠損は
  stdout 空。
  test 方針: 同一 file を Bash payload と Write payload で投げ、前者だけ無出力を assert。

- **C3 required skill の自動判定 (file 名ベース、決裁 5)**
  分類表は下記が全て。表に無い file (拡張子なしを含む) は空集合 = allow (D2)。
  拡張子は大小文字を無視する (`Foo.PY` = `.py`)。file の中身は読まない。
    todos  : basename が `todos.md` → `{writing-todos}` (排他)
    handoff: basename が `handoff.md` / `*-handoff.md` / `*_handoff.md` → `{handoff}` (排他)
    skill  : basename が `SKILL.md`、または path が `/files/claude_managed-hooks/` か
             `/etc/claude-code/hooks/` を含む → `+{writing-skills}`
    code   : 拡張子が `.py .sh .bash .zsh .rb .ts .js .mjs .rs .go .c .h .cpp .java .kt
             .swift .lua .pl` → `+{writing-code}`、`.py` は `+{writing-python}`、
             `.sh` / `.bash` / `.zsh` は `+{writing-bash}`
    memory : path が `/var/lib/claude-rag-memory/` を含む → なし = allow (D5)
  `~/.claude/hooks/` は skill kind の anchor ではない。
  test 方針: 代表 path 表を回し、必要な file だけ deny・他は無出力を assert。

- **C4 test file の上積み (決裁 5)**
  入力: **code kind の file** で、basename が `test_*.py` / `*_test.py` / `*.test.py` /
  `*.test.ts` / `*.spec.ts` / `*.spec.rb` のいずれか、または path が `/tests/` / `/test/` /
  `/spec/` を含むもの。basename の比較は拡張子と同じく大小文字を無視する (`Foo.Test.PY` も
  test file)。出力: 該当 kind の skill に `writing-tests` を加える。列挙は閉じており、
  `pkg/foo_test.go` は `{writing-code}` のみ。code kind でない file (`tests/notes.md` /
  `tests/todos.md`) には加えない。
  test 方針: `tests/foo.py` の deny 文面に writing-tests が含まれ、`tests/notes.md` は無出力。

- **C5 active 窓 (D1)**
  入力: state に `{"writing-code": {"ts": T, "prompt_id": P}}`、payload の prompt_id = Q。
  出力: `P == Q` なら T が何秒前でも active。`P != Q` (または Q 欠損) でも
  `now - T <= 1800` なら active。両方外れたら inactive → deny。
  test 方針: (同 prompt_id + ts 10000 秒前) と (別 prompt_id + ts 10 秒前) の 2 例で allow、
  (別 prompt_id + ts 3600 秒前) で deny を assert。

- **C6 state file の missing / corrupt 非対称**
  入力: state file が (a) 存在しない (b) 中身が壊れた JSON (c) JSON だが dict でない。
  出力: (a) → required が非空なら deny。(b)(c) → allow (stdout 空)。
  test 方針: 3 通りの state を作り分け、(a) だけ deny を assert。

- **C7 deny 文面 (D4、決裁 3)**
  入力: `/repo/x/foo.py` への Write、active 空、state 存在。出力: reason は改行を含まない
  1 行で、`skill-reminder-gate: /repo/x/foo.py: writing-code writing-python を invoke
  してから書き直せ` に逐語一致。skill 名は sorted・半角 space 1 個区切り、末尾に句点なし。
  label が複数 file になる commit pathspec deny だけ label 側を `, ` で連結する。
  test 方針: reason 文字列の完全一致と `"\n" not in reason` を assert。

- **C8 subagent 免除 (D3)**
  入力: `agent_id` が非空文字列の gate / commit-gate payload (state は未生成)。
  出力: stdout 空。`agent_id` が欠損・空文字なら通常判定。
  test 方針: 同一 payload に `agent_id` を足すと deny が消えることを assert。

- **C9 record-skill**
  入力: PostToolUse payload (`tool_input.skill` = "writing-code")。`tool_response` に
  `is_error` / `error` / `success: false` / `status ∈ {error, failed, failure}` の
  いずれも無ければ成功。出力: stdout 空。副作用として state に
  `{"writing-code": {"ts": <now>, "prompt_id": <payload の prompt_id>}}` を upsert
  (既存 key は保存、同 dir の一時 file へ書いて `os.replace` で置換、決裁 6)。失敗兆候あり・
  `skill` が非文字列/空・`session_id` 欠損・`agent_id` 非空 のときは書かない。stdout には
  成否によらず何も出さない (決裁 3)。
  test 方針: 成功 payload → gate が allow に変わる / 失敗 payload → deny のまま、を assert。
  並行 record-skill の後、state dir に残るのは `main.json` 1 本で、中身は有効な JSON dict。
  並行 upsert の後も各 process が書いた key は全て残る (書込後に再読して自分の key と読取時点の
  key 集合が残っているか検証し、崩れていれば再試行、上限 5 回。lock は使わない)。state が
  corrupt (非 JSON / 非 dict / 不正 record) のときは `{}` から作り直して upsert する
  (corrupt のまま session 終了まで gate を無効化しない)。

- **C10 commit-gate = handoff + literal pathspec (D6、決裁 1)**
  入力: `tool_name` = Bash、`tool_input.command` (文字列)。
  規則 1 (handoff、D6): `check_uncommitted_at_handoff.writes_handoff_doc(command)` が真
  (heredoc / redirect / 別 process を問わず) なら `{handoff}` を要求。label は `handoff doc`。
  規則 2 (commit pathspec、決裁 1): command を改行と `;` `&&` `||` `|` `&` `(` `)` で segment に
  分け (行継続 `\\` + 改行は 1 行に連結)、segment の先頭 token が `git` で、global option
  (`-C <dir>` / `-c <k=v>` / `--<name>[=<v>]`) を読み飛ばした次の token が `commit` なら
  `git commit` 呼出とみなす (兄弟 hook deny_compound_git_commit と同じ受理集合)。その呼出に
  `--` があり、その後ろの
  token が literal pathspec (引用符を剥いた後に `*` `?` `[` `]` `$` `` ` `` を含まない) なら、
  各 token を C3 の分類表に掛けて要求 skill を union する。label は該当 token を出現順・重複
  除去して `, ` 連結した文字列 (cwd で絶対化しない、realpath しない)。
  規則 1 を先に評価し deny ならそこで終了 (inv7)。missing が空・`--` が無い・pathspec が
  glob / 変数・handoff doc へ書かない command・module の import 失敗・`agent_id` 付きは
  stdout 空。git は一度も起動しない。
  test 方針: `cat > docs/x-handoff.md <<EOF` で deny、`cat docs/x-handoff.md` (読取のみ) と
  `git commit -am wip` / `git commit -m x -- src/*.py` で無出力、`git commit -m x -- a.py`
  で deny、`git` shim の呼出 log が空であることを assert。

- **C11 state root の上書き (決裁 4)**
  入力: 環境変数 `SKILL_REMINDER_STATE_DIR` を設定した record-skill / gate 実行。
  出力: 記録は `<override>/active/<session_id>/main.json` に落ち、既定 root
  (`$HOME/.claude/hooks/state/skill_reminder`) には何も作られない。上書き無しの gate は
  同じ payload で deny する。宣言 file dir (`~/.claude/plugins/data/skill_reminder_decl/`)
  は D2 で廃止したので、どの mode でも作られない。transcript も開かず command も起動しない
  ので、fixture が HOME (または override) を temp dir に向ければ state 面を全て観測できる。
  test 方針: override 付き record → override 下に state、既定 root は不在、override 付き
  gate は allow・無しは deny を assert。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "skill_reminder_gate.py"
)
SESSION = "sess-1"
PROMPT = "prompt-1"
WINDOW = 1800
PREFIX = "skill-reminder-gate: "

# 全 skill 語彙。deny 文面の言い回しに依存せず、要求された skill 集合だけを取り出すために使う。
VOCABULARY = frozenset(
    {
        "writing-code",
        "writing-python",
        "writing-bash",
        "writing-tests",
        "writing-skills",
        "writing-todos",
        "handoff",
        "memory-routing",
    }
)
# path 内の handoff doc 名を skill 名と誤認しないよう、token の両隣が path 文字でないことを要求する。
TOKEN_RE = re.compile(r"(?<![\w/.\-])[a-z]+(?:-[a-z]+)*(?![\w/.\-])")

GIT_SHIM = '#!/bin/sh\nprintf "%s\\n" "$*" >> "$GIT_CALL_LOG"\nexit 0\n'


class Fixture:
    """Temp HOME (state root), a repo-shaped cwd, an override state root and a git shim on PATH."""

    def __init__(self) -> None:
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="srg-"))
        self.home = os.path.join(self.tmp, "home")
        self.repo = os.path.join(self.tmp, "repo")
        self.override = os.path.join(self.tmp, "alt-state")
        self.hook_dir = os.path.join(self.repo, "files", "claude_managed-hooks")
        bin_dir = os.path.join(self.tmp, "bin")
        for path in (
            self.home,
            self.hook_dir,
            bin_dir,
            os.path.join(self.repo, "docs"),
        ):
            os.makedirs(path)
        shim = os.path.join(bin_dir, "git")
        with open(shim, "w", encoding="utf-8") as handle:
            handle.write(GIT_SHIM)
        os.chmod(shim, 0o755)
        self.path = bin_dir + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin")
        self.git_log = os.path.join(self.tmp, "git-calls.log")
        # 実在しない path: hook が transcript を読まないことの観測点 (C11)。
        self.transcript = os.path.join(self.tmp, "missing-transcript.jsonl")

    def state_dir(self, session: str = SESSION, *, override: bool = False) -> str:
        root = (
            self.override
            if override
            else os.path.join(self.home, ".claude", "hooks", "state", "skill_reminder")
        )
        return os.path.join(root, "active", session)

    def write_state(
        self, body: str, session: str = SESSION, *, override: bool = False
    ) -> str:
        directory = self.state_dir(session, override=override)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "main.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def git_calls(self) -> list[str]:
        if not os.path.exists(self.git_log):
            return []
        with open(self.git_log, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]

    def reset(self) -> None:
        shutil.rmtree(os.path.join(self.home, ".claude"), ignore_errors=True)
        shutil.rmtree(self.override, ignore_errors=True)
        if os.path.exists(self.git_log):
            os.remove(self.git_log)

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def run_hook(
    mode: str,
    payload: object,
    fx: Fixture,
    *,
    raw: str | None = None,
    env_extra: dict | None = None,
) -> subprocess.CompletedProcess:
    env = {"PATH": fx.path, "HOME": fx.home, "GIT_CALL_LOG": fx.git_log}
    if env_extra:
        env.update(env_extra)
    body = raw if raw is not None else json.dumps(payload, ensure_ascii=False)
    return subprocess.run(
        [sys.executable, HOOK, mode],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
    )


class GateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = Fixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def setUp(self) -> None:
        self.fx.reset()

    # -- fixtures ----------------------------------------------------------------------------
    def seed(
        self,
        skills,
        *,
        prompt: object = PROMPT,
        age: float = 0.0,
        session: str = SESSION,
        override: bool = False,
    ) -> None:
        now = time.time()
        state = {name: {"ts": now - age, "prompt_id": prompt} for name in skills}
        self.fx.write_state(json.dumps(state), session, override=override)

    # -- payload builders --------------------------------------------------------------------
    def write_payload(
        self,
        path: str,
        *,
        tool: str = "Write",
        key: str = "file_path",
        cwd: str | None = None,
        session: object = SESSION,
        prompt: object = PROMPT,
        agent: object = None,
        event: object = "PreToolUse",
    ) -> dict:
        payload: dict = {
            "tool_name": tool,
            "tool_input": {key: path},
            "cwd": self.fx.repo if cwd is None else cwd,
            "transcript_path": self.fx.transcript,
        }
        for field, value in (
            ("hook_event_name", event),
            ("session_id", session),
            ("prompt_id", prompt),
            ("agent_id", agent),
        ):
            if value is not None:
                payload[field] = value
        return payload

    def bash_payload(self, command: str, **kw) -> dict:
        payload = self.write_payload("", **kw)
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {"command": command}
        return payload

    def record_payload(
        self,
        skill: object = "writing-code",
        *,
        response: object = None,
        session: object = SESSION,
        prompt: object = PROMPT,
        agent: object = None,
    ) -> dict:
        payload: dict = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": skill},
            "cwd": self.fx.repo,
        }
        for field, value in (
            ("session_id", session),
            ("prompt_id", prompt),
            ("agent_id", agent),
            ("tool_response", response),
        ):
            if value is not None:
                payload[field] = value
        return payload

    # -- assertions --------------------------------------------------------------------------
    def invoke(self, mode: str, payload: object, **kw) -> subprocess.CompletedProcess:
        proc = run_hook(mode, payload, self.fx, **kw)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertLessEqual(len(proc.stderr.splitlines()), 1, proc.stderr)
        return proc

    def deny(self, payload: object, mode: str = "gate", **kw) -> str:
        proc = self.invoke(mode, payload, **kw)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"expected one deny line, got {proc.stdout!r}")
        out = json.loads(lines[0])["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "deny")
        reason = out["permissionDecisionReason"]
        self.assertNotIn("\n", reason)
        return reason

    def allow(self, payload: object, mode: str = "gate", **kw) -> None:
        proc = self.invoke(mode, payload, **kw)
        self.assertEqual(proc.stdout, "", f"expected no output, got {proc.stdout!r}")

    def demanded(self, payload: object, mode: str = "gate", **kw) -> set:
        """deny 文面から要求 skill 集合だけを取り出す (言い回しに依存しない観測)。"""
        found = TOKEN_RE.findall(self.deny(payload, mode, **kw))
        return {token for token in found if token in VOCABULARY}

    # -- C1: output shape and fail-open ------------------------------------------------------
    def test_c1_malformed_stdin_is_allowed(self) -> None:
        for mode in ("gate", "commit-gate", "record-skill"):
            for raw in (
                "",
                "   ",
                "{",
                "[]",
                "null",
                "3",
                '{"tool_name": "Write"',
                "not json",
            ):
                with self.subTest(mode=mode, raw=raw):
                    self.allow(None, mode, raw=raw)

    def test_c1_unknown_mode_is_allowed(self) -> None:
        self.seed([])
        payload = self.write_payload(os.path.join(self.fx.repo, "foo.py"))
        for mode in ("", "bogus", "declare"):
            with self.subTest(mode=mode):
                self.allow(payload, mode)

    def test_c1_mode_payload_mismatch_is_allowed(self) -> None:
        self.seed([])
        self.allow(self.record_payload(), "gate")
        self.allow(
            self.write_payload(os.path.join(self.fx.repo, "foo.py")), "record-skill"
        )
        self.deny(self.write_payload(os.path.join(self.fx.repo, "foo.py")))

    def test_c1_exception_shaped_payloads_are_allowed(self) -> None:
        broken = [
            {"tool_name": "Write", "tool_input": ["file_path"], "session_id": SESSION},
            {
                "tool_name": "Write",
                "tool_input": {"file_path": 7},
                "session_id": SESSION,
            },
            {
                "tool_name": "Write",
                "tool_input": {"file_path": {"a": 1}},
                "session_id": SESSION,
            },
            {"tool_name": "Write", "tool_input": {"file_path": "foo.py"}, "cwd": 3},
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/repo/foo.py"},
                "session_id": ["not", "a", "string"],
            },
            {"tool_name": 5, "tool_input": {"file_path": "/repo/foo.py"}},
        ]
        for payload in broken:
            with self.subTest(payload=payload):
                self.allow(payload)
                self.allow(payload, "commit-gate")
                self.allow(payload, "record-skill")

    def test_c1_unreadable_state_is_allowed(self) -> None:
        os.makedirs(os.path.join(self.fx.state_dir(), "main.json"), exist_ok=True)
        self.allow(self.write_payload(os.path.join(self.fx.repo, "foo.py")))

    def test_c1_deny_is_one_json_line(self) -> None:
        self.seed([])
        proc = self.invoke(
            "gate", self.write_payload(os.path.join(self.fx.repo, "foo.py"))
        )
        self.assertTrue(proc.stdout.endswith("\n"), repr(proc.stdout))
        self.assertEqual(len(proc.stdout.splitlines()), 1, repr(proc.stdout))
        data = json.loads(proc.stdout)
        self.assertEqual(set(data), {"hookSpecificOutput"})
        self.assertEqual(
            set(data["hookSpecificOutput"]),
            {"hookEventName", "permissionDecision", "permissionDecisionReason"},
        )

    def test_c1_hook_event_name_is_not_required(self) -> None:
        self.seed([])
        self.deny(self.write_payload(os.path.join(self.fx.repo, "foo.py"), event=None))
        self.allow(
            self.write_payload(os.path.join(self.fx.repo, "notes.md"), event=None)
        )

    # -- C2: gated tools and path resolution -------------------------------------------------
    def test_c2_write_family_is_gated(self) -> None:
        self.seed([])
        for tool in ("Write", "Edit", "MultiEdit"):
            with self.subTest(tool=tool):
                path = os.path.join(self.fx.repo, "foo.py")
                self.assertEqual(
                    self.demanded(self.write_payload(path, tool=tool)),
                    {"writing-code", "writing-python"},
                )

    def test_c2_notebook_path_is_the_fallback_key(self) -> None:
        """NotebookEdit carries notebook_path; a code path proves the fallback is read."""
        self.seed([])
        path = os.path.join(self.fx.repo, "nb", "foo.py")
        self.assertEqual(
            self.demanded(
                self.write_payload(path, tool="NotebookEdit", key="notebook_path")
            ),
            {"writing-code", "writing-python"},
        )

    def test_c2_other_tools_are_ignored(self) -> None:
        self.seed([])
        path = os.path.join(self.fx.repo, "foo.py")
        for tool in ("Read", "Grep", "Glob", "Task", "Skill", "WebFetch"):
            with self.subTest(tool=tool):
                self.allow(self.write_payload(path, tool=tool))
        self.allow(self.bash_payload(f"python3 {path}"))

    def test_c2_relative_path_resolves_against_payload_cwd(self) -> None:
        self.seed([])
        reason = self.deny(self.write_payload("sub/foo.py"))
        self.assertIn(os.path.join(self.fx.repo, "sub", "foo.py"), reason)

    def test_c2_missing_path_is_allowed(self) -> None:
        self.seed([])
        payload = self.write_payload(os.path.join(self.fx.repo, "foo.py"))
        payload["tool_input"] = {}
        self.allow(payload)
        self.allow(self.write_payload(""))

    # -- C3: required skills from the file name ----------------------------------------------
    def rel(self, *parts: str) -> str:
        return os.path.join(self.fx.repo, *parts)

    def test_c3_todos_and_handoff_docs(self) -> None:
        self.seed([])
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("todos.md"))), {"writing-todos"}
        )
        for name in ("handoff.md", "rebuild-handoff.md", "old_handoff.md"):
            with self.subTest(name=name):
                self.assertEqual(
                    self.demanded(self.write_payload(self.rel("drafts", name))),
                    {"handoff"},
                )
        self.allow(self.write_payload(self.rel("handoff-notes.md")))

    def test_c3_skill_md_and_hook_scripts_require_writing_skills(self) -> None:
        self.seed([])
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("skills", "x", "SKILL.md"))),
            {"writing-skills"},
        )
        self.assertEqual(
            self.demanded(self.write_payload(os.path.join(self.fx.hook_dir, "g.py"))),
            {"writing-skills", "writing-code", "writing-python"},
        )
        self.assertEqual(
            self.demanded(self.write_payload(os.path.join(self.fx.hook_dir, "g.sh"))),
            {"writing-skills", "writing-code", "writing-bash"},
        )
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("g.py"))),
            {"writing-code", "writing-python"},
        )

    def test_c3_hook_dir_anchors_are_the_two_named_ones(self) -> None:
        """C3: the skill kind is anchored on /files/claude_managed-hooks/ and /etc/claude-code/hooks/."""
        self.seed([])
        self.assertEqual(
            self.demanded(self.write_payload("/etc/claude-code/hooks/g.py")),
            {"writing-skills", "writing-code", "writing-python"},
        )
        # 拡張子を問わず anchor 配下は skill kind。
        self.assertEqual(
            self.demanded(
                self.write_payload(os.path.join(self.fx.hook_dir, "notes.txt"))
            ),
            {"writing-skills"},
        )
        # deploy 先の user hook dir は anchor ではない (§6 の受入済み残課題)。
        self.assertEqual(
            self.demanded(self.write_payload(self.rel(".claude", "hooks", "g.py"))),
            {"writing-code", "writing-python"},
        )

    def test_c3_code_extensions_require_writing_code(self) -> None:
        self.seed([])
        cases = {
            "foo.py": {"writing-code", "writing-python"},
            "foo.sh": {"writing-code", "writing-bash"},
            "foo.bash": {"writing-code", "writing-bash"},
            "foo.zsh": {"writing-code", "writing-bash"},
            "foo.go": {"writing-code"},
            "foo.ts": {"writing-code"},
            "foo.js": {"writing-code"},
            "foo.mjs": {"writing-code"},
            "foo.rs": {"writing-code"},
            "foo.rb": {"writing-code"},
            "foo.c": {"writing-code"},
            "foo.h": {"writing-code"},
            "foo.cpp": {"writing-code"},
            "foo.java": {"writing-code"},
            "foo.kt": {"writing-code"},
            "foo.swift": {"writing-code"},
            "foo.lua": {"writing-code"},
            "foo.pl": {"writing-code"},
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(
                    self.demanded(self.write_payload(self.rel(name))), expected
                )

    def test_c3_skill_less_files_are_allowed(self) -> None:
        self.seed([])
        for name in (
            "README.md",
            "data.json",
            "notes.txt",
            "Makefile",
            "runner",
            "x.yaml",
            "foo.tsx",  # 拡張子表は閉じている: 表に無い code 風拡張子も allow
        ):
            with self.subTest(name=name):
                self.allow(self.write_payload(self.rel(name)))

    def test_c3_memory_entries_are_allowed(self) -> None:
        """D5: memory entry の routing は memory_routing_gate の管轄で、本 hook は素通しする。"""
        self.seed([])
        for path in (
            "/var/lib/claude-rag-memory/org/2026-08-27-x.md",
            "/var/lib/claude-rag-memory/user/notes.md",
            os.path.join(self.fx.home, ".claude", "memory", "entry.md"),
        ):
            with self.subTest(path=path):
                self.allow(self.write_payload(path))

    def test_c3_extension_case_is_normalized(self) -> None:
        self.seed([])
        self.assertEqual(
            self.demanded(self.write_payload("/repo/x/Foo.PY")),
            {"writing-code", "writing-python"},
        )
        self.assertEqual(
            self.demanded(self.write_payload("/repo/x/Run.SH")),
            {"writing-code", "writing-bash"},
        )

    # -- C4: writing-tests on top of the kind ------------------------------------------------
    def test_c4_test_files_add_writing_tests(self) -> None:
        self.seed([])
        cases = {
            ("tests", "foo.py"): {"writing-code", "writing-python", "writing-tests"},
            ("test", "foo.go"): {"writing-code", "writing-tests"},
            ("spec", "foo.rb"): {"writing-code", "writing-tests"},
            ("test_foo.py",): {"writing-code", "writing-python", "writing-tests"},
            ("foo_test.py",): {"writing-code", "writing-python", "writing-tests"},
            ("foo.test.py",): {"writing-code", "writing-python", "writing-tests"},
            ("foo.test.ts",): {"writing-code", "writing-tests"},
            ("foo.spec.ts",): {"writing-code", "writing-tests"},
            ("foo.spec.rb",): {"writing-code", "writing-tests"},
        }
        for parts, expected in cases.items():
            with self.subTest(parts=parts):
                self.assertEqual(
                    self.demanded(self.write_payload(self.rel(*parts))), expected
                )

    def test_c4_the_test_name_list_is_closed(self) -> None:
        """C4: 決裁 5 の basename 表に無い `*_test.go` は dir 条件にも当たらず code kind のまま。"""
        self.seed([])
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("pkg", "foo_test.go"))),
            {"writing-code"},
        )

    def test_c4_non_code_files_never_add_writing_tests(self) -> None:
        self.seed([])
        self.allow(self.write_payload(self.rel("tests", "notes.md")))
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("tests", "todos.md"))),
            {"writing-todos"},
        )

    # -- C5: the active window ---------------------------------------------------------------
    PY_SKILLS = ("writing-code", "writing-python")

    def test_c5_same_prompt_id_is_active_at_any_age(self) -> None:
        self.seed(self.PY_SKILLS, prompt=PROMPT, age=10000)
        self.allow(self.write_payload(self.rel("foo.py")))

    def test_c5_fresh_record_from_another_prompt_is_active(self) -> None:
        self.seed(self.PY_SKILLS, prompt="prompt-0", age=10)
        self.allow(self.write_payload(self.rel("foo.py")))

    def test_c5_stale_record_from_another_prompt_denies(self) -> None:
        self.seed(self.PY_SKILLS, prompt="prompt-0", age=3600)
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("foo.py"))), set(self.PY_SKILLS)
        )

    def test_c5_window_boundary_is_1800_seconds(self) -> None:
        self.seed(self.PY_SKILLS, prompt="prompt-0", age=WINDOW - 2)
        self.allow(self.write_payload(self.rel("foo.py")))
        self.seed(self.PY_SKILLS, prompt="prompt-0", age=WINDOW + 2)
        self.deny(self.write_payload(self.rel("foo.py")))

    def test_c5_payload_without_prompt_id_uses_the_window(self) -> None:
        self.seed(self.PY_SKILLS, age=10)
        self.allow(self.write_payload(self.rel("foo.py"), prompt=None))
        self.seed(self.PY_SKILLS, age=3600)
        self.deny(self.write_payload(self.rel("foo.py"), prompt=None))

    def test_c5_only_missing_skills_are_demanded(self) -> None:
        self.seed(["writing-code"])
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("foo.py"))), {"writing-python"}
        )

    # -- C6: missing vs corrupt state --------------------------------------------------------
    def test_c6_missing_state_denies(self) -> None:
        self.deny(self.write_payload(self.rel("foo.py")))
        os.makedirs(self.fx.state_dir(), exist_ok=True)
        self.deny(self.write_payload(self.rel("foo.py")))

    def test_c6_corrupt_state_allows(self) -> None:
        for body in ("{", "", "not json", '{"writing-code": '):
            with self.subTest(body=body):
                self.fx.write_state(body)
                self.allow(self.write_payload(self.rel("foo.py")))

    def test_c6_non_dict_state_allows(self) -> None:
        for body in ("[]", "null", '"writing-code"', "5"):
            with self.subTest(body=body):
                self.fx.write_state(body)
                self.allow(self.write_payload(self.rel("foo.py")))

    # -- C7: the deny wording ----------------------------------------------------------------
    def test_c7_deny_reason_is_verbatim(self) -> None:
        self.seed([])
        self.assertEqual(
            self.deny(self.write_payload("/repo/x/foo.py")),
            PREFIX
            + "/repo/x/foo.py: writing-code writing-python を invoke してから書き直せ",
        )

    def test_c7_missing_skills_are_sorted_and_space_joined(self) -> None:
        self.seed([])
        reason = self.deny(self.write_payload(os.path.join(self.fx.hook_dir, "g.py")))
        self.assertTrue(reason.startswith(PREFIX), reason)
        self.assertTrue(
            reason.endswith(
                ": writing-code writing-python writing-skills を invoke してから書き直せ"
            ),
            reason,
        )

    def test_c7_commit_gate_label_is_handoff_doc(self) -> None:
        self.seed([])
        reason = self.deny(
            self.bash_payload("cat > docs/x-handoff.md <<'EOF'\nx\nEOF\n"),
            "commit-gate",
        )
        self.assertEqual(
            reason, PREFIX + "handoff doc: handoff を invoke してから書き直せ"
        )

    # -- C8: subagent exemption --------------------------------------------------------------
    def test_c8_agent_id_bypasses_the_gate(self) -> None:
        path = self.rel("foo.py")
        self.deny(self.write_payload(path))
        self.allow(self.write_payload(path, agent="agent-1"))

    def test_c8_empty_agent_id_is_still_gated(self) -> None:
        self.seed([])
        self.deny(self.write_payload(self.rel("foo.py"), agent=""))

    def test_c8_agent_id_bypasses_the_commit_gate(self) -> None:
        command = "cat > docs/x-handoff.md <<'EOF'\nx\nEOF\n"
        self.seed([])
        self.deny(self.bash_payload(command), "commit-gate")
        self.allow(self.bash_payload(command, agent="agent-1"), "commit-gate")

    # -- C9: record-skill --------------------------------------------------------------------
    def test_c9_recorded_skills_unlock_the_gate(self) -> None:
        self.allow(
            self.record_payload("writing-code", response={"result": "ok"}),
            "record-skill",
        )
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("foo.py"))), {"writing-python"}
        )
        self.allow(self.record_payload("writing-python"), "record-skill")
        self.allow(self.write_payload(self.rel("foo.py")))

    def test_c9_failure_signals_are_not_recorded(self) -> None:
        self.seed([])
        failures = (
            {"is_error": True},
            {"error": "boom"},
            {"success": False},
            {"status": "error"},
            {"status": "failed"},
            {"status": "failure"},
        )
        for response in failures:
            with self.subTest(response=response):
                self.allow(
                    self.record_payload("writing-code", response=response),
                    "record-skill",
                )
                self.assertEqual(
                    self.demanded(self.write_payload(self.rel("foo.py"))),
                    {"writing-code", "writing-python"},
                )

    def test_c9_invalid_record_payloads_write_nothing(self) -> None:
        self.seed([])
        cases = (
            self.record_payload(None),
            self.record_payload(""),
            self.record_payload(5),
            self.record_payload("writing-code", session=None),
            self.record_payload("writing-code", agent="agent-1"),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.allow(payload, "record-skill")
                self.assertEqual(
                    self.demanded(self.write_payload(self.rel("foo.py"))),
                    {"writing-code", "writing-python"},
                )

    def test_c9_record_writes_the_documented_state_file(self) -> None:
        self.allow(self.record_payload("writing-code"), "record-skill")
        path = os.path.join(self.fx.state_dir(), "main.json")
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertEqual(set(state), {"writing-code"})
        self.assertEqual(state["writing-code"]["prompt_id"], PROMPT)
        self.assertIsInstance(state["writing-code"]["ts"], float)

    def test_c9_state_file_is_valid_json_after_replacement(self) -> None:
        """inv8: lock を使わないが os.replace 置換ゆえ、main.json は常に有効な JSON dict。"""
        env = {
            "PATH": self.fx.path,
            "HOME": self.fx.home,
            "GIT_CALL_LOG": self.fx.git_log,
        }
        skills = ("writing-code", "writing-python", "writing-bash", "writing-tests")
        procs = [
            subprocess.Popen(
                [sys.executable, HOOK, "record-skill"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            for _ in skills
        ]
        for proc, skill in zip(procs, skills, strict=True):
            _, err = proc.communicate(
                json.dumps(self.record_payload(skill)), timeout=60
            )
            self.assertEqual(proc.returncode, 0, err)
        directory = self.fx.state_dir()
        self.assertEqual(os.listdir(directory), ["main.json"])
        with open(os.path.join(directory, "main.json"), encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertIsInstance(state, dict)
        self.assertTrue(state and set(state) <= set(skills), state)

    # -- C10: commit-gate covers handoff docs only -------------------------------------------
    def test_c10_handoff_write_requires_the_handoff_skill(self) -> None:
        self.seed([])
        for command in (
            "cat > docs/x-handoff.md <<'EOF'\nx\nEOF\n",
            "printf 'x' > docs/x-handoff.md",
            "tee drafts/old_handoff.md <<EOF\nx\nEOF\n",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    self.demanded(self.bash_payload(command), "commit-gate"),
                    {"handoff"},
                )

    def test_c10_handoff_write_passes_when_the_skill_is_active(self) -> None:
        self.seed(["handoff"])
        self.allow(
            self.bash_payload("cat > docs/x-handoff.md <<'EOF'\nx\nEOF\n"),
            "commit-gate",
        )

    def test_c10_handoff_reads_are_not_gated(self) -> None:
        self.seed([])
        for command in ("cat docs/x-handoff.md", "ls docs/", "wc -l docs/x-handoff.md"):
            with self.subTest(command=command):
                self.allow(self.bash_payload(command), "commit-gate")

    def test_c10_non_handoff_bash_writes_are_not_gated(self) -> None:
        """D3: Bash 経由の一般的な書込は、handoff doc 以外 gate しない。"""
        self.seed([])
        for command in (
            "cat > foo.py <<'EOF'\nx\nEOF\n",
            "sed -i s/a/b/ foo.sh",
            "tee pkg/foo.rb <<EOF\nx\nEOF\n",
            "printf 'x' > tests/foo.py",
        ):
            with self.subTest(command=command):
                self.allow(self.bash_payload(command), "commit-gate")

    def test_c10_commit_literal_pathspec_requires_the_file_kind(self) -> None:
        self.seed([])
        cases = {
            "git commit -m x -- a.py": {"writing-code", "writing-python"},
            "git commit -m x -- a.py b.sh": {
                "writing-code",
                "writing-python",
                "writing-bash",
            },
            "git add a.py && git commit -m x -- 'a.py'": {
                "writing-code",
                "writing-python",
            },
            "git commit -m x -- drafts/old_handoff.md": {"handoff"},
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(
                    self.demanded(self.bash_payload(command), "commit-gate"), expected
                )

    def test_c10_commit_pathspec_label_lists_the_tokens(self) -> None:
        self.seed([])
        self.assertEqual(
            self.deny(self.bash_payload("git commit -m x -- a.py"), "commit-gate"),
            PREFIX + "a.py: writing-code writing-python を invoke してから書き直せ",
        )
        self.assertEqual(
            self.deny(self.bash_payload("git commit -m x -- a.py b.sh"), "commit-gate"),
            PREFIX
            + "a.py, b.sh: writing-bash writing-code writing-python を invoke してから書き直せ",
        )

    def test_c10_commit_pathspec_passes_when_the_skills_are_active(self) -> None:
        self.seed(["writing-code", "writing-python"])
        self.allow(self.bash_payload("git commit -m x -- a.py"), "commit-gate")

    def test_c10_commits_without_literal_pathspec_are_allowed(self) -> None:
        self.seed([])
        for command in (
            "git commit -am wip",
            "git commit --amend --no-edit",
            "git add a.py && git commit -m x",
            "git commit -m x -- src/*.py",
            'git commit -m x -- "$FILE"',
            "git commit -m x -- notes.md",
        ):
            with self.subTest(command=command):
                self.allow(self.bash_payload(command), "commit-gate")
        self.assertEqual(self.fx.git_calls(), [])

    def test_c10_handoff_rule_is_evaluated_first(self) -> None:
        """inv7: handoff 規則が deny した時点で終わるので、label は handoff doc のまま。"""
        self.seed([])
        reason = self.deny(
            self.bash_payload(
                "cat > docs/x-handoff.md <<'EOF'\nx\nEOF\ngit commit -m x -- a.py"
            ),
            "commit-gate",
        )
        self.assertEqual(
            reason, PREFIX + "handoff doc: handoff を invoke してから書き直せ"
        )

    def test_c10_git_is_never_executed(self) -> None:
        self.seed([])
        self.deny(
            self.bash_payload("cat > docs/x-handoff.md <<'EOF'\nx\nEOF\n"),
            "commit-gate",
        )
        self.deny(self.bash_payload("git commit -m x -- a.py"), "commit-gate")
        self.allow(self.bash_payload("git commit -am wip"), "commit-gate")
        self.allow(self.write_payload(self.rel("foo.py"), agent="agent-1"))
        self.assertEqual(self.fx.git_calls(), [])

    def test_c10_non_bash_payloads_are_ignored(self) -> None:
        self.seed([])
        self.allow(self.write_payload(self.rel("foo.py")), "commit-gate")

    def test_c10_state_missing_denies_and_corrupt_allows(self) -> None:
        command = "cat > docs/x-handoff.md <<'EOF'\nx\nEOF\n"
        self.deny(self.bash_payload(command), "commit-gate")
        self.fx.write_state("{")
        self.allow(self.bash_payload(command), "commit-gate")

    # -- C11: state root override -------------------------------------------------------------
    def test_c11_state_root_can_be_overridden(self) -> None:
        env = {"SKILL_REMINDER_STATE_DIR": self.fx.override}
        for skill in ("writing-code", "writing-python"):
            self.allow(self.record_payload(skill), "record-skill", env_extra=env)
        self.assertTrue(
            os.path.exists(os.path.join(self.fx.state_dir(override=True), "main.json"))
        )
        self.assertFalse(os.path.exists(os.path.join(self.fx.state_dir(), "main.json")))
        self.allow(self.write_payload(self.rel("foo.py")), env_extra=env)
        self.deny(self.write_payload(self.rel("foo.py")))

    def test_c11_no_declaration_files_are_written(self) -> None:
        """D2: 宣言 file dir は廃止したので、どの mode でも作られない。"""
        decl = os.path.join(self.fx.home, ".claude", "plugins", "data")
        self.seed([])
        self.allow(self.write_payload(self.rel("runner")))
        self.deny(self.write_payload(self.rel("foo.py")))
        self.allow(self.bash_payload("git commit -am wip"), "commit-gate")
        self.allow(self.record_payload("writing-code"), "record-skill")
        self.assertFalse(os.path.exists(decl), decl)

    def test_c11_transcript_and_git_are_never_touched(self) -> None:
        self.seed(self.PY_SKILLS)
        self.allow(self.write_payload(self.rel("foo.py")))
        self.seed([])
        self.deny(self.write_payload(self.rel("foo.py")))
        self.assertFalse(os.path.exists(self.fx.transcript))
        self.assertEqual(self.fx.git_calls(), [])

    # -- 独立レビュー 1 巡目の所見からの契約訂正 (2026-08-27) -------------------------------
    def test_c10_commit_on_a_later_line_is_still_gated(self) -> None:
        """C10: 改行は command 境界。deny_compound_git_commit が改行区切りへ誘導する既定形。"""
        self.seed([])
        for command in (
            "git add todos.md\ngit commit -m wip -- todos.md",
            "git status\n  git commit -m wip -- todos.md",
            "echo start\ngit commit -m wip -- todos.md",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    self.demanded(self.bash_payload(command), "commit-gate"),
                    {"writing-todos"},
                )

    def test_c10_git_global_options_before_commit_are_gated(self) -> None:
        """C10: avoid_cd が `git -C <repo>` へ誘導するので、global option 前置も呼出。"""
        self.seed([])
        hook_py = "files/claude_managed-hooks/g.py"
        cases = {
            "git -C /home/x/repo commit -m wip -- todos.md": {"writing-todos"},
            "git --no-pager commit -m wip -- todos.md": {"writing-todos"},
            "git -c user.name=x commit -m wip -- todos.md": {"writing-todos"},
            f"git -C /home/x/repo commit -q -m wip -m body -- {hook_py}": {
                "writing-code",
                "writing-python",
                "writing-skills",
            },
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(
                    self.demanded(self.bash_payload(command), "commit-gate"), expected
                )

    def test_c9_concurrent_records_keep_every_key(self) -> None:
        """C9: 並行 upsert の後も各 process の key が残る (再読で競合を検出して再試行)。"""
        env = {
            "PATH": self.fx.path,
            "HOME": self.fx.home,
            "GIT_CALL_LOG": self.fx.git_log,
        }
        skills = ("writing-code", "writing-python", "writing-bash", "writing-tests")
        for _ in range(8):
            self.fx.reset()
            procs = [
                subprocess.Popen(
                    [sys.executable, HOOK, "record-skill"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                for _ in skills
            ]
            for proc, skill in zip(procs, skills, strict=True):
                assert proc.stdin is not None
                proc.stdin.write(json.dumps(self.record_payload(skill)))
                proc.stdin.close()
            for proc in procs:
                self.assertEqual(proc.wait(timeout=60), 0)
            with open(
                os.path.join(self.fx.state_dir(), "main.json"), encoding="utf-8"
            ) as handle:
                state = json.load(handle)
            self.assertEqual(set(state), set(skills), state)

    def test_c9_corrupt_state_is_rebuilt_by_record(self) -> None:
        """C9: corrupt state は record-skill が {} から作り直す (無音の恒久 fail-open を防ぐ)。"""
        self.fx.write_state("{ broken")
        self.allow(self.record_payload("writing-code"), "record-skill")
        with open(
            os.path.join(self.fx.state_dir(), "main.json"), encoding="utf-8"
        ) as handle:
            state = json.load(handle)
        self.assertEqual(set(state), {"writing-code"})
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("foo.py"))), {"writing-python"}
        )

    def test_c4_test_stem_ignores_case(self) -> None:
        """C4: stem の比較も大小文字を無視する (`Foo.Test.PY` は test file)。"""
        self.seed([])
        self.assertEqual(
            self.demanded(self.write_payload(self.rel("Foo.Test.PY"))),
            {"writing-code", "writing-python", "writing-tests"},
        )

    def test_c11_session_id_with_separators_writes_nothing(self) -> None:
        """inv9: session_id が path 分離子を含む payload は state を作らず allow。"""
        session = "a/../../escaped"
        self.allow(self.record_payload("writing-code", session=session), "record-skill")
        found = [
            os.path.join(directory, name)
            for directory, _, names in os.walk(self.fx.tmp)
            for name in names
            if name == "main.json"
        ]
        self.assertEqual(found, [])
        self.allow(self.write_payload(self.rel("foo.py"), session=session))


if __name__ == "__main__":
    unittest.main()
