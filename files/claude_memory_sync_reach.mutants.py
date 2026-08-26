#!/usr/bin/env python3
"""Orderer-owned mutants for `claude_memory_sync --reach`: each must make the acceptance tests fail.

The implementation must contain the four seam lines verbatim so the mutants apply;
a missing seam counts as a failure of the delivery, not of this script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "claude_memory_sync")
TESTS = os.path.join(HERE, "claude_memory_sync.reach.test.py")

MUTANTS = {
    "m1-window-removed": ("REACH_DAYS = 30", "REACH_DAYS = 3000"),
    "m2-hot-threshold-removed": ("HOT_EMITS = 20", "HOT_EMITS = 2000"),
    "m3-mismatch-counted": ("\"AND coalesce(kind, 'emit') = 'emit' \"", '"" '),
    "m4-hot-off-by-one": ("if count >= HOT_EMITS:", "if count > HOT_EMITS:"),
}


def run_tests(work: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(work, "claude_memory_sync.reach.test.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    return proc.returncode == 0


def main() -> int:
    with open(CLI, encoding="utf-8") as handle:
        source = handle.read()
    survivors = []
    for name, (seam, mutated) in MUTANTS.items():
        if source.count(seam) != 1:
            print(f"{name}: seam not found exactly once -> delivery rejected")
            survivors.append(name)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(TESTS, os.path.join(tmp, "claude_memory_sync.reach.test.py"))
            path = os.path.join(tmp, "claude_memory_sync")
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
