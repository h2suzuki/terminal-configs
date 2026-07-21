"""Run: python3 files/claude_managed-hooks/test_git_corpus.py"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from git_corpus_cases import (
    CASES_TSV,
    PATTERNS,
    REPO_ROOT,
    CaseMode,
    CorpusCase,
    StaticRule,
    build_cases,
    write_cases_tsv,
)
from skill_reminder_gate import _amend_paths, _find_commits, _staged_under

RESULTS_TSV = REPO_ROOT / "drafts/git-corpus/results.tsv"
COMMAND_TIMEOUT_SECONDS = 10
DOCUMENTED_BYPASSES = frozenset(
    {
        "command_substitution_arg_02_bf95e2880f68",
        "var_assign_then_expansion_03_30a6c97b07ec",
        "loop_over_refs_02_3cda16b141da",
        "subshell_and_nested_shell_02_f801f20700b0",
        "subshell_and_nested_shell_03_5d156bf61989",
        "git_global_config_flags_generated_01_2d5dcef9e53f",
        "subshell_and_nested_shell_generated_01_bb2482892d70",
        "subshell_and_nested_shell_generated_02_5fa16e13549a",
        "subshell_and_nested_shell_generated_03_0b75c6feddfc",
    }
)
KNOWN_GAPS = {
    **dict.fromkeys(DOCUMENTED_BYPASSES, "documented_bypass"),
    "commit_bypass_and_editor_flags_03_166b5f82f94a": "false_positive",
}
COMMIT_CATEGORIES = ("success", "documented_bypass", "missed", "false_positive")
PATH_CATEGORIES = ("success", "mismatch", "indeterminate", "not_applicable")


@dataclass(frozen=True)
class DetectResult:
    makes_commit: bool
    paths: set[str] | None


@dataclass(frozen=True)
class GroundTruth:
    makes_commit: bool
    paths: set[str]
    returncode: int


@dataclass(frozen=True)
class Evaluation:
    case: CorpusCase
    commit_category: str
    path_category: str
    detected: DetectResult
    truth: GroundTruth | None


class CurrentCommitGateAdapter:
    """Adapt the current commit detector and path resolver to the corpus API."""

    _INDETERMINATE = re.compile(
        r"(?:\$[A-Za-z_][A-Za-z0-9_]*\s+commit|"
        r"git\s+\$\(|git\s+[`\"']?\$[A-Za-z_({]|"
        r"alias\.[A-Za-z0-9_-]+=commit|"
        r"\b(?:eval|source)\b|subprocess\.(?:run|call|Popen)|"
        r"xargs\s+git|find\b.+-exec\s+git|"
        r"\b(?:bash|sh)\s+-(?:c|s)\b)",
        re.S,
    )

    def detect(self, command: str, repo: str) -> DetectResult:
        expanded = command.replace("${REPO}", repo).replace("$REPO", repo)
        commits = _find_commits(expanded)
        if not commits:
            if self._INDETERMINATE.search(expanded):
                return DetectResult(False, None)
            return DetectResult(False, set())
        detected_paths: set[str] = set()
        for commit in commits:
            if any("$" in path for path in commit.pathspecs):
                return DetectResult(True, None)
            cwd = repo
            if commit.cwd_override:
                cwd = (
                    commit.cwd_override
                    if os.path.isabs(commit.cwd_override)
                    else os.path.join(repo, commit.cwd_override)
                )
            if "--" in commit.args:
                paths, base, expanded_pathspec = _staged_under(
                    list(commit.pathspecs), cwd
                )
                if not expanded_pathspec:
                    return DetectResult(True, None)
            elif commit.amend_like:
                amended = _amend_paths(commit, cwd)
                if amended is None:
                    return DetectResult(True, None)
                paths, base = amended
            else:
                return DetectResult(True, None)
            detected_paths.update(_repo_relative(path, base) for path in paths)
        return DetectResult(True, detected_paths)


_ADAPTER = CurrentCommitGateAdapter()


def detect(command: str, repo: str) -> DetectResult:
    """Call the configured detector through the stable corpus interface."""
    return _ADAPTER.detect(command, repo)


def _repo_relative(path: str, base: str) -> str:
    if os.path.isabs(path):
        return os.path.relpath(path, base)
    return os.path.normpath(path)


def _run_checked(
    arguments: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def _git_env(temp_root: Path) -> dict[str, str]:
    home = temp_root / "home"
    scratch = temp_root / "tmp"
    home.mkdir()
    scratch.mkdir()
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "TMPDIR": str(scratch),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_EDITOR": "true",
        "GIT_SEQUENCE_EDITOR": "true",
        "PAGER": "cat",
    }


def _init_repo(temp_root: Path, env: dict[str, str]) -> Path:
    repo = temp_root / "repo"
    repo.mkdir()
    _run_checked(["git", "init", "-q", "-b", "main"], repo, env)
    _run_checked(["git", "config", "user.name", "Corpus Test"], repo, env)
    _run_checked(["git", "config", "user.email", "corpus@example.invalid"], repo, env)
    _run_checked(["git", "config", "core.quotePath", "false"], repo, env)
    initial = {
        "tracked.txt": "initial\n",
        "alpha.txt": "initial alpha\n",
        "beta.py": "initial beta\n",
        "日本語.txt": "初期\n",
        "nested/inner.txt": "initial nested\n",
    }
    for relative, content in initial.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _run_checked(["git", "add", "--all"], repo, env)
    _run_checked(["git", "commit", "-qm", "initial"], repo, env)
    for relative in initial:
        with (repo / relative).open("a", encoding="utf-8") as target:
            target.write("corpus change\n")
    _run_checked(["git", "add", "--all"], repo, env)
    return repo


def _head(repo: Path, env: dict[str, str]) -> str:
    return _run_checked(["git", "rev-parse", "HEAD"], repo, env).stdout.strip()


def _head_paths(repo: Path, env: dict[str, str]) -> set[str]:
    output = _run_checked(
        ["git", "show", "--name-only", "--pretty=", "HEAD"], repo, env
    ).stdout
    return {line for line in output.splitlines() if line}


def _execute_case(
    case: CorpusCase, temp_parent: Path
) -> tuple[DetectResult, GroundTruth]:
    with tempfile.TemporaryDirectory(prefix="git-corpus-", dir=temp_parent) as raw_root:
        temp_root = Path(raw_root)
        env = _git_env(temp_root)
        repo = _init_repo(temp_root, env)
        env["REPO"] = str(repo)
        detected = detect(case.command, str(repo))
        before = _head(repo, env)
        completed = subprocess.run(
            ["/bin/bash", "-o", "nounset", "-o", "pipefail", "-c", case.command],
            cwd=repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        after = _head(repo, env)
        changed = before != after
        paths = _head_paths(repo, env) if changed else set()
        return detected, GroundTruth(changed, paths, completed.returncode)


def _evaluate_executable(
    case: CorpusCase, detected: DetectResult, truth: GroundTruth
) -> Evaluation:
    if truth.makes_commit and not detected.makes_commit:
        commit_category = (
            "documented_bypass" if case.case_id in DOCUMENTED_BYPASSES else "missed"
        )
    elif not truth.makes_commit and detected.makes_commit:
        commit_category = "false_positive"
    else:
        commit_category = "success"
    if detected.paths is None:
        path_category = "indeterminate"
    elif truth.makes_commit and detected.makes_commit:
        path_category = "success" if detected.paths == truth.paths else "mismatch"
    else:
        path_category = "not_applicable"
    return Evaluation(case, commit_category, path_category, detected, truth)


def _evaluate_static(case: CorpusCase) -> Evaluation:
    detected = detect(case.command, "/nonexistent/corpus-static-repo")
    if case.static_rule == StaticRule.NO_COMMIT:
        commit_category = "false_positive" if detected.makes_commit else "success"
    else:
        commit_category = (
            "success" if detected.paths is None or detected.makes_commit else "missed"
        )
    path_category = "indeterminate" if detected.paths is None else "not_applicable"
    return Evaluation(case, commit_category, path_category, detected, None)


def _escape_tsv(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def _write_results(evaluations: list[Evaluation]) -> None:
    commit_by_pattern: dict[str, Counter[str]] = defaultdict(Counter)
    path_by_pattern: dict[str, Counter[str]] = defaultdict(Counter)
    for evaluation in evaluations:
        commit_by_pattern[evaluation.case.pattern][evaluation.commit_category] += 1
        path_by_pattern[evaluation.case.pattern][evaluation.path_category] += 1
    rows = [
        "pattern\tcommit_success\tdocumented_bypass\tmissed\tfalse_positive\t"
        "path_success\tpath_mismatch\tpath_indeterminate\tpath_not_applicable\ttotal"
    ]
    for pattern in PATTERNS:
        commit_counts = commit_by_pattern[pattern]
        path_counts = path_by_pattern[pattern]
        rows.append(
            "\t".join(
                (
                    pattern,
                    *(str(commit_counts[category]) for category in COMMIT_CATEGORIES),
                    *(str(path_counts[category]) for category in PATH_CATEGORIES),
                    str(sum(commit_counts.values())),
                )
            )
        )
    rows.append("")
    rows.append("commit_category\tpath_category\tcase_id\tpattern\treturncode\tcommand")
    for evaluation in evaluations:
        if evaluation.commit_category == "success" and evaluation.path_category not in {
            "mismatch",
            "indeterminate",
        }:
            continue
        returncode = (
            "static" if evaluation.truth is None else str(evaluation.truth.returncode)
        )
        rows.append(
            "\t".join(
                (
                    evaluation.commit_category,
                    evaluation.path_category,
                    evaluation.case.case_id,
                    evaluation.case.pattern,
                    returncode,
                    _escape_tsv(evaluation.case.command),
                )
            )
        )
    RESULTS_TSV.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _print_report(evaluations: list[Evaluation]) -> None:
    commit_by_pattern: dict[str, Counter[str]] = defaultdict(Counter)
    path_by_pattern: dict[str, Counter[str]] = defaultdict(Counter)
    for evaluation in evaluations:
        commit_by_pattern[evaluation.case.pattern][evaluation.commit_category] += 1
        path_by_pattern[evaluation.case.pattern][evaluation.path_category] += 1
    print(
        "pattern\tcommit_success\tdocumented_bypass\tmissed\tfalse_positive\t"
        "path_success\tpath_mismatch\tpath_indeterminate\tpath_not_applicable\ttotal"
    )
    for pattern in PATTERNS:
        commit_counts = commit_by_pattern[pattern]
        path_counts = path_by_pattern[pattern]
        print(
            f"{pattern}\t"
            + "\t".join(
                [
                    *(str(commit_counts[category]) for category in COMMIT_CATEGORIES),
                    *(str(path_counts[category]) for category in PATH_CATEGORIES),
                    str(sum(commit_counts.values())),
                ]
            )
        )
    for category in ("documented_bypass", "missed", "false_positive"):
        print(f"\n{category} commands (verbatim):")
        selected = [item for item in evaluations if item.commit_category == category]
        if not selected:
            print("(none)")
        for evaluation in selected:
            print(f"[{evaluation.case.case_id}]")
            print(evaluation.case.command)
            print("---")
    commit_totals = Counter(item.commit_category for item in evaluations)
    path_totals = Counter(item.path_category for item in evaluations)
    print(
        "\ncommit_total\t"
        + "\t".join(
            f"{category}={commit_totals[category]}" for category in COMMIT_CATEGORIES
        )
        + f"\tcases={len(evaluations)}"
    )
    print(
        "path_total\t"
        + "\t".join(
            f"{category}={path_totals[category]}" for category in PATH_CATEGORIES
        )
        + f"\tcases={len(evaluations)}"
    )


class GitCorpusTest(unittest.TestCase):
    def test_corpus_against_current_adapter(self) -> None:
        if not shutil_which("git"):
            self.fail("git executable is required")
        cases = build_cases()
        write_cases_tsv(cases, CASES_TSV)
        temp_parent = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
        if not temp_parent.is_dir():
            self.fail(f"temporary directory does not exist: {temp_parent}")
        evaluations: list[Evaluation] = []
        for case in cases:
            if case.mode == CaseMode.STATIC:
                evaluation = _evaluate_static(case)
                if case.static_rule == StaticRule.NO_COMMIT:
                    self.assertNotEqual("false_positive", evaluation.commit_category)
                else:
                    self.assertNotEqual("missed", evaluation.commit_category)
                evaluations.append(evaluation)
                continue
            detected, truth = _execute_case(case, temp_parent)
            evaluations.append(_evaluate_executable(case, detected, truth))
        _write_results(evaluations)
        _print_report(evaluations)
        unexpected = {
            evaluation.case.case_id: evaluation.commit_category
            for evaluation in evaluations
            if evaluation.commit_category in {"missed", "false_positive"}
            and evaluation.case.case_id not in KNOWN_GAPS
        }
        self.assertEqual({}, unexpected)
        observed_gaps = {
            evaluation.case.case_id: evaluation.commit_category
            for evaluation in evaluations
            if evaluation.case.case_id in KNOWN_GAPS
        }
        self.assertEqual(KNOWN_GAPS, observed_gaps)
        self.assertEqual(
            DOCUMENTED_BYPASSES,
            frozenset(
                evaluation.case.case_id
                for evaluation in evaluations
                if evaluation.commit_category == "documented_bypass"
            ),
        )
        self.assertEqual(
            [],
            [
                evaluation.case.case_id
                for evaluation in evaluations
                if evaluation.path_category == "mismatch"
            ],
        )
        self.assertEqual(len(cases), len(evaluations))
        self.assertEqual(set(PATTERNS), {case.pattern for case in cases})
        self.assertTrue(
            all(
                3 <= sum(case.pattern == pattern for case in cases) <= 10
                for pattern in PATTERNS
            )
        )


def shutil_which(command: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


if __name__ == "__main__":
    unittest.main(verbosity=2)
