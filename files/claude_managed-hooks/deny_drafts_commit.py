#!/usr/bin/env python3
"""PreToolUse(Bash) hook: keep drafts/ scratch files, and added references to them, out of git.

dangling-ref-check: allow (this hook quotes the drafts/ rule it enforces)

Exit:
  0: not `git add` / `git commit`, nothing drafts-related would be recorded, or any parse / git error
  2: `git add` of a drafts/ path, or a commit recording a drafts/ path or an added drafts/ reference
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

from check_dangling_refs import (
    DRAFTS_REF,
    OPT_OUT_RE,
    drafts_exempt,
    in_drafts,
    run_git,
)

HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?^[ \t]*\1\b", re.MULTILINE
)
ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=.*")
OPERATOR_CHARS = ";&|()"
GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
COMMIT_VALUE_LONGS = frozenset(
    {
        "--message",
        "--file",
        "--author",
        "--date",
        "--template",
        "--reuse-message",
        "--reedit-message",
        "--fixup",
        "--squash",
        "--cleanup",
        "--trailer",
        "--pathspec-from-file",
    }
)
COMMIT_VALUE_SHORTS = frozenset("mFCct")
DIFF = ("-c", "core.quotepath=false", "diff", "--no-renames", "--diff-filter=ACMR")

# Deny text is deliberately verbose (cause, fix per case, no side effects); do not trim.
GUIDANCE = (
    "直し方:\n"
    "- drafts/ 配下の path は `git add` しない。 stage 済みなら、 未 commit の file は"
    " `git restore --staged -- <path>`、 追跡済みの file は `git rm --cached -- <path>` で index から外す"
    " (手元の file は残る)。 repo の .gitignore に `drafts/` が無ければ足す\n"
    "- drafts/ は他の環境にも他の reader にも存在しない。 参照が要る内容は本文に直接書くか、"
    " tracked な場所へ移してからその path を書く\n"
    "- drafts/ の path を機械的に照合する code など意図的な場合に限り、 その file に"
    " `dangling-ref-check: allow` を置く\n"
    "この hook は file も index も変更しない。\n"
)


def git_invocations(command: str):
    """Yield (argv after `git`) for each shell segment whose program is git."""
    text = HEREDOC.sub(lambda m: "_" + m.group(2), command)
    text = text.replace("\\\n", " ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=OPERATOR_CHARS)
    lexer.whitespace_split = True
    words: list[str] = []
    for token in [*lexer, ";"]:
        if token and all(char in OPERATOR_CHARS for char in token):
            while words and ASSIGNMENT.fullmatch(words[0]):
                words.pop(0)
            if words and os.path.basename(words[0]) == "git":
                yield words[1:]
            words = []
        else:
            words.append(token)


def split_global(argv: list[str], cwd: str) -> tuple[str, str, list[str]]:
    repo = cwd
    while argv and argv[0].startswith("-"):
        if argv[0] == "-C" and len(argv) > 1:
            repo = os.path.join(repo, argv[1])
        argv = argv[2:] if argv[0] in GIT_VALUE_OPTIONS else argv[1:]
    return repo, (argv[0] if argv else ""), argv[1:]


def toplevel(repo: str) -> str | None:
    if not os.path.isdir(repo):
        return None
    proc = run_git(repo, "rev-parse", "--show-toplevel")
    if proc is None or proc.returncode != 0:
        return None
    return os.path.realpath(proc.stdout.strip())


def added_drafts(repo: str, args: list[str]) -> set[str]:
    top = toplevel(repo)
    if top is None:
        return set()
    if "--" in args:
        split = args.index("--")
        specs = [a for a in args[:split] if not a.startswith("-")] + args[split + 1 :]
    else:
        specs = [a for a in args if not a.startswith("-")]
    rels = (
        os.path.relpath(os.path.realpath(os.path.join(repo, spec)), top)
        for spec in specs
    )
    return {rel for rel in rels if not rel.startswith("..") and in_drafts(rel)}


def commit_pathspecs(args: list[str]) -> tuple[list[str], bool]:
    """(pathspecs, whether -a / --all) of a `git commit` argv, skipping option values."""
    paths: list[str] = []
    all_flag = False
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--":
            paths += args[index:]
            break
        if arg.startswith("--"):
            name = arg.split("=", 1)[0]
            all_flag = all_flag or name == "--all"
            if name in COMMIT_VALUE_LONGS and "=" not in arg:
                index += 1
        elif arg.startswith("-") and len(arg) > 1:
            for pos, char in enumerate(arg[1:], 1):
                all_flag = all_flag or char == "a"
                if char in COMMIT_VALUE_SHORTS:
                    if pos == len(arg) - 1:
                        index += 1
                    break
        else:
            paths.append(arg)
    return paths, all_flag


def recorded(repo: str, *args: str) -> tuple[list[str], dict[str, list[str]]] | None:
    """(changed paths, added lines per path) of one diff, or None when git fails."""
    names = run_git(repo, *DIFF, "--name-only", "-z", *args)
    patch = run_git(repo, *DIFF, "--no-color", "--no-ext-diff", "-U0", *args)
    if names is None or patch is None or names.returncode or patch.returncode:
        return None
    added: dict[str, list[str]] = {}
    current = None
    previous = ""
    for line in patch.stdout.splitlines():
        if previous.startswith("--- ") and line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif current is not None and line.startswith("+"):
            added.setdefault(current, []).append(line[1:])
        previous = line
    return [name for name in names.stdout.split("\0") if name], added


def has_marker(top: str, rel: str) -> bool:
    try:
        with open(os.path.join(top, rel), encoding="utf-8", errors="replace") as fh:
            return bool(OPT_OUT_RE.search(fh.read()))
    except OSError:
        return False


def commit_findings(
    repo: str, args: list[str]
) -> tuple[set[str], set[tuple[str, str]]]:
    top = toplevel(repo)
    if top is None:
        return set(), set()
    paths, all_flag = commit_pathspecs(args)
    sources: list[tuple[str, ...]] = [("--cached",)]
    if all_flag:
        sources.append(("HEAD",))
    elif paths:
        sources.append(("HEAD", "--", *paths))
    files: set[str] = set()
    refs: set[tuple[str, str]] = set()
    for source in sources:
        result = recorded(repo, *source)
        if result is None:
            continue
        names, added = result
        files |= {name for name in names if in_drafts(name)}
        for rel, lines in added.items():
            if in_drafts(rel) or drafts_exempt(rel) or has_marker(top, rel):
                continue
            refs |= {
                (rel, m.group(0)) for line in lines for m in DRAFTS_REF.finditer(line)
            }
    return files, refs


def message(files: set[str], refs: set[tuple[str, str]]) -> str:
    lines = [
        "deny-drafts-commit: drafts/ は gitignore された scratch 置き場で、 git に記録しない。",
        "",
    ]
    if files:
        lines += [
            "記録されかけた drafts/ 配下の path:",
            *(f"  - {p}" for p in sorted(files)),
            "",
        ]
    if refs:
        lines += [
            "drafts/ 配下を指す追加行:",
            *(f"  - {p}: {r}" for p, r in sorted(refs)),
            "",
        ]
    return "\n".join(lines) + "\n" + GUIDANCE


def run(payload: object) -> int:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or "git" not in command:
        return 0
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) else os.getcwd()
    files: set[str] = set()
    refs: set[tuple[str, str]] = set()
    for argv in git_invocations(command):
        repo, subcommand, args = split_global(argv, cwd)
        if subcommand == "add":
            files |= added_drafts(repo, args)
        elif subcommand == "commit":
            found_files, found_refs = commit_findings(repo, args)
            files |= found_files
            refs |= found_refs
    if not files and not refs:
        return 0
    sys.stderr.write(message(files, refs))
    return 2


def main() -> int:
    try:
        return run(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
