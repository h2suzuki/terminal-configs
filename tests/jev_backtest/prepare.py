#!/usr/bin/env python3
"""Lay out each backtest case as a one-file git repo whose uncommitted change is the edit to judge.

Usage: prepare.py <out-dir> <ky-clone>
Prints one JSON line per case: {"id", "label", "kind", "cwd", "command"}; pass cwd and command to
the connected jev server's context_gate tool, then read the judgments from its log.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "backtest",
    "GIT_AUTHOR_EMAIL": "backtest@example.com",
    "GIT_COMMITTER_NAME": "backtest",
    "GIT_COMMITTER_EMAIL": "backtest@example.com",
}


def git(cwd: Path | str, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
        env=ENV,
    ).stdout


def main() -> int:
    out, ky = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads((HERE / "cases.json").read_text())
    if git(ky, "rev-parse", "HEAD").strip() != data["repos"]["ky"]["head"]:
        sys.exit(f"{ky} is not at the pinned ky commit {data['repos']['ky']['head']}")
    for case in data["cases"]:
        source = ROOT if case["repo"] == "terminal-configs" else ky
        base = case.get("base") or case["sha"] + "^"
        repo = out / case["id"]
        target = repo / case["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q", "-b", "main")
        target.write_text(git(source, "show", f"{base}:{case['file']}"))
        git(repo, "add", case["file"])
        git(repo, "commit", "-q", "-m", "base")
        if "patch" in case:
            git(repo, "apply", "-", stdin=case["patch"])
        else:
            target.write_text(git(source, "show", f"{case['sha']}:{case['file']}"))
        message = case["subject"].replace('"', "'")
        print(
            json.dumps(
                {
                    "id": case["id"],
                    "label": case["label"],
                    "kind": case["kind"],
                    "origin": case["origin"],
                    "cwd": str(repo),
                    "command": f'git commit -m "{message}" -- {case["file"]}',
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
