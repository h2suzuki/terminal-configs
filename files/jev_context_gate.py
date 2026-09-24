"""Before `git commit`, judge with Jev whether each added hunk fits its context and each added file its place;
the jev server calls check(). Only a clear "does not fit" denies; any Jev, key, or network failure skips and tells the user."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

DENY_BELOW = 0.5  # real README commits: misplaced text ≤ 0.25, fitting ≥ 0.72
QUESTION_VERSION = "fdet-8"
STATE_LIMIT = 12000  # characters of JSON state per request; Jev caps state plus question at 32k tokens
CHUNK_LIMIT = 1500  # characters of added text per judged piece
AROUND = 6
TOP_LEVEL = "(top level of the file)"
OUTLINE_LIMIT = 40
ROLE_LIMIT = 600
BODY_LIMIT = 300
SECTION_LIMIT = 5000
SIBLING_LIMIT = 1200
HEAD_LIMIT = 200
OPENING_LIMIT = 3000
DEADLINE = float(os.environ.get("JEV_CONTEXT_GATE_DEADLINE", "25"))
LOG = os.environ.get("JEV_CONTEXT_GATE_LOG") or os.path.expanduser(
    "~/.claude/hooks/state/jev_context_gate/log.jsonl"
)
MARKDOWN = {".md", ".markdown"}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SCOPE_RE = re.compile(
    r"^\s*(?:"
    r"(?:async\s+)?def\s"
    r"|(?:export\s+)?(?:default\s+)?class\s"
    r"|(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s"
    r"|(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^()]*\)(?:\s*:\s*[^=]+?)?|[A-Za-z_$][\w$]*)\s*=>\s*\{"
    r"|(?:export\s+)?(?:declare\s+)?(?:interface|enum|namespace|module)\s"
    r"|(?:export\s+)?(?:declare\s+)?type\s+[A-Za-z_$][\w$]*(?:<[^=]*>)?\s*=\s*\{"
    r"|(?:pub\s+)?fn\s"
    r"|func\s"
    r"|\[[^\]]+\]\s*$"
    r"|(?:describe|it|test)(?:\.\w+)*\s*\(.*\{\s*$"
    # method/accessor definitions, excluding control-flow statements of the same "name(...) {" shape
    r"|(?:(?:static|async|get|set|public|private|protected|readonly|override|abstract)\s+){0,4}"
    r"(?!if\b|for\b|while\b|switch\b|catch\b|else\b|function\b|return\b)"
    r"#?[A-Za-z_][\w:$-]*\s*\([^()]*\)(?:\s*:\s*[^{};=]+?)?\s*\{"
    r")"
)
TEST_SCOPE_RE = re.compile(
    r"(?:async\s+)?def\s+test|(?:describe|it|test)(?:\.\w+)*\s*\("
)
HEREDOC_RE = re.compile(r"\A\$\(cat <<-?(['\"]?)(\w+)\1\n(.*?)\n\2\n?\)\Z", re.S)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
LINK_RE = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
LIST_RE = re.compile(r"^\s*[-*+]\s|^\s*\d+\.\s")

SLOTS = (
    "`form.background_of_change` says what the commit does and `form.file_kind_and_role` what kind of file "
    "`document.file` is. `{h}.place_and_its_purpose` names the {place} into which `{p}.added_lines` was inserted "
    "(between `{p}.lines_before` and `{p}.lines_after`) and what that {place} is for; "
)
# Wording is the variant measured on real README commits, including the optional audience slot it names.
FIT = {
    "docs": (
        SLOTS.replace("{place}", "section")
        + "`{h}.audience_of_this_place`, when present, says who reads it; `{h}.style_of_this_place` "
        "describes how the section's existing content is written; `{p}.what_the_edit_adds` describes the added text. "
        "Does the added text give the reader of this section what they came for?",
        "The added text is what a reader who came to this section for its stated purpose needs at this point: "
        "the same topic, the same reader, the same level of detail and the same terse style as `{p}.lines_before` "
        "and `{p}.lines_after`.",
        "The added text serves a different reader or purpose: it explains how the project's own scripts, source "
        "files or tests work behind the scenes; states rules for maintainers or editors (source-of-truth files, "
        "sync rules, tests to run, permission mappings between tools); reports research, evidence, verification "
        "dates or caveats about external documentation; adds reference detail beyond what the surrounding steps "
        "give; or belongs under a different heading.",
    ),
    "code": (
        SLOTS.replace("{place}", "scope")
        + "`{h}.style_of_this_place` lists the file's definitions before this change; `{p}.what_the_edit_adds` "
        "describes the added lines. Do the added lines carry out the responsibility of that scope?",
        "The added lines carry out or support the responsibility that the scope's name describes, in the same "
        "style as the surrounding lines.",
        "The added lines do a different job (a side effect, an unrelated feature, or I/O the scope does not call "
        "for), or they belong in a different function, module, or file.",
    ),
    "test": (
        SLOTS.replace("{place}", "test")
        + "`{h}.style_of_this_place` lists the file's tests before this change; `{p}.what_the_edit_adds` "
        "describes the added lines. Do the added lines check what that test is about?",
        "The added lines check or set up the behavior that the test's name and existing assertions are about.",
        "The added lines check something unrelated to the test's name, such as a different feature or a detail "
        "of the test file itself.",
    ),
    "module": (
        "`form.background_of_change` says what the commit does and `form.file_kind_and_role` what kind of file "
        "`document.file` is. `{p}.added_lines` was added at the top level of the file, outside any function or "
        "test (between `{p}.lines_before` and `{p}.lines_after`); `{h}.style_of_this_place` lists the file's "
        "definitions before this change; `{p}.what_the_edit_adds` describes the added lines. Do the added lines "
        "belong at the top level of this file?",
        "The added lines are top-level content this kind of file keeps: imports, constants, module setup, or new "
        "functions, classes or tests that fit the file's role and the background of the change.",
        "The added lines are statements that belong inside an existing function or test, content of another "
        "language or file type, or code unrelated to the file's role.",
    ),
}
STYLE = (
    "The section `{s}.new_section` (heading `{s}.heading`) was newly added to `document.file`, a document whose "
    "role is `document.file_role`. Its sibling sections at the same level are listed in `{s}.sibling_sections` "
    "with the same counted statistics and, where given, their text. Is the new section written in the same "
    "style and at the same level of detail as its siblings?",
    "Same kind of content per topic as the siblings: short paragraphs and command blocks, about the same "
    "amount of text per subsection, no structures the siblings do not use. A reader moving between the "
    "sections would notice no change of author or register.",
    "Noticeably more elaborate than the siblings: comparison tables, many external reference links, "
    "verification dates, caveats about what documentation does or does not say, or explanations of why "
    "something works; or much more text per topic than the siblings give.",
)
NEW_FILE = (
    "`{f}.path` is a file this commit adds to the repository. `form.background_of_change` says what the commit "
    "does; `{f}.file_kind_and_role`, `{f}.shape` and `{f}.opening` show what the file is; `{f}.directory_neighbors` "
    "lists what the repository already keeps in `{f}.directory`, the file's directory or, when that directory is "
    "new, its nearest existing parent (subdirectories end in a slash). Is this file "
    "finished repository content that belongs at this path?",
    "The file is maintained project content (source, test, configuration, or documentation written for its "
    "readers) of the kind, naming and language that `{f}.directory_neighbors` shows this directory keeps.",
    "The file is working material kept in its raw form (a draft, notes, a requirements or design memo, a plan, "
    "a session log, a review report, or a conversation transcript) rather than content distilled for its readers; "
    "or it is a kind of file that `{f}.directory_neighbors` shows this directory does not keep, such as a prose "
    "document at the top level of a repository that keeps its documents in a docs directory.",
)
PLACEMENT_MISFIT = "置いた場所の文脈に合いません (配置の問い)"
STYLE_MISFIT = "新しい節の書きぶりが同じ階層の節と合いません (節の書きぶりの問い)"
NEW_FILE_MISFIT = "この場所に置く完成したファイルではありません (新規ファイルの問い)"


class Skip(Exception):
    """Jev could not give a verdict; the commit proceeds and the user is told why."""


def commit_message(options: list[str]) -> str:
    parts, rest = [], iter(options)
    for option in rest:
        if option in {"-m", "--message"}:
            parts.append(next(rest, ""))
        elif option.startswith("--message="):
            parts.append(option.split("=", 1)[1])
        elif option.startswith("-m") and len(option) > 2:
            parts.append(option[2:])
    # shlex leaves -m "$(cat <<'EOF' ... EOF)" unexpanded; the commit hooks require that form.
    parts = [(m.group(3) if (m := HEREDOC_RE.match(p)) else p) for p in parts]
    return "\n\n".join(p for p in parts if p)


def commit_target(payload: dict) -> tuple[Path, list[str], bool, bool, str] | None:
    if str(payload.get("tool_name", "")).rsplit(".", 1)[-1] not in {
        "Bash",
        "exec_command",
        "shell_command",
    }:
        return None
    inp = payload.get("tool_input")
    if not isinstance(inp, dict):
        return None
    command = inp.get("cmd", inp.get("command"))
    try:
        words = shlex.split(command) if isinstance(command, str) else []
    except ValueError:
        return None
    cwd = Path(inp.get("workdir") or payload.get("cwd") or ".")
    start = next((i for i, w in enumerate(words) if os.path.basename(w) == "git"), None)
    if start is None:
        return None
    rest = words[start + 1 :]
    while rest and rest[0].startswith("-"):
        option = rest.pop(0)
        if option in {"-C", "-c"} and rest:
            value = rest.pop(0)
            cwd = cwd / value if option == "-C" else cwd
    if not rest or rest[0] != "commit":
        return None
    args = rest[1:]
    paths = args[args.index("--") + 1 :] if "--" in args else []
    options = args[: args.index("--")] if "--" in args else args
    all_tracked = any(
        o == "--all" or (re.fullmatch(r"-[a-zA-Z]+", o) and "a" in o) for o in options
    )
    return cwd, paths, "--amend" in options, all_tracked, commit_message(options)


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )


def changed_hunks(
    cwd: Path, paths: list[str], amend: bool, all_tracked: bool
) -> list[dict]:
    base = "HEAD^" if amend else "HEAD"
    if git(cwd, "rev-parse", "--verify", "--quiet", base).returncode:
        return []
    worktree = bool(paths) or all_tracked
    diff = git(cwd, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
               *([] if worktree else ["--cached"]), base, "--", *paths)  # fmt: skip
    hunks, name, new_file = [], None, False
    for line in diff.stdout.splitlines():
        if line.startswith("diff --git "):
            name, new_file = None, False
        elif line.startswith("--- /dev/null"):
            new_file = True
        elif line.startswith("+++ "):
            name = None if line == "+++ /dev/null" else line[6:]
        elif name and (match := HUNK_RE.match(line)):
            hunks.append({"file": name, "start": int(match.group(1)), "added": [], "new": new_file})  # fmt: skip
        elif name and hunks and hunks[-1]["file"] == name and line.startswith("+"):
            hunks[-1]["added"].append(line[1:])
    top = git(cwd, "rev-parse", "--show-toplevel").stdout.strip() or str(cwd)
    images: dict[str, tuple[list[str], list[str]]] = {}
    for hunk in hunks:
        if (name := hunk["file"]) not in images:
            text = (
                (Path(top) / name).read_text(errors="replace")
                if worktree
                else git(cwd, "show", f":{name}").stdout
            )
            pre = git(cwd, "show", f"{base}:{name}").stdout
            images[name] = (text.splitlines(), pre.splitlines())
        hunk["image"], hunk["pre"] = images[hunk["file"]]
        if hunk["new"]:
            hunk["neighbors"] = neighbors(cwd, base, hunk["file"])
    return [h for h in hunks if any(line.strip() for line in h["added"])]


def neighbors(cwd: Path, base: str, name: str) -> tuple[str, list[str]]:
    """(directory, entries) the base commit keeps where `name` is added, or in its nearest existing parent
    when that directory is new; subdirectories end in a slash."""
    folder, found = os.path.dirname(name), []
    while True:
        listing = git(cwd, "ls-tree", "--full-tree", base, *(["--", f"{folder}/"] if folder else []))  # fmt: skip
        for row in listing.stdout.splitlines():
            meta, _, path = row.partition("\t")
            found.append(
                os.path.basename(path) + ("/" if meta.split()[1] == "tree" else "")
            )
        if found or not folder:
            break
        folder = os.path.dirname(folder)
    extra = len(found) - OUTLINE_LIMIT
    return folder or "(top level)", found[:OUTLINE_LIMIT] + (
        [f"(and {extra} more)"] if extra > 0 else []
    )


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    found, fenced = [], False
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            fenced = not fenced
        elif not fenced and (match := HEADING_RE.match(line)):
            found.append((i, len(match.group(1)), match.group(2)))
    return found


def section_end(heads: list[tuple[int, int, str]], pos: int, total: int) -> int:
    return next((i for i, lv, _ in heads[pos + 1 :] if lv <= heads[pos][1]), total)


def first_paragraph(lines: list[str], start: int, stop: int) -> str:
    text: list[str] = []
    for line in lines[start:stop]:
        if HEADING_RE.match(line) or (text and not line.strip()):
            break
        if line.strip():
            text.append(line.strip())
    return " ".join(text)[:ROLE_LIMIT]


def file_role(lines: list[str], markdown: bool) -> str:
    if markdown:
        heads = headings(lines)
        title = heads[0][2] if heads else ""
        body = first_paragraph(lines, heads[0][0] + 1 if heads else 0, len(lines))
        return f"{title}: {body}".strip(": ")
    body = [line for line in lines[:40] if not line.startswith("#!")]
    text = "\n".join(body).lstrip()
    if (quote := text[:3]) in {'"""', "'''"}:
        return text[3:].split(quote, 1)[0].strip()[:ROLE_LIMIT]
    comments = []
    for line in body:
        if not line.strip().startswith(("#", "//")):
            break
        comments.append(line.strip().lstrip("#/ "))
    return " ".join(comments)[:ROLE_LIMIT]


def stats(lines: list[str]) -> dict:
    text = "\n".join(lines)
    return {
        "lines": sum(1 for line in lines if line.strip()),
        "paragraphs": sum(1 for p in re.split(r"\n\s*\n", text) if p.strip()),
        "table_rows": sum(1 for line in lines if TABLE_RE.match(line)),
        "code_blocks": sum(1 for line in lines if FENCE_RE.match(line)) // 2,
        "external_links": len(LINK_RE.findall(text)),
        "subheadings": sum(1 for line in lines if HEADING_RE.match(line)),
    }


def shape_sentence(lines: list[str]) -> str:
    # Counted in code so that Jev compares stated numbers instead of estimating them.
    kinds = []
    if any(HEADING_RE.match(line) for line in lines):
        kinds.append("a heading")
    if rows := sum(1 for line in lines if TABLE_RE.match(line)):
        kinds.append(f"table rows ({rows})")
    if any(LIST_RE.match(line) for line in lines):
        kinds.append("a bullet or numbered list")
    if any(FENCE_RE.match(line) or line.startswith("    $") for line in lines):
        kinds.append("a command block")
    outside, fenced = [], False
    for line in lines:
        fenced ^= bool(FENCE_RE.match(line))
        outside.append("" if fenced or FENCE_RE.match(line) else line)
    text = "\n".join(outside)
    prose = [
        p
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
        and not TABLE_RE.match(p.strip().splitlines()[0])
        and not HEADING_RE.match(p.strip())
    ]
    if prose:
        longest = max(len(p) for p in prose)
        size = "short" if longest < 160 else "medium" if longest < 320 else "long"
        kinds.append(
            f"{len(prose)} prose paragraph(s), longest {size} ({longest} characters)"
        )
    links = len(LINK_RE.findall(text))
    kinds.append(f"{links} external link(s)" if links else "no external links")
    codes = len(re.findall(r"`[^`]+`", text))
    kinds.append(f"{codes} inline code span(s) (paths, commands, keys)")
    count = sum(1 for line in lines if line.strip())
    return f"{count} non-empty line(s): " + ", ".join(kinds) + "."


def markdown_place(lines: list[str], index: int) -> tuple[str, str]:
    heads, chain = headings(lines), []
    for head in heads:
        if head[0] > index:
            break
        chain = [c for c in chain if c[1] < head[1]] + [head]
    location = " > ".join(c[2] for c in chain) or "(before the first heading)"
    # The title's intro is already in file_kind_and_role; an intro stops before the edit so it never quotes it.
    intros = [
        (c[2], first_paragraph(lines, c[0] + 1, index)) for c in chain if c != heads[0]
    ]
    purpose = " ".join(f"Section '{title}: {text}'" for title, text in intros if text)
    return location, f"{location}. {purpose}".rstrip()


def markdown_style(pre: list[str], location: str) -> str:
    heads = headings(pre)
    for title in reversed(location.split(" > ")):
        for pos, (i, _, name) in enumerate(heads):
            if name == title:
                body = pre[i + 1 : section_end(heads, pos, len(pre))]
                return f"Existing content of the section '{title}' before this change: {shape_sentence(body)}"
    return f"Section is new; whole document before this change: {shape_sentence(pre)}"


def json_walk(lines: list[str]) -> tuple[list[list[str]], list[str]]:
    """Every key path in order of appearance, and the keys still open after the last line."""
    stack: list[str | None] = []
    keys: list[list[str]] = []
    pending = last = None
    in_string = escaped = False
    buffer: list[str] = []
    for ch in "\n".join(lines):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string, last = False, "".join(buffer)
            else:
                buffer.append(ch)
        elif ch == '"':
            in_string, buffer = True, []
        elif ch == ":" and last is not None:
            pending = last
            keys.append([k for k in stack if k is not None] + [last])
        elif ch in "{[":
            stack.append(pending)
            pending = last = None
        elif ch in "}],":
            if ch != "," and stack:
                stack.pop()
            pending = last = None
    return keys, [k for k in stack if k is not None]


def code_scope(lines: list[str], index: int) -> str:
    indent, chain = len(lines[index]) - len(lines[index].lstrip()), []
    for line in reversed(lines[:index]):
        depth, text = len(line) - len(line.lstrip()), line.strip()
        if not text or depth >= indent or text[0] in ")]}":
            continue
        if SCOPE_RE.match(line):
            chain.insert(0, text[:80])
            indent = depth
        elif text.endswith(("{", ":")):
            # An unnamed block still encloses the line, so a sibling above it must not pass for the scope.
            indent = depth
    return " > ".join(chain) or TOP_LEVEL


def paragraphs(
    added: list[str], first: int, markdown: bool
) -> list[tuple[int, list[str]]]:
    # Judged whole, a long new section scored as fitting; so Markdown splits on blank lines, but a code fragment had no place of its own.
    found, chunk, fenced, begin = [], [], False, first
    for offset, line in enumerate([*added, None]):
        heading_only = all(HEADING_RE.match(c) or not c.strip() for c in chunk)
        opens_block = line is not None and FENCE_RE.match(line) and not fenced
        new_paragraph = (
            markdown and not fenced and line is not None and line.strip() and chunk and not chunk[-1].strip()
        )  # fmt: skip
        full = (
            line is not None and chunk and len("\n".join([*chunk, line])) > CHUNK_LIMIT
        )
        if chunk and (
            line is None or full or (new_paragraph and not heading_only and not opens_block)
        ):  # fmt: skip
            while not chunk[-1].strip():
                chunk.pop()
            found.append((begin, chunk))
            chunk = []
        if line is None:
            break
        if FENCE_RE.match(line):
            fenced = not fenced
        if not chunk:
            if not line.strip():
                continue
            begin = first + offset
        chunk.append(line[:CHUNK_LIMIT])
    return found


def places(hunks: list[dict]) -> list[dict]:
    """Consecutive pieces of one file under the same place, each place with its slots filled in code."""
    found: list[dict] = []
    for hunk in (h for h in hunks if not h["new"]):
        name, image, pre = hunk["file"], hunk["image"], hunk["pre"]
        markdown = Path(name).suffix in MARKDOWN
        for begin, chunk in paragraphs(hunk["added"], hunk["start"] - 1, markdown):
            at = min(begin, len(image) - 1)
            if markdown:
                kind, (location, place) = "docs", markdown_place(image, at)
                style, adds = markdown_style(pre, location), shape_sentence(chunk)
            elif Path(name).suffix == ".json":
                location = place = " > ".join(json_walk(image[:at])[1]) or TOP_LEVEL
                outline = dict.fromkeys(
                    " > ".join(path) for path in json_walk(pre)[0] if len(path) <= 2
                )
                style = "Keys before this change: " + (
                    "; ".join(list(outline)[:OUTLINE_LIMIT]) or "(none)"
                )
                adds = (
                    f"{sum(1 for c in chunk if c.strip())} non-empty line(s) of code."
                )
                kind = "module" if location == TOP_LEVEL else "code"
            else:
                location = place = code_scope(image, at)
                # Fixtures and helpers in a test file have a job to do, not a behavior to check.
                kind = (
                    "test" if TEST_SCOPE_RE.match(location.split(" > ")[-1]) else "code"
                )
                scopes = [line.strip()[:80] for line in pre if SCOPE_RE.match(line)]
                style = "Definitions before this change: " + (
                    "; ".join(scopes[:OUTLINE_LIMIT]) or "(none)"
                )
                adds = (
                    f"{sum(1 for c in chunk if c.strip())} non-empty line(s) of {kind}."
                )
                # A scope question has no scope to ask about at the top level of the file.
                kind = "module" if location == TOP_LEVEL else kind
            text = "\n".join(chunk)
            piece = {
                "what_the_edit_adds": adds,
                "lines_before": image[max(0, begin - AROUND) : begin],
                "added_lines": text,
                "lines_after": image[begin + len(chunk) : begin + len(chunk) + AROUND],
                "_log": {
                    "file": name, "line": begin + 1, "kind": kind, "place": location,
                    "what_the_edit_adds": adds,
                    "added_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "added_head": text[:HEAD_LIMIT], "fit": None, "failed": False,
                },
            }  # fmt: skip
            if found and found[-1]["_key"] == (name, kind, place):
                found[-1]["pieces"].append(piece)
            else:
                found.append({"place_and_its_purpose": place, "style_of_this_place": style,
                              "pieces": [piece], "_file": name, "_kind": kind,
                              "_key": (name, kind, place)})  # fmt: skip
    return found


def new_sections(hunks: list[dict]) -> list[dict]:
    """Each top-level heading a hunk adds, with its whole section and the nearest siblings for comparison."""
    fresh = {
        (h["file"], i)
        for h in hunks
        for i in range(h["start"] - 1, h["start"] - 1 + len(h["added"]))
    }
    found = []
    for hunk in hunks:
        name, image = hunk["file"], hunk["image"]
        if Path(name).suffix not in MARKDOWN or hunk["new"]:
            continue
        heads = headings(image)
        first, stop = hunk["start"] - 1, hunk["start"] - 1 + len(hunk["added"])
        added = [h for h in heads if first <= h[0] < stop]
        top = min((h[1] for h in added), default=0)
        for pos, (i, level, title) in enumerate(heads):
            if not first <= i < stop or level != top:
                continue
            parent = next(
                (p for p in range(pos - 1, -1, -1) if heads[p][1] < level), None
            )
            low = heads[parent][0] if parent is not None else -1
            high = (
                section_end(heads, parent, len(image))
                if parent is not None
                else len(image)
            )
            siblings = [
                q for q, h in enumerate(heads)
                if h[1] == level and low < h[0] < high and (name, h[0]) not in fresh
            ]  # fmt: skip
            nearest = [q for q in siblings if q < pos][-1:] + [
                q for q in siblings if q > pos
            ][:1]
            body = image[i : section_end(heads, pos, len(image))]
            found.append({
                "heading": title,
                "new_section": {**stats(body), "text": "\n".join(body)[:SECTION_LIMIT]},
                "sibling_sections": [
                    {"heading": heads[q][2], **stats(text), "text": "\n".join(text)[:SIBLING_LIMIT]}
                    for q in nearest
                    for text in [image[heads[q][0] : section_end(heads, q, len(image))]]
                ],
                "_file": name,
                "_shown": [line for line in body if line.strip()][:2],
                "_log": {"file": name, "line": i + 1, "place": markdown_place(image, i)[0],
                         "heading": title, "style": None, "failed": False},
            })  # fmt: skip
    return found


def new_file(hunk: dict, role: str) -> dict:
    """The file a commit adds, shown whole enough to tell finished content from a raw draft."""
    name, image = hunk["file"], hunk["image"]
    return {
        "path": name,
        "file_kind_and_role": role,
        "shape": shape_sentence(image),
        "opening": "\n".join(image)[:OPENING_LIMIT],
        "directory": hunk["neighbors"][0],
        "directory_neighbors": hunk["neighbors"][1],
        "_shown": [line for line in image if line.strip()][:2],
        "_log": {"file": name, "line": 1, "place": os.path.dirname(name) or "(top level)",
                 "placed": None, "failed": False},
    }  # fmt: skip


def public(value):
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [public(v) for v in value]
    return value


def state_of(base: dict, units: list[dict]) -> dict:
    sections = [u for u in units if "new_section" in u]
    return {
        **base,
        "hunks": [u for u in units if "pieces" in u],
        **({"new_sections": sections} if sections else {}),
    }


def size(state: dict) -> int:
    return len(json.dumps(public(state), ensure_ascii=False))


def fitted(base: dict, place: dict) -> list[dict]:
    """A place stays whole unless it alone overflows a request; then it continues in parts under the same slots."""
    parts = [{**place, "pieces": []}]
    for piece in place["pieces"]:
        while size(state_of(base, [{**place, "pieces": [piece]}])) > STATE_LIMIT and (
            piece["lines_before"] or piece["lines_after"]
        ):
            piece = {**piece, "lines_before": piece["lines_before"][1:], "lines_after": piece["lines_after"][:-1]}  # fmt: skip
        grown = {**parts[-1], "pieces": [*parts[-1]["pieces"], piece]}
        if parts[-1]["pieces"] and size(state_of(base, [grown])) > STATE_LIMIT:
            parts.append({**place, "pieces": [piece]})
        else:
            parts[-1] = grown
    return parts


def requests(hunks: list[dict], message: str) -> list[dict]:
    subject, _, body = message.partition("\n\n")
    background = subject + (f" ({body.strip()[:BODY_LIMIT]})" if body.strip() else "")
    units = places(hunks)
    sections = new_sections(hunks)
    found = []
    for name in dict.fromkeys(h["file"] for h in hunks):
        hunk = next(h for h in hunks if h["file"] == name)
        markdown = Path(name).suffix in MARKDOWN
        role = file_role(hunk["image"], markdown)
        kind = (
            f"{role} Whole document: {shape_sentence(hunk['pre'])}"
            if markdown
            else role
        )
        base = {"form": {"background_of_change": background, "file_kind_and_role": kind},
                "document": {"file": name, "file_role": role}}  # fmt: skip
        if hunk["new"]:
            found.append({**base, "form": {"background_of_change": background}, "hunks": [],
                          "new_files": [new_file(hunk, role)]})  # fmt: skip
            continue
        mine = [p for u in units if u["_file"] == name for p in fitted(base, u)]
        groups: list[list[dict]] = [[]]
        for unit in mine + [s for s in sections if s["_file"] == name]:
            if groups[-1] and size(state_of(base, [*groups[-1], unit])) > STATE_LIMIT:
                groups.append([])
            groups[-1].append(unit)
        found += [state_of(base, g) for g in groups if g]
    return found


def noul_question(question: tuple[str, str, str], **slots: str) -> dict:
    ask, true, false = (text.format(**slots) for text in question)
    return {
        "type": "noul",
        "instructions": ask,
        "criteria": {"true": true, "false": false},
    }


def questions(state: dict) -> dict:
    asked = {}
    for i, place in enumerate(state["hunks"]):
        for j in range(len(place["pieces"])):
            asked[f"fits_{i}_{j}"] = noul_question(
                FIT[place["_kind"]], h=f"hunks[{i}]", p=f"hunks[{i}].pieces[{j}]"
            )
    for k in range(len(state.get("new_sections", []))):
        asked[f"style_{k}"] = noul_question(STYLE, s=f"new_sections[{k}]")
    for k in range(len(state.get("new_files", []))):
        asked[f"placed_{k}"] = noul_question(NEW_FILE, f=f"new_files[{k}]")
    return asked


def noul(answers: dict, key: str) -> float:
    try:
        return float(answers[key]["noul"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Skip("Jev の応答に判定が欠けていました") from exc


def judge(
    states: list[dict], record: dict, evaluate
) -> list[tuple[dict, list[str], str, float]]:
    deadline = time.monotonic() + DEADLINE
    failures = []
    for state in states:
        began = time.monotonic()
        if began >= deadline:
            raise Skip("Jev の応答が時間内に返りませんでした")
        reply = evaluate(public(state), questions(state), deadline - began)
        if not isinstance(reply, dict) or not isinstance(reply.get("answers"), dict):
            raise Skip("Jev の応答を読めませんでした")
        record["request_latency_ms"].append(round((time.monotonic() - began) * 1000))
        record["model"] = reply.get("model") or record["model"]
        usage = reply.get("usage")
        tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        if isinstance(tokens, int):
            record["input_tokens"] = (record["input_tokens"] or 0) + tokens
        answers = reply["answers"]
        for i, place in enumerate(state["hunks"]):
            for j, piece in enumerate(place["pieces"]):
                fit = piece["_log"]["fit"] = noul(answers, f"fits_{i}_{j}")
                if fit < DENY_BELOW:
                    piece["_log"]["failed"] = True
                    shown = [t for t in piece["added_lines"].splitlines() if t.strip()][
                        :2
                    ]
                    failures.append((piece["_log"], shown, PLACEMENT_MISFIT, fit))
        for k, section in enumerate(state.get("new_sections", [])):
            style = section["_log"]["style"] = noul(answers, f"style_{k}")
            if style < DENY_BELOW:
                section["_log"]["failed"] = True
                failures.append(
                    (section["_log"], section["_shown"], STYLE_MISFIT, style)
                )
        for k, added in enumerate(state.get("new_files", [])):
            placed = added["_log"]["placed"] = noul(answers, f"placed_{k}")
            if placed < DENY_BELOW:
                added["_log"]["failed"] = True
                failures.append(
                    (added["_log"], added["_shown"], NEW_FILE_MISFIT, placed)
                )
    return failures


def deny_reason(failures: list[tuple[dict, list[str], str, float]]) -> str:
    lines = [
        "jev-context-gate: 追加した内容に、Jev が文脈に合わないと判定した箇所があります。"
    ]
    for where, shown, why, score in failures:
        lines.append(
            f"- {where['file']}:{where['line']} 「{where['place']}」 {why} (確率 {score:.2f})"
        )
        lines += [f"  + {text[:120]}" for text in shown]
    lines.append(
        "配置の問いは該当行を削るか文脈に合う場所へ移し、節の書きぶりの問いは同じ階層の節に分量と書き方を揃え、"
        "新規ファイルの問いは下書きを読み手向けに蒸留して内容に合うディレクトリへ置くかコミットから外してから、"
        "コミットし直してください。hook 自身はファイルを変更しません。"
    )
    return "\n".join(lines)


def write_log(record: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # a log failure must never change the commit decision
        pass


def check(payload: dict, evaluate) -> dict:
    """Hook output for one PreToolUse payload; evaluate(state, questions, seconds_left) returns Jev's reply or raises Skip."""
    target = commit_target(payload) if isinstance(payload, dict) else None
    if target is None:
        return {}
    cwd, paths, amend, all_tracked, message = target
    hunks = changed_hunks(cwd, paths, amend, all_tracked)
    states = requests(hunks, message) if hunks else []
    if not states:
        return {}
    began = time.monotonic()
    record = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "session_id": payload.get("session_id"), "cwd": str(cwd),
        "repo": git(cwd, "rev-parse", "--show-toplevel").stdout.strip(),
        "subject": message.split("\n", 1)[0], "outcome": "allow", "skip_reason": None,
        "threshold": DENY_BELOW, "question_version": QUESTION_VERSION, "model": None,
        "input_tokens": None, "latency_ms": None, "request_latency_ms": [],
        "server_pid": os.getpid(),
    }  # fmt: skip
    output = {}
    try:
        if failures := judge(states, record, evaluate):
            record["outcome"] = "deny"
            decision = {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                        "permissionDecisionReason": deny_reason(failures)}  # fmt: skip
            output = {"hookSpecificOutput": decision}
    except Skip as skip:
        record["outcome"], record["skip_reason"] = "skip", str(skip)
        output = {"systemMessage": skip_notice(skip)}
    record["latency_ms"] = round((time.monotonic() - began) * 1000)
    units = [u for s in states for u in s["hunks"]]
    record["pieces"] = [p["_log"] for u in units for p in u["pieces"]]
    record["new_sections"] = [
        s["_log"] for st in states for s in st.get("new_sections", [])
    ]
    record["new_files"] = [f["_log"] for st in states for f in st.get("new_files", [])]
    write_log(record)
    return output


def skip_notice(reason: object) -> str:
    return f"jev-context-gate: Jev の文脈チェックを省略しました (理由: {reason})"


def gather(cwd: str, command: str) -> list[dict]:
    """The Jev requests check() would send for this Bash command, for a judge outside the jev server."""
    target = commit_target(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    )
    if target is None:
        return []
    cwd_path, paths, amend, all_tracked, message = target
    hunks = changed_hunks(cwd_path, paths, amend, all_tracked)
    return [
        {"state": public(s), "questions": questions(s)}
        for s in (requests(hunks, message) if hunks else [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the Jev requests for a git commit (gather)."
    )
    commands = parser.add_subparsers(dest="action", required=True)
    gather_parser = commands.add_parser("gather")
    gather_parser.add_argument("--cwd", required=True)
    gather_parser.add_argument("--command", required=True)
    args = parser.parse_args()
    print(json.dumps({"requests": gather(args.cwd, args.command)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
