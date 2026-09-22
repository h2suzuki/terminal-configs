"""Exercise the deployed settings helper without changing the operator's home."""

import ast
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

    def run_helper(self, expected=0, *flags):
        result = subprocess.run(
            [sys.executable, str(HELPER), "--settings", str(self.path), *flags],
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
        command = "run setup_agy_permissions --sandbox-auto --shared-policy /etc/antigravity-cli/skel/permissions.json\n"
        self.assertIn(command, setup)
        self.assertLess(
            setup.index(command),
            setup.index("run install_claude_extensions\n"),
        )
        for installer in ("debian12.sh", "ubuntu2404-wsl.sh"):
            self.assertIn(
                "copy setup_agy_permissions /usr/local/bin/setup_agy_permissions -m 0755",
                (ROOT / installer).read_text(),
            )
            self.assertIn(
                "copy antigravity_user-permissions.json /etc/antigravity-cli/skel/permissions.json -m 0644",
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
        with (
            patch(
                "os.fsync",
                side_effect=lambda _: self.path.write_text('{"changed":true}'),
            ),
            self.assertRaisesRegex(ValueError, "changed during setup"),
        ):
            configure(self.path)
        self.assertEqual(self.path.read_text(), '{"changed":true}')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_sandbox_auto_updates_preset_even_when_grant_already_exists(self):
        permissions = {
            "allow": [GRANT],
            "ask": ["command(sudo)"],
            "deny": ["read_file(/secret)"],
        }
        self.write(
            json.dumps(
                {
                    "permissions": permissions,
                    "toolPermission": "request-review",
                    "enableTerminalSandbox": False,
                    "colorScheme": "dark",
                }
            )
        )
        self.run_helper(0, "--sandbox-auto")
        data = json.loads(self.path.read_text())
        self.assertEqual(data["permissions"], permissions)
        self.assertEqual(data["toolPermission"], "proceed-in-sandbox")
        self.assertIs(data["enableTerminalSandbox"], True)
        self.assertEqual(data["colorScheme"], "dark")
        first = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.run_helper(0, "--sandbox-auto")
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), first)

    def test_shared_policy_matches_reviewed_codex_and_claude_scope(self):
        policy = json.loads(
            (ROOT / "files/antigravity_user-permissions.json").read_text()
        )
        tree = ast.parse((ROOT / "files/codex_sandbox_exclusions.rules").read_text())
        prefixes = []
        for stmt in tree.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                args = {k.arg: ast.literal_eval(k.value) for k in stmt.value.keywords}
                self.assertEqual(args["decision"], "allow")
                prefixes.append("command(" + " ".join(args["pattern"]) + ")")
        self.assertEqual(
            set(prefixes), {r for r in policy["allow"] if r.startswith("command(")}
        )
        claude = json.loads((ROOT / "files/claude_managed-settings.json").read_text())[
            "sandbox"
        ]
        self.assertEqual(
            {"write_file(" + p + ")" for p in claude["filesystem"]["allowWrite"]},
            {r for r in policy["allow"] if r.startswith("write_file(")},
        )
        denied = [
            r["path"] for r in claude["credentials"]["files"] if r["mode"] == "deny"
        ] + claude["filesystem"]["denyRead"]
        self.assertEqual({"read_file(" + p + ")" for p in denied}, set(policy["deny"]))
        self.assertIn(
            "network_access = true", (ROOT / "files/codex_config.toml").read_text()
        )
        self.assertIn("read_url(*)", policy["allow"])
        self.assertNotIn("command(*)", policy["allow"])
        self.assertNotIn("mcp(*)", policy["allow"])

    def test_shared_policy_expands_home_preserves_overrides_and_is_idempotent(self):
        policy = ROOT / "files/antigravity_user-permissions.json"
        self.write(
            json.dumps(
                {"permissions": {"ask": ["command(git)"], "deny": ["command(docker)"]}}
            )
        )
        self.run_helper(0, "--sandbox-auto", "--shared-policy", str(policy))
        data = json.loads(self.path.read_text())
        self.assertIn(
            "write_file(" + str(Path.home() / "worktrees") + ")",
            data["permissions"]["allow"],
        )
        self.assertIn("command(docker)", data["permissions"]["deny"])
        self.assertEqual(data["permissions"]["ask"], ["command(git)"])
        first = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.run_helper(0, "--sandbox-auto", "--shared-policy", str(policy))
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), first)

    def test_invalid_shared_policy_does_not_change_settings(self):
        self.write("{}")
        policy = self.path.parent / "bad-policy.json"
        policy.write_text('{"allow":"mcp(*)"}')
        self.run_helper(1, "--shared-policy", str(policy))
        self.assertEqual(self.path.read_text(), "{}")

    def test_policy_resolves_each_runtime_home_without_fixed_username(self):
        configure = runpy.run_path(str(HELPER))["configure"]
        policy = ROOT / "files/antigravity_user-permissions.json"
        for name in ("first account", "another-user"):
            with self.subTest(name=name):
                home = self.path.parent.parent / name
                settings = home / "settings.json"
                with patch.object(Path, "home", return_value=home):
                    configure(settings, sandbox_auto=True, shared_policy=policy)
                permissions = json.loads(settings.read_text())["permissions"]
                self.assertIn(f"write_file({home / 'worktrees'})", permissions["allow"])
                self.assertIn(f"read_file({home / '.ssh'})", permissions["deny"])


if __name__ == "__main__":
    unittest.main()
