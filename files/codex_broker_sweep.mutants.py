#!/usr/bin/env python3
"""Orderer-owned mutants for codex_broker_sweep.py: each must make the acceptance tests fail.

The implementation must contain the six seam lines verbatim so the mutants apply;
a missing seam counts as a failure of the delivery, not of this script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_managed-hooks")
GATE = os.path.join(HOOKS, "codex_broker_sweep.py")
TESTS = os.path.join(HOOKS, "codex_broker_sweep.test.py")

MUTANTS = {
    "m1-worktree-regex-drops-prune": (
        '    r"\\s+worktree\\s+(?:remove|prune)\\b"',
        '    r"\\s+worktree\\s+(?:remove)\\b"',
    ),
    "m2-ledger-condition-fires-on-zero": (
        "    if reap + stale <= 0:",
        "    if reap + stale < 0:",
    ),
    "m3-fail-open-swallows-timeout": (
        "    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:",
        "    except (FileNotFoundError,) as exc:",
    ),
    "m4-summary-regex-never-matches": (
        'SUMMARY_RE = re.compile(r"keep=(\\d+)\\s+reap=(\\d+)\\s+stale=(\\d+)")',
        'SUMMARY_RE = re.compile(r"keep=(\\d+)\\s+REAP=(\\d+)\\s+stale=(\\d+)")',
    ),
    "m5-lock-shared": (
        "        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)",
        "        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)",
    ),
    "m6-double-invocation": (
        "    proc = run_reaper(timeout)",
        "    proc = run_reaper(timeout)\n    run_reaper(timeout)",
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "codex_broker_sweep.test.py")],
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
            shutil.copy(TESTS, os.path.join(tmp, "codex_broker_sweep.test.py"))
            path = os.path.join(tmp, "codex_broker_sweep.py")
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
