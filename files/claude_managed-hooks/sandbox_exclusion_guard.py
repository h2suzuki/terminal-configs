#!/usr/bin/env python3
"""
Sandbox excluded-command hook for Bash.

SessionStart proactively injects the live excludedCommands roster once per session.
PreToolUse denies path-prefixed and sudo forms and warns on other wrappers, all
of which miss the match and fall back into the sandbox. PostToolUseFailure
answers sandbox-looking failures with the live excludedCommands roster, so a
wrong calling form is not misread as a sandbox limit. A failure on a
credential-protected path gets a stronger answer: being unable to read one back
is not evidence of running inside the sandbox.

Claude Code matches each Bash execution segment, so a compound command or a
direct assignment prefix still reaches the host and is deliberately not flagged.

Exit:
  0: pass, or advise with hookSpecificOutput.additionalContext
  2: a path-prefixed or sudo-wrapped excluded command is blocked

Always exits 0 on any unexpected error (fail-open).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

import sandbox_exclusions
from sandbox_exclusions import (
    bare_form,
    claim_once,
    credential_paths,
    load_patterns,
    roster_text,
    sandbox_restricts_commands,
)

# sandbox 制限と見分けがつかない失敗症状 — 誤帰属が起きるのはここ。
SANDBOX_SYMPTOM = re.compile(
    r"Permission denied|Operation not permitted|Read-only file system|"
    r"Could not resolve host|Network is unreachable|Connection timed out|"
    r"Temporary failure in name resolution|\bEACCES\b|\bEPERM\b",
    re.IGNORECASE,
)
ASSIGNMENT = re.compile(r"^\w+=\S*$")
# 照合前に剥がされない wrapper — 内側が除外コマンドでも sandbox に落ちる。
# timeout / time / nice / nohup / stdbuf / command / builtin / noglob / xargs は
# 剥がされる側なので、ここに入れると誤検知になる。
WRAPPERS = frozenset({"sudo", "env", "npx", "bunx", "uvx"})
SEPARATOR = re.compile(r"&&|\|\||[;|&\n]")  # top-level 制御演算子のみ
COMMENT = re.compile(r"#.*$", re.MULTILINE)
# $(...)/`...` は host 化不能ゆえマスクして segment 対象外にする (F1)。
SUBST = re.compile(r"\$\([^()]*\)|`[^`]*`")
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)


def _strip_heredoc(m: re.Match) -> str:
    """Replace heredoc body with `_`, keeping trailing shell code on the opener line."""
    return "_" + m.group(2)


def _glob_match(value: str, pattern: str) -> bool:
    """Match a Claude excludedCommands star glob with full-string anchors."""
    translated = re.escape(pattern).replace(r"\*", ".*")
    if translated.endswith(r"\ .*") and pattern.count("*") == 1:
        translated = translated[:-4] + r"(\ .*)?"
    return re.fullmatch(translated, value, re.DOTALL) is not None


def _wrapped_command(tokens: list[str], patterns: list[str]) -> str:
    """Return the excluded command a wrapper runs, past the wrapper's own options."""
    for position, token in enumerate(tokens):
        if token.startswith("-") or ASSIGNMENT.match(token) or "/" in token:
            continue
        candidate = " ".join(tokens[position:])
        if any(_glob_match(candidate, pattern) for pattern in patterns):
            return candidate
    return ""


def _classify(cmd: str, patterns: list[str]) -> tuple[str, str, str]:
    """Return block/warn/pass, the excluded invocation, and its reason."""
    scanned = HEREDOC.sub(_strip_heredoc, cmd)
    scanned = QUOTED.sub("_", scanned)
    scanned = SUBST.sub("_", scanned)
    scanned = COMMENT.sub("", scanned)
    warning: tuple[str, str, str] | None = None
    for segment in SEPARATOR.split(scanned):
        tokens = segment.strip().split()
        # 先頭の直接代入は照合前に剥がされる — `FOO=1 gh ...` は一致し host で走る。
        while tokens and ASSIGNMENT.match(tokens[0]):
            tokens.pop(0)
        if not tokens:
            continue
        program = tokens[0]
        basename = os.path.basename(program)
        if basename in WRAPPERS:
            nested = _wrapped_command(tokens[1:], patterns)
            if nested:
                if basename == "sudo":
                    return "block", nested, "sudo"
                if warning is None:
                    warning = "warn", nested, basename
            continue
        normalized = " ".join([basename, *tokens[1:]])
        if not any(_glob_match(normalized, pattern) for pattern in patterns):
            continue
        if "/" in program:
            return "block", normalized, "path prefix"
    return warning or ("pass", "", "")


def _emit(event: str, msg: str) -> None:
    output: dict[str, str] = {"hookEventName": event, "additionalContext": msg}
    if event == "PreToolUse":
        output["permissionDecision"] = "allow"
    sys.stdout.write(
        json.dumps({"hookSpecificOutput": output}, ensure_ascii=False) + "\n"
    )


def _roster_suffix(payload: dict, patterns: list[str]) -> str:
    """Append the roster only when this session has not been shown it yet."""
    if not claim_once(payload, "roster"):
        return ""
    return "\n" + roster_text(patterns)


def _indirect_mentions(cmd: str, patterns: list[str]) -> list[str]:
    """Return excluded commands reached through a form that misses the match."""
    heads = {bare_form(p).split()[0] for p in patterns if bare_form(p)}
    scanned = QUOTED.sub(" ", SUBST.sub(" ", HEREDOC.sub(_strip_heredoc, cmd)))
    found: list[str] = []
    for segment in SEPARATOR.split(COMMENT.sub("", scanned)):
        tokens = segment.split()
        while tokens and ASSIGNMENT.match(tokens[0]):
            tokens.pop(0)
        if not tokens:
            continue
        leader = os.path.basename(tokens[0])
        # 剥がされる wrapper と裸名の先頭呼びは一致する — 誤検知させない。
        if "/" in tokens[0]:
            candidates = [leader]
        elif leader in WRAPPERS:
            candidates = [os.path.basename(t) for t in tokens[1:]]
        else:
            continue
        found.extend(n for n in candidates if n in heads and n not in found)
    return found


def _handle_failure(payload: dict, patterns: list[str], cmd: str) -> int:
    """Answer a sandbox-looking Bash failure with the roster before misattribution."""
    response = payload.get("tool_response") or {}
    if not isinstance(response, dict):
        return 0
    output = "\n".join(
        value
        for key in ("output", "stdout", "stderr", "error", "message", "tool_result")
        if isinstance(value := response.get(key), str)
    )
    if not output or not SANDBOX_SYMPTOM.search(output):
        return 0
    touched = [p for p in credential_paths() if p in cmd or p in output]
    if touched:
        if not claim_once(payload, "failure-credential"):
            return 0
        message = (
            f"credential 保護 path (`{touched[0]}`) への操作が失敗しました。 これは "
            "sandbox の credential 保護による遮断で、 excludedCommands とは別の層です。\n"
            "**読み書きできないことは「今 sandbox 内で動いている」証拠になりません。** "
            "書き込んだ値を読み返せない事実から実行環境を推論しないでください。 同じ file "
            "でも、 一覧にある除外コマンド経由なら読めます (例: 認証情報を直接 cat すると "
            "拒否されるが、 対応する CLI を裸名で呼べば読める)。"
        )
    elif mentioned := _indirect_mentions(cmd, patterns):
        if not claim_once(payload, "failure-indirect"):
            return 0
        message = (
            f"失敗した command は除外コマンド {', '.join(f'`{m}`' for m in mentioned)} を "
            "segment 先頭以外で呼んでいます。 この形は除外に一致せず sandbox 内で走るため、"
            "この失敗は sandbox の制限ではなく呼び方が原因の可能性が高いです。"
        )
    else:
        if not claim_once(payload, "failure-generic"):
            return 0
        message = (
            "sandbox 制限と区別できない症状で Bash が失敗しました。 sandbox のせいと"
            "結論づける前に、 同じ作業を除外コマンドで行えないかを確認してください。"
        )
    _emit(
        payload.get("hook_event_name") or "PostToolUseFailure",
        message + _roster_suffix(payload, patterns),
    )
    return 0


def _run(payload: object, patterns: list[str] | None = None) -> int:
    if not isinstance(payload, dict):
        return 0
    patterns = load_patterns() if patterns is None else patterns
    event = payload.get("hook_event_name")
    if event == "SessionStart":
        if not claim_once(payload, "session-start-roster"):
            return 0
        _emit("SessionStart", roster_text(patterns))
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return 0
    if event == "PostToolUseFailure":
        return _handle_failure(payload, patterns, cmd)
    decision, normalized, reason = _classify(cmd, patterns)
    if decision == "pass":
        return 0
    if decision == "warn":
        if not claim_once(payload, reason):
            return 0
        message = (
            f"`{reason}` 経由で除外コマンド `{normalized}` を呼んでいます。 wrapper は "
            "照合前に剥がされないため、この形は除外に一致せず sandbox 内で走ります。 "
            f"`{normalized}` を segment 先頭に置いて直接呼んでください。"
            "この警告は同一セッション中、その種別につき 1 回だけ表示されます。"
        )
        _emit("PreToolUse", message + _roster_suffix(payload, patterns))
        return 0
    if reason == "sudo":
        detail = "`sudo` 前置は除外に一致せず、sandbox 内では権限昇格もできません"
    else:
        detail = "path 前置は除外に一致せず sandbox 内実行に落ちます"
    sys.stderr.write(
        f"sandbox-exclusion-guard: excluded command `{normalized}` を block しました。"
        f"{detail}。\n\n"
        f"Retry: `{normalized}` を segment 先頭に裸名で置いてください。 "
        "`cd x && <裸名> ...` や `FOO=1 <裸名> ...` は一致するので、そのまま使えます。\n"
    )
    return 2


def main() -> int:
    try:
        # 制限が無いなら何も読まず即 no-op — 空の roster は無効化の証拠ではない。
        if not sandbox_restricts_commands():
            return 0
        payload = json.loads(sys.stdin.read() or "{}")
        return _run(payload)
    except Exception:
        return 0


class GateTest(unittest.TestCase):
    """Detection matrix / mtime cache / executable bit. Run: python3 -m unittest sandbox_exclusion_guard"""

    PATTERNS = [
        "git *",
        "dsa_launcher *",
        "dsa *",
        "cargo test *",
        "node *codex-companion.mjs*",
    ]
    BLOCK = (
        "/usr/bin/git push",
        "tools/dsa_launcher restart db",
        "cd x && /usr/bin/git push",
        "sudo git push",
        "sudo dsa_launcher restart db",
        "sudo -u deploy git push",
        "VAR=x git push && /usr/bin/git push",
    )
    WARN = (
        "env git push",
        "env FOO=1 dsa foo",
        "npx dsa foo",
        "env -i git push",
    )
    # 実装は segment 単位照合で、直接代入と一部 wrapper を剥がしてから照合する。
    PASS = (
        "git push",
        "dsa_launcher restart db",
        "cargo test foo",
        "VAR=val git push",
        "FOO=1 BAR=2 dsa foo",
        "cd app && git push",
        "echo hi ; cargo test x",
        "git",
        "timeout 5 git push",
        "nohup dsa_launcher restart db",
        "nice -n 10 cargo test x",
        "git push && echo done",
        "git log | head",
        "timeout 5 git push",
        "nice -n 10 cargo test x",
        "VERSION=$(git describe)",
        "x=$(dsa foo)",
        "cargo build",
        "node app.js",
        "which git",
        "man dsa",
        'echo "cd x && git push"',
        "# git push",
        "result=$(cd /repo; tools/dsa_launcher status)",
        "echo `git status`",
        "# deploy\ngit push",
    )

    def setUp(self):
        self.state_dir = tempfile.TemporaryDirectory()
        # latch state は共有 module 側 — patch 先を誤ると実 state を汚す。
        self.state_patch = mock.patch.object(
            sandbox_exclusions, "STATE_DIR", self.state_dir.name
        )
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.addCleanup(self.state_dir.cleanup)

    @staticmethod
    def _result(
        cmd: str,
        patterns: list[str],
        session_id: str | None = None,
        transcript_path: str | None = None,
    ) -> tuple[int, str, str]:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}}
        if session_id is not None:
            payload["session_id"] = session_id
        if transcript_path is not None:
            payload["transcript_path"] = transcript_path
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = _run(payload, patterns)
        return result, stdout.getvalue(), stderr.getvalue()

    @classmethod
    def _emit_for(cls, payload: dict) -> tuple[int, str, str]:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = _run(payload, cls.PATTERNS)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_blocks_path_and_bare_sudo_invocations(self):
        for cmd in self.BLOCK:
            result, stdout, stderr = self._result(cmd, self.PATTERNS)
            self.assertEqual(result, 2, cmd)
            self.assertEqual(stdout, "", cmd)
            self.assertIn("excluded command", stderr, cmd)
            self.assertIn("segment 先頭", stderr, cmd)

    def test_warns_without_blocking_ambiguous_invocations(self):
        for cmd in self.WARN:
            result, stdout, stderr = self._result(cmd, self.PATTERNS)
            self.assertEqual(result, 0, cmd)
            self.assertEqual(stderr, "", cmd)
            output = json.loads(stdout)["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "PreToolUse", cmd)
            self.assertEqual(output["permissionDecision"], "allow", cmd)
            self.assertIn("sandbox 内で走ります", output["additionalContext"], cmd)
            if cmd.startswith("sudo"):
                self.assertIn("権限昇格できず失敗", output["additionalContext"], cmd)

        first = self._result("env git push", self.PATTERNS, session_id="same")
        second = self._result("env dsa foo", self.PATTERNS, session_id="same")
        self.assertNotEqual(first[1], "")
        self.assertEqual(second, (0, "", ""))

        first = self._result(
            "npx dsa foo", self.PATTERNS, session_id="different-reason"
        )
        second = self._result(
            "env git push",
            self.PATTERNS,
            session_id="different-reason",
        )
        self.assertNotEqual(first[1], "")
        self.assertNotEqual(second[1], "")

        first = self._result("env git push", self.PATTERNS, session_id="one")
        second = self._result("env git push", self.PATTERNS, session_id="two")
        self.assertNotEqual(first[1], "")
        self.assertNotEqual(second[1], "")

    def test_passes_host_and_nonmatching_invocations_silently(self):
        for cmd in self.PASS:
            result, stdout, stderr = self._result(cmd, self.PATTERNS)
            self.assertEqual(result, 0, cmd)
            self.assertEqual(stdout, "", cmd)
            self.assertEqual(stderr, "", cmd)

    def test_empty_patterns_allow_everything(self):
        self.assertEqual(self._result("env git push", []), (0, "", ""))

    def test_warns_every_time_without_a_latch_key(self):
        first = self._result("env git push", self.PATTERNS)
        second = self._result("env git push", self.PATTERNS)
        self.assertNotEqual(first[1], "")
        self.assertNotEqual(second[1], "")

    def test_transcript_path_is_a_latch_key_fallback(self):
        first = self._result(
            "env git push", self.PATTERNS, transcript_path="/tmp/transcript"
        )
        second = self._result(
            "env git push", self.PATTERNS, transcript_path="/tmp/transcript"
        )
        self.assertNotEqual(first[1], "")
        self.assertEqual(second, (0, "", ""))

    def test_warns_when_latch_state_cannot_be_written(self):
        with mock.patch.object(os, "replace", side_effect=OSError):
            result, stdout, stderr = self._result(
                "env git push", self.PATTERNS, session_id="unwritable"
            )
        self.assertEqual(result, 0)
        self.assertNotEqual(stdout, "")
        self.assertEqual(stderr, "")

    def test_session_start_emits_the_roster_once(self):
        payload = {"hook_event_name": "SessionStart", "session_id": "start"}
        result, stdout, stderr = self._emit_for(payload)
        self.assertEqual((result, stderr), (0, ""))
        output = json.loads(stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertIn("sandbox.excludedCommands", output["additionalContext"])
        self.assertIn("`git *`", output["additionalContext"])
        self.assertEqual(self._emit_for(payload), (0, "", ""))

    def test_failure_still_gets_the_roster_after_session_start(self):
        session_id = "start-then-failure"
        start = {"hook_event_name": "SessionStart", "session_id": session_id}
        failure = {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://example.com"},
            "tool_response": {"stderr": "curl: Connection timed out"},
            "session_id": session_id,
        }
        self.assertNotEqual(self._emit_for(start)[1], "")
        result, stdout, stderr = self._emit_for(failure)
        self.assertEqual((result, stderr), (0, ""))
        context = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("sandbox のせいと", context)
        self.assertIn("`git *`", context)

    def test_failure_rejects_the_credential_store_inference(self):
        secret = os.path.join(os.path.expanduser("~"), ".config", "gh", "hosts.yml")
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": f"cat {secret}"},
            "tool_response": {"stderr": f"cat: {secret}: Permission denied"},
            "session_id": "credential",
        }
        with mock.patch.object(
            sys.modules[__name__], "credential_paths", lambda: [secret]
        ):
            _, stdout, _ = self._emit_for(payload)
        context = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("証拠になりません", context)
        self.assertIn("推論しないでください", context)
        self.assertNotIn("呼び方が原因", context)

    def test_failure_answers_sandbox_symptoms_with_the_roster(self):
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://example.com"},
            "tool_response": {"stderr": "curl: Connection timed out"},
            "session_id": "generic",
        }
        result, stdout, stderr = self._emit_for(payload)
        self.assertEqual((result, stderr), (0, ""))
        context = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("sandbox のせいと", context)
        self.assertIn("`git *`", context)
        self.assertEqual(self._emit_for(payload), (0, "", ""))

    def test_failure_names_an_indirectly_called_excluded_command(self):
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": "env git push"},
            "tool_response": {"stderr": "fatal: Permission denied"},
            "session_id": "indirect",
        }
        _, stdout, _ = self._emit_for(payload)
        context = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("`git`", context)
        self.assertIn("呼び方が原因", context)

    def test_failure_stays_silent_without_a_sandbox_symptom(self):
        payload = {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": "grep missing file"},
            "tool_response": {"stderr": "grep: file: No such file or directory"},
            "session_id": "unrelated",
        }
        self.assertEqual(self._emit_for(payload), (0, "", ""))

    def test_roster_is_appended_only_once_per_session(self):
        first = self._result("env git push", self.PATTERNS, session_id="once")
        second = self._result("npx dsa foo", self.PATTERNS, session_id="once")
        self.assertIn("`git *`", first[1])
        self.assertNotIn("`git *`", second[1])

    def test_no_op_returns_before_reading_stdin_when_unrestricted(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        def explode():
            raise AssertionError("stdin was read after the no-op gate")

        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(
            sys.modules[__name__], "sandbox_restricts_commands", lambda: False
        ):
            with mock.patch.object(sys, "stdin", mock.Mock(read=explode)):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = main()
        self.assertEqual((result, stdout.getvalue(), stderr.getvalue()), (0, "", ""))

    def test_file_is_executable(self):
        self.assertTrue(os.access(os.path.abspath(__file__), os.X_OK))


if __name__ == "__main__":
    sys.exit(main())
