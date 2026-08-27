#!/usr/bin/env python3
"""Orderer-owned mutants for stop_checks.py: each must make the acceptance tests fail.

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
HOOK = os.path.join(HOOKS, "stop_checks.py")
TESTS = os.path.join(HOOKS, "stop_checks.test.py")

MUTANTS = {
    "m1-fenced-text-becomes-scannable": (
        "scan = _strip_code_and_quotes(normalized)",
        "scan = normalized",
    ),
    "m2-ledger-boundary-inverted": (
        "heavy_edit = len(edited_paths) >= LEDGER_MIN_EDITS",
        "heavy_edit = len(edited_paths) > LEDGER_MIN_EDITS",
    ),
    "m3-turn-counter-frozen": (
        "count = previous_count + 1",
        "count = previous_count",
    ),
    "m4-normalization-removed": (
        'normalized = unicodedata.normalize("NFKC", final_text)',
        "normalized = final_text",
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "stop_checks.test.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    return proc.returncode == 0


def main() -> int:
    with open(HOOK, encoding="utf-8") as handle:
        source = handle.read()
    survivors = []
    for name, (seam, mutated) in MUTANTS.items():
        if source.count(seam) != 1:
            print(f"{name}: seam not found exactly once -> delivery rejected")
            survivors.append(name)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(TESTS, os.path.join(tmp, "stop_checks.test.py"))
            path = os.path.join(tmp, "stop_checks.py")
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
