#!/usr/bin/env python3
"""Orderer-owned mutants for codex_order_lint: each must make the acceptance tests fail.

The implementation must contain the four seam lines verbatim so the mutants apply;
a missing seam counts as a failure of the delivery, not of this script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

FILES = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(FILES, "codex_order_lint")
TESTS = os.path.join(FILES, "codex_order_lint.test.py")
TEMPLATES = os.path.join(FILES, "claude_managed-skills", "codex-delegation")

MUTANTS = {
    "m1-non-utf8-not-caught": (
        "        except UnicodeDecodeError:",
        "        except LookupError:",
    ),
    "m2-treatment-boundary-shifted": (
        "TREATMENT_MIN_ROUND = 3",
        "TREATMENT_MIN_ROUND = 4",
    ),
    "m3-previous-verdict-key-flattened": (
        '        "has_previous_verdict": has_nonempty_section(lines, "前巡 verdict"),',
        '        "has_previous_verdict": False,',
    ),
    "m4-fences-not-normalised": (
        "    live = [lines[index] for index in outside_fences(lines)]",
        "    live = lines",
    ),
}


def run_tests(directory: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(directory, "codex_order_lint.test.py")],
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
            shutil.copy(TESTS, os.path.join(tmp, "codex_order_lint.test.py"))
            # 雛形の探索順は配備先が先だが、 配備前の repo でも --new が通るよう隣も張る。
            skills = os.path.join(tmp, "claude_managed-skills")
            os.makedirs(skills)
            os.symlink(TEMPLATES, os.path.join(skills, "codex-delegation"))
            path = os.path.join(tmp, "codex_order_lint")
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
