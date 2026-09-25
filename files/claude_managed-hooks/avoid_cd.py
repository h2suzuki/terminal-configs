#!/usr/bin/env python3
"""
Avoid-cd hook for Claude Code.

PreToolUse hook on Bash. Detects leading-`cd` (or bare `cd`) and emits
hookSpecificOutput.additionalContext suggesting alternatives (pushd/popd,
absolute paths, `git -C <repo>`).

Scope is INTENTIONALLY narrow: only leading-`cd` is flagged. Embedded forms
(`; cd`, `bash -c 'cd ...'`, `(cd /tmp; ls)`) are NOT flagged here; the
runtime-symptom detector `detect_cwd_pollution.py` (PostToolUseFailure)
catches their cwd pollution. Broadening would over-flag legitimate subshell
idioms.

Only a leading `cd` in a compound command is denied; all other commands are
allowed, and standalone leading-`cd` forms remain advisory allows. `pushd` and
`popd` are not detected.

The git-push allowlist exception (`git push origin main` run as the bare
string) does not begin with the current leading-`cd` predicate, so no carve-out
is required.

Exit code is always 0 (fail-open): any parsing exception is swallowed so a
hook bug never blocks Claude.
"""

from __future__ import annotations

import json
import re
import sys
import unittest

from contextlib import redirect_stdout
from io import StringIO

CD_PREFIX_RE = re.compile(r"^\s*cd(?![A-Za-z0-9_-])")
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b",
    re.MULTILINE,
)
BACKTICK = re.compile(r"`[^`]*`")
COMMENT = re.compile(r"(?m)(?<!\S)#.*$")


def _emit(msg: str, *, deny: bool = False) -> None:
    decision = "deny" if deny else "allow"
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
        }
    }
    if deny:
        payload["hookSpecificOutput"]["permissionDecisionReason"] = msg
    else:
        payload["hookSpecificOutput"]["additionalContext"] = msg
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _masked_command(cmd: str) -> str:
    masked = cmd
    while True:
        masked_again = HEREDOC.sub(lambda match: "_" + match.group(2), masked)
        if masked_again == masked:
            break
        masked = masked_again
    masked = QUOTED.sub("_", masked)
    masked = re.sub(r"\\[\s\S]", "_", masked)
    result: list[str] = []
    index = 0
    while index < len(masked):
        if masked.startswith("$(", index) or masked.startswith("${", index):
            opening = masked[index + 1]
            closing = ")" if opening == "(" else "}"
            depth = 1
            index += 2
            while index < len(masked) and depth:
                if masked[index] == opening:
                    depth += 1
                elif masked[index] == closing:
                    depth -= 1
                index += 1
            result.append("_")
        else:
            result.append(masked[index])
            index += 1
    masked = BACKTICK.sub("_", "".join(result))
    return COMMENT.sub("", masked)


def _has_compound_operator_after_cd(cmd: str) -> bool:
    masked = _masked_command(cmd)
    if any(mark in masked for mark in ('"', "'", "`")):
        return False
    if re.search(r"<<-?(?!<)\s*['\"]?\w+['\"]?", masked):
        return False
    parts = re.split(r"&&|\|\||[;|\n]", masked.strip(), maxsplit=1)
    return len(parts) > 1 and parts[1].strip() != ""


DENY_REASON = (
    "複合コマンドの先頭に `cd` があり、cwd が後続 turn に残るため deny しました。"
    "実害として、後続コマンドの相対 path と `git commit -- <path>` の pathspec が壊れます"
    "（`git commit -- <path>` の pathspec 破壊を実測）。"
    "絶対 path を使うか、`git -C <repo> ...` を使ってください。"
    "どうしても cwd の移動が必要なら `pushd` と `popd` を使うか、"
    "`cd` を単独の Bash 呼び出しに分けてください。"
    "単独の `cd` と `pushd` / `popd` は deny されません。"
)


def _run(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return 0
    if not CD_PREFIX_RE.match(cmd):
        return 0
    if _has_compound_operator_after_cd(cmd):
        _emit(DENY_REASON, deny=True)
        return 0
    snippet = cmd if len(cmd) <= 80 else cmd[:80] + "..."
    _emit(
        f"cd で始まる Bash コマンドが検出されました: `{snippet}`\n"
        "次のいずれかへの置換を検討してください:\n"
        "- 絶対パスで直接コマンドを書く (例: `mkdir /a/b/c && mv /a/b/x /a/b/c/`)\n"
        "- git なら `git -C <repo>` を使う (例: `git -C /repo status`)\n"
        "- どうしても cd が必要なら `pushd` / `popd` / `dirs` でスタックを意識する\n"
        "例外: `git push origin main` のみ allowlist 文字列マッチのため `-C` 抜き必須 "
        "(詳細は project memory `feedback_git_push_allowlist.md`)。"
    )
    return 0


class AvoidCdTest(unittest.TestCase):
    """Detection matrix. Run: python3 -m unittest avoid_cd"""

    @staticmethod
    def _result(payload: dict) -> tuple[str, int]:
        stdout = StringIO()
        with redirect_stdout(stdout):
            result = _run(payload)
        return stdout.getvalue(), result

    def test_denies_leading_cd_compound_commands(self):
        for cmd in (
            "cd /x && ls",
            "cd /x; ls",
            "cd /x ;ls",
            "cd /x || true",
            "cd /x | tee f",
            "  cd /x && git push",
            "cd /x\nls",
            "cd;ls",
            "cd&&ls",
            "cd /x && grep '#foo' f",
            "cd /x#y && ls",
            'cd /x && echo "<<a"',
            "cd /x && echo '<<a'",
            "cd /x && echo $((1<<2))",
            "cd /x && ls # <<EOF",
            "cd /x <<EOF && ls\nbody\nEOF",
        ):
            output, result = self._result(
                {"tool_name": "Bash", "tool_input": {"command": cmd}}
            )
            hook_output = json.loads(output)["hookSpecificOutput"]
            self.assertEqual(result, 0, cmd)
            self.assertEqual(hook_output["permissionDecision"], "deny", cmd)
            reason = hook_output["permissionDecisionReason"]
            for phrase in ("cwd", "相対 path", "pathspec", "絶対 path", "git -C"):
                self.assertIn(phrase, reason, cmd)
            self.assertIn("pushd", reason, cmd)
            self.assertIn("popd", reason, cmd)
            self.assertIn("単独の `cd`", reason, cmd)

    def test_advises_on_standalone_leading_cd(self):
        for cmd in (
            "cd /x",
            "cd",
            "cd -",
            'cd "/x && y"',
            'cd "$(ls | head -1)"',
            "cd `ls | head -1`",
            "cd /repo\n",
            "cd \\\n  /repo",
            "cd /a \\\n /b",
            "cd ${DIR:-/tmp/a|b}",
            "cd /x <<A <<B\n1\nA\n2\nB",
            "cd /x <<EOF\nbody",
            'cd /x "unterminated',
            "cd /x\n\n",
            "\ncd /x",
            "cd /x;",
            "cd /repo  # use git log | head",
            "cd /x # note && then",
            "cd $( (cd /a; pwd) )",
            "cd /x/$((i|1))",
            'cd "$(dirname "$(readlink -f "$0")")"',
            "cd /x <<EOF\nls && true\nEOF",
        ):
            output, result = self._result(
                {"tool_name": "Bash", "tool_input": {"command": cmd}}
            )
            hook_output = json.loads(output)["hookSpecificOutput"]
            self.assertEqual(result, 0, cmd)
            self.assertEqual(hook_output["permissionDecision"], "allow", cmd)
            self.assertIn("additionalContext", hook_output, cmd)
            self.assertNotIn("permissionDecisionReason", hook_output, cmd)

    def test_ignores_nonleading_and_non_cd_commands(self):
        for cmd in ("pushd /x && ls", "popd", "ls && cd /x", "cdb --help"):
            output, result = self._result(
                {"tool_name": "Bash", "tool_input": {"command": cmd}}
            )
            self.assertEqual(result, 0, cmd)
            self.assertEqual(output, "", cmd)

    def test_fails_open_for_invalid_payloads(self):
        for payload in (
            {"tool_name": "Python", "tool_input": {"command": "cd /x && ls"}},
            {"tool_name": "Bash", "tool_input": {}},
        ):
            output, result = self._result(payload)
            self.assertEqual(result, 0)
            self.assertEqual(output, "")
        stdin = sys.stdin
        stdout = sys.stdout
        try:
            sys.stdin = StringIO("{")
            sys.stdout = StringIO()
            self.assertEqual(main(), 0)
            self.assertEqual(sys.stdout.getvalue(), "")
        finally:
            sys.stdin = stdin
            sys.stdout = stdout


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        _run(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
