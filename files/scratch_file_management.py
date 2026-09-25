#!/usr/bin/env python3
"""Shared, bounded workspace checks; not a shell interpreter or a sandbox.

dangling-ref-check: allow
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

# Source checkout and installed bundle use the same legacy drafts implementation.
sys.path.insert(0, str(Path(__file__).resolve().parent / "claude_managed-hooks"))
import deny_drafts_commit as drafts


class Violation(Exception):
    pass


TMP = Path("/tmp")
# the per-session dir that session_cleanup.py removes; no other /tmp path is cleaned
SESSION_SCRATCH_RE = re.compile(r"/tmp/claude-scratch-[^/]+(?:/.*)?")
SESSION_SCRATCH_VAR_RE = re.compile(
    r"/tmp/claude-scratch-\$(?:CLAUDE_CODE_SESSION_ID|\{CLAUDE_CODE_SESSION_ID\})(?:/.*)?"
)
RECURSIVE_COPY_FLAGS = {"-r", "-R", "-a", "--recursive", "--archive"}
# states the whole rule so the fix is not /var/tmp for everything; kept long on purpose
TMP_MESSAGE = (
    "/tmp is small and often RAM-backed, and only the per-session scratch dir "
    "/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID/ is removed at session end; other /tmp "
    "paths, including a harness scratchpad, stay. Put small, short-lived temp in that "
    "scratch dir, and nothing in /tmp whose size is uncertain or can grow large (copied "
    "trees, logs, downloads, builds). Research notes, intermediate output and reports go "
    "in the repository's ignored drafts/ (confirm with git check-ignore first); what fits "
    "neither /tmp nor drafts/ goes in /var/tmp."
)


def _in_tmp(path):
    return path == TMP or TMP in path.parents


def _session_scratch(path):
    return bool(SESSION_SCRATCH_RE.fullmatch(str(path)))


# a /tmp path inside a fenced block of the final answer: a command handed to the user
FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
TMP_PATH_RE = re.compile(r"(?<![\w.-])/tmp(?:/|\b)")


def check_stop(payload):
    """Reject a final answer whose commands for the user write or read under /tmp."""
    if payload.get("stop_hook_active") or os.environ.get("CLAUDE_HOOK_CHILD"):
        return  # one rewrite per answer; a hook-spawned session has no user to hand commands to
    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        return
    if any(TMP_PATH_RE.search(block) for block in FENCE_RE.findall(message)):
        raise Violation(
            "A command handed to the user uses /tmp. "
            + TMP_MESSAGE
            + " Rewrite the answer."
        )


def git(cwd, *args):
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return result.stdout


@lru_cache(maxsize=128)
def root(cwd):
    try:
        return Path(git(cwd, "rev-parse", "--show-toplevel").strip()).resolve()
    except ValueError:
        return None


@lru_cache(maxsize=32)
def tracked_dirs(top):
    try:
        names = git(top, "ls-tree", "-r", "--name-only", "-z", "HEAD").split("\0")
    except ValueError:  # unborn repository
        names = []
    return {name.split("/", 1)[0] for name in names if "/" in name}


def allowed_dirs(top):
    path = top / ".workspace-layout.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text())
    entries = data.get("directories", {})
    if not isinstance(entries, dict) or any(
        not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
        or name in {".", "..", "drafts"}
        or not isinstance(reason, str)
        or not reason.strip()
        for name, reason in entries.items()
    ):
        raise Violation(
            "Invalid .workspace-layout.json: directories must map root names to user-request reasons."
        )
    return set(entries)


def check_path(cwd, name, *, directory=False):
    if "$TMPDIR" in name or "${TMPDIR}" in name:
        raise Violation(
            "Unresolved TMPDIR write: set and validate it in this same command, or use scratch_file_management run."
        )
    if not name or any(char in name for char in "$`*"):
        return  # Dynamic shell paths are outside this check's bounded grammar.
    path = Path(cwd, name).resolve()
    if _in_tmp(path):
        if _session_scratch(path):
            return
        raise Violation(TMP_MESSAGE)
    top = root(cwd)
    if top is None:
        return
    try:
        relative = path.relative_to(top)
    except ValueError:
        return
    parts = relative.parts
    if not parts:
        return
    if "drafts" in parts:
        probe = path / ".scratch-file-management-probe" if directory else path
        result = subprocess.run(
            ["git", "-C", str(top), "check-ignore", "-q", "--", str(probe)], check=False
        )
        if result.returncode:
            raise Violation(
                "drafts/ must be ignored before writing scratch files; add drafts/ to .gitignore."
            )
        return
    if (directory or len(parts) > 1) and parts[0] not in tracked_dirs(
        top
    ) | allowed_dirs(top):
        raise Violation(
            f"New repository root directory {parts[0]!r}: use ignored drafts/ for temporary output. "
            "For a user-requested permanent layout, record its name and request in .workspace-layout.json."
        )


def segments(command):
    # Skip heredoc bodies (including commit messages) rather than interpreting their contents.
    command = drafts.HEREDOC.sub(lambda match: "_" + match.group(2), command)
    lexer = shlex.shlex(
        command.replace("\\\n", " "), posix=True, punctuation_chars=";&|<>\n"
    )
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    words = []
    for token in [*lexer, ";"]:
        if token and all(c in ";&|\n" for c in token):
            if words:
                yield words
            words = []
        else:
            words.append(token)


def expand(value, variables):
    def replace(match):
        name = match.group(1) or match.group(2)
        return variables.get(name, "$" + name)

    return re.sub(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::\?[^}]*)?\}|\$([A-Za-z_][A-Za-z0-9_]*)",
        replace,
        value,
    )


def check_temp(words, variables, cwd):
    if not words or Path(words[0]).name != "mktemp":
        return
    dest = variables.get("TMPDIR", "")
    args = words[1:]
    skip = False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg in {"-p", "--tmpdir"} and index + 1 < len(args):
            dest = args[index + 1]
            skip = True
        elif arg.startswith("--tmpdir="):
            dest = arg.split("=", 1)[1]
        elif "/" in arg and not arg.startswith("-"):
            dest = str(Path(arg).parent)
    dest = expand(dest, variables)
    if SESSION_SCRATCH_VAR_RE.fullmatch(dest):
        return
    if not dest or "$" in dest or "`" in dest:
        raise Violation(
            "mktemp needs an explicit, nonempty scratch directory. Use scratch_file_management run -- COMMAND."
        )
    path = Path(cwd, dest).resolve()
    if _session_scratch(path):
        return
    if path == Path("/") or _in_tmp(path):
        raise Violation(TMP_MESSAGE)
    top = root(cwd)
    if path != Path("/var/tmp") and Path("/var/tmp") not in path.parents:
        if top is None or (
            path != top / "drafts" and top / "drafts" not in path.parents
        ):
            raise Violation(
                "Use owned command scratch under ignored drafts/ or permitted /var/tmp."
            )
        check_path(top, str(path), directory=True)


def check_git(cwd, args):
    if any(arg.split("=", 1)[0] in {"--git-dir", "--work-tree"} for arg in args):
        raise Violation(
            "Use git -C WORKTREE for checked add/commit operations; explicit Git directory overrides are not supported."
        )
    args = [
        part
        for arg in args
        for part in (
            ["-C", arg[2:]] if arg.startswith("-C") and len(arg) > 2 else [arg]
        )
    ]
    repo, subcommand, rest = drafts.split_global(args, str(cwd))
    if subcommand not in {"add", "commit"}:
        return
    top = root(repo)
    if top is None:
        return
    # Keep the tested drafts-reference checks, including commit -a and path commits.
    legacy = {
        "tool_name": "Bash",
        "cwd": str(cwd),
        "tool_input": {"command": shlex.join(["git", *args])},
    }
    if drafts.run(legacy):
        raise Violation(
            "drafts/ paths or newly added references must not be staged or committed."
        )
    if subcommand == "commit":
        names = git(top, "ls-files", "-z").split("\0")
    else:
        # Ask Git to resolve pathspecs without changing the real index or worktree.
        specs = []
        force = False
        after_dash = False
        for arg in rest:
            if arg == "--":
                after_dash = True
            elif not after_dash and arg.startswith("--pathspec-from-file"):
                raise Violation(
                    "Use explicit git add paths so scratch file management can check the selected files."
                )
            elif not after_dash and arg.startswith("-"):
                force |= arg == "--force" or (not arg.startswith("--") and "f" in arg)
            else:
                specs.append(arg)
        names = git(
            repo,
            "ls-files",
            "--full-name",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *specs,
        ).split("\0")
        if force:
            names += git(
                repo,
                "ls-files",
                "--full-name",
                "-z",
                "--others",
                "--ignored",
                "--exclude-standard",
                "--",
                *specs,
            ).split("\0")
    for name in filter(None, names):
        if drafts.in_drafts(name):
            raise Violation(
                f"Do not stage or commit drafts/ files: {name}. Untrack with git rm --cached; keep local files."
            )
        check_path(top, name)


def check_shell(command, cwd):
    variables = {"HOME": os.path.expanduser("~")}
    for words in segments(command):
        while words and (
            words[0] in {"env", "export"}
            or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])
        ):
            word = words.pop(0)
            if "=" in word:
                name, value = word.split("=", 1)
                variables[name] = expand(value, variables)
                if name == "TMPDIR" and (
                    not variables[name] or variables[name] in {"/", "/tmp"}
                ):
                    raise Violation(
                        "TMPDIR must be nonempty and scoped to owned scratch; use scratch_file_management run -- COMMAND."
                    )
        if not words:
            continue
        words = [expand(word, variables) for word in words]
        program = Path(words[0]).name
        if program == "cd" and len(words) == 2 and "$" not in words[1]:
            cwd = Path(cwd, words[1]).resolve()
        elif program == "git":
            if any(
                name in variables
                for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
            ):
                raise Violation(
                    "Git environment overrides cannot be checked here; use a normal worktree index."
                )
            check_git(cwd, words[1:])
        check_temp(words, variables, cwd)
        for index, word in enumerate(words[:-1]):
            if word in {">", ">>", "&>"}:
                if "$TMPDIR" in words[index + 1]:
                    raise Violation(
                        "Unresolved TMPDIR write: set and validate it in this same command, or use scratch_file_management run."
                    )
                check_path(cwd, words[index + 1])
        if program in {"mkdir", "touch", "tee"}:
            for word in words[1:]:
                if not word.startswith("-") and word not in {">", ">>", "<"}:
                    check_path(cwd, word, directory=program == "mkdir")
        elif program in {"cp", "mv", "install", "rsync"} and len(words) > 2:
            recursive = program == "rsync" or any(
                w in RECURSIVE_COPY_FLAGS for w in words[1:-1]
            )
            if (
                recursive
                and "$" not in words[-1]
                and _in_tmp(Path(cwd, words[-1]).resolve())
            ):
                raise Violation("A tree's size is uncertain. " + TMP_MESSAGE)
            check_path(cwd, words[-1])


def check(payload):
    if not isinstance(payload, dict):
        return
    if payload.get("hook_event_name") == "Stop":
        check_stop(payload)
        return
    if payload.get("hook_event_name", "PreToolUse") != "PreToolUse":
        return
    tool = payload.get("tool_name", "").rsplit(".", 1)[-1]
    inp = payload.get("tool_input", {})
    cwd = payload.get("cwd") or os.getcwd()
    if isinstance(inp, dict):
        cwd = inp.get("workdir") or cwd
    if tool in {"Bash", "exec_command", "shell_command"} and isinstance(inp, dict):
        command = inp.get("cmd", inp.get("command", ""))
        if isinstance(command, str):
            check_shell(command, cwd)
    elif tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"} and isinstance(
        inp, dict
    ):
        check_path(cwd, inp.get("file_path") or inp.get("notebook_path") or "")
    elif tool == "apply_patch":
        patch = (
            inp
            if isinstance(inp, str)
            else inp.get("command", inp.get("input", inp.get("patch", "")))
        )
        if isinstance(patch, str):
            for name in re.findall(
                r"^\*\*\* (?:Add File|Update File|Move to): (.+)$", patch, re.MULTILINE
            ):
                check_path(cwd, name)


def run_temp(command):
    top = root(Path.cwd())
    if top is None:
        raise Violation("Run from a Git worktree with ignored drafts/.")
    if Path(command[0]).name == "git":
        check_git(Path.cwd(), command[1:])
    check_path(top, "drafts", directory=True)
    scratch = top / "drafts"
    if scratch.is_symlink():
        raise Violation(
            "Refusing symlink drafts/ for command scratch; preserve its existing target."
        )
    scratch.mkdir(exist_ok=True)
    # TemporaryDirectory removes only the unique directory created by this invocation.
    with tempfile.TemporaryDirectory(prefix="command-", dir=scratch) as owned:
        return subprocess.run(
            command, env={**os.environ, "TMPDIR": owned}, check=False
        ).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["hook", "run"], nargs="?", default="hook")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == "run":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                parser.error("run requires a command")
            return run_temp(command)
        check(json.load(sys.stdin))
    except Violation as exc:
        print(f"scratch-file-management: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        # Unsupported shell syntax and Git failures are visible, never advertised as checked.
        print(f"scratch-file-management: unable to check: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
