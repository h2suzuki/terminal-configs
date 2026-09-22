"""Exercise the deployed settings helper without changing the operator's home."""

import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "files/setup_agy_permissions"
GRANT = "mcp(agent-coord_agent_coord/*)"


class AgyPermissionsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "user settings/settings.json"

    def write(self, text):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text)

    def run_helper(self, expected=0):
        result = subprocess.run(
            [sys.executable, str(HELPER), "--settings", str(self.path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_new_settings_scoped_grant_and_private_mode(self):
        self.run_helper()
        self.assertEqual(
            json.loads(self.path.read_text()), {"permissions": {"allow": [GRANT]}}
        )
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_preserves_existing_settings_and_idempotent_bytes(self):
        existing = {
            "colorScheme": "dark",
            "trustedWorkspaces": ["/work"],
            "toolPermission": "request-review",
            "permissions": {
                "allow": ["command(git)"],
                "deny": ["command(rm)"],
                "ask": ["mcp(other/*)"],
            },
        }
        self.write(json.dumps(existing))
        self.path.chmod(0o640)
        self.run_helper()
        existing["permissions"]["allow"].append(GRANT)
        self.assertEqual(json.loads(self.path.read_text()), existing)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        first = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.run_helper()
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), first)

    def test_explicit_ask_and_deny_preserved_and_warned(self):
        for kind, rule in (
            ("ask", "mcp(*)"),
            ("deny", "mcp(agent-coord_agent_coord/send)"),
        ):
            with self.subTest(kind=kind):
                self.write(json.dumps({"permissions": {kind: [rule]}}))
                result = self.run_helper()
                self.assertIn(f"existing {kind}", result.stderr)
                permissions = json.loads(self.path.read_text())["permissions"]
                self.assertEqual(permissions[kind], [rule])
                self.assertEqual(permissions["allow"], [GRANT])

    def test_invalid_settings_never_overwritten(self):
        for text in (
            "{",
            "[]",
            '{"permissions":null}',
            '{"permissions":{"allow":"bad"}}',
            '{"permissions":{"deny":[1]}}',
        ):
            with self.subTest(text=text):
                self.write(text)
                self.run_helper(expected=1)
                self.assertEqual(self.path.read_text(), text)

    def test_symlink_not_replaced_or_followed(self):
        target = self.path.parent.parent / "external.json"
        target.write_text("{}")
        self.path.parent.mkdir()
        self.path.symlink_to(target)
        self.run_helper(expected=1)
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_text(), "{}")

    def test_atomic_replace_failure_preserves_original_and_cleans_temp(self):
        self.write("{}")
        configure = runpy.run_path(str(HELPER))["configure"]
        with (
            patch("os.replace", side_effect=OSError("fixture")),
            self.assertRaises(OSError),
        ):
            configure(self.path)
        self.assertEqual(self.path.read_text(), "{}")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_setup_and_both_installers_wire_executable(self):
        setup = (ROOT / "files/setup_user_environment").read_text()
        self.assertIn("run setup_agy_permissions\n", setup)
        self.assertLess(
            setup.index("run setup_agy_permissions\n"),
            setup.index("run install_claude_extensions\n"),
        )
        for installer in ("debian12.sh", "ubuntu2404-wsl.sh"):
            self.assertIn(
                "copy setup_agy_permissions /usr/local/bin/setup_agy_permissions -m 0755",
                (ROOT / installer).read_text(),
            )

    def test_installed_executable_runs_without_python_wrapper(self):
        installed = self.path.parent.parent / "setup_agy_permissions"
        subprocess.run(
            ["install", "-m", "0755", str(HELPER), str(installed)], check=True
        )
        subprocess.run(
            [str(installed), "--settings", str(self.path)],
            check=True,
            capture_output=True,
        )
        self.assertEqual(
            json.loads(self.path.read_text())["permissions"]["allow"], [GRANT]
        )

    def test_concurrent_settings_change_not_overwritten(self):
        self.write("{}")
        configure = runpy.run_path(str(HELPER))["configure"]
        with patch(
            "os.fsync", side_effect=lambda _: self.path.write_text('{"changed":true}')
        ), self.assertRaisesRegex(ValueError, "changed during setup"):
            configure(self.path)
        self.assertEqual(self.path.read_text(), '{"changed":true}')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
