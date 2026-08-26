#!/usr/bin/env python3
"""Black-box contract tests for memory_routing_gate.py check:/when: rules.

Contract (each claim maps to one or more tests):
  N1  new entry (target path does not exist on disk) with no non-empty check:
      line in frontmatter -> deny naming check: (existing entries are exempt)
  N2  check: present but its stripped value is over 100 characters -> deny
      naming the 100-character limit
  N3  check: that is negative-only (ends in するな/しないこと/禁止/べからず/NG,
      optional trailing punctuation) AND contains none of the action tokens
      (せよ/して/する/確認/照合/検査/比較/読/実行/走らせ/数え/挙げ/示せ/直せ/修正/書/測/添え/開)
      -> deny naming the positive-form rule; a negative ending WITH an action
      token elsewhere in the value is allowed (fail-open)
  N4  existing entry (target path exists on disk) re-written without check:
      -> allowed (other rules still apply)
  N5  when:, if present, must be a space-separated subset of
      {prompt, stop, after-subagent} -> deny naming the allowed values;
      when: absent -> allowed (default prompt). check:/when: are read from
      the frontmatter only, via the same ^key:[ \\t]*(.+)$ MULTILINE regex
      style as reminder:/keywords:
  R1  regression: pre-existing denies (missing reminder:, missing keywords:,
      bad models: tag, oneline_summary: present, missing grant) and the
      current allow path (fully valid new entry with check: and
      when: prompt stop) are unchanged by the N1-N5 addition
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

GATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "memory_routing_gate.py"
)
CLONE_ORG = "/var/lib/claude-rag-memory/claude-lessons-learned/org"
EXISTING_ENTRY = os.path.join(CLONE_ORG, "feedback_self_build_over_delegation.md")
NEW_ENTRY = os.path.join(CLONE_ORG, "feedback_zz_contract_probe.md")

DEFAULT_FIELDS = {
    "name": "name: feedback_zz_contract_probe",
    "description": "description: contract probe entry for memory_routing_gate tests",
    "metadata": "metadata:\n  type: feedback",
    "reminder": "reminder: 同じ日付を書く前に日付の生成元を確認せよ",
    "keywords": "keywords: codex_broker_reap",
    "models": "models: fable-5",
    "check": "check: 直前の出力に codex_broker_reap の呼び出し有無を確認せよ",
    "when": "when: prompt stop",
}
FIELD_ORDER = (
    "name",
    "description",
    "metadata",
    "reminder",
    "keywords",
    "models",
    "check",
    "when",
)
DEFAULT_BODY = (
    "\n## 理由\n\ncontract probe 用の dummy 理由文。\n\n"
    "## 事例\n\n- 2026-08-27: contract probe 実行時の dummy 事例。\n"
)


def make_entry(
    overrides: dict[str, str | None] | None = None, body: str | None = None
) -> str:
    """valid entry を組み立て、 overrides で 1 field ずつ書き換え/除去する。"""
    fields = dict(DEFAULT_FIELDS)
    for key, value in (overrides or {}).items():
        if value is None:
            fields.pop(key, None)
        else:
            fields[key] = value
    fm = "\n".join(fields[k] for k in FIELD_ORDER if k in fields)
    return f"---\n{fm}\n---\n{body if body is not None else DEFAULT_BODY}"


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.isdir(CLONE_ORG):
            self.skipTest(
                "memory clone (/var/lib/claude-rag-memory) not present on this machine"
            )
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def grant(self, entry_path: str) -> None:
        grants_dir = os.path.join(
            self.home, ".claude", "hooks", "state", "memory-routing", "grants"
        )
        os.makedirs(grants_dir, exist_ok=True)
        with open(os.path.join(grants_dir, os.path.basename(entry_path)), "w") as fh:
            fh.write(entry_path)

    def run_guard(self, path: str, content: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["HOME"] = self.home
        payload = json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": content},
                "cwd": "/tmp",
            }
        )
        return subprocess.run(
            [sys.executable, GATE, "guard"],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=env,
        )

    def assert_deny(self, proc: subprocess.CompletedProcess, substring: str) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(
            out["hookSpecificOutput"]["permissionDecision"], "deny", reason
        )
        self.assertIn(substring, reason)

    def assert_allow(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "", proc.stdout)

    def test_n1_new_entry_without_check_denied(self) -> None:
        """N1: target path absent + no check: line -> deny naming check:."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry({"check": None}))
        self.assert_deny(proc, "check:")

    def test_n2_check_too_long_denied(self) -> None:
        """N2: check: value over 100 chars -> deny naming the 100-char limit."""
        self.grant(NEW_ENTRY)
        long_check = "check: " + "あ" * 101
        proc = self.run_guard(NEW_ENTRY, make_entry({"check": long_check}))
        self.assert_deny(proc, "100")

    def test_n3_negative_only_check_denied(self) -> None:
        """N3: negative-only check: (no action token) -> deny naming the positive-form rule."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(
            NEW_ENTRY, make_entry({"check": "check: 同じ間違いをしないこと"})
        )
        self.assert_deny(proc, "肯定形")

    def test_n3_suruna_suffix_denied(self) -> None:
        """N3: 「〜するな」 ends in する+な; the token scan must stop before the suffix."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry({"check": "check: 自作するな"}))
        self.assert_deny(proc, "肯定形")

    def test_n3_negative_with_action_token_allowed(self) -> None:
        """N3: negative ending WITH an action token elsewhere is fail-open -> allowed."""
        self.grant(NEW_ENTRY)
        val = "check: 直前の出力を確認せよ、判定基準の変更は禁止"
        proc = self.run_guard(NEW_ENTRY, make_entry({"check": val}))
        self.assert_allow(proc)

    def test_n4_existing_entry_without_check_allowed(self) -> None:
        """N4: existing entry (path exists) re-written without check: -> allowed."""
        self.grant(EXISTING_ENTRY)
        proc = self.run_guard(EXISTING_ENTRY, make_entry({"check": None, "when": None}))
        self.assert_allow(proc)

    def test_n5_when_invalid_value_denied(self) -> None:
        """N5: when: value outside {prompt,stop,after-subagent} -> deny naming allowed values."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry({"when": "when: sometime"}))
        self.assert_deny(proc, "after-subagent")

    def test_n5_when_absent_defaults_to_allowed(self) -> None:
        """N5: when: absent -> allowed (default prompt)."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry({"when": None}))
        self.assert_allow(proc)

    def test_n5_when_valid_subset_allowed(self) -> None:
        """N5: when: with a valid space-separated subset -> allowed."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(
            NEW_ENTRY, make_entry({"when": "when: stop after-subagent"})
        )
        self.assert_allow(proc)

    def test_r1_missing_reminder_denied(self) -> None:
        """R1: missing reminder: still denies unchanged."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry({"reminder": None}))
        self.assert_deny(proc, "reminder:")

    def test_r1_missing_keywords_denied(self) -> None:
        """R1: missing keywords: still denies unchanged."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry({"keywords": None}))
        self.assert_deny(proc, "keywords:")

    def test_r1_bad_models_tag_denied(self) -> None:
        """R1: malformed models: tag still denies unchanged."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry({"models": "models: BAD_TAG!!"}))
        self.assert_deny(proc, "models:")

    def test_r1_oneline_summary_denied(self) -> None:
        """R1: oneline_summary: present still denies unchanged."""
        self.grant(NEW_ENTRY)
        body = "oneline_summary: 旧形式\n" + DEFAULT_BODY
        proc = self.run_guard(NEW_ENTRY, make_entry(body=body))
        self.assert_deny(proc, "oneline_summary:")

    def test_r1_missing_grant_denied(self) -> None:
        """R1: no grant minted still denies unchanged (no grant created here)."""
        proc = self.run_guard(NEW_ENTRY, make_entry())
        self.assert_deny(proc, "/memory-routing")

    def test_r1_fully_valid_new_entry_allowed(self) -> None:
        """R1: fully valid new entry with check: and when: prompt stop -> allowed."""
        self.grant(NEW_ENTRY)
        proc = self.run_guard(NEW_ENTRY, make_entry())
        self.assert_allow(proc)


if __name__ == "__main__":
    unittest.main()
