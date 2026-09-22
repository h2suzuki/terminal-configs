#!/usr/bin/env python3
"""Integration fixtures for shared hygiene. dangling-ref-check: allow"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tomllib

FILES = Path(__file__).resolve().parents[1] / "files"
HOOK = FILES / "workspace_hygiene.py"
ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


class HygieneTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name) / "repo"
        self.top.mkdir()
        self.git("init", "-q")
        self.write(".gitignore", "drafts/\n")
        self.write("src/main.py", "print('source')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.write("drafts/peer/report.txt", "keep")

    def write(self, name, content):
        path = self.top / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.top), *args],
            env=ENV,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def hook(self, tool, inp, expected=0, cwd=None):
        before = self.git("ls-files", "--stage", "-z")
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            env=ENV,
            text=True,
            input=json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "cwd": str(cwd or self.top),
                    "tool_name": tool,
                    "tool_input": inp,
                }
            ),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        self.assertEqual(
            self.git("ls-files", "--stage", "-z"), before, "hook changed index"
        )
        self.assertEqual((self.top / "drafts/peer/report.txt").read_text(), "keep")
        return result

    def shells(self, command, expected=0):
        for tool, key in (
            ("Bash", "command"),
            ("exec_command", "cmd"),
            ("functions.exec_command", "cmd"),
        ):
            with self.subTest(tool=tool, command=command):
                self.hook(tool, {key: command}, expected)

    def test_explicit_drafts_add(self):
        for command in (
            "git add drafts/peer/report.txt",
            "git add -f drafts",
            "git add --force -- drafts/peer/report.txt",
        ):
            self.shells(command, 2)

    def test_force_broad_add(self):
        self.shells("git add -f .", 2)
        self.shells("git add --force ':(glob)**/*.txt'", 2)

    def test_normal_broad_add_ignores_drafts(self):
        self.write("src/new.py", "source")
        self.shells("git add .")

    def test_staged_drafts_commit(self):
        self.git("add", "-f", "drafts/peer/report.txt")
        for command in (
            "git commit -m test",
            "git commit --amend --no-edit",
            "git commit -am test",
        ):
            self.shells(command, 2)

    def test_untracking_is_allowed(self):
        self.git("add", "-f", "drafts/peer/report.txt")
        self.git("commit", "-qm", "leak")
        self.git("rm", "--cached", "drafts/peer/report.txt")
        self.shells("git commit -m untrack")

    def test_path_commit(self):
        self.git("add", "-f", "drafts/peer/report.txt")
        self.git("commit", "-qm", "leak")
        self.shells("git commit -m test -- drafts/peer/report.txt", 2)

    def test_references_still_checked(self):
        self.write("src/readme.md", "see drafts/private.md\n")
        self.git("add", "src/readme.md")
        self.shells("git commit -m update", 2)

    def test_commit_message_not_a_path(self):
        self.shells("git commit -m 'mention drafts/peer/report.txt'")

    def test_git_c_and_workdir(self):
        self.hook(
            "Bash",
            {"command": f"git -C {self.top} add -f drafts"},
            2,
            cwd=self.temp.name,
        )
        self.hook(
            "Bash",
            {"command": f"git -C{self.top} add -f drafts"},
            2,
            cwd=self.temp.name,
        )
        self.hook(
            "exec_command",
            {"cmd": "git add -f drafts", "workdir": str(self.top)},
            2,
            cwd=self.temp.name,
        )

    def test_cd_compound(self):
        self.hook(
            "exec_command",
            {"cmd": f"cd {self.top} && git add -f drafts"},
            2,
            cwd=self.temp.name,
        )

    def test_claude_file_tools(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            self.hook(tool, {"file_path": str(self.top / "reports/out.md")}, 2)
            self.hook(tool, {"file_path": str(self.top / "src/new.py")})
            self.hook(tool, {"file_path": str(self.top / "drafts/own.md")})

    def test_codex_patch_shapes(self):
        patch = "*** Begin Patch\n*** Add File: reports/out.md\n+report\n*** End Patch"
        for inp in (patch, {"command": patch}, {"input": patch}, {"patch": patch}):
            self.hook("apply_patch", inp, 2)
        self.hook(
            "apply_patch", {"command": patch.replace("reports/out.md", "src/new.py")}
        )

    def test_patch_move(self):
        self.hook(
            "apply_patch",
            {
                "command": "*** Begin Patch\n*** Update File: src/main.py\n*** Move to: reports/moved.py\n*** End Patch"
            },
            2,
        )

    def test_shell_root_outputs(self):
        for command in (
            "mkdir -p reports",
            "touch reports/x",
            "echo report > reports/x",
            "printf x | tee reports/x",
            "cp src/main.py reports/x",
        ):
            self.shells(command, 2)
        self.shells("mkdir -p src/feature && touch src/feature/new.py")
        self.shells("cat src/main.py")

    def test_new_existing_untracked_root_staging(self):
        self.write("reports/previous.txt", "preexisting file, do not delete")
        self.shells("git add .", 2)
        self.assertTrue((self.top / "reports/previous.txt").exists())

    def test_staged_new_root_commit(self):
        self.write("reports/new.txt", "report")
        self.git("add", "reports")
        self.shells("git commit -m reports", 2)

    def test_user_requested_layout(self):
        self.write(
            ".workspace-layout.json",
            json.dumps({"directories": {"tests": "User requested permanent tests"}}),
        )
        self.shells("mkdir -p tests")
        self.hook("Write", {"file_path": "tests/test_main.py"})
        self.write("tests/test_main.py", "assert True")
        self.shells("git add tests .workspace-layout.json")
        self.git("add", "tests", ".workspace-layout.json")
        self.shells("git commit -m tests")

    def test_layout_never_exempts_drafts(self):
        self.write(
            ".workspace-layout.json",
            json.dumps({"directories": {"drafts": "not valid"}}),
        )
        self.shells("git add -f drafts", 2)

    def test_drafts_must_be_ignored(self):
        self.write(".gitignore", "")
        self.hook("Write", {"file_path": "drafts/own.md"}, 2)

    def test_tmpdir(self):
        for command in (
            "mktemp",
            "TMPDIR= mktemp",
            "TMPDIR=/ mktemp",
            "mktemp -p /tmp",
            'echo x > "$TMPDIR/x"',
            "mktemp # /var/tmp is not routing",
        ):
            self.shells(command, 2)
        self.shells(f'TMPDIR="{self.top}/drafts" mktemp')
        self.shells("mktemp -p /var/tmp")
        self.shells("mktemp -d drafts/temp.XXXXXX")
        self.shells('mkdir -p "$TMPDIR/output"', 2)
        self.shells("mktemp -p /var/tmp/owned")

    def test_git_overrides_are_not_silently_checked_in_wrong_repository(self):
        self.shells("git --git-dir=/some/repo/.git add -f drafts", 2)
        self.shells("GIT_INDEX_FILE=/some/index git commit -m test", 2)

    def test_user_skill_link_preserves_conflicts(self):
        spec = importlib.util.spec_from_file_location(
            "installer", FILES / "install_workspace_hygiene.py"
        )
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        home = Path(self.temp.name) / "user"
        old = home / ".claude/skills/workspace-hygiene"
        old.parent.mkdir(parents=True)
        old.symlink_to("/etc/claude-code/skills/workspace-hygiene")
        with patch.object(Path, "is_file", return_value=True):
            installer.link_user_skill(home)
            installer.link_user_skill(home)
        self.assertFalse(old.is_symlink())
        target = home / ".claude/skills/scratch-file-management"
        self.assertEqual(
            str(target.readlink()), "/etc/claude-code/skills/scratch-file-management"
        )
        target.unlink()
        target.mkdir()
        peer = target / "SKILL.md"
        peer.write_text("peer skill")
        with self.assertRaises(ValueError):
            installer.link_user_skill(home)
        self.assertEqual(peer.read_text(), "peer skill")

    def test_readonly_mentions_and_heredoc(self):
        self.shells("echo 'mktemp is documentation'")
        self.shells("cat <<'EOF'\nmkdir reports\nEOF\n")

    def test_run_cleanup_preserves_peer_and_status(self):
        code = "import os,pathlib,sys; p=pathlib.Path(os.environ['TMPDIR']); print(p); (p/'x').write_text('tmp'); sys.exit(7)"
        result = subprocess.run(
            [sys.executable, str(HOOK), "run", "--", sys.executable, "-c", code],
            cwd=self.top,
            capture_output=True,
            text=True,
            env=ENV,
            check=False,
        )
        self.assertEqual(result.returncode, 7, result.stderr)
        owned = Path(result.stdout.strip())
        self.assertEqual(owned.parent, self.top / "drafts")
        self.assertFalse(owned.exists())
        self.assertEqual((self.top / "drafts/peer/report.txt").read_text(), "keep")

    def test_run_rejects_symlink_scratch(self):
        (self.top / "drafts").rename(self.top / "existing-output")
        (self.top / "drafts").symlink_to(
            self.top / "existing-output", target_is_directory=True
        )
        result = subprocess.run(
            [sys.executable, str(HOOK), "run", "--", "true"],
            cwd=self.top,
            capture_output=True,
            text=True,
            env=ENV,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue((self.top / "existing-output/peer/report.txt").exists())

    def test_run_does_not_bypass_git_check(self):
        result = subprocess.run(
            [sys.executable, str(HOOK), "run", "--", "git", "add", "-f", "."],
            cwd=self.top,
            capture_output=True,
            text=True,
            env=ENV,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("drafts/", self.git("ls-files"))

    def test_both_installer_merges_preserve_peer_files(self):
        for name in ("debian12.sh", "ubuntu2404-wsl.sh"):
            source = (FILES.parent / name).read_text()
            merge = re.search(
                r"(?m)^merge_dir\(\)\n\{.*?^\}", source, re.DOTALL
            ).group()
            fixture = Path(self.temp.name) / name
            owned = fixture / "files/policy/nested/owned"
            owned.parent.mkdir(parents=True)
            owned.write_text("updated")
            peer = fixture / "target/peer"
            peer.parent.mkdir(parents=True)
            peer.write_text("preserve")
            script = (
                'TOP_DIR="$TEST_INSTALL_ROOT"\ncopy() { install -D "$TOP_DIR/files/$1" "$2"; }\n'
                + merge
                + '\nmerge_dir policy "$TOP_DIR/target"'
            )
            subprocess.run(
                ["bash", "-eu", "-c", script],
                env={**ENV, "TEST_INSTALL_ROOT": str(fixture)},
                check=True,
            )
            self.assertEqual(peer.read_text(), "preserve")
            self.assertEqual((fixture / "target/nested/owned").read_text(), "updated")

    def test_install_preserves_config_and_peer_files(self):
        stage = Path(self.temp.name) / "stage"
        codex = stage / "etc/codex/config.toml"
        codex.parent.mkdir(parents=True)
        codex.write_text(
            'model = "preserve-me"\n[sandbox_workspace_write]\nwritable_roots = ["~/worktrees"]\n'
        )
        peer = stage / "etc/codex/skills/peer/SKILL.md"
        peer.parent.mkdir(parents=True)
        peer.write_text("peer")
        retired = []
        for client, name in (
            ("codex", "workspace-hygiene"),
            ("claude-code", "workspace-hygiene"),
            ("claude-code", "browser-verification"),
        ):
            old = stage / f"etc/{client}/skills/{name}/SKILL.md"
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text("old managed skill")
            retired.append(old)
        browser = stage / "etc/claude-code/skills/browser-testing-guide/SKILL.md"
        browser.parent.mkdir(parents=True)
        browser.write_text("new browser guide")
        claude = stage / "etc/claude-code/managed-settings.d/extensions.json"
        claude.parent.mkdir(parents=True)
        claude.write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["existing"]},
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {"type": "command", "command": "peer-command"},
                                    {
                                        "type": "command",
                                        "command": "/etc/claude-code/hooks/tmpdir_scratch_gate.py",
                                    },
                                ],
                            }
                        ]
                    },
                }
            )
        )
        for _ in range(2):
            subprocess.run(
                [
                    sys.executable,
                    str(FILES / "install_workspace_hygiene.py"),
                    "--root",
                    str(stage),
                ],
                check=True,
                capture_output=True,
                env=ENV,
            )
        config = tomllib.loads(codex.read_text())
        self.assertEqual(config["model"], "preserve-me")
        self.assertEqual(
            config["sandbox_workspace_write"]["writable_roots"], ["~/worktrees"]
        )
        self.assertEqual(len(config["hooks"]["PreToolUse"]), 1)
        settings = json.loads(claude.read_text())
        commands = [
            h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]
        ]
        self.assertEqual(
            commands, ["peer-command", "/usr/local/bin/workspace_hygiene hook"]
        )
        self.assertEqual(settings["permissions"], {"allow": ["existing"]})
        self.assertEqual(peer.read_text(), "peer")
        self.assertTrue(all(not old.exists() for old in retired))
        self.assertEqual(browser.read_text(), "new browser guide")
        for client in ("codex", "claude-code"):
            self.assertEqual(
                (
                    stage / f"etc/{client}/skills/scratch-file-management/SKILL.md"
                ).read_bytes(),
                (FILES / "shared_skills/scratch-file-management/SKILL.md").read_bytes(),
            )
        deployed = stage / "usr/local/lib/workspace_hygiene/workspace_hygiene.py"
        result = subprocess.run(
            [sys.executable, str(deployed)],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "cwd": str(self.top),
                    "tool_input": {"command": "git add -f ."},
                }
            ),
            text=True,
            capture_output=True,
            env=ENV,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_both_installers_and_config(self):
        for name in ("debian12.sh", "ubuntu2404-wsl.sh"):
            path = FILES.parent / name
            subprocess.run(["bash", "-n", str(path)], check=True)
            source = path.read_text()
            self.assertIn(
                'run python3 "$TOP_DIR/files/install_workspace_hygiene.py"', source
            )
            self.assertNotIn("find /etc/codex -depth", source)
            self.assertNotIn("find /etc/claude-code -depth", source)
            for client in ("codex", "claude-code"):
                self.assertIn(
                    f"copy shared_skills/sandbox-host-recovery/SKILL.md /etc/{client}/skills/sandbox-host-recovery/SKILL.md",
                    source,
                )
        config = tomllib.loads((FILES / "codex_config.toml").read_text())
        self.assertEqual(
            config["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
            "/usr/local/bin/workspace_hygiene hook",
        )
        self.assertEqual(
            config["hooks"]["SessionStart"][0]["hooks"][0]["command"],
            "/usr/local/bin/claude_memory_sync --pull",
        )
        self.assertEqual(
            config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"],
            "python3 /etc/claude-code/skel/hooks/memory_surface.py --codex",
        )
        self.assertEqual(
            config["hooks"]["Stop"][0]["hooks"][0]["command"],
            "python3 /etc/claude-code/skel/hooks/memory_surface.py --codex-stop",
        )


if __name__ == "__main__":
    unittest.main()
