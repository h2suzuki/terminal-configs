#!/usr/bin/env python3
"""Orderer-owned mutants for codex_delegation_gate.py: each must make the acceptance tests fail.

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
GATE = os.path.join(HOOKS, "codex_delegation_gate.py")
TESTS = os.path.join(HOOKS, "codex_delegation_gate.test.py")

MUTANTS = {
    "m1-mentions-become-launches": (
        "scan = strip_quotes_heredocs_comments(command)",
        "scan = command",
    ),
    "m2-primary-checkout-inverted": (
        "primary = git_dir == common_dir",
        "primary = git_dir != common_dir",
    ),
    "m3-write-flag-dropped": (
        'WRITE_FLAGS = frozenset({"--write", "--resume", "--resume-last"})',
        'WRITE_FLAGS = frozenset({"--resume", "--resume-last"})',
    ),
    "m4-same-root-check-dead": (
        "same_root = launch_root == session_root",
        "same_root = True",
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "codex_delegation_gate.test.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
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
            shutil.copy(TESTS, os.path.join(tmp, "codex_delegation_gate.test.py"))
            path = os.path.join(tmp, "codex_delegation_gate.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(source.replace(seam, mutated))
            os.chmod(path, 0o755)
            killed = not run_tests(tmp)
            print(f"{name}: {'killed' if killed else 'SURVIVED'}")
            if not killed:
                survivors.append(name)
    print(f"survivors={len(survivors)}/{len(MUTANTS)}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
