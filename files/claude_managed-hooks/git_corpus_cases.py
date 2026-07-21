"""Build safe, reviewable cases from the extracted git command corpus."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
from pathlib import Path
import re

EXPECTED_SOURCE_COUNT = 4041
REVIEW_SOURCE_LIMIT = 4000
REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TSV = REPO_ROOT / "drafts/git-corpus/unique-git-commands.tsv"
CASES_TSV = REPO_ROOT / "drafts/git-corpus/cases.tsv"


class CaseMode(StrEnum):
    EXECUTE = "execute"
    STATIC = "static"


class StaticRule(StrEnum):
    NO_COMMIT = "pattern_does_not_create_commit"
    INDETERMINATE = "detector_must_not_claim_no_commit"


@dataclass(frozen=True)
class SourceCommand:
    frequency: int
    command: str


@dataclass(frozen=True)
class CorpusCase:
    case_id: str
    pattern: str
    command: str
    source_command: str
    source_frequency: int
    mode: CaseMode = CaseMode.EXECUTE
    static_rule: StaticRule | None = None


PATTERNS = (
    "git_c_repo_target",
    "semicolon_sequence",
    "pathspec_double_dash",
    "single_git_invocation",
    "pipe_postprocess",
    "multiline_script",
    "redirect_stderr_and_file",
    "and_chain",
    "non_git_command_mentioning_git",
    "multiline_commit_message_dq",
    "command_substitution_arg",
    "var_assign_then_expansion",
    "non_ascii_message_and_path",
    "cd_then_git",
    "or_chain_verdict_idiom",
    "git_C_relative_and_worktree",
    "heredoc_body_as_data",
    "multi_dash_m",
    "loop_over_refs",
    "heredoc_commit_message",
    "comment_in_script",
    "amend_and_history_rewrite",
    "git_global_config_flags",
    "backslash_line_continuation",
    "combined_short_flags",
    "commit_message_from_file_or_stdin",
    "subshell_and_nested_shell",
    "command_prefix_wrapper",
    "commit_bypass_and_editor_flags",
)


CASE_COMMANDS: dict[str, tuple[str, str, str]] = {
    "git_c_repo_target": (
        'git -C "$REPO" commit -m "c target" -- alpha.txt',
        'git -C "$REPO" status --short',
        'git -C "$REPO" -C . commit -m "double c" -- beta.py',
    ),
    "semicolon_sequence": (
        'git status --short; git commit -m "after status" -- alpha.txt',
        "echo 'message; data'; git commit -m 'two statements' -- beta.py",
        "git commit -m 'semicolon; inside' -- alpha.txt; git log -1 --oneline",
    ),
    "pathspec_double_dash": (
        'git commit -m "explicit alpha" -- alpha.txt',
        "git diff --cached -- beta.py",
        'git commit -m "unicode path" -- "日本語.txt"',
    ),
    "single_git_invocation": (
        "git status --short",
        'git commit -m "single commit" -- alpha.txt',
        "git log -1 --oneline",
    ),
    "pipe_postprocess": (
        'git commit -m "piped commit" -- alpha.txt | cat',
        "git status --short | head -n 2",
        "printf '%s\\n' 'git commit -m data' | grep commit",
    ),
    "multiline_script": (
        "git status --short\ngit commit -m 'next line' -- alpha.txt",
        "echo before\ngit status --porcelain\necho after",
        "# setup line\ngit commit -m 'after comment' -- beta.py\ngit log -1 --oneline",
    ),
    "redirect_stderr_and_file": (
        'git commit -m "redirected" -- alpha.txt > "$TMPDIR/commit.out" 2>&1',
        'git status --short 2> "$TMPDIR/status.err"',
        "echo 'git commit is documentation' > \"$TMPDIR/howto.txt\"",
    ),
    "and_chain": (
        "git add alpha.txt && git commit -m 'and commit' -- alpha.txt",
        "git status --short && git log -1 --oneline",
        "git commit -m 'and echo' -- beta.py && echo committed",
    ),
    "non_git_command_mentioning_git": (
        "printf '%s\\n' 'git commit -m example'",
        "echo git status is documented here",
        "test -n 'git push'",
    ),
    "multiline_commit_message_dq": (
        'git commit -m "subject\n\nbody line" -- alpha.txt',
        'git commit -m "日本語 subject\nbody" -- "日本語.txt"',
        'git commit -m "body has ; and &&\nstill message" -- beta.py',
    ),
    "command_substitution_arg": (
        'git commit -m "$(printf generated)" -- alpha.txt',
        'git $(printf commit) -m "expanded subcommand" -- beta.py',
        'git commit -m "head is $(git rev-parse --short HEAD)" -- alpha.txt',
    ),
    "var_assign_then_expansion": (
        'MSG="variable message"; git commit -m "$MSG" -- alpha.txt',
        'TARGET=beta.py; git commit -m "variable path" -- "$TARGET"',
        'G="git -C $REPO"; $G commit -qm variable-command',
    ),
    "non_ascii_message_and_path": (
        'git commit -m "日本語の変更" -- "日本語.txt"',
        'git commit -m "全角記号（確認）" -- alpha.txt',
        'git status --short -- "日本語.txt"',
    ),
    "cd_then_git": (
        'cd "$REPO" && git commit -m "after cd" -- alpha.txt',
        'cd "$REPO/nested" && git status --short',
        'cd "$REPO/nested" && git commit -m "parent path" -- ../beta.py',
    ),
    "or_chain_verdict_idiom": (
        "git commit -m 'verdict' -- alpha.txt && echo OK || echo NG",
        "git status --short && echo OK || echo NG",
        "git diff --quiet && echo CLEAN || echo DIRTY",
    ),
    "git_C_relative_and_worktree": (
        'cd "$REPO" && git -C . commit -m "relative c" -- alpha.txt',
        'cd "$REPO/nested" && git -C .. commit -m "parent c" -- beta.py',
        'git -C "$REPO/nested" status --short',
    ),
    "heredoc_body_as_data": (
        "cat > \"$TMPDIR/howto.md\" <<'EOF'\ngit commit -m hidden\nEOF",
        "cat <<'EOF' > \"$TMPDIR/data.txt\"\ngit commit --amend\nEOF\ngit status --short",
        'cat <<EOF > "$TMPDIR/data2.txt"\ngit push origin main\nEOF',
    ),
    "multi_dash_m": (
        "git commit -m 'subject' -m 'body' -- alpha.txt",
        "git commit -m one -m two -m three -- beta.py",
        "git commit --message='long subject' -m 'second paragraph' -- alpha.txt",
    ),
    "loop_over_refs": (
        'for ref in HEAD main; do git rev-parse "$ref"; done',
        'for action in commit; do git "$action" -m loop -- alpha.txt; done',
        'for path in alpha.txt beta.py; do git status --short -- "$path"; done',
    ),
    "heredoc_commit_message": (
        "git commit -m \"$(cat <<'EOF'\nheredoc subject\n\nheredoc body\nEOF\n)\" -- alpha.txt",
        'git commit -m "$(cat <<EOF\n日本語 heredoc\nEOF\n)" -- "日本語.txt"',
        "git commit -m \"$(cat <<'EOF'\nmessage with ; && #63d8e6\nEOF\n)\" -- beta.py",
    ),
    "comment_in_script": (
        "# git commit -m hidden\ngit status --short",
        "git commit -m 'issue #6' -- alpha.txt # trailing comment",
        "echo '#63d8e6'; git commit -m 'color #63d8e6' -- beta.py",
    ),
    "amend_and_history_rewrite": (
        "git commit --amend --no-edit",
        "git stash push -m corpus-test",
        "git reset --soft HEAD",
    ),
    "git_global_config_flags": (
        "git -c core.pager=cat commit -m 'config flag' -- alpha.txt",
        "git --no-pager status --short",
        'git --git-dir="$REPO/.git" --work-tree="$REPO" commit -m "dirs" -- beta.py',
    ),
    "backslash_line_continuation": (
        "git commit \\\n  -m 'continued' \\\n  -- alpha.txt",
        "git \\\n  status --short",
        "git commit -m 'continued path' -- \\\n  beta.py",
    ),
    "combined_short_flags": (
        "git commit -am 'all tracked'",
        "git commit -qm'quiet joined' -- alpha.txt",
        "git commit -m'joined message' -- beta.py",
    ),
    "commit_message_from_file_or_stdin": (
        "printf '%s\\n' 'message file' > \"$TMPDIR/message.txt\"; git commit -F \"$TMPDIR/message.txt\" -- alpha.txt",
        "git commit -F - -- beta.py <<'EOF'\nmessage from stdin\nEOF",
        "printf '%s\\n' 'stdin pipe' | git commit -F - -- alpha.txt",
    ),
    "subshell_and_nested_shell": (
        "(git commit -m 'subshell' -- alpha.txt)",
        "bash -c 'git commit -m nested -- beta.py'",
        "bash -s <<'SH'\ngit commit -m heredoc-shell -- alpha.txt\nSH",
    ),
    "command_prefix_wrapper": (
        "timeout 5 git commit -m timeout -- alpha.txt",
        "nice -n 10 git commit -m nice -- beta.py",
        "GIT_OPTIONAL_LOCKS=0 git status --short",
    ),
    "commit_bypass_and_editor_flags": (
        "git commit --no-verify -m bypass -- alpha.txt",
        "git commit -n -m short-bypass -- beta.py",
        "GIT_EDITOR=true git commit -- alpha.txt",
    ),
}

GENERATED_COMMANDS = {
    "git_global_config_flags": ("git -c alias.ci=commit ci -m alias -- alpha.txt",),
    "loop_over_refs": (
        "find . -maxdepth 0 -exec git commit -m find-exec -- alpha.txt \\;",
    ),
    "subshell_and_nested_shell": (
        "eval 'git commit -m eval -- alpha.txt'",
        "printf '%s\\n' 'git commit -m sourced -- beta.py' > \"$TMPDIR/generated.sh\"; source \"$TMPDIR/generated.sh\"",
        'python3 -c \'import subprocess; subprocess.run(["git", "commit", "-m", "python", "--", "alpha.txt"], check=True)\'',
    ),
}


def _unescape_command(value: str) -> str:
    output: list[str] = []
    position = 0
    while position < len(value):
        if value[position : position + 2] == "\\n":
            output.append("\n")
            position += 2
        elif value[position : position + 2] == "\\\\":
            output.append("\\")
            position += 2
        else:
            output.append(value[position])
            position += 1
    return "".join(output)


def _escape_field(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def load_source_commands(path: Path = SOURCE_TSV) -> tuple[SourceCommand, ...]:
    sources: list[SourceCommand] = []
    with path.open(encoding="utf-8") as corpus:
        for line_number, line in enumerate(corpus, 1):
            frequency, separator, command = line.rstrip("\n").partition("\t")
            if not separator or not frequency.isdigit():
                raise ValueError(f"invalid corpus row {line_number}")
            sources.append(SourceCommand(int(frequency), _unescape_command(command)))
    if len(sources) != EXPECTED_SOURCE_COUNT:
        raise ValueError(
            f"expected {EXPECTED_SOURCE_COUNT} corpus rows, found {len(sources)}"
        )
    return tuple(sources)


def _matches(pattern: str, command: str) -> bool:
    checks = {
        "git_c_repo_target": lambda: bool(
            re.search(r"(?:^|\s)git\s+(?:[^\n;|&]+\s+)?-C(?:\s|['\"])", command)
        ),
        "semicolon_sequence": lambda: ";" in command,
        "pathspec_double_dash": lambda: bool(
            re.search(r"\bgit\b[^\n]*\s--(?:\s|$)", command)
        ),
        "single_git_invocation": lambda: (
            command.lstrip().startswith("git ")
            and not re.search(r"[;|\n]|&&|\|\|", command)
        ),
        "pipe_postprocess": lambda: bool(re.search(r"(?<!\|)\|(?!\|)", command)),
        "multiline_script": lambda: "\n" in command,
        "redirect_stderr_and_file": lambda: bool(re.search(r"(?:\d?>|>&)", command)),
        "and_chain": lambda: "&&" in command,
        "non_git_command_mentioning_git": lambda: (
            "git" in command
            and not bool(
                re.search(r"(?:^|[;&|()\n]\s*|\s)(?:git|[^\s/]+/git)\s", command)
            )
        ),
        "multiline_commit_message_dq": lambda: bool(
            re.search(r"git[^\n]*commit[^\n]*-m\s+\"[^\"]*\n", command)
        ),
        "command_substitution_arg": lambda: "$(" in command or "`" in command,
        "var_assign_then_expansion": lambda: bool(
            re.search(r"\b[A-Za-z_][A-Za-z0-9_]*=.*(?:\n|;).*\$", command, re.S)
        ),
        "non_ascii_message_and_path": lambda: not command.isascii(),
        "cd_then_git": lambda: bool(
            re.search(r"(?:^|[;\n])\s*cd\s+.+(?:&&|;)\s*git\b", command)
        ),
        "or_chain_verdict_idiom": lambda: "&&" in command and "||" in command,
        "git_C_relative_and_worktree": lambda: (
            bool(re.search(r"git\s+-C\s+(?:\.|\.\.|\$|['\"]?[^/\s'\"]+)", command))
            or "worktree" in command
        ),
        "heredoc_body_as_data": lambda: (
            "<<" in command and bool(re.search(r"\n.*git\b", command, re.S))
        ),
        "multi_dash_m": lambda: (
            len(re.findall(r"(?:^|\s)-m(?:\s|['\"])", command)) >= 2
        ),
        "loop_over_refs": lambda: bool(
            re.search(r"\b(?:for|while)\b.+\b(?:do|git)\b", command, re.S)
        ),
        "heredoc_commit_message": lambda: bool(
            re.search(r"git[^\n]*commit[^\n]*\$\(cat\s+<<", command)
        ),
        "comment_in_script": lambda: "#" in command,
        "amend_and_history_rewrite": lambda: bool(
            re.search(r"\b(?:--amend|stash|reset|rebase)\b", command)
        ),
        "git_global_config_flags": lambda: bool(
            re.search(r"\bgit\s+(?:-c\s+|--no-pager|--git-dir|--work-tree)", command)
        ),
        "backslash_line_continuation": lambda: "\\\n" in command,
        "combined_short_flags": lambda: bool(
            re.search(r"\bcommit\s+-(?:[a-zA-Z]{2,}|m['\"])", command)
        ),
        "commit_message_from_file_or_stdin": lambda: bool(
            re.search(r"\bcommit\b[^\n]*(?:-F|--file)", command)
        ),
        "subshell_and_nested_shell": lambda: bool(
            re.search(r"(?:^|[;&|\n]\s*)\(|\b(?:bash|sh)\s+-(?:c|s)\b", command)
        ),
        "command_prefix_wrapper": lambda: bool(
            re.search(
                r"(?:^|[;&|\n]\s*)(?:timeout|nice|env|[A-Za-z_][A-Za-z0-9_]*=\S+)\s+(?:[^\n;]+\s+)?git\b",
                command,
            )
        ),
        "commit_bypass_and_editor_flags": lambda: bool(
            re.search(
                r"\bcommit\b[^\n]*(?:--no-verify|(?:^|\s)-n(?:\s|$)|GIT_EDITOR)",
                command,
            )
        ),
    }
    return checks[pattern]()


def _representatives(
    pattern: str, sources: tuple[SourceCommand, ...]
) -> tuple[SourceCommand, SourceCommand, SourceCommand]:
    matching = [source for source in sources if _matches(pattern, source.command)]
    if not matching:
        raise ValueError(f"no corpus source matched {pattern}")
    chosen: list[SourceCommand] = []
    reviewable = [
        source for source in matching if len(source.command) <= REVIEW_SOURCE_LIMIT
    ]
    for source in (
        matching[0],
        min(matching, key=lambda item: len(item.command)),
        max(reviewable or matching, key=lambda item: len(item.command)),
    ):
        if source not in chosen:
            chosen.append(source)
    for source in matching:
        if len(chosen) == 3:
            break
        if source not in chosen:
            chosen.append(source)
    if len(chosen) != 3:
        raise ValueError(f"fewer than three distinct corpus sources matched {pattern}")
    return chosen[0], chosen[1], chosen[2]


def _source_id(command: str) -> str:
    return hashlib.sha256(command.encode()).hexdigest()[:12]


def _static_cases(sources: tuple[SourceCommand, ...]) -> tuple[CorpusCase, ...]:
    rules = (
        (
            "single_git_invocation",
            re.compile(r"^git push(?:\s|$)"),
            StaticRule.NO_COMMIT,
        ),
        ("pipe_postprocess", re.compile(r"^git push.*\|", re.S), StaticRule.NO_COMMIT),
        (
            "git_c_repo_target",
            re.compile(r"git\s+-C\s+\S+\s+pull(?:\s|$)"),
            StaticRule.NO_COMMIT,
        ),
        (
            "subshell_and_nested_shell",
            re.compile(r"xargs\s+git\s+push"),
            StaticRule.INDETERMINATE,
        ),
    )
    cases: list[CorpusCase] = []
    for position, (pattern, matcher, rule) in enumerate(rules, 1):
        source = next((item for item in sources if matcher.search(item.command)), None)
        if source is None:
            continue
        cases.append(
            CorpusCase(
                f"static_{position:02d}_{_source_id(source.command)}",
                pattern,
                source.command,
                source.command,
                source.frequency,
                CaseMode.STATIC,
                rule,
            )
        )
    return tuple(cases)


def build_cases(
    sources: tuple[SourceCommand, ...] | None = None,
) -> tuple[CorpusCase, ...]:
    corpus = sources if sources is not None else load_source_commands()
    cases: list[CorpusCase] = []
    for pattern in PATTERNS:
        for position, (command, source) in enumerate(
            zip(CASE_COMMANDS[pattern], _representatives(pattern, corpus), strict=True),
            1,
        ):
            cases.append(
                CorpusCase(
                    f"{pattern}_{position:02d}_{_source_id(source.command)}",
                    pattern,
                    command,
                    source.command,
                    source.frequency,
                )
            )
    for pattern, commands in GENERATED_COMMANDS.items():
        for position, command in enumerate(commands, 1):
            cases.append(
                CorpusCase(
                    f"{pattern}_generated_{position:02d}_{_source_id(command)}",
                    pattern,
                    command,
                    command,
                    0,
                )
            )
    cases.extend(_static_cases(corpus))
    counts = {
        pattern: sum(case.pattern == pattern for case in cases) for pattern in PATTERNS
    }
    invalid = {
        pattern: count for pattern, count in counts.items() if not 3 <= count <= 10
    }
    if invalid:
        raise ValueError(f"pattern case count outside 3..10: {invalid}")
    return tuple(cases)


def write_cases_tsv(cases: tuple[CorpusCase, ...], path: Path = CASES_TSV) -> None:
    rows = [
        "case_id\tpattern\tmode\tstatic_rule\tsource_frequency\tcommand\tsource_command"
    ]
    rows.extend(
        "\t".join(
            (
                case.case_id,
                case.pattern,
                case.mode,
                case.static_rule or "",
                str(case.source_frequency),
                _escape_field(case.command),
                _escape_field(case.source_command),
            )
        )
        for case in cases
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_cases_tsv(build_cases())
