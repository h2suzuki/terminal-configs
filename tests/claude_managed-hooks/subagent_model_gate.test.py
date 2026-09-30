#!/usr/bin/env python3
"""Black-box tests for subagent_model_gate.py: stdin payload in, exit code / stdout JSON out."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "files",
    "claude_managed-hooks",
    "subagent_model_gate.py",
)


def run_hook(payload: object) -> subprocess.CompletedProcess:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK], input=body, capture_output=True, text=True, check=False
    )


def spawn(**tool_input: object) -> dict:
    return {"tool_name": "Agent", "tool_input": tool_input}


class ModelGateTest(unittest.TestCase):
    def assertDenied(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("model", out["permissionDecisionReason"])

    def assertSilent(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_missing_model_is_denied(self):
        """Claim 1: a spawn that never chose a model inherits the parent unconsidered, so it is refused."""
        self.assertDenied(run_hook(spawn(prompt="review this", description="review")))

    def test_explicit_model_passes(self):
        """Claim 2: any explicit choice passes, the parent's own model included."""
        for model in ("haiku", "sonnet", "opus", "fable"):
            with self.subTest(model=model):
                self.assertSilent(run_hook(spawn(prompt="x", model=model)))

    def test_fork_passes_without_model(self):
        """Claim 3: a fork always runs on the parent model, so there is no choice to make."""
        self.assertSilent(run_hook(spawn(prompt="x", subagent_type="fork")))

    def test_blank_model_counts_as_missing(self):
        """Claim 1 boundary: an empty string is not a choice."""
        self.assertDenied(run_hook(spawn(prompt="x", model="  ")))

    def test_other_tools_are_ignored(self):
        """Claim 4: only Task / Agent spawns are gated."""
        self.assertSilent(run_hook({"tool_name": "Bash", "tool_input": {}}))

    def test_denial_names_both_managed_agents(self):
        """Claim 1 corollary: the refusal points to investigator (investigation) and implementer (implementation), neither needing `model`."""
        reason = json.loads(run_hook(spawn(prompt="x")).stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn('`subagent_type: "investigator"`', reason)
        self.assertIn('`subagent_type: "implementer"`', reason)

    def test_garbage_input_fails_open(self):
        """Claim 5: unreadable payloads never block."""
        self.assertSilent(run_hook("not json"))
        self.assertSilent(run_hook([1, 2]))

    def test_definition_model_counts_as_a_choice(self):
        """Claim 6: an agent whose definition names a model (not inherit) already chose one."""
        with tempfile.TemporaryDirectory() as cwd:
            agents = os.path.join(cwd, ".claude", "agents")
            os.makedirs(agents)
            for name, model_line in (
                ("worker", "model: sonnet\n"),
                ("heir", "model: inherit\n"),
                ("bare", ""),
            ):
                with open(
                    os.path.join(agents, f"{name}.md"), "w", encoding="utf-8"
                ) as f:
                    f.write(
                        f"---\nname: {name}\ndescription: d\n{model_line}---\nbody\n"
                    )
            with self.subTest(agent="worker"):
                self.assertSilent(
                    run_hook({**spawn(prompt="x", subagent_type="worker"), "cwd": cwd})
                )
            for agent in ("heir", "bare", "unknown"):
                with self.subTest(agent=agent):
                    self.assertDenied(
                        run_hook({**spawn(prompt="x", subagent_type=agent), "cwd": cwd})
                    )


class ImplementerDefinitionTest(unittest.TestCase):
    def test_implementer_runs_sonnet_5_5_at_xhigh(self):
        """The managed implementer agent pins Sonnet 5.5 and xhigh effort in its frontmatter."""
        path = os.path.join(
            os.path.dirname(HOOK), "..", "claude_managed-agents", "implementer.md"
        )
        with open(path, encoding="utf-8") as f:
            front = f.read().split("---\n")[1].splitlines()
        self.assertIn("name: implementer", front)
        self.assertIn("model: claude-sonnet-5-5", front)
        self.assertIn("effort: xhigh", front)


class InvestigatorDefinitionTest(unittest.TestCase):
    PATH = os.path.join(
        os.path.dirname(HOOK), "..", "claude_managed-agents", "investigator.md"
    )

    def test_investigator_runs_sonnet_5_5_at_xhigh_and_cannot_edit(self):
        """The managed investigator agent pins Sonnet 5.5 and xhigh effort, and denies the file-editing tools."""
        with open(self.PATH, encoding="utf-8") as f:
            front = f.read().split("---\n")[1].splitlines()
        self.assertIn("name: investigator", front)
        self.assertIn("model: claude-sonnet-5-5", front)
        self.assertIn("effort: xhigh", front)
        (denied,) = [line for line in front if line.startswith("disallowedTools:")]
        for tool in ("Edit", "Write", "NotebookEdit"):
            with self.subTest(tool=tool):
                self.assertIn(
                    tool, [t.strip() for t in denied.split(":", 1)[1].split(",")]
                )

    def test_investigator_spawn_needs_no_model(self):
        """The gate reads the definition's pinned model, so the real investigator.md lets a spawn omit `model`."""
        with tempfile.TemporaryDirectory() as cwd:
            agents = os.path.join(cwd, ".claude", "agents")
            os.makedirs(agents)
            shutil.copy(self.PATH, agents)
            proc = run_hook(
                {**spawn(prompt="x", subagent_type="investigator"), "cwd": cwd}
            )
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)


if __name__ == "__main__":
    unittest.main()
