#!/usr/bin/env python3
"""Deny shared-tree write-capable codex tasks from a PreToolUse Bash hook.

この hook は token 列の走査であり shell interpreter ではない。literal な先頭
``cd <path>`` は追跡するが、``pushd`` / ``if cd ...; then`` / ``cd -P`` /
変数代入を前置した ``cd`` のように cwd を変える別構文と、``$VAR`` の展開は
検出しない。gate の目的は共有ツリーへの誤った書き込み委譲を防ぐことであり、
迂回の意図を持つ利用者を止めることではない。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


GIT_TIMEOUT_SECONDS = 2
CODEX_SCRIPT = "codex-companion.mjs"
WRITE_FLAGS = {"--write", "--resume-last", "--resume"}
SHELL_PUNCTUATION = frozenset(";&|()")
ESCAPE_HATCH = "CODEX_SHARED_TREE_OK=1"

# The reason is intentionally verbose so corrective actions survive model trimming.
DENY_REASON = (
    "codex-worktree-gate: 共有 checkout では書き込みを伴う codex task を起動できません。"
    "codex が実際に走る cwd を git で実測した結果、linked worktree ではありません。"
    "発注側が git worktree add で worktree を作り、その path を codex の --cwd に渡してください。"
    'Agent の isolation: "worktree" は使わないでください（走行中の worktree が自動掃除される実例あり）。'
    "read-only レビューなら --write を外せば通ります。"
    "意図的に共有ツリーへ書く場合は、codex を起動するセグメントの先頭に CODEX_SHARED_TREE_OK=1 を付けてください。"
    "この hook 自身は file を変更しません。"
)
ESCAPE_CONTEXT = (
    "共有ツリーへの codex 書き込みを明示許可で通過。"
    "並行セッションの変更が混在する可能性がある。"
)


def _emit(output: dict[str, str]) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    **output,
                }
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def _fail_open(reason: str) -> None:
    sys.stderr.write(
        f"codex-worktree-gate: {reason}; allowing because git context was not verified.\n"
    )


def _shell_tokens(command: str) -> list[str]:
    normalized_command = command.replace("\r\n", ";").replace("\n", ";")
    lexer = shlex.shlex(normalized_command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        _fail_open("command could not be tokenized")
        return []


# bash -c/eval recursion is out of scope; only this shell level is tokenized.


def _is_separator(token: str) -> bool:
    return bool(token) and all(char in SHELL_PUNCTUATION for char in token)


def _is_codex_script(token: str) -> bool:
    return token == CODEX_SCRIPT or token.replace("\\", "/").endswith(
        f"/{CODEX_SCRIPT}"
    )


def _argument_words(tokens: list[str]) -> list[str]:
    return [word for token in tokens for word in token.split()]


def _find_codex_write_segment(
    command: str,
    payload_cwd: str | None = None,
) -> list[tuple[list[str], int, str | None]]:
    segment: list[str] = []
    matches: list[tuple[list[str], int, str | None]] = []
    effective_cwd = os.path.abspath(payload_cwd) if payload_cwd else None
    group_cwd: list[str | None] = []
    for token in [*_shell_tokens(command), "&&"]:
        if _is_separator(token):
            if token == "(":
                group_cwd.append(effective_cwd)
                segment = []
                continue
            for index, candidate in enumerate(segment):
                if not _is_codex_script(candidate):
                    continue
                words = _argument_words(segment[index + 1 :])
                has_task = "task" in words
                has_write_flag = any(
                    argument.split("=", 1)[0] in WRITE_FLAGS for argument in words
                )
                if has_task and has_write_flag:
                    matches.append((segment, index, effective_cwd))
            if segment and segment[0] == "cd" and len(segment) > 1:
                cd_target = segment[1]
                effective_cwd = (
                    os.path.abspath(os.path.join(effective_cwd, cd_target))
                    if effective_cwd is not None
                    else cd_target
                )
            if token == ")":
                effective_cwd = group_cwd.pop() if group_cwd else None
            segment = []
        else:
            segment.append(token)
    return matches


def _resolve_command_cwd(
    segment: list[str],
    script_index: int,
    payload_cwd: str,
    cd_path: str | None = None,
) -> str | None:
    effective_cwd = cd_path if cd_path is not None else payload_cwd
    arguments = segment[script_index + 1 :]
    for index, argument in enumerate(arguments):
        if argument in {"--cwd", "-C"}:
            if index + 1 >= len(arguments) or not arguments[index + 1]:
                _fail_open("codex cwd option has no path")
                return None
            raw_path = arguments[index + 1]
        elif argument.startswith("--cwd="):
            raw_path = argument.split("=", 1)[1]
            if not raw_path:
                _fail_open("codex cwd option has no path")
                return None
        else:
            continue
        return os.path.abspath(os.path.join(effective_cwd, raw_path))
    return effective_cwd


def _is_linked_worktree(git_dir: str, common_dir: str) -> bool:
    return os.path.abspath(git_dir) != os.path.abspath(common_dir)


def _git_dir(cwd: str) -> tuple[str, str] | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        _fail_open("git rev-parse timed out")
        return None
    except Exception as exc:
        _fail_open(f"git rev-parse could not run ({type(exc).__name__})")
        return None
    if result.returncode != 0:
        detail = result.stderr.strip() if isinstance(result.stderr, str) else ""
        _fail_open(
            f"git rev-parse exited with status {result.returncode}"
            + (f": {detail}" if detail else "")
        )
        return None
    lines = result.stdout.splitlines() if isinstance(result.stdout, str) else []
    if len(lines) < 2 or not lines[0].strip() or not lines[1].strip():
        _fail_open("git rev-parse returned incomplete git directories")
        return None
    git_dir = os.path.abspath(lines[0].strip())
    common_dir = os.path.abspath(os.path.join(cwd, lines[1].strip()))
    return git_dir, common_dir


def _gate(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return
    # agent_id でも codex-rescue subagent の Bash から起動されるため判定を省略しない。
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command")
    if not isinstance(command, str):
        return
    cwd = payload.get("cwd")
    payload_cwd = cwd if isinstance(cwd, str) and cwd else None
    matches = _find_codex_write_segment(command, payload_cwd)
    if not matches:
        return
    needs_cwd = any(segment[0] != ESCAPE_HATCH for segment, _, _ in matches)
    if payload_cwd is None and needs_cwd:
        _fail_open("payload cwd is missing")
        return
    escaped = False
    for segment, script_index, effective_cwd in matches:
        if segment and segment[0] == ESCAPE_HATCH:
            escaped = True
            continue
        effective_cwd = _resolve_command_cwd(
            segment, script_index, payload_cwd or "", effective_cwd
        )
        if effective_cwd is None:
            continue
        git_dirs = _git_dir(effective_cwd)
        if git_dirs is None or _is_linked_worktree(*git_dirs):
            continue
        _emit(
            {
                "permissionDecision": "deny",
                "permissionDecisionReason": DENY_REASON,
            }
        )
        return
    if escaped:
        _emit({"additionalContext": ESCAPE_CONTEXT})


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception as exc:
        _fail_open(f"hook payload could not be parsed ({type(exc).__name__})")
        return 0
    try:
        _gate(payload)
    except Exception as exc:
        _fail_open(f"unexpected gate error ({type(exc).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def _git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(["init", "-q"], cwd=path)
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(["add", "tracked.txt"], cwd=path)
    _git(
        [
            "-c",
            "user.name=Codex Gate Test",
            "-c",
            "user.email=codex-gate@example.invalid",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=path,
    )


class GitFixture:
    """Real git primary and linked worktrees shared by the whole suite."""

    def __init__(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.primary = root / "primary"
        _init_repo(self.primary)
        self.linked = root / "linked"
        _git(["worktree", "add", "-q", str(self.linked), "HEAD"], cwd=self.primary)
        self.subdir = self.linked / "nested"
        self.subdir.mkdir()

    def close(self) -> None:
        self.tempdir.cleanup()


def _invoke(payload: object | str) -> tuple[int, dict | None, str]:
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(sys, "stdin", stdin),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = main()
    text = stdout.getvalue().strip()
    return exit_code, json.loads(text) if text else None, stderr.getvalue()


class CodexWorktreeGateTest(unittest.TestCase):
    """Order document claims are observed at the hook boundary."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.git = GitFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.git.close()

    @staticmethod
    def _payload(command: str, cwd: Path | None = None, **extra: object) -> dict:
        tool_input: dict[str, object] = {"command": command}
        payload = {"tool_name": "Bash", "tool_input": tool_input, **extra}
        if cwd is not None:
            payload["cwd"] = str(cwd)
        return payload

    def _allow(self, payload: dict) -> tuple[dict | None, str]:
        exit_code, output, stderr = _invoke(payload)
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        return output, stderr

    def _deny(self, payload: dict) -> str:
        exit_code, output, stderr = _invoke(payload)
        self.assertEqual(exit_code, 0)
        if output is None:
            self.fail("expected a hook output for a denied command")
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(stderr, "")
        return output["hookSpecificOutput"]["permissionDecisionReason"]

    def test_primary_task_write_denies_with_recovery_actions(self):
        reason = self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self.assertIn("git worktree add", reason)
        self.assertIn("--write を外せば", reason)
        self.assertIn("CODEX_SHARED_TREE_OK=1", reason)
        self.assertIn("hook 自身は file を変更しません", reason)

    def test_linked_worktree_task_write_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )

    def test_linked_worktree_subdirectory_task_write_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.subdir,
            )
        )

    def test_primary_read_only_task_allows(self):
        self._allow(
            self._payload("node /opt/codex-companion.mjs task", self.git.primary)
        )

    def test_primary_directory_named_worktrees_still_denies(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "worktrees" / "proj"
            _init_repo(repo)
            self._deny(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    repo,
                )
            )

    def test_git_dir_passes_timeout_to_git(self):
        calls = []

        def recorder(*args, **kwargs):
            calls.append(kwargs)
            return subprocess.CompletedProcess(
                args,
                0,
                "/tmp/repo/.git\n/tmp/repo/.git\n",
                "",
            )

        with mock.patch.object(subprocess, "run", side_effect=recorder):
            self.assertEqual(
                _git_dir("/tmp/repo"),
                ("/tmp/repo/.git", "/tmp/repo/.git"),
            )
        self.assertEqual(calls[0]["timeout"], GIT_TIMEOUT_SECONDS)

    def test_primary_resume_last_denies_without_write_flag(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --resume-last",
                self.git.primary,
            )
        )

    def test_primary_resume_denies_without_write_flag(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --resume",
                self.git.primary,
            )
        )

    def test_explicit_shared_tree_token_allows_with_context(self):
        exit_code, output, stderr = _invoke(
            self._payload(
                "CODEX_SHARED_TREE_OK=1 node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        if output is None:
            self.fail("expected escape-hatch context")
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("共有ツリーへの codex 書き込みを明示許可で通過", context)

    def test_newlines_are_segment_boundaries_and_escape_is_scoped(self):
        for separator in ("\n", "\r\n"):
            with self.subTest(separator=repr(separator)):
                self._deny(
                    self._payload(
                        "CODEX_SHARED_TREE_OK=1 node /opt/codex-companion.mjs task --write"
                        f"{separator}node /opt/codex-companion.mjs task --write",
                        self.git.primary,
                    )
                )
                self._allow(
                    self._payload(
                        "node /opt/codex-companion.mjs task --write"
                        f"{separator}node /opt/codex-companion.mjs task --write",
                        self.git.linked,
                    )
                )

    def test_newline_cd_segments_update_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.linked}\ncd {self.git.primary}\n"
                "node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked}\nnode /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_shared_tree_token_after_codex_args_does_not_bypass(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write --env CODEX_SHARED_TREE_OK=1",
                self.git.primary,
            )
        )

    def test_review_with_write_flag_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs review --write",
                self.git.primary,
            )
        )

    def test_segment_boundaries_prevent_cross_command_match(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --dry-run && echo --write",
                self.git.primary,
            )
        )
        self._allow(
            self._payload(
                "echo codex-companion.mjs task ; node /opt/other.mjs --write",
                self.git.primary,
            )
        )

    def test_all_write_capable_segments_are_evaluated(self):
        self._deny(
            self._payload(
                f"node /opt/codex-companion.mjs task --cwd {self.git.linked} --write "
                "&& node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
        self._allow(
            self._payload(
                f"node /opt/codex-companion.mjs task --cwd {self.git.linked} --write "
                "&& node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )

    def test_escape_hatch_is_scoped_to_its_segment(self):
        self._deny(
            self._payload(
                "CODEX_SHARED_TREE_OK=1 node /opt/codex-companion.mjs task --write "
                "&& node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_backup_script_name_does_not_match(self):
        self._allow(
            self._payload(
                "node /opt/backup-codex-companion.mjs.bak task --write",
                self.git.primary,
            )
        )

    def test_quoted_write_flags_are_detected(self):
        self._deny(
            self._payload(
                'node /opt/codex-companion.mjs task "--write --background prompt"',
                self.git.primary,
            )
        )

    def test_command_cwd_options_use_effective_cwd(self):
        for option in (
            f"--cwd {self.git.primary}",
            f"--cwd={self.git.primary}",
            f"-C {self.git.primary}",
        ):
            self._deny(
                self._payload(
                    f"node /opt/codex-companion.mjs {option} task --write",
                    self.git.linked,
                )
            )
        self._allow(
            self._payload(
                f"node /opt/codex-companion.mjs --cwd {self.git.linked} task --write",
                self.git.primary,
            )
        )

    def test_relative_command_cwd_uses_payload_base(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs --cwd ../primary task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs --cwd ../linked task --write",
                self.git.primary,
            )
        )

    def test_command_cwd_preserves_spaces_in_raw_tokens(self):
        self.assertEqual(
            _resolve_command_cwd(
                [
                    "node",
                    "/opt/codex-companion.mjs",
                    "--cwd",
                    "dir with space",
                    "task",
                    "--write",
                ],
                1,
                "/payload",
            ),
            "/payload/dir with space",
        )

    def test_parenthesized_segments_are_detected(self):
        self._deny(
            self._payload(
                "(node /opt/codex-companion.mjs task --write)",
                self.git.primary,
            )
        )
        self._deny(
            self._payload(
                f"(cd {self.git.primary} && node /opt/codex-companion.mjs task --write)",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"(cd {self.git.linked} && node /opt/codex-companion.mjs task --write)",
                self.git.primary,
            )
        )

    def test_subshell_inherits_outer_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && (node /opt/codex-companion.mjs task --write)",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked} && (node /opt/codex-companion.mjs task --write)",
                self.git.primary,
            )
        )

    def test_subshell_cd_does_not_leak_to_outer_segment(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && (cd {self.git.linked} && "
                "node /opt/codex-companion.mjs task --write) && "
                "node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )

    def test_cd_prefix_sets_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && node /opt/codex-companion.mjs task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked} && node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )

    def test_relative_command_cwd_uses_cd_effective_cwd(self):
        self._deny(
            self._payload(
                f"cd {self.git.primary} && node /opt/codex-companion.mjs --cwd . "
                "task --write",
                self.git.linked,
            )
        )
        self._allow(
            self._payload(
                f"cd {self.git.linked} && node /opt/codex-companion.mjs --cwd . "
                "task --write",
                self.git.primary,
            )
        )

    def test_quoted_shell_operator_is_not_a_separator(self):
        self._deny(
            self._payload(
                'node /opt/codex-companion.mjs task "--write &"',
                self.git.primary,
            )
        )

    def test_unrelated_bash_allows(self):
        self._allow(self._payload("printf 'hello'", self.git.primary))

    def test_non_task_codex_subcommand_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs status --json",
                self.git.primary,
            )
        )

    def test_non_repo_cwd_fails_open_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as tempdir:
            _, stderr = self._allow(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    Path(tempdir),
                )
            )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("git", stderr.lower())
        self.assertIn("exited with status", stderr)

    def test_missing_cwd_fails_open_with_diagnostic(self):
        _, stderr = self._allow(
            self._payload("node /opt/codex-companion.mjs task --write")
        )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("cwd", stderr.lower())

    def test_missing_git_executable_fails_open_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as empty_path:
            with mock.patch.dict(os.environ, {"PATH": empty_path}, clear=False):
                _, stderr = self._allow(
                    self._payload(
                        "node /opt/codex-companion.mjs task --write",
                        self.git.primary,
                    )
                )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("git", stderr.lower())
        self.assertIn("could not run", stderr)

    def test_git_timeout_fails_open_with_diagnostic(self):
        timeout = subprocess.TimeoutExpired(["git", "rev-parse"], 0.1)
        with mock.patch.object(subprocess, "run", side_effect=timeout):
            _, stderr = self._allow(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    self.git.primary,
                )
            )
        self.assertIn("codex-worktree-gate", stderr)
        self.assertIn("timed out", stderr.lower())

    def test_tokenize_failure_fails_open_with_diagnostic(self):
        exit_code, output, stderr = _invoke(
            self._payload(
                "node /opt/codex-companion.mjs task --write $'unterminated",
                self.git.primary,
            )
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        self.assertIn("could not be tokenized", stderr)

    def test_invalid_json_fails_open_with_diagnostic(self):
        exit_code, output, stderr = _invoke("{")
        self.assertEqual(exit_code, 0)
        self.assertIsNone(output)
        self.assertIn("could not be parsed", stderr)

    def test_file_is_executable(self):
        self.assertTrue(os.access(os.path.abspath(__file__), os.X_OK))

    def test_subprocess_entrypoint_denies(self):
        process = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            input=json.dumps(
                self._payload(
                    "node /opt/codex-companion.mjs task --write",
                    self.git.primary,
                )
            ),
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(process.returncode, 0)
        output = json.loads(process.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(process.stderr, "")

    def test_agent_id_does_not_bypass_primary_tree_deny(self):
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
                agent_id="agent-123",
            )
        )

    def test_non_bash_tool_allows(self):
        self._allow(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
                tool_name="Read",
            )
        )
        self._deny(
            self._payload(
                "node /opt/codex-companion.mjs task --write",
                self.git.primary,
            )
        )
