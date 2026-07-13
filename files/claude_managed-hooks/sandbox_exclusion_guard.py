#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: classify sandbox excluded-command invocations.

Claude Code recognizes bare shell command words for sandbox.excludedCommands.
Path-prefixed and sudo invocations are denied when they would fail inside the
sandbox; ambiguous env/compound/sudo-option forms receive an advisory.

Exit:
  0: pass, or warn with hookSpecificOutput.additionalContext
  2: a path-prefixed or bare-sudo excluded command is blocked

Always exits 0 on any unexpected error (fail-open).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import unittest

SYSTEM_SETTINGS = "/etc/claude-code/managed-settings.json"
SYSTEM_SETTINGS_GLOB = "/etc/claude-code/managed-settings.d/*.json"
USER_SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "sandbox_exclusion_guard"
)
CACHE_PATH = os.path.join(STATE_DIR, "cache.json")
ASSIGNMENT = re.compile(r"^\w+=\S*$")
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


def _config_paths() -> list[str]:
    """Return the existing excludedCommands config files."""
    candidates = [SYSTEM_SETTINGS, *glob.glob(SYSTEM_SETTINGS_GLOB), USER_SETTINGS]
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        candidates.extend(
            [
                os.path.join(project, ".claude", "settings.json"),
                os.path.join(project, ".claude", "settings.local.json"),
            ]
        )
    return sorted({path for path in candidates if os.path.isfile(path)})


def _cache_key(paths: list[str]) -> list[list[str | int]]:
    """Build a sorted path/mtime_ns key, skipping files that cannot be statted."""
    key: list[list[str | int]] = []
    for path in paths:
        try:
            key.append([path, os.stat(path).st_mtime_ns])
        except OSError:
            pass
    return sorted(key)


def _load_patterns() -> list[str]:
    """Load the union of excludedCommands, reusing an mtime-keyed cache."""
    paths = _config_paths()
    key = _cache_key(paths)
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("key") == key and isinstance(cached.get("patterns"), list):
            return [p for p in cached["patterns"] if isinstance(p, str)]
    except (OSError, ValueError, AttributeError):
        pass
    patterns = set()
    for entry in key:
        path = str(entry[0])
        try:
            with open(path, encoding="utf-8") as f:
                values = json.load(f).get("sandbox", {}).get("excludedCommands", [])
            patterns.update(p for p in values if isinstance(p, str))
        except (OSError, ValueError, AttributeError):
            pass
    result = sorted(patterns)
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"key": key, "patterns": result}, f)
    except OSError:
        pass
    return result


def _glob_match(value: str, pattern: str) -> bool:
    """Match a Claude excludedCommands star glob with full-string anchors."""
    translated = re.escape(pattern).replace(r"\*", ".*")
    return re.fullmatch(translated, value, re.DOTALL) is not None


def _classify(cmd: str, patterns: list[str]) -> tuple[str, str, str]:
    """Return block/warn/pass, the excluded invocation, and its reason."""
    scanned = HEREDOC.sub(_strip_heredoc, cmd)
    scanned = QUOTED.sub("_", scanned)
    scanned = SUBST.sub("_", scanned)
    scanned = COMMENT.sub("", scanned)
    segments = [s for s in SEPARATOR.split(scanned) if s.strip()]
    warning: tuple[str, str, str] | None = None
    for index, segment in enumerate(segments):
        tokens = segment.strip().split()
        if not tokens:
            continue
        had_env = False
        while tokens and ASSIGNMENT.match(tokens[0]):
            had_env = True
            tokens.pop(0)
        if not tokens:
            continue
        program = tokens[0]
        basename = os.path.basename(program)
        if basename == "sudo":
            for position, candidate in enumerate(tokens[1:], start=1):
                if "/" in candidate or candidate.startswith("-"):
                    continue
                normalized = " ".join(tokens[position:])
                if not any(_glob_match(normalized, pattern) for pattern in patterns):
                    continue
                if position == 1:
                    return "block", normalized, "bare sudo"
                if warning is None:
                    warning = "warn", normalized, "sudo with options"
                break
            continue
        normalized = " ".join([basename, *tokens[1:]])
        if not any(_glob_match(normalized, pattern) for pattern in patterns):
            # Non-sudo wrappers are intentionally not traversed; path forms behind them are a known gap.
            continue
        if "/" in program:
            return "block", normalized, "path prefix"
        if had_env and warning is None:
            warning = "warn", normalized, "environment prefix"
        elif index > 0 and warning is None:
            warning = "warn", normalized, "non-leading compound segment"
    return warning or ("pass", "", "")


def _emit(msg: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(payload: object, patterns: list[str] | None = None) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str):
        return 0
    patterns = _load_patterns() if patterns is None else patterns
    decision, normalized, reason = _classify(cmd, patterns)
    if decision == "pass":
        return 0
    if decision == "warn":
        message = (
            f"除外コマンド `{normalized}` のこの呼び出し方 ({reason}) は sandbox 内実行に"
            "なる可能性があります。除外コマンドは path/env/wrapper を付けず、裸名で先頭に"
            "置くと確実に host 実行されます。"
        )
        if reason == "sudo with options":
            message += " sudo は sandbox 内で権限昇格できず失敗します。"
        _emit(message)
        return 0
    if reason == "bare sudo":
        detail = "sudo は sandbox 内で権限昇格できず失敗します"
    else:
        detail = "path 前置では除外対象にならず sandbox 内実行に落ちるため失敗します"
    sys.stderr.write(
        f"sandbox-exclusion-guard: excluded command `{normalized}` を block しました。"
        f"{detail}。\n\n"
        "Retry: path や sudo を付けず、除外コマンドを裸名で command の先頭に置いて"
        "呼び出してください。これにより確実に host 実行されます。\n"
    )
    return 2


def main() -> int:
    try:
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
        "VAR=x git push && /usr/bin/git push",
    )
    WARN = (
        "VAR=val git push",
        "FOO=1 BAR=2 dsa foo",
        "cd app && git push",
        "echo hi ; cargo test x",
        "sudo -u deploy git push",
    )
    PASS = (
        "git push",
        "dsa_launcher restart db",
        "cargo test foo",
        "git push && echo done",
        "git log | head",
        "timeout 5 git push",
        "nice -n 10 cargo test x",
        "env -i git push",
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

    @staticmethod
    def _result(cmd: str, patterns: list[str]) -> tuple[int, str, str]:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}}
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = _run(payload, patterns)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_blocks_path_and_bare_sudo_invocations(self):
        for cmd in self.BLOCK:
            result, stdout, stderr = self._result(cmd, self.PATTERNS)
            self.assertEqual(result, 2, cmd)
            self.assertEqual(stdout, "", cmd)
            self.assertIn("excluded command", stderr, cmd)
            self.assertIn("裸名", stderr, cmd)

    def test_warns_without_blocking_ambiguous_invocations(self):
        for cmd in self.WARN:
            result, stdout, stderr = self._result(cmd, self.PATTERNS)
            self.assertEqual(result, 0, cmd)
            self.assertEqual(stderr, "", cmd)
            output = json.loads(stdout)["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "PreToolUse", cmd)
            self.assertEqual(output["permissionDecision"], "allow", cmd)
            self.assertIn(
                "sandbox 内実行になる可能性", output["additionalContext"], cmd
            )
            if cmd.startswith("sudo"):
                self.assertIn("権限昇格できず失敗", output["additionalContext"], cmd)

    def test_passes_host_and_nonmatching_invocations_silently(self):
        for cmd in self.PASS:
            result, stdout, stderr = self._result(cmd, self.PATTERNS)
            self.assertEqual(result, 0, cmd)
            self.assertEqual(stdout, "", cmd)
            self.assertEqual(stderr, "", cmd)

    def test_empty_patterns_allow_everything(self):
        self.assertEqual(self._result("cd app && git push", []), (0, "", ""))

    def test_mtime_cache_recomputes(self):
        import tempfile
        import time
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "settings.json")
            cache = os.path.join(tmp, "state", "cache.json")
            with open(config, "w", encoding="utf-8") as f:
                json.dump({"sandbox": {"excludedCommands": ["git *"]}}, f)
            patches = (
                mock.patch.object(sys.modules[__name__], "SYSTEM_SETTINGS", config),
                mock.patch.object(
                    sys.modules[__name__],
                    "SYSTEM_SETTINGS_GLOB",
                    os.path.join(tmp, "none", "*.json"),
                ),
                mock.patch.object(
                    sys.modules[__name__],
                    "USER_SETTINGS",
                    os.path.join(tmp, "missing.json"),
                ),
                mock.patch.object(sys.modules[__name__], "CACHE_PATH", cache),
                mock.patch.dict(os.environ, {}, clear=True),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                self.assertEqual(_load_patterns(), ["git *"])
                old_mtime = os.stat(config).st_mtime_ns
                with open(config, "w", encoding="utf-8") as f:
                    json.dump({"sandbox": {"excludedCommands": ["dsa *"]}}, f)
                if os.stat(config).st_mtime_ns == old_mtime:
                    time.sleep(0.002)
                    os.utime(config, None)
                self.assertEqual(_load_patterns(), ["dsa *"])

    def test_file_is_executable(self):
        self.assertTrue(os.access(os.path.abspath(__file__), os.X_OK))


if __name__ == "__main__":
    sys.exit(main())
