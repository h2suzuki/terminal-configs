#!/usr/bin/env python3
"""Orderer-owned mutants for memory_routing_gate.py: each must make the contract tests fail.

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
GATE = os.path.join(HOOKS, "memory_routing_gate.py")
TESTS = os.path.join(HOOKS, "memory_routing_gate.test.py")

MUTANTS = {
    "m1-new-entry-check-required-dead": (
        "if not os.path.exists(path) and not check_val:",
        "if False and not check_val:",
    ),
    "m2-check-length-limit-widened": (
        "if len(check_val) > CHECK_MAX_LEN:",
        "if len(check_val) > 1000:",
    ),
    "m3-negative-only-regex-dead": (
        '_CHECK_NEGATIVE_RE = re.compile(r"(するな|しないこと|禁止|べからず|NG)[。.!！]?$")',
        '_CHECK_NEGATIVE_RE = re.compile(r"(?!)")',
    ),
    "m4-when-allowed-set-bypassed": (
        "if not all(v in WHEN_VALUES for v in mw.group(1).strip().split()):",
        "if not all(True for v in mw.group(1).strip().split()):",
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "memory_routing_gate.test.py")],
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
            shutil.copy(TESTS, os.path.join(tmp, "memory_routing_gate.test.py"))
            path = os.path.join(tmp, "memory_routing_gate.py")
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
