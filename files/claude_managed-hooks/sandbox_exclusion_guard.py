#!/usr/bin/env python3
"""
PreToolUse(Bash) hook: deny broken sandbox excluded-command invocations.

Claude Code matches sandbox.excludedCommands globs at the start of the raw
command. Path, environment/wrapper, and non-leading compound forms can miss
that anchor and silently run inside the sandbox. This hook finds an excluded
command after normalizing those forms and denies it so callers can retry with
the bare command at the leading anchor.

Exit:
  0: command matches the host-execution glob, or contains no broken invocation
  2: an excluded command would miss the leading-anchor glob

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
WRAPPERS = {
    "sudo",
    "env",
    "command",
    "nohup",
    "nice",
    "time",
    "stdbuf",
    "setsid",
    "ionice",
}
ASSIGNMENT = re.compile(r"^\w+=\S*$")
# top-level 制御演算子のみで分割。$(...)/`...` は host 化不能ゆえ segment 対象外 (F1)。
SEPARATOR = re.compile(r"&&|\|\||[;|&\n]")
COMMENT = re.compile(r"#.*$", re.MULTILINE)
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


def _segment_violation(cmd: str, patterns: list[str]) -> tuple[str, list[str]] | None:
    """Return the normalized excluded invocation and broken-form reasons."""
    scanned = HEREDOC.sub(_strip_heredoc, cmd)
    scanned = QUOTED.sub("_", scanned)
    scanned = COMMENT.sub("", scanned)
    segments = SEPARATOR.split(scanned)
    for index, segment in enumerate(segments):
        tokens = segment.strip().split()
        if not tokens:
            continue
        env_prefix = False
        wrapper_prefix = False
        while tokens and ASSIGNMENT.match(tokens[0]):
            env_prefix = True
            tokens.pop(0)
        while tokens and os.path.basename(tokens[0]) in WRAPPERS:
            wrapper_prefix = True
            tokens.pop(0)
            # wrapper の env 代入 / bare option を読み飛ばす (値付き option は既知ギャップ)。
            while tokens and (ASSIGNMENT.match(tokens[0]) or tokens[0].startswith("-")):
                if ASSIGNMENT.match(tokens[0]):
                    env_prefix = True
                tokens.pop(0)
        if not tokens:
            continue
        program = tokens[0]
        basename = os.path.basename(program)
        normalized = " ".join([basename, *tokens[1:]])
        if any(_glob_match(normalized, pattern) for pattern in patterns):
            reasons = []
            if "/" in program:
                reasons.append("path prefix")
            if env_prefix:
                reasons.append("environment prefix")
            if wrapper_prefix:
                reasons.append("wrapper prefix")
            if index > 0:
                reasons.append("non-leading compound segment")
            if reasons:
                return normalized, reasons
    return None


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
    raw_lstripped = cmd.lstrip()
    if any(_glob_match(raw_lstripped, pattern) for pattern in patterns):
        return 0
    violation = _segment_violation(cmd, patterns)
    if not violation:
        return 0
    normalized, reasons = violation
    sys.stderr.write(
        "sandbox-exclusion-guard: denied excluded command "
        f"`{normalized}` because its {' / '.join(reasons)} prevents the "
        "leading-anchor excludedCommands glob from matching, so it would "
        "silently run inside the sandbox and may break.\n\n"
        "Retry: invoke the excluded command by its bare name without a path, "
        "environment assignment, or wrapper, and put it first in the compound "
        "command or run it as a standalone Bash call. This guarantees the "
        "leading-anchor glob matches and the command runs on the host.\n"
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
    POSITIVE = (
        "cd app && git push",
        "set -e; dsa foo",
        "/usr/bin/git push",
        "tools/dsa_launcher restart db",
        "FOO=1 git push",
        "sudo git push",
        "env dsa_launcher restart db",
        "echo hi && cargo test foo",
        "/usr/bin/node /path/codex-companion.mjs --x",
        "env -i git push",
    )
    NEGATIVE = (
        "git push",
        "dsa_launcher restart db",
        "cargo test foo",
        "git push && echo done",
        "git log | head",
        "git",
        "cargo build",
        "node app.js",
        "which git",
        "man dsa",
        "type cargo",
        'echo "cd x && git push"',
        "# git push",
        "grep 'dsa foo' README.md",
        "VERSION=$(git describe --tags)",
        "X=$(dsa foo)",
    )

    @staticmethod
    def _result(cmd: str, patterns: list[str]) -> int:
        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}}
        return _run(payload, patterns)

    def test_denies_broken_excluded_invocations(self):
        for cmd in self.POSITIVE:
            self.assertEqual(self._result(cmd, self.PATTERNS), 2, cmd)

    def test_allows_anchor_matches_and_boundaries(self):
        for cmd in self.NEGATIVE:
            self.assertEqual(self._result(cmd, self.PATTERNS), 0, cmd)

    def test_empty_patterns_allow_everything(self):
        self.assertEqual(self._result("cd app && git push", []), 0)

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
