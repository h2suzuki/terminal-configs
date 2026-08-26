#!/usr/bin/env python3
"""Orderer-owned mutants for deny_command_patterns.py: each must make the acceptance tests fail.

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
GATE = os.path.join(HOOKS, "deny_command_patterns.py")
TESTS = os.path.join(HOOKS, "deny_command_patterns.test.py")

MUTANTS = {
    "m1-pkill-not-a-kill": (
        'KILL_RE = re.compile(r"\\b(?:fuser\\s+-k|pkill|killall)\\b")',
        'KILL_RE = re.compile(r"\\b(?:fuser\\s+-k|killall)\\b")',
    ),
    "m2-timeout-exemption-dead": (
        'TIMEOUT_RE = re.compile(r"\\btimeout\\b")',
        'TIMEOUT_RE = re.compile(r"\\bnever-timeout\\b")',
    ),
    "m3-git-not-exempt": (
        'START_EXEMPT = frozenset({"git"})',
        "START_EXEMPT = frozenset()",
    ),
    "m4-quotes-not-stripped": (
        "stripped = strip_quotes_and_heredocs(command)",
        "stripped = command",
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "deny_command_patterns.test.py")],
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
            shutil.copy(TESTS, os.path.join(tmp, "deny_command_patterns.test.py"))
            path = os.path.join(tmp, "deny_command_patterns.py")
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
