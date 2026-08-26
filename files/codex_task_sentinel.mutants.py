#!/usr/bin/env python3
"""Orderer-owned mutants for codex_task_sentinel: each must make the acceptance tests fail.

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
SENTINEL = os.path.join(HERE, "codex_task_sentinel")
TESTS = os.path.join(HERE, "codex_task_sentinel.test.py")

MUTANTS = {
    "m1-cancelled-counts-as-alive": (
        'ALIVE_STATUSES = frozenset({"queued", "running"})',
        'ALIVE_STATUSES = frozenset({"queued", "running", "cancelled"})',
    ),
    "m2-token-check-disabled": (
        "return last == token",
        "return True",
    ),
    "m3-stall-comparison-inverted": (
        "if age > stall_seconds:",
        "if age < stall_seconds:",
    ),
    "m4-only-first-root-searched": (
        "for root in roots:",
        "for root in roots[:1]:",
    ),
}


def run_tests(sentinel_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(sentinel_dir, "codex_task_sentinel.test.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    return proc.returncode == 0


def main() -> int:
    with open(SENTINEL, encoding="utf-8") as handle:
        source = handle.read()
    survivors = []
    for name, (seam, mutated) in MUTANTS.items():
        if source.count(seam) != 1:
            print(f"{name}: seam not found exactly once -> delivery rejected")
            survivors.append(name)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(TESTS, os.path.join(tmp, "codex_task_sentinel.test.py"))
            path = os.path.join(tmp, "codex_task_sentinel")
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
