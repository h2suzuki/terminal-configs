#!/usr/bin/env python3
"""Orderer-owned mutants for frozen_docs_gate.py: each must make the acceptance tests fail.

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
HOOKS = os.path.join(HERE, "claude_managed-hooks")
GATE = os.path.join(HOOKS, "frozen_docs_gate.py")
TESTS = os.path.join(HOOKS, "frozen_docs_gate.test.py")
REPO_DOCS = os.path.join(HERE, "..", "docs")

MUTANTS = {
    "m1-marker-never-matches": (
        r'FROZEN_MARKER = re.compile(r"^凍結 \(\d{4}-\d{2}-\d{2}\)", re.MULTILINE)',
        r'FROZEN_MARKER = re.compile(r"^never$", re.MULTILINE)',
    ),
    "m2-one-extra-line-tolerated": (
        "if len(work) > len(head):",
        "if len(work) > len(head) + 1:",
    ),
    "m3-dash-c-ignored": ('if token == "-C":', 'if token == "-Z":'),
    "m4-index-instead-of-head": ('HEAD_REF = "HEAD"', 'HEAD_REF = ""'),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "frozen_docs_gate.test.py")],
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
            shutil.copytree(REPO_DOCS, os.path.join(tmp, "docs"))
            shutil.copy(TESTS, os.path.join(hooks, "frozen_docs_gate.test.py"))
            path = os.path.join(hooks, "frozen_docs_gate.py")
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
