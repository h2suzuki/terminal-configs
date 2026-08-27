#!/usr/bin/env python3
"""Orderer-owned mutants for skill_reminder_gate.py: each must make the acceptance tests fail.

The implementation must contain the four seam lines verbatim, exactly once each, so the mutants apply;
a missing or duplicated seam counts as a failure of the delivery, not of this script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_managed-hooks")
GATE = os.path.join(HOOKS, "skill_reminder_gate.py")
TESTS = os.path.join(HOOKS, "skill_reminder_gate.test.py")
HANDOFF_MODULE = os.path.join(HOOKS, "check_uncommitted_at_handoff.py")

MUTANTS = {
    "m1-corrupt-state-becomes-empty": (
        "        return None  # corrupt / unreadable state -> fail open",
        "        return {}  # corrupt / unreadable state -> fail open",
    ),
    "m2-window-comparison-inverted": (
        "    fresh = now - record_ts <= SKILL_WINDOW_SECONDS",
        "    fresh = now - record_ts > SKILL_WINDOW_SECONDS",
    ),
    "m3-deny-prefix-dropped": (
        'DENY_PREFIX = "skill-reminder-gate: "',
        'DENY_PREFIX = ""',
    ),
    "m4-extension-case-not-normalized": (
        "    ext = os.path.splitext(name)[1].lower()",
        "    ext = os.path.splitext(name)[1]",
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "skill_reminder_gate.test.py")],
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
            shutil.copy(TESTS, os.path.join(tmp, "skill_reminder_gate.test.py"))
            if os.path.exists(HANDOFF_MODULE):
                shutil.copy(
                    HANDOFF_MODULE, os.path.join(tmp, "check_uncommitted_at_handoff.py")
                )
            path = os.path.join(tmp, "skill_reminder_gate.py")
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
