#!/usr/bin/env python3
"""
Shared excludedCommands roster for the sandbox hooks.

`sandbox.excludedCommands` varies per host, so the roster is always rendered
from the live settings files rather than hardcoded. The sandbox hooks import
from here so the advice is written once and stays identical across them.
"""

from __future__ import annotations

import contextlib
import glob
import hashlib
import json
import os
import tempfile
import unittest

SYSTEM_SETTINGS = "/etc/claude-code/managed-settings.json"
SYSTEM_SETTINGS_GLOB = "/etc/claude-code/managed-settings.d/*.json"
USER_SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "sandbox_exclusion_guard"
)
CLAIM_STATE_PREFIX = "warn-"


def config_paths() -> list[str]:
    """Return the existing sandbox settings files, lowest precedence first."""
    candidates = [USER_SETTINGS]
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        candidates.extend(
            [
                os.path.join(project, ".claude", "settings.json"),
                os.path.join(project, ".claude", "settings.local.json"),
            ]
        )
    candidates.extend(sorted(glob.glob(SYSTEM_SETTINGS_GLOB)))
    candidates.append(SYSTEM_SETTINGS)
    return list(dict.fromkeys(path for path in candidates if os.path.isfile(path)))


def _sandbox_section(path: str) -> dict:
    """Return one settings file's sandbox object, empty when unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            section = json.load(f).get("sandbox")
    except (OSError, ValueError, AttributeError):
        return {}
    return section if isinstance(section, dict) else {}


def load_patterns() -> list[str]:
    """Rescan every settings file and return the union of excludedCommands.

    Deliberately uncached: drop-ins under managed-settings.d change per project
    and the files are small enough that a fresh scan costs nothing.
    """
    patterns: set[str] = set()
    for path in config_paths():
        values = _sandbox_section(path).get("excludedCommands", [])
        if isinstance(values, list):
            patterns.update(p for p in values if isinstance(p, str))
    return sorted(patterns)


def sandbox_restricts_commands() -> bool:
    """Report whether the sandbox is on and still constrains commands.

    Checked before any roster lookup: an empty excludedCommands list means
    nothing escapes the sandbox, never that the sandbox is off.
    """
    enabled = False
    unrestricted = False
    for path in config_paths():
        section = _sandbox_section(path)
        if isinstance(value := section.get("enabled"), bool):
            enabled = value
        if isinstance(value := section.get("allowUnsandboxedCommands"), bool):
            unrestricted = value
    return enabled and not unrestricted


def credential_paths() -> list[str]:
    """Return the credential paths the sandbox denies, expanded to absolute."""
    paths: set[str] = set()
    for config in config_paths():
        entries = _sandbox_section(config).get("credentials", {})
        files = entries.get("files", []) if isinstance(entries, dict) else []
        if not isinstance(files, list):
            continue
        for entry in files:
            if not isinstance(entry, dict) or entry.get("mode") != "deny":
                continue
            if isinstance(path := entry.get("path"), str) and path:
                paths.add(os.path.expanduser(path))
    return sorted(paths)


def _latch_key(payload: dict) -> str | None:
    """Return the session identity used for once-per-session latches."""
    for field in ("session_id", "transcript_path"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return f"{field}:{value}"
    return None


def claim_once(payload: dict, reason: str) -> bool:
    """Return whether this reason is unclaimed for this session, claiming it."""
    latch_key = _latch_key(payload)
    if latch_key is None:
        return True
    try:
        digest = hashlib.sha256(latch_key.encode("utf-8")).hexdigest()
        state_path = os.path.join(STATE_DIR, f"{CLAIM_STATE_PREFIX}{digest}.json")
        reasons: set[str] = set()
        try:
            with open(state_path, encoding="utf-8") as f:
                values = json.load(f).get("reasons", [])
            if not isinstance(values, list):
                raise ValueError("claim state reasons is not a list")
            reasons = {value for value in values if isinstance(value, str)}
        except (OSError, ValueError, AttributeError, TypeError):
            pass
        if reason in reasons:
            return False
        reasons.add(reason)
        os.makedirs(STATE_DIR, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{CLAIM_STATE_PREFIX}", suffix=".tmp", dir=STATE_DIR
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"reasons": sorted(reasons)}, f, ensure_ascii=False)
            os.replace(temp_path, state_path)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    except Exception:
        return True
    return True


def roster_once(payload: dict, patterns: list[str]) -> str:
    """Return the roster the first time a session asks, empty string after."""
    return roster_text(patterns) if claim_once(payload, "roster") else ""


def bare_form(pattern: str) -> str:
    """Render a pattern as the bare leading form that actually reaches the host."""
    return pattern.split("*", 1)[0].strip() or pattern


def roster_text(patterns: list[str]) -> str:
    """Render the live host-escape roster plus the direct-invocation rule."""
    if not patterns:
        return (
            "この環境の sandbox.excludedCommands は空です。 host 実行が要る作業は、"
            "ユーザーに `!` prefix での実行を依頼してください。"
        )
    listed = " / ".join(f"`{p}`" for p in patterns)
    sample = bare_form(patterns[0])
    return (
        f"この環境の sandbox.excludedCommands (設定から生成): {listed}\n"
        "これらは sandbox の外 (host 権限) で走り、 sandbox の filesystem / network "
        "制限を受けません。 照合は Bash の実行 segment 単位で、 1 segment でも一致すれば "
        "その Bash 呼び出し全体が host 実行になります。\n"
        f"一致する形 (直指定): `{sample} ...` / `cd x && {sample} ...` / "
        f"`FOO=1 {sample} ...` / `timeout 5 {sample} ...`。 直接代入と一部 wrapper は "
        "照合前に剥がされます。\n"
        f"一致しない形: `/usr/bin/{sample} ...` (path 前置) / `sudo {sample} ...` / "
        f"`env {sample} ...` `npx {sample} ...` (wrapper 経由) / quote 内の言及。 "
        "これらは sandbox に落ちるので、失敗しても sandbox の制限が原因ではありません。\n"
        "plugin 由来の CLI も、 一覧にあれば host で走ります。 "
        "「plugin だから sandbox を出られない」 は誤りです。"
    )


@contextlib.contextmanager
def _settings_fixture(system_settings: dict):
    """Point the module at a throwaway settings tree for the duration."""
    import sys
    from unittest import mock

    with tempfile.TemporaryDirectory() as tmp:
        system = os.path.join(tmp, "managed-settings.json")
        drop_in_dir = os.path.join(tmp, "managed-settings.d")
        os.makedirs(drop_in_dir)
        with open(system, "w", encoding="utf-8") as f:
            json.dump(system_settings, f)
        module = sys.modules[__name__]
        with (
            mock.patch.object(module, "SYSTEM_SETTINGS", system),
            mock.patch.object(
                module, "SYSTEM_SETTINGS_GLOB", os.path.join(drop_in_dir, "*.json")
            ),
            mock.patch.object(
                module, "USER_SETTINGS", os.path.join(tmp, "absent.json")
            ),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            yield {"system": system, "drop_in_dir": drop_in_dir}


class RosterTest(unittest.TestCase):
    """Roster rendering / bare-form derivation. Run: python3 -m unittest sandbox_exclusions"""

    PATTERNS = ["agent-browser *", "gh *", "node *codex-companion.mjs*"]

    def test_roster_lists_every_live_pattern(self):
        text = roster_text(self.PATTERNS)
        for pattern in self.PATTERNS:
            self.assertIn(f"`{pattern}`", text)

    def test_roster_states_the_direct_invocation_rule(self):
        text = roster_text(self.PATTERNS)
        for phrase in ("直指定", "segment 単位", "path 前置", "sudo", "wrapper 経由"):
            self.assertIn(phrase, text)

    def test_roster_marks_compound_and_assignment_forms_as_matching(self):
        text = roster_text(self.PATTERNS)
        matching, missing = text.split("一致しない形", 1)
        for form in ("cd x &&", "FOO=1", "timeout 5"):
            self.assertIn(form, matching)
        for form in ("/usr/bin/", "sudo ", "env ", "npx "):
            self.assertIn(form, missing)

    def test_roster_corrects_the_plugin_misconception(self):
        self.assertIn("plugin", roster_text(self.PATTERNS))

    def test_roster_handles_an_empty_list(self):
        text = roster_text([])
        self.assertIn("空です", text)
        self.assertNotIn("裸名", text)

    def test_bare_form_strips_the_glob(self):
        self.assertEqual(bare_form("gh *"), "gh")
        self.assertEqual(bare_form("claude --bg *"), "claude --bg")
        self.assertEqual(bare_form("node *codex-companion.mjs*"), "node")
        self.assertEqual(bare_form("docker"), "docker")

    def test_patterns_are_reread_on_every_call(self):
        with _settings_fixture({"sandbox": {"excludedCommands": ["git *"]}}) as paths:
            self.assertEqual(load_patterns(), ["git *"])
            with open(paths["system"], "w", encoding="utf-8") as f:
                json.dump({"sandbox": {"excludedCommands": ["dsa *"]}}, f)
            self.assertEqual(load_patterns(), ["dsa *"])

    def test_drop_ins_are_scanned_and_unioned(self):
        with _settings_fixture({"sandbox": {"excludedCommands": ["git *"]}}) as paths:
            with open(os.path.join(paths["drop_in_dir"], "a.json"), "w") as f:
                json.dump({"sandbox": {"excludedCommands": ["docker *"]}}, f)
            self.assertEqual(load_patterns(), ["docker *", "git *"])

    def test_sandbox_restricts_commands_reflects_the_managed_switch(self):
        with _settings_fixture({"sandbox": {"enabled": True}}) as paths:
            self.assertTrue(sandbox_restricts_commands())
            with open(paths["system"], "w", encoding="utf-8") as f:
                json.dump({"sandbox": {"enabled": False}}, f)
            self.assertFalse(sandbox_restricts_commands())

    def test_sandbox_disabled_when_no_file_declares_it(self):
        with _settings_fixture({"sandbox": {"excludedCommands": ["git *"]}}):
            self.assertFalse(sandbox_restricts_commands())

    def test_unsandboxed_commands_allowance_lifts_the_restriction(self):
        settings = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": True}}
        with _settings_fixture(settings):
            self.assertFalse(sandbox_restricts_commands())

    def test_an_empty_roster_is_not_read_as_a_disabled_sandbox(self):
        with _settings_fixture({"sandbox": {"enabled": True}}):
            self.assertEqual(load_patterns(), [])
            self.assertTrue(sandbox_restricts_commands())

    def test_managed_settings_outrank_a_drop_in(self):
        with _settings_fixture({"sandbox": {"enabled": True}}) as paths:
            with open(os.path.join(paths["drop_in_dir"], "a.json"), "w") as f:
                json.dump({"sandbox": {"enabled": False}}, f)
            self.assertTrue(sandbox_restricts_commands())

    def test_file_is_executable(self):
        self.assertTrue(os.access(os.path.abspath(__file__), os.X_OK))


if __name__ == "__main__":
    unittest.main()
