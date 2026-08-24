#!/usr/bin/env python3
"""PreToolUse(Write) hook: 発注書は雛形の骨組みから始めさせる。

記憶から書き起こした新規発注書の Write を deny し、 同じ path へ
`codex_order_lint --new` が作った骨組みを書き出す。 骨組みは hook が書くので
model はまだ読んでおらず、 read_before_edit が次の Edit を止める = 雛形を読むことが
唯一の進み方になる。 「参照する」 という別行為を作らないための形。

判定は codex_order_lint --metadata の order_document をそのまま使う (語からの推測を
足さない)。 既に所見ゼロで書けている Write は素通しする。 Bash 経由の作成には届かず、
その場合は今日と同じ挙動に戻るだけで悪化はしない。

canonical source: files/claude_managed-hooks/codex_order_scaffold.py
deploy: /etc/claude-code/hooks/  両者を同 session で同内容に保つ。

Exit: 0 always (deny は stdout の permissionDecision で表す。 失敗は必ず allow)。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ORDER_LINT = "/usr/local/bin/codex_order_lint"
ORDER_LINT_TIMEOUT = 10
DRAFTS_DIR = "drafts"
FIX_HEADING = "## 修正方式"
REVIEW_KINDS = frozenset({"adversarial", "acceptance"})


def _emit_deny(reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def _is_candidate(path: str) -> bool:
    """drafts/ 配下の、まだ無い .md だけ。 既存 file を外すので割り込みは 1 文書 1 回。"""
    if not path.endswith(".md") or os.path.exists(path):
        return False
    return DRAFTS_DIR in os.path.normpath(path).split(os.sep)


def _metadata(content: str) -> dict | None:
    """content を検査器に掛けた結果。 読めなければ None (= allow)。"""
    if not os.path.isfile(ORDER_LINT):
        return None
    probe = tempfile.NamedTemporaryFile(
        "w", suffix=".md", encoding="utf-8", delete=False
    )
    try:
        with probe:
            probe.write(content)
        done = subprocess.run(
            [ORDER_LINT, "--metadata", probe.name],
            capture_output=True,
            text=True,
            timeout=ORDER_LINT_TIMEOUT,
            check=False,
        )
        parsed = json.loads(done.stdout)
        return parsed if isinstance(parsed, dict) else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.unlink(probe.name)
        except OSError:
            pass


def _kind(metadata: dict, content: str) -> str:
    """どの雛形を出すか。 検査器が fix 契約を起こす条件と同じものを見る。"""
    fix_active = (
        metadata.get("round") is not None
        or bool(metadata.get("methods"))
        or any(line.strip() == FIX_HEADING for line in content.splitlines())
    )
    if fix_active:
        return "fix"
    if metadata.get("review_kind") in REVIEW_KINDS:
        return "review"
    return "plain"


def _seed(kind: str, path: str) -> str | None:
    """骨組みを書き出し、 検査器が出した 1 行を返す。 失敗は None (= allow)。"""
    try:
        done = subprocess.run(
            [ORDER_LINT, "--new", kind, path],
            capture_output=True,
            text=True,
            timeout=ORDER_LINT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or path


def _deny_text(seeded: str, path: str) -> str:
    # 文面は意図的に冗長 / trim せず維持 (誰が file を作ったかと、次の一手を明示するため)。
    return (
        "発注書は雛形の骨組みから始めてください。 記憶から書き起こした Write を止め、"
        f"代わりに本 hook が骨組みを書き出しました: {seeded}\n"
        f"次の一手: {path} を Read し、 空欄 (未記入) を埋める Edit を入れてください。"
        " 空欄が残っている間は codex_order_lint が所見として数え、 委譲は通りません。\n"
        "種類を選び直すなら、 その file を消してから下記のいずれかを実行してください:\n"
        "  codex_order_lint --new plain <path>   通常の発注書\n"
        "  codex_order_lint --new fix <path>     fix 巡の発注書 (巡番号は同 directory から決まる)\n"
        "  codex_order_lint --new review <path>  レビュー発注書"
    )


def cmd(payload: object) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Write":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    path, content = tool_input.get("file_path"), tool_input.get("content")
    if not isinstance(path, str) or not isinstance(content, str):
        return 0
    if not _is_candidate(path):
        return 0
    metadata = _metadata(content)
    if metadata is None or not metadata.get("order_document"):
        return 0
    if not metadata.get("findings"):  # 一発で規約を満たした Write は止めない
        return 0
    seeded = _seed(_kind(metadata, content), path)
    if seeded is None:
        return 0
    _emit_deny(_deny_text(seeded, path))
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        return cmd(payload)
    except Exception:
        pass  # fail-open
    return 0


class ScaffoldTest(unittest.TestCase):
    """骨組みを置いてから止める。 Run: python3 -m unittest codex_order_scaffold"""

    ORDER = "# 発注書: 例\n\nreview-kind: none\n\n## スコープ\n\n未記入\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.drafts = os.path.join(self.tmp, "drafts")
        os.makedirs(self.drafts)
        self.old_lint = globals()["ORDER_LINT"]
        repo_lint = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "codex_order_lint",
        )
        if os.path.isfile(repo_lint):
            globals()["ORDER_LINT"] = repo_lint

    def tearDown(self):
        globals()["ORDER_LINT"] = self.old_lint
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _payload(self, path: str, content: str = ORDER, tool: str = "Write") -> dict:
        return {
            "tool_name": tool,
            "tool_input": {"file_path": path, "content": content},
        }

    def _run(self, payload: dict) -> str:
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            cmd(payload)
        return out.getvalue()

    def test_a_remembered_order_is_denied_and_the_skeleton_is_written(self):
        if not os.path.isfile(ORDER_LINT):
            self.skipTest("検査器が repo にも配備先にも無い")
        target = os.path.join(self.drafts, "sample-order.md")
        output = self._run(self._payload(target))
        self.assertIn("deny", output)
        self.assertTrue(os.path.isfile(target))
        with open(target, encoding="utf-8") as handle:
            self.assertIn("未記入", handle.read())

    def test_non_write_tools_and_non_draft_paths_are_untouched(self):
        for path, tool in (
            (os.path.join(self.drafts, "x-order.md"), "Edit"),
            (os.path.join(self.tmp, "x-order.md"), "Write"),
            (os.path.join(self.drafts, "notes.txt"), "Write"),
        ):
            with self.subTest(path=path, tool=tool):
                self.assertEqual(self._run(self._payload(path, tool=tool)), "")

    def test_an_existing_file_is_never_interrupted_twice(self):
        target = os.path.join(self.drafts, "again-order.md")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(self.ORDER)
        self.assertEqual(self._run(self._payload(target)), "")

    def test_a_document_that_is_not_an_order_passes(self):
        if not os.path.isfile(ORDER_LINT):
            self.skipTest("検査器が repo にも配備先にも無い")
        target = os.path.join(self.drafts, "memo.md")
        memo = "# 設計メモ\n\n本文だけの覚書。\n"
        self.assertEqual(self._run(self._payload(target, memo)), "")
        self.assertFalse(os.path.exists(target))

    def test_a_missing_linter_fails_open(self):
        globals()["ORDER_LINT"] = os.path.join(self.tmp, "absent")
        target = os.path.join(self.drafts, "sample-order.md")
        self.assertEqual(self._run(self._payload(target)), "")
        self.assertFalse(os.path.exists(target))

    def test_kind_follows_the_linters_own_activation(self):
        self.assertEqual(_kind({"round": 3}, ""), "fix")
        self.assertEqual(_kind({}, "## 修正方式\n"), "fix")
        self.assertEqual(_kind({"review_kind": "adversarial"}, ""), "review")
        self.assertEqual(_kind({"review_kind": "none"}, ""), "plain")


if __name__ == "__main__":
    sys.exit(main())
