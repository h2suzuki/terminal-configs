#!/usr/bin/env python3
"""Orderer-owned mutants for todos_structure_gate.py: each must make the acceptance tests fail.

The implementation must contain the four seam lines verbatim so the mutants apply;
a missing seam counts as a failure of the delivery, not of this script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_managed-hooks")
GATE = os.path.join(HOOKS, "todos_structure_gate.py")
TESTS = os.path.join(HOOKS, "todos_structure_gate.test.py")
REPO_TODOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "todos.md")

MUTANTS = {
    "m1-block-limit-removed": ("MAX_BLOCK_LINES = 40", "MAX_BLOCK_LINES = 4000"),
    "m2-dash-c-ignored": ('if token == "-C":', 'if token == "-Z":'),
    "m3-goal-not-required": (
        'REQUIRED_KEYS = ("起票:", "Goal:", "Exit Criteria:")',
        'REQUIRED_KEYS = ("起票:",)',
    ),
    "m4-never-triggers": (
        "target = todos_commit_target(command, cwd)",
        "target = None",
    ),
    "m5-kessai-not-a-decision-word": (
        'DECISION_WORDS = ("決裁", "承認", "合意", "採用")',
        'DECISION_WORDS = ("承認", "合意", "採用")',
    ),
    "m6-consent-always-satisfied": (
        '    return "「" in paragraph or any(marker in paragraph for marker in CONSENT_MARKERS)',
        "    return True",
    ),
    "m7-baseline-ignored": (
        "    added = set(work_lines) - set(head_lines)",
        "    added = set(work_lines)",
    ),
    "m8-teianchu-not-a-marker": (
        'CONSENT_MARKERS = ("提案中", "発話証跡なし", "要確認", "未承認", "無承認", "承認不備", "不採用")',
        'CONSENT_MARKERS = ("発話証跡なし", "要確認", "未承認", "無承認", "承認不備", "不採用")',
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "todos_structure_gate.test.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    return proc.returncode == 0


def main() -> int:
    with open(GATE, encoding="utf-8") as handle:
        source = handle.read()
    survivors = []
    for name, (seam, mutated) in MUTANTS.items():
        if source.count(seam) != 1:
            print(f"{name}: seam not found exactly once -> delivery rejected")
            survivors.append(name)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            hooks = os.path.join(tmp, "files", "claude_managed-hooks")
            os.makedirs(hooks)
            shutil.copy(REPO_TODOS, os.path.join(tmp, "todos.md"))
            shutil.copy(TESTS, os.path.join(hooks, "todos_structure_gate.test.py"))
            path = os.path.join(hooks, "todos_structure_gate.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(source.replace(seam, mutated))
            os.chmod(path, 0o755)
            killed = not run_tests(hooks)
            print(f"{name}: {'killed' if killed else 'SURVIVED'}")
            if not killed:
                survivors.append(name)
    print(f"survivors={len(survivors)}/{len(MUTANTS)}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
