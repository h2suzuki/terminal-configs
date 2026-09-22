"""Keep shared instructions identical and client-specific differences explicit."""

import unittest
from pathlib import Path

FILES = Path(__file__).resolve().parents[1] / "files"


class AgentGuidanceTest(unittest.TestCase):
    def test_shared_guidance_and_personal_scope(self):
        codex = (FILES / "codex_user-AGENTS.md").read_text()
        managed = (FILES / "claude_managed-CLAUDE.md").read_text()
        personal = (FILES / "claude_user-CLAUDE.md").read_text()
        personal_heading = "## user の名称\n"
        claude_heading = "## Claude Code 固有の最終行書式\n"
        codex_shared, codex_personal = codex.split(personal_heading)
        claude_shared, claude_only = managed.split(claude_heading)

        self.assertEqual(codex_shared, claude_shared)
        self.assertEqual(personal_heading + codex_personal, personal)
        self.assertIn("commit の実行・保留・タイミング・粒度", claude_shared)
        self.assertNotIn("commit", personal)
        self.assertNotIn(personal_heading, managed)
        self.assertIn("Stop hook", claude_only)
        self.assertIn("communication-lint", claude_only)
        self.assertIn("[結論]", claude_only)
        self.assertIn("[質問]", claude_only)


if __name__ == "__main__":
    unittest.main()
