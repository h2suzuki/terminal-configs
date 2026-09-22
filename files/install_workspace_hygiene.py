#!/usr/bin/env python3
"""Install just shared workspace hygiene; --root stages a reproducible fixture."""

import argparse
import json
import shutil
import sys
from pathlib import Path

import tomllib

COMMAND = "/usr/local/bin/workspace_hygiene hook"
MATCHER = (
    "^(Bash|exec_command|shell_command|apply_patch|Write|Edit|MultiEdit|NotebookEdit)$"
)


def link_user_skill(home):
    target = home / ".claude/skills/workspace-hygiene"
    expected = Path("/etc/claude-code/skills/workspace-hygiene")
    if target.is_symlink() and target.readlink() == expected:
        return
    if target.exists() or target.is_symlink():
        raise ValueError(f"Preserving conflicting user skill: {target}")
    if not (expected / "SKILL.md").is_file():
        raise ValueError("Install the machine-wide workspace-hygiene skill first.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(expected, target_is_directory=True)


def install(source, root):
    def destination(name):
        path = root / name.lstrip("/")
        # Never follow a peer's symlink while installing machine-wide files.
        if path.is_symlink() or any(
            p.is_symlink() for p in path.parents if p != root.parent
        ):
            raise ValueError(f"Refusing symlink destination: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def copy(name, target, mode=0o644):
        path = destination(target)
        shutil.copyfile(source / name, path)
        path.chmod(mode)

    copy(
        "workspace_hygiene.py",
        "/usr/local/lib/workspace_hygiene/workspace_hygiene.py",
        0o755,
    )
    for name in ("deny_drafts_commit.py", "check_dangling_refs.py"):
        copy("claude_managed-hooks/" + name, "/usr/local/lib/workspace_hygiene/" + name)
    wrapper = destination("/usr/local/bin/workspace_hygiene")
    wrapper.write_text(
        '#!/bin/sh\nexec python3 /usr/local/lib/workspace_hygiene/workspace_hygiene.py "$@"\n'
    )
    wrapper.chmod(0o755)
    for client in ("claude-code", "codex"):
        copy(
            "shared_skills/workspace-hygiene/SKILL.md",
            f"/etc/{client}/skills/workspace-hygiene/SKILL.md",
        )
    copy(
        "claude_managed-skills/temp-file-discipline/SKILL.md",
        "/etc/claude-code/skills/temp-file-discipline/SKILL.md",
    )

    path = destination("/etc/claude-code/managed-settings.d/extensions.json")
    data = json.loads(path.read_text()) if path.exists() else {}
    groups = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for group in groups:
        group["hooks"] = [
            h
            for h in group.get("hooks", [])
            if h.get("command")
            not in {
                COMMAND,
                "/etc/claude-code/hooks/tmpdir_scratch_gate.py",
                "/etc/claude-code/hooks/deny_drafts_commit.py",
            }
        ]
    groups[:] = [g for g in groups if g.get("hooks")]
    groups.append(
        {
            "matcher": MATCHER,
            "hooks": [{"type": "command", "command": COMMAND, "timeout": 30}],
        }
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    path = destination("/etc/codex/config.toml")
    text = path.read_text() if path.exists() else ""
    config = tomllib.loads(text)
    registered = [
        h
        for g in config.get("hooks", {}).get("PreToolUse", [])
        for h in g.get("hooks", [])
        if h.get("command") == COMMAND
    ]
    if not registered:
        text += (
            "\n[[hooks.PreToolUse]]\nmatcher = "
            + json.dumps(MATCHER)
            + '\n\n[[hooks.PreToolUse.hooks]]\ntype = "command"\ncommand = '
            + json.dumps(COMMAND)
            + "\ntimeout = 30\n"
        )
        tomllib.loads(text)
        path.write_text(text)
    print(
        f"Placed workspace hygiene under {root}; restart clients and inspect /hooks and skill discovery."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument(
        "--user",
        action="store_true",
        help="link the installed skill for the current Claude user only",
    )
    args = parser.parse_args()
    try:
        if args.user:
            link_user_skill(Path.home())
        else:
            install(Path(__file__).resolve().parent, args.root.resolve())
    except (OSError, ValueError) as exc:
        print(f"workspace-hygiene install failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
