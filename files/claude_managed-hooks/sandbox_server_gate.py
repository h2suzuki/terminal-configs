#!/usr/bin/env python3
"""
Sandbox-server-unreachable-from-host advisory hook for Claude Code.

PreToolUse hook on Bash. Detects commands that start a long-running dev/
preview server inside the sandbox (`npm run dev`, `vite`, `python -m
http.server`, `cargo run --bin dsa-server`, ...) and emits
hookSpecificOutput.additionalContext warning that the sandbox is not
reachable from the host browser — mirrors `avoid_cd.py`'s architecture:
never deny, just advise.

Once-per-window: the same session is only advised once per
ADVISE_WINDOW_SECONDS (state file keyed by session_id) so a legitimate
retry/rerun in the same turn is not re-nagged.

Exit code is always 0 (fail-open): any parsing exception is swallowed so a
hook bug never blocks Claude.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unittest

# command 位置 (行頭 / ; & | ( 後 / $( ` 後) に限定 — echo 引数・quote・comment 内の FP を排除
_CMD_START = r"(?:^|[;&|(]|\$\(|`)\s*"
# 右端 \b で部分一致 FP を排除 (developer / devtools / dsa-serverless / runner)。
# vite は serve/default 起動のみ (build/preview/optimize/--version/-v は非対象)。
# cargo run 汎用形は対象外 — 既知 server 起動 (--bin dsa-server) に限定。
SERVER_RE = re.compile(
    _CMD_START + r"(?:"
    r"npm run dev\b|"
    r"pnpm(?: run)? dev\b|"
    r"yarn dev\b|"
    r"python3? -m http\.server\b|"
    r"dsa-server\b|"
    r"cargo run\b.*--bin[= ]dsa-server\b|"
    r"vite\b(?!\s+(?:build|preview|optimize|--version|-v)\b)"
    r")"
)

STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "sandbox_server_gate"
)
ADVISE_WINDOW_SECONDS = 300  # 同一 session の re-advise を抑える窓


def _state_path(session_id: str) -> str:
    return os.path.join(STATE_DIR, session_id)


def _recently_advised(session_id: str, now: float) -> bool:
    if not session_id:
        return False
    try:
        with open(_state_path(session_id), encoding="utf-8") as f:
            ts = float(f.read().strip())
    except (OSError, ValueError):
        return False
    return (now - ts) < ADVISE_WINDOW_SECONDS


def _record_advised(session_id: str, now: float) -> None:
    if not session_id:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(_state_path(session_id), "w", encoding="utf-8") as f:
            f.write(str(now))
    except OSError:
        pass


def _emit(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: object, now: float) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("tool_name") != "Bash":
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return
    if not SERVER_RE.search(cmd):
        return
    session_id = payload.get("session_id")
    if not isinstance(session_id, str):
        session_id = ""
    if _recently_advised(session_id, now):
        return
    _record_advised(session_id, now)
    _emit(
        "検証サーバーの起動コマンドが検出されました。 sandbox からは host browser に "
        "届きません。 excludedCommands launcher (`dsa_launcher` 等) か `!` での host "
        "実行を検討してください。"
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        _run(payload, time.time())
    except Exception:
        pass
    return 0


class GateTest(unittest.TestCase):
    """発火 / 非発火 boundary matrix / once-per-window / 実行 bit. Run: python3 -m unittest sandbox_server_gate"""

    # server 起動 (発火すべき)
    _POSITIVE = (
        "npm run dev",
        "npm run dev -- --host",
        "cd app && npm run dev",
        "vite",
        "vite dev --port 3000",
        "pnpm dev",
        "pnpm run dev",
        "yarn dev",
        "python -m http.server",
        "python3 -m http.server 8000",
        "dsa-server start",
        "cargo run --bin dsa-server",
        "cargo run --release --bin dsa-server",
    )
    # レビュー実測 FP + boundary negative (発火してはならない)
    _NEGATIVE = (
        "echo invite",
        "npm run developer",
        "pnpm devtools",
        "dsa-serverless deploy",
        "cargo runner",
        "cargo run",  # 汎用形は除外 (既知 server 起動のみ)
        "cargo run --bin other-tool",
        "vite build",
        "vite preview",
        "vite --version",
        "vite -v",
        'echo "npm run dev"',
        "# vite を後で起動する",
        "grep 'yarn dev' README.md",
        "git status",
        "npm run build",
    )

    @staticmethod
    def _run(cmd, sid="s1"):
        import io
        from contextlib import redirect_stdout

        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": sid}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _run(payload, time.time())
        out = buf.getvalue().strip()
        return json.loads(out)["hookSpecificOutput"] if out else None

    def test_fires_on_dev_server_commands(self):
        import tempfile
        from unittest import mock

        with mock.patch.object(sys.modules[__name__], "STATE_DIR", tempfile.mkdtemp()):
            for cmd in self._POSITIVE:
                out = self._run(cmd, sid=cmd)
                assert out is not None, cmd
                self.assertEqual(out["permissionDecision"], "allow")
                self.assertIn("host browser", out["additionalContext"])

    def test_no_fire_on_boundary_negatives(self):
        import tempfile
        from unittest import mock

        with mock.patch.object(sys.modules[__name__], "STATE_DIR", tempfile.mkdtemp()):
            for cmd in self._NEGATIVE:
                self.assertIsNone(self._run(cmd, sid=cmd), cmd)

    def test_advise_once_per_window_per_session(self):
        import tempfile
        from unittest import mock

        with mock.patch.object(sys.modules[__name__], "STATE_DIR", tempfile.mkdtemp()):
            self.assertIsNotNone(self._run("vite", sid="s1"))  # 窓内 1 回目 -> advise
            self.assertIsNone(self._run("vite", sid="s1"))  # 窓内 retry -> silent
            self.assertIsNotNone(self._run("vite", sid="s2"))  # 別 session は独立

    def test_file_is_executable(self):
        # deploy は mode 保存 cp、hook 配線は直接実行 — 実行 bit 必須
        self.assertTrue(os.access(os.path.abspath(__file__), os.X_OK))


if __name__ == "__main__":
    sys.exit(main())
