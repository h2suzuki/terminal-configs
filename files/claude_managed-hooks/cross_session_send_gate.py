#!/usr/bin/env python3
"""SendMessage 発信文の承認断定語を送信前に検査する gate。"""

from __future__ import annotations

import io
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock


ASSERTION_RE = re.compile(
    r"(承認|裁定|決定|合意)(済み|されました|が出た|を得た|いただいた)"
)
QUOTE_RE = re.compile(r"「[^」]*」", re.DOTALL)
FORM_MARKERS = ("出所", "verbatim", "引用")
# deny 文面は意図的に冗長なため trim 禁止。
DENY_REASON = (
    "send-message-approval-gate: 発信文の地の文に承認断定語が form 標識なしで"
    "含まれるため deny しました。承認語を発信者の解釈で書かないでください。"
    "書けるのは本人発言の verbatim 引用（「」+ 出所）+ 承認 scope の読み + "
    "未承認事項のみです。本人発言を「」で verbatim 引用し、出所を明記した "
    "form へ書き直せば送信できます。hook 自身は message を変更しません。"
)


def _has_form(message: str) -> bool:
    """本人発言の引用 form を満たす標識があるか返す。"""
    return QUOTE_RE.search(message) is not None and any(
        marker in message for marker in FORM_MARKERS
    )


def _emit_deny() -> None:
    """PreToolUse の deny 応答を出力する。"""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")


def _run(payload: object) -> None:
    """正しい message がある payload だけを検査する。"""
    if not isinstance(payload, dict):
        return
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    message = tool_input.get("message")
    if not isinstance(message, str):
        return
    ground_text = QUOTE_RE.sub("", message)
    if ASSERTION_RE.search(ground_text) and not _has_form(message):
        _emit_deny()


def main() -> int:
    """stdin payload を読み、異常時は送信を妨げず終了する。"""
    try:
        _run(json.loads(sys.stdin.read()))
    except Exception:
        return 0
    return 0


class SendMessageApprovalGateTest(unittest.TestCase):
    """発火、非発火、fail-open、登録を検証する。"""

    def _invoke(self, raw: str) -> tuple[int, dict | None]:
        stdin = io.StringIO(raw)
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", stdin),
            mock.patch.object(sys, "stdout", stdout),
        ):
            exit_code = main()
        text = stdout.getvalue()
        return exit_code, json.loads(text) if text else None

    def _message(self, message: str) -> tuple[int, dict | None]:
        payload = {"tool_input": {"message": message}}
        return self._invoke(json.dumps(payload, ensure_ascii=False))

    def test_denies_all_assertion_alternations(self) -> None:
        for noun in ("承認", "裁定", "決定", "合意"):
            for suffix in ("済み", "されました", "が出た", "を得た", "いただいた"):
                with self.subTest(noun=noun, suffix=suffix):
                    exit_code, output = self._message(f"この件は{noun}{suffix}です。")
                    self.assertEqual(exit_code, 0)
                    if output is None:
                        self.fail("deny 応答がありません")
                    hook_output = output["hookSpecificOutput"]
                    self.assertEqual(hook_output["permissionDecision"], "deny")
                    self.assertEqual(
                        hook_output["permissionDecisionReason"], DENY_REASON
                    )

    def test_allows_scope_descriptions(self) -> None:
        for message in ("承認 scope の読み", "未承認事項", "裁定待ち"):
            with self.subTest(message=message):
                self.assertEqual(self._message(message), (0, None))

    def test_allows_assertion_inside_quote(self) -> None:
        self.assertEqual(self._message("本人は「承認済み」と発言した。"), (0, None))

    def test_allows_compliant_form_markers(self) -> None:
        for marker in FORM_MARKERS:
            with self.subTest(marker=marker):
                message = (
                    f"本人発言「着手してください」\n{marker}: 本人の発言\n"
                    "承認済み scope の読み: 対象 A のみ\n未承認事項: 対象 B"
                )
                self.assertEqual(self._message(message), (0, None))

    def test_allows_message_without_assertion(self) -> None:
        self.assertEqual(self._message("調査結果を共有してください。"), (0, None))

    def test_malformed_json_fails_open(self) -> None:
        self.assertEqual(self._invoke("{"), (0, None))

    def test_missing_message_fails_open(self) -> None:
        for payload in ({}, {"tool_input": {}}, {"tool_input": {"message": None}}):
            with self.subTest(payload=payload):
                self.assertEqual(self._invoke(json.dumps(payload)), (0, None))

    def test_send_message_matcher_is_registered(self) -> None:
        config_path = (
            Path(__file__).resolve().parents[1] / "claude_managed-extensions.json"
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        expected = {
            "matcher": "^SendMessage$",
            "hooks": [
                {
                    "type": "command",
                    "command": "/etc/claude-code/hooks/cross_session_send_gate.py",
                }
            ],
        }
        self.assertEqual(config["hooks"]["PreToolUse"].count(expected), 1)

    def test_hook_is_executable(self) -> None:
        self.assertTrue(Path(__file__).stat().st_mode & 0o100)


if __name__ == "__main__":
    sys.exit(main())
