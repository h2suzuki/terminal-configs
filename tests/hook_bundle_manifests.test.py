#!/usr/bin/env python3
"""Consistency tests for the UserPromptSubmit / Stop hook bundles.

Contract (each claim maps to one test):
  M1  managed and user settings register UserPromptSubmit and Stop once each, through
      claude_hook_bundle --file <the matching .hooks manifest>
  M2  every child in every manifest has a canonical source in files/; a hook-dir child's
      source is executable
  M3  the user legacy fragment lists exactly the user manifests' children, so an upgrade
      removes every per-hook entry the bundle replaced
"""

from __future__ import annotations

import json
import os
import shlex
import unittest

FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files")
BUNDLE = "/usr/local/bin/claude_hook_bundle"
SCOPES = {
    "managed": (
        "claude_managed-extensions.json",
        "claude_managed-hooks",
        "/etc/claude-code/hooks/",
    ),
    "user": ("claude_user-extensions.json", "claude_user-hooks", "~/.claude/hooks/"),
}
MANIFESTS = {"UserPromptSubmit": "user_prompt_submit.hooks", "Stop": "stop.hooks"}
DEPLOYED_SOURCES = {
    "/etc/claude-code/hooks/": ("claude_managed-hooks", "shared_hooks"),
    "~/.claude/hooks/": ("claude_user-hooks",),
    "/usr/local/bin/": ("",),
}


def load_json(name: str) -> dict:
    with open(os.path.join(FILES, name), encoding="utf-8") as f:
        return json.load(f)


def children(hook_dir: str, manifest: str) -> list[list[str]]:
    with open(os.path.join(FILES, hook_dir, manifest), encoding="utf-8") as f:
        return [argv for line in f if (argv := shlex.split(line, comments=True))]


def source_of(program: str) -> str | None:
    for prefix, dirs in DEPLOYED_SOURCES.items():
        if program.startswith(prefix):
            name = program[len(prefix) :]
            for d in dirs:
                for candidate in (name, name + ".py"):
                    path = os.path.join(FILES, d, candidate)
                    if os.path.isfile(path):
                        return path
    return None


class ManifestTest(unittest.TestCase):
    def test_m1_one_bundle_registration_per_event(self):
        for scope, (settings, _, prefix) in SCOPES.items():
            events = load_json(settings)["hooks"]
            for event, manifest in MANIFESTS.items():
                with self.subTest(scope=scope, event=event):
                    (group,) = events[event]
                    (hook,) = group["hooks"]
                    argv = shlex.split(hook["command"])
                    self.assertEqual(argv[0], BUNDLE)
                    self.assertEqual(argv[argv.index("--file") + 1], prefix + manifest)

    def test_m2_every_child_has_an_executable_source(self):
        for scope, (_, hook_dir, _) in SCOPES.items():
            for manifest in MANIFESTS.values():
                for argv in children(hook_dir, manifest):
                    with self.subTest(scope=scope, child=argv[0]):
                        path = source_of(argv[0])
                        self.assertIsNotNone(path, f"no source in files/ for {argv[0]}")
                        # A CLI's installer may wrap a non-executable source; a hook script runs bare.
                        if not argv[0].startswith("/usr/local/bin/"):
                            self.assertTrue(os.access(str(path), os.X_OK), path)

    def test_m3_legacy_fragment_matches_the_user_manifests(self):
        legacy = load_json("claude_user-extensions.legacy.json")["hooks"]
        for event, manifest in MANIFESTS.items():
            with self.subTest(event=event):
                old = [
                    shlex.split(h["command"]) for g in legacy[event] for h in g["hooks"]
                ]
                self.assertEqual(old, children("claude_user-hooks", manifest))


if __name__ == "__main__":
    unittest.main()
