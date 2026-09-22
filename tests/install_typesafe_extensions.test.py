"""Run the setup shell with fixture CLIs; never install into the real home."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUB = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ["TYPESAFE_TEST_ROOT"])
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([name, *args]) + "\\n")
if name == "claude" and args[:2] == ["plugin", "enable"]:
    if os.environ.get("TYPESAFE_TEST_FAIL_ENABLE"):
        sys.exit(7)
    (root / "enabled").touch()
if name == "claude" and args == ["plugin", "list"]:
    print("typesafe@typesafe-ai: " + ("enabled" if (root / "enabled").exists() else "disabled"))
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

    def test_disabled_plugin_enabled_before_final_list_and_all_commands_echoed(self):
        for _ in range(2):
            result = self.run_setup()
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
        for call in calls:
            self.assertIn("=> " + " ".join(call), result.stdout)
        self.assertFalse(any(call[0] == "jev" for call in calls))

    def test_enable_failure_stops_instead_of_printing_success(self):
        self.env["TYPESAFE_TEST_FAIL_ENABLE"] = "1"
        result = self.run_setup()
        self.assertEqual(result.returncode, 7)
        self.assertIn("ERROR(7)", result.stdout)
        self.assertNotIn(["claude", "plugin", "list"], self.calls())
        self.assertFalse(any(call[0] == "codex" for call in self.calls()))

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


if __name__ == "__main__":
    unittest.main()
