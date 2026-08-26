#!/usr/bin/env python3
"""Orderer-owned mutants for the per-session emit cap in memory_surface.py: each must make the tests fail.

The implementation must contain the four seam lines verbatim so the mutants apply;
a missing seam counts as a failure of the delivery, not of this script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_user-hooks")
HOOK = os.path.join(HOOKS, "memory_surface.py")
TESTS = os.path.join(HOOKS, "memory_surface.test.py")

MUTANTS = {
    "m1-cap-removed": ("SESSION_EMIT_CAP = 2", "SESSION_EMIT_CAP = 200"),
    "m2-cap-off-by-one": (
        "if _session_emits(con, file_path, session_id) >= SESSION_EMIT_CAP:",
        "if _session_emits(con, file_path, session_id) > SESSION_EMIT_CAP:",
    ),
    "m3-mismatch-counted": ("\"AND coalesce(kind, 'emit') = 'emit'\",", '"",'),
    "m4-session-ignored": (
        "\"AND coalesce(session_id, '') = coalesce(?, '') \"",
        '"AND ? IS NOT NULL "',
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "memory_surface.test.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
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
            shutil.copy(TESTS, os.path.join(tmp, "memory_surface.test.py"))
            with open(
                os.path.join(tmp, "memory_surface.py"), "w", encoding="utf-8"
            ) as handle:
                handle.write(source.replace(seam, mutated))
            killed = not run_tests(tmp)
            print(f"{name}: {'killed' if killed else 'SURVIVED'}")
            if not killed:
                survivors.append(name)
    print(f"survivors={len(survivors)}/{len(MUTANTS)}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
