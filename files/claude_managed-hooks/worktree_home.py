#!/usr/bin/env python3
"""WorktreeCreate / WorktreeRemove hook: Claude Code worktrees go to ~/worktrees/<repo>/<name>, as Codex's do.
EnterWorktree(path) outside .claude/worktrees/ always prompts, so Claude enters these by name through this hook."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / "worktrees"
NAME_RE = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")


def git(*args: str, cwd: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )


def fail(message: str) -> int:
    print(f"worktree_home: {message}", file=sys.stderr)
    return 1


def common_dir(cwd: str | Path) -> Path | None:
    result = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def ref_exists(ref: str, cwd: Path) -> bool:
    return git("rev-parse", "--verify", "--quiet", ref, cwd=cwd).returncode == 0


def create(payload: dict) -> int:
    name = payload.get("name") or ""
    if not NAME_RE.fullmatch(name) or ".." in name.split("/"):
        return fail(f"unsupported worktree name: {name!r}")
    common = common_dir(payload.get("cwd") or ".")
    if common is None:
        return fail("not inside a git repository")
    target = ROOT / common.parent.name / name
    if not target.is_dir():
        if ref_exists(f"refs/heads/{name}", common):
            args = [str(target), name]
        else:
            args = [
                "-b",
                name,
                str(target),
                "origin/HEAD" if ref_exists("origin/HEAD", common) else "HEAD",
            ]
        added = git("worktree", "add", *args, cwd=common)
        if added.returncode:
            return fail(added.stderr.strip())
    print(target)
    return 0


def remove(payload: dict) -> int:
    path = Path(payload.get("worktree_path") or "")
    if not path.is_dir():
        return 0
    common = common_dir(path)
    if common is None:
        return fail(f"not a git worktree: {path}")
    branch = git("branch", "--show-current", cwd=path).stdout.strip()
    # No --force: a worktree holding changes stays; branch -d deletes only a merged branch.
    removed = git("worktree", "remove", str(path), cwd=common)
    if removed.returncode:
        return fail(removed.stderr.strip())
    if branch:
        git("branch", "-d", branch, cwd=common)
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    handler = {"WorktreeCreate": create, "WorktreeRemove": remove}.get(
        payload.get("hook_event_name")
    )
    return (
        handler(payload)
        if handler
        else fail(f"unexpected event: {payload.get('hook_event_name')}")
    )


if __name__ == "__main__":
    sys.exit(main())
