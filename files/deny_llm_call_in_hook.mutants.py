#!/usr/bin/env python3
"""Orderer-owned mutants for deny_llm_call_in_hook.py: each must make the acceptance tests fail.

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
GATE = os.path.join(HOOKS, "deny_llm_call_in_hook.py")
TESTS = os.path.join(HOOKS, "deny_llm_call_in_hook.test.py")

MUTANTS = {
    "m1-bg-not-a-call": (
        'LLM_CALL_RE = re.compile(r"\\bclaude\\s+(?:-p|--bg)\\b")',
        'LLM_CALL_RE = re.compile(r"\\bclaude\\s+(?:-p)\\b")',
    ),
    "m2-lint-not-exempt": (
        'EXEMPT_PREFIXES = ("claude-md-lint",)',
        "EXEMPT_PREFIXES = ()",
    ),
    "m3-scope-never-matches": (
        'HOOK_DIR_RE = re.compile(r"(?:claude_managed-hooks|claude_user-hooks|\\.claude/hooks|claude-code/hooks|skel/hooks)/[^/]+$")',
        'HOOK_DIR_RE = re.compile(r"^never$")',
    ),
    "m4-multiedit-ignored": (
        'for edit in tool_input.get("edits") or []:',
        "for edit in []:",
    ),
}


def run_tests(hooks_dir: str) -> bool:
    proc = subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "deny_llm_call_in_hook.test.py")],
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
            shutil.copy(TESTS, os.path.join(tmp, "deny_llm_call_in_hook.test.py"))
            path = os.path.join(tmp, "deny_llm_call_in_hook.py")
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
