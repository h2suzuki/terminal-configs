"""Run the setup shell with fixture CLIs; never install into the real home."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_CLAUDE = shutil.which("claude")
STUB = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ["TYPESAFE_TEST_ROOT"])
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([name, *args]) + "\\n")
if name == "claude" and args[:2] == ["plugin", "enable"]:
    if (root / "enabled").exists():
        print("Plugin is already enabled", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("TYPESAFE_TEST_FAIL_ENABLE"):
        sys.exit(7)
    (root / "enabled").touch()
if name == "claude" and args == ["plugin", "list"]:
    print("typesafe@typesafe-ai: " + ("enabled" if (root / "enabled").exists() else "disabled"))
if name == "claude" and args == ["plugin", "list", "--json"]:
    print(json.dumps([{"id":"typesafe@typesafe-ai","scope":"user","enabled":(root / "enabled").exists()}]))
if args[:2] == ["mcp", "remove"]:
    sys.exit(1)
"""


class TypeSafeSetupTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        binary = self.root / "bin"
        binary.mkdir()
        for name in ("claude", "codex", "jev", "npx"):
            target = binary / name
            target.write_text(STUB)
            target.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "TYPESAFE_TEST_ROOT": str(self.root),
        }

    def run_setup(self):
        return subprocess.run(
            ["bash", str(ROOT / "files/install_typesafe_extensions")],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def calls(self):
        return [
            json.loads(line)
            for line in (self.root / "calls.jsonl").read_text().splitlines()
        ]

    def test_disabled_plugin_enabled_before_final_list_and_install_commands_echoed(
        self,
    ):
        outputs = []
        for _ in range(2):
            result = self.run_setup()
            outputs.append(result.stdout)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("typesafe@typesafe-ai: enabled", result.stdout)
            self.assertNotIn("disabled", result.stdout)
            self.assertNotIn("TypeSafe / Jev installed", result.stdout)
            self.assertNotIn("Restart Codex", result.stdout)
        calls = self.calls()
        enabled = [
            "claude",
            "plugin",
            "enable",
            "typesafe@typesafe-ai",
            "--scope",
            "user",
        ]
        self.assertLess(calls.index(enabled), calls.index(["claude", "plugin", "list"]))
        self.assertEqual(calls.count(enabled), 1)
        for call in calls:
            if call[1:3] == ["mcp", "remove"] or call[-1:] == ["--json"]:
                continue
            self.assertIn("=> " + " ".join(call), "".join(outputs))
        self.assertFalse(any(call[0] == "jev" for call in calls))

    def test_enable_failure_stops_instead_of_printing_success(self):
        self.env["TYPESAFE_TEST_FAIL_ENABLE"] = "1"
        result = self.run_setup()
        self.assertEqual(result.returncode, 7)
        self.assertIn("ERROR(7)", result.stdout)
        self.assertNotIn(["claude", "plugin", "list"], self.calls())
        self.assertFalse(any(call[0] == "codex" for call in self.calls()))

    def test_enabled_plugin_never_calls_non_idempotent_enable(self):
        (self.root / "enabled").touch()
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(
            any(call[1:3] == ["plugin", "enable"] for call in self.calls())
        )

    def test_user_setup_lists_only_after_typesafe_setup(self):
        setup = (ROOT / "files/setup_user_environment").read_text()
        self.assertLess(
            setup.index("run install_claude_extensions"),
            setup.index("run install_typesafe_extensions"),
        )
        self.assertNotIn(
            "run claude plugin list",
            (ROOT / "files/install_claude_extensions").read_text(),
        )


@unittest.skipUnless(REAL_CLAUDE, "Claude CLI required for native enablement test")
class NativeClaudeEnableTest(unittest.TestCase):
    def test_real_cli_disabled_enabled_and_repeated_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marketplace = root / "marketplace"
            manifest = marketplace / ".claude-plugin/marketplace.json"
            plugin = marketplace / "plugins/typesafe/.claude-plugin/plugin.json"
            manifest.parent.mkdir(parents=True)
            plugin.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps(
                    {
                        "name": "typesafe-ai",
                        "owner": {"name": "fixture"},
                        "plugins": [
                            {"name": "typesafe", "source": "./plugins/typesafe"}
                        ],
                    }
                )
            )
            plugin.write_text(json.dumps({"name": "typesafe", "version": "0.0.0"}))
            env = {**os.environ, "CLAUDE_CONFIG_DIR": str(root / "config")}

            def cli(*args, expected=0):
                result = subprocess.run(
                    [REAL_CLAUDE, *args],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(
                    result.returncode, expected, result.stdout + result.stderr
                )
                return result

            cli("plugin", "marketplace", "add", str(marketplace))
            cli("plugin", "install", "typesafe@typesafe-ai", "--scope", "user")
            already = cli(
                "plugin",
                "enable",
                "typesafe@typesafe-ai",
                "--scope",
                "user",
                expected=1,
            )
            self.assertIn("already enabled", already.stdout + already.stderr)
            cli("plugin", "disable", "typesafe@typesafe-ai", "--scope", "user")
            script = (ROOT / "files/install_typesafe_extensions").read_text()
            runner = script[
                script.index("run()\n") : script.index("# Avoid interpreting")
            ]
            guard = script[
                script.index("claude plugin list --json |") : script.index(
                    "# Codex supports"
                )
            ]
            for enable_expected in (True, False):
                result = subprocess.run(
                    ["bash", "-c", runner + guard],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(
                    "=> claude plugin enable" in result.stdout, enable_expected
                )
                state = json.loads(cli("plugin", "list", "--json").stdout)
                selected = [
                    p
                    for p in state
                    if p["id"] == "typesafe@typesafe-ai" and p["scope"] == "user"
                ]
                self.assertEqual(len(selected), 1)
                self.assertIs(selected[0]["enabled"], True)


if __name__ == "__main__":
    unittest.main()
