"""Before `git commit`, judge with Jev whether each added hunk fits its context and each added file its place;
the jev server calls check(). Only a clear "does not fit" denies; any Jev, key, or network failure skips and tells the user."""

from __future__ import annotations

import argparse
import ast
import datetime
import functools
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Any

try:
    import tree_sitter
    import tree_sitter_bash
    import tree_sitter_json
    import tree_sitter_markdown
    import tree_sitter_python
    import tree_sitter_typescript
except ImportError:  # without the parsers the gate skips and says why, instead of breaking the jev server
    tree_sitter = None

DENY_BELOW = 0.5  # real README commits: misplaced text ≤ 0.25, fitting ≥ 0.72
QUESTION_VERSION = "struct-1"
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
GRAMMAR_OF_SUFFIX = {
    ".py": "python", ".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx",
    ".js": "tsx", ".jsx": "tsx", ".mjs": "tsx", ".cjs": "tsx", ".sh": "bash", ".bash": "bash",
    ".json": "json", ".md": "markdown", ".markdown": "markdown",
}  # fmt: skip
GRAMMAR_OF_SHEBANG = {"python": "python", "bash": "bash", "sh": "bash", "node": "tsx"}
LANGUAGE_OF_SUFFIX = {
    ".py": "Python", ".ts": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".sh": "Shell", ".bash": "Shell", ".json": "JSON",
}  # fmt: skip
LANGUAGE_OF_GRAMMAR = {"python": "Python", "bash": "Shell", "tsx": "JavaScript"}
# Syntax-tree nodes that are a place of their own; everything else (if, for, callbacks) belongs to the place around it.
PLACE_NODES = {
    "python": {"function_definition", "class_definition"},
    "typescript": {"function_declaration", "generator_function_declaration", "class_declaration",
                   "abstract_class_declaration", "method_definition", "interface_declaration",
                   "type_alias_declaration", "enum_declaration", "internal_module", "module"},
    "bash": {"function_definition"},
}  # fmt: skip
PLACE_NODES["tsx"] = PLACE_NODES["typescript"]
TEST_CALL_RE = re.compile(r"(?:describe|it|test)(?:\.\w+)*")
TEST_FILE_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__)/|[._-](?:test|spec)\.[^/]+$|(?:^|/)test_[^/]+$"
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


def default_role(name: str, lines: list[str]) -> str:
    """For a file with no docstring or header comment: its language and whether it is a test."""
    language = LANGUAGE_OF_SUFFIX.get(Path(name).suffix) or LANGUAGE_OF_GRAMMAR.get(
        grammar_of(name, lines) or ""
    )
    if not language:
        return ""
    return (
        f"{language} {'test' if TEST_FILE_RE.search(name) else 'source'} file"
        if language != "JSON"
        else "JSON file"
    )


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


def markdown_place(
    lines: list[str], index: int, below: int | None = None
) -> tuple[str, str]:
    heads, chain = headings(lines), []
    for head in heads:
        if head[0] > index or (below and head[0] == index):
            break
        chain = [c for c in chain if c[1] < head[1]] + [head]
    if below:
        # A new heading joins its parent section; placed in itself, it always fits.
        chain = [c for c in chain if c[1] < below]
    location = " > ".join(c[2] for c in chain) or "(before the first heading)"
    # The title's intro is already in file_kind_and_role; an intro stops before the edit so it never quotes it.
    intros = [
        (c[2], first_paragraph(lines, c[0] + 1, index)) for c in chain if c != heads[0]
    ]
    return location, " ".join(
        f"Section '{title}: {text}'" for title, text in intros if text
    )


def markdown_style(pre: list[str], location: str) -> str:
    heads = headings(pre)
    for title in reversed(location.split(" > ")):
        for pos, (i, _, name) in enumerate(heads):
            if name == title:
                body = pre[i + 1 : section_end(heads, pos, len(pre))]
                return f"Existing content of the section '{title}' before this change: {shape_sentence(body)}"
    return f"Section is new; whole document before this change: {shape_sentence(pre)}"


def grammar_of(name: str, lines: list[str]) -> str | None:
    if (suffix := Path(name).suffix) in GRAMMAR_OF_SUFFIX:
        return GRAMMAR_OF_SUFFIX[suffix]
    head = lines[0] if lines and lines[0].startswith("#!") else ""
    return next(
        (
            g
            for word, g in GRAMMAR_OF_SHEBANG.items()
            if re.search(rf"\b{word}\d*\b", head)
        ),
        None,
    )


@functools.cache
def parser(grammar: str):
    if tree_sitter is None:
        raise Skip("構文解析器 (tree-sitter) が jev の実行環境に入っていません")
    language = {
        "python": tree_sitter_python.language, "typescript": tree_sitter_typescript.language_typescript,
        "tsx": tree_sitter_typescript.language_tsx, "bash": tree_sitter_bash.language,
        "json": tree_sitter_json.language, "markdown": tree_sitter_markdown.language,
    }[grammar]()  # fmt: skip
    return tree_sitter.Parser(tree_sitter.Language(language))


@functools.lru_cache(maxsize=16)
def parse(grammar: str, text: str):
    return parser(grammar).parse(text.encode())


def node_at(tree, lines: list[str], row: int):
    """The smallest node at the first non-blank character of line `row`."""
    line = lines[row] if row < len(lines) else ""
    column = len(line[: len(line) - len(line.lstrip())].encode())
    return tree.root_node.descendant_for_point_range((row, column), (row, column))


def node_text(node) -> str:
    return node.text.decode(errors="replace") if node is not None else ""


def is_place(node, grammar: str) -> bool:
    if node.type in PLACE_NODES.get(grammar, ()):
        return True
    if grammar in ("typescript", "tsx") and node.type == "call_expression":
        return bool(
            TEST_CALL_RE.fullmatch(node_text(node.child_by_field_name("function")))
        )
    # An arrow or function expression is a place only when a name is bound to it.
    return node.type in ("arrow_function", "function_expression", "function") and (
        node.parent is not None and node.parent.type == "variable_declarator"
    )


def context_of(node, grammar: str, lines: list[str]) -> str | None:
    """How a comment, docstring, string or embedded document that holds the line is named in the place."""
    if node.end_point.row == node.start_point.row:
        return None
    if node.type == "comment":
        return "(inside a comment)"
    if node.type == "heredoc_redirect":
        return f"(inside the here-document of `{lines[node.start_point.row].strip()[:80]}`)"
    if node.type == "fenced_code_block":
        info = next((c for c in node.named_children if c.type == "info_string"), None)
        return f"(inside a ```{node_text(info).strip()} code block)"
    if node.type in ("string", "template_string") and grammar != "json":
        statement = node.parent
        if (
            grammar == "python"
            and statement is not None
            and statement.type == "expression_statement"
        ):
            body = statement.parent
            first = (
                next((c for c in body.named_children if c.type != "comment"), None)
                if body
                else None
            )
            if first == statement:
                return "(module docstring)" if body.type == "module" else "(docstring)"
        return "(inside a multi-line string)"
    return None


def enclosing(name: str, lines: list[str], row: int, since: int) -> list[str]:
    """The places that hold line `row` and began before line `since`, outermost first, then the innermost context."""
    if (grammar := grammar_of(name, lines)) is None:
        return []
    tree = parse(grammar, "\n".join(lines))
    chain: list[tuple[int, str]] = []
    inner = None
    node = node_at(tree, lines, row)
    while node is not None:
        if node.start_point.row < since:
            if grammar == "json" and node.type == "pair":
                key = node.child_by_field_name("key")
                label = (
                    json.loads(node_text(key))
                    if key is not None and key.type == "string"
                    else node_text(key)
                )
                chain.append((node.start_point.row, str(label)))
            elif is_place(node, grammar) and (
                not chain or chain[-1][0] != node.start_point.row
            ):
                chain.append(
                    (node.start_point.row, lines[node.start_point.row].strip()[:80])
                )
            elif inner is None and not chain:
                inner = context_of(node, grammar, lines)
        node = node.parent
    return [label for _, label in reversed(chain)] + ([inner] if inner else [])


def code_scope(name: str, lines: list[str], index: int) -> str:
    return " > ".join(enclosing(name, lines, index, index)) or TOP_LEVEL


def definitions(name: str, lines: list[str]) -> list[str]:
    """Header lines of the places the file defines, or for JSON its key paths two levels deep, in file order."""
    if (grammar := grammar_of(name, lines)) is None:
        return []
    tree = parse(grammar, "\n".join(lines))
    found: list[tuple[int, str]] = []
    stack: list[tuple[Any, tuple[str, ...]]] = [(tree.root_node, ())]
    while stack:
        node, keys = stack.pop()
        if grammar == "json" and node.type == "pair":
            key = node.child_by_field_name("key")
            keys = (*keys, str(json.loads(node_text(key)) if key is not None and key.type == "string" else node_text(key)))  # fmt: skip
            if len(keys) <= 2:
                found.append((node.start_point.row, " > ".join(keys)))
        elif grammar != "json" and is_place(node, grammar):
            found.append(
                (node.start_point.row, lines[node.start_point.row].strip()[:80])
            )
        stack.extend((child, keys) for child in reversed(node.children))
    return list(dict.fromkeys(label for _, label in sorted(found, key=lambda f: f[0])))


def added_definition(name: str, lines: list[str], rows: range) -> str | None:
    """The header of the first place that the added rows begin."""
    if (grammar := grammar_of(name, lines)) is None:
        return None
    tree = parse(grammar, "\n".join(lines))
    for row in rows:
        node = node_at(tree, lines, row)
        while node is not None and node.start_point.row == row:
            if is_place(node, grammar):
                return lines[row].strip()[:80]
            node = node.parent
    return None


def syntax_error(name: str, lines: list[str]) -> str | None:
    """Why the file does not parse in its own language, or None when it does or has no grammar."""
    grammar, text = grammar_of(name, lines), "\n".join(lines)
    if grammar == "json":
        try:
            json.loads(text)
        except ValueError as error:
            return f"行 {getattr(error, 'lineno', '?')}: {getattr(error, 'msg', error)}"
        return None
    if grammar == "python":
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ast.parse(text)
        except SyntaxError as error:
            return f"行 {error.lineno}: {error.msg}"
        return None
    if (
        grammar in ("typescript", "tsx", "bash")
        and (tree := parse(grammar, text)).root_node.has_error
    ):
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "ERROR" or node.is_missing:
                return f"行 {node.start_point.row + 1}: 構文エラー"
            stack.extend(
                reversed([c for c in node.children if c.has_error or c.is_missing])
            )
        return "構文エラー"
    return None


def syntax_breaks(hunks: list[dict]) -> list[dict]:
    """Files that parsed before this change and do not after it."""
    files = {h["file"]: h for h in hunks if not h["new"]}
    return [
        {"file": name, "why": why}
        for name, hunk in files.items()
        if syntax_error(name, hunk["pre"]) is None
        and (why := syntax_error(name, hunk["image"]))
    ]


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


def pieces_by_place(
    name: str, image: list[str], chunks: list[tuple[int, list[str]]], since: int
) -> list[tuple[int, list[str]]]:
    """Split each chunk where its lines leave one enclosing place for another; blank lines stay with the lines above."""
    found = []
    for begin, chunk in chunks:
        start, current = 0, None
        for offset, line in enumerate(chunk):
            if not line.strip():
                continue
            chain = enclosing(name, image, begin + offset, since)
            if current is not None and chain != current:
                kept = chunk[start:offset]
                while not kept[-1].strip():
                    kept.pop()
                found.append((begin + start, kept))
                start = offset
            current = chain
        found.append((begin + start, chunk[start:]))
    return found


def places(hunks: list[dict]) -> list[dict]:
    """Consecutive pieces of one file under the same place, each place with its slots filled in code."""
    found: list[dict] = []
    for hunk in (h for h in hunks if not h["new"]):
        name, image, pre = hunk["file"], hunk["image"], hunk["pre"]
        markdown = Path(name).suffix in MARKDOWN
        since = hunk["start"] - 1
        for begin, chunk in pieces_by_place(
            name, image, paragraphs(hunk["added"], since, markdown), since
        ):
            at = min(begin, len(image) - 1)
            count = sum(1 for c in chunk if c.strip())
            chain = enclosing(name, image, at, since)
            context = chain[-1] if chain and chain[-1].startswith("(") else None
            if markdown:
                head = HEADING_RE.match(next(c for c in chunk if c.strip()))
                level = len(head.group(1)) if head else None
                location, purpose = markdown_place(image, at, level)
                style, adds = markdown_style(pre, location), shape_sentence(chunk)
                if context:
                    location = f"{location} > {context}"
                    adds = f"{count} line(s) inside an existing {context[len('(inside a ') : -len(' code block)')]} code block."
                kind, place = "docs", f"{location}. {purpose}".rstrip()
                if head:
                    before = [h for h in headings(image[:at]) if h[1] <= (level or 0)]
                    after = (
                        f"after the section '{before[-1][2]}'"
                        if before and before[-1][1] == level
                        else "first in its parent section"
                    )
                    adds = f"{adds[:-1]}; a new section (heading '{head.group(2)}') placed {after}."
            elif context in ("(module docstring)", "(docstring)"):
                location = place = " > ".join(chain)
                style = "Definitions before this change: " + ("; ".join(definitions(name, pre)[:OUTLINE_LIMIT]) or "(none)")  # fmt: skip
                kind, adds = "docs", shape_sentence(chunk)
            else:
                location = place = " > ".join(chain) or TOP_LEVEL
                places_only = [c for c in chain if not c.startswith("(")]
                listed = definitions(name, pre)[:OUTLINE_LIMIT]
                if grammar_of(name, image) == "json":
                    style = "Keys before this change: " + (
                        "; ".join(listed) or "(none)"
                    )
                    kind = "code"
                else:
                    style = "Definitions before this change: " + (
                        "; ".join(listed) or "(none)"
                    )
                    # Fixtures and helpers in a test file have a job to do, not a behavior to check.
                    kind = (
                        "test"
                        if places_only and TEST_SCOPE_RE.match(places_only[-1])
                        else "code"
                    )
                adds = f"{count} non-empty line(s) of {kind}"
                defined = added_definition(name, image, range(at, at + len(chunk)))
                if places_only and defined:
                    # Stated so Jev sees a definition moved inside another one.
                    adds += f", defining `{defined}` inside `{places_only[-1]}`"
                adds += "."
                # A scope question has no scope to ask about at the top level of the file.
                kind = kind if places_only else "module"
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
        role = file_role(hunk["image"], markdown) or default_role(name, hunk["image"])
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


def syntax_reason(broken: list[dict]) -> str:
    lines = [f"jev-context-gate: {b['file']} は変更後に構文として読めません ({b['why']})。変更前は読めていました。" for b in broken]  # fmt: skip
    lines.append(
        "構文を直してからコミットし直してください。hook 自身はファイルを変更しません。"
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
    try:
        broken = syntax_breaks(hunks)
        states = [] if broken else requests(hunks, message) if hunks else []
    except Skip as skip:
        return {"systemMessage": skip_notice(skip)}
    if not states and not broken:
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
        if broken:
            # Whether a file parses is computed in code; Jev is not asked about a file that no longer does.
            record["outcome"], record["syntax_breaks"] = "deny", broken
            decision = {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                        "permissionDecisionReason": syntax_reason(broken)}  # fmt: skip
            output = {"hookSpecificOutput": decision}
        elif failures := judge(states, record, evaluate):
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


def gathered(cwd: str, command: str) -> tuple[list[dict], list[dict]]:
    """The Jev requests check() would send for this Bash command, and the files it denies without asking Jev."""
    target = commit_target(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    )
    if target is None:
        return [], []
    cwd_path, paths, amend, all_tracked, message = target
    hunks = changed_hunks(cwd_path, paths, amend, all_tracked)
    if broken := syntax_breaks(hunks):
        return [], broken
    states = requests(hunks, message) if hunks else []
    return [{"state": public(s), "questions": questions(s)} for s in states], []


def gather(cwd: str, command: str) -> list[dict]:
    """The Jev requests check() would send for this Bash command, for a judge outside the jev server."""
    return gathered(cwd, command)[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the Jev requests for a git commit (gather)."
    )
    commands = parser.add_subparsers(dest="action", required=True)
    gather_parser = commands.add_parser("gather")
    gather_parser.add_argument("--cwd", required=True)
    gather_parser.add_argument("--command", required=True)
    args = parser.parse_args()
    sent, broken = gathered(args.cwd, args.command)
    print(json.dumps({"requests": sent, "syntax_breaks": broken}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
