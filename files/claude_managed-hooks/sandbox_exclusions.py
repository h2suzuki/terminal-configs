#!/usr/bin/env python3
"""
Shared excludedCommands roster for the sandbox hooks.

`sandbox.excludedCommands` varies per host, so the roster is always rendered
from the live settings files rather than hardcoded. The sandbox hooks import
from here so the advice is written once and stays identical across them.
"""

from __future__ import annotations

import contextlib
import glob
import hashlib
import json
import os
import re
import tempfile
import unittest

SYSTEM_SETTINGS = "/etc/claude-code/managed-settings.json"
SYSTEM_SETTINGS_GLOB = "/etc/claude-code/managed-settings.d/*.json"
USER_SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "hooks", "state", "sandbox_exclusion_guard"
)
CLAIM_STATE_PREFIX = "warn-"
# `!` は auto mode の許可を与えるだけ — sandbox の外に出る手段と取り違えない。
BANG_CAVEAT = (
    "ユーザーへ `!` prefix での実行を依頼しても sandbox の外には出ません。 `!` が与えるのは "
    "auto mode の実行許可だけで、 sandbox の許可ではありません。 host 権限が要るなら上の"
    "一覧を使い、 一覧で足りない作業は Claude Code の外の terminal で実行してもらってください。"
)


def config_paths() -> list[str]:
    """Return the existing sandbox settings files, lowest precedence first."""
    candidates = [USER_SETTINGS]
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        candidates.extend(
            [
                os.path.join(project, ".claude", "settings.json"),
                os.path.join(project, ".claude", "settings.local.json"),
            ]
        )
    candidates.extend(sorted(glob.glob(SYSTEM_SETTINGS_GLOB)))
    candidates.append(SYSTEM_SETTINGS)
    return list(dict.fromkeys(path for path in candidates if os.path.isfile(path)))


def _sandbox_section(path: str) -> dict:
    """Return one settings file's sandbox object, empty when unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            section = json.load(f).get("sandbox")
    except (OSError, ValueError, AttributeError):
        return {}
    return section if isinstance(section, dict) else {}


def load_patterns() -> list[str]:
    """Rescan every settings file and return the union of excludedCommands.

    Deliberately uncached: drop-ins under managed-settings.d change per project
    and the files are small enough that a fresh scan costs nothing.
    """
    patterns: set[str] = set()
    for path in config_paths():
        values = _sandbox_section(path).get("excludedCommands", [])
        if isinstance(values, list):
            patterns.update(p for p in values if isinstance(p, str))
    return sorted(patterns)


def sandbox_restricts_commands() -> bool:
    """Report whether the sandbox is on and still constrains commands.

    Checked before any roster lookup: an empty excludedCommands list means
    nothing escapes the sandbox, never that the sandbox is off.
    """
    enabled = False
    unrestricted = False
    for path in config_paths():
        section = _sandbox_section(path)
        if isinstance(value := section.get("enabled"), bool):
            enabled = value
        if isinstance(value := section.get("allowUnsandboxedCommands"), bool):
            unrestricted = value
    return enabled and not unrestricted


def credential_paths() -> list[str]:
    """Return the credential paths the sandbox denies, expanded to absolute."""
    paths: set[str] = set()
    for config in config_paths():
        entries = _sandbox_section(config).get("credentials", {})
        files = entries.get("files", []) if isinstance(entries, dict) else []
        if not isinstance(files, list):
            continue
        for entry in files:
            if not isinstance(entry, dict) or entry.get("mode") != "deny":
                continue
            if isinstance(path := entry.get("path"), str) and path:
                paths.add(os.path.expanduser(path))
    return sorted(paths)


def _latch_key(payload: dict) -> str | None:
    """Return the session identity used for once-per-session latches."""
    for field in ("session_id", "transcript_path"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return f"{field}:{value}"
    return None


def claim_once(payload: dict, reason: str) -> bool:
    """Return whether this reason is unclaimed for this session, claiming it."""
    latch_key = _latch_key(payload)
    if latch_key is None:
        return True
    try:
        digest = hashlib.sha256(latch_key.encode("utf-8")).hexdigest()
        state_path = os.path.join(STATE_DIR, f"{CLAIM_STATE_PREFIX}{digest}.json")
        reasons: set[str] = set()
        try:
            with open(state_path, encoding="utf-8") as f:
                values = json.load(f).get("reasons", [])
            if not isinstance(values, list):
                raise ValueError("claim state reasons is not a list")
            reasons = {value for value in values if isinstance(value, str)}
        except (OSError, ValueError, AttributeError, TypeError):
            pass
        if reason in reasons:
            return False
        reasons.add(reason)
        os.makedirs(STATE_DIR, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{CLAIM_STATE_PREFIX}", suffix=".tmp", dir=STATE_DIR
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"reasons": sorted(reasons)}, f, ensure_ascii=False)
            os.replace(temp_path, state_path)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    except Exception:
        return True
    return True


def roster_once(payload: dict, patterns: list[str]) -> str:
    """Return the roster the first time a session asks, empty string after."""
    return roster_text(patterns) if claim_once(payload, "roster") else ""


def bare_form(pattern: str) -> str:
    """Render a pattern as the bare leading form that actually reaches the host."""
    return pattern.split("*", 1)[0].strip() or pattern


def glob_match(value: str, pattern: str) -> bool:
    """Match a Claude excludedCommands star glob with full-string anchors."""
    translated = re.escape(pattern).replace(r"\*", ".*")
    if translated.endswith(r"\ .*") and pattern.count("*") == 1:
        translated = translated[:-4] + r"(\ .*)?"
    return re.fullmatch(translated, value, re.DOTALL) is not None


SEGMENT_CAP = 10000  # Claude Code matches a longer command as one segment
# Claude Code 2.1.280 の known-safe 変数 (binary 内の Set)。 他の変数の先頭代入は呼び出しを sandbox に残す。
SAFE_ENV = frozenset(
    {
        "GOEXPERIMENT", "GOOS", "GOARCH", "CGO_ENABLED", "GO111MODULE",
        "RUST_BACKTRACE", "RUST_LOG", "NODE_ENV", "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTEST_DEBUG",
        "ANTHROPIC_API_KEY", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_TIME",
        "CHARSET", "TERM", "COLORTERM", "NO_COLOR", "FORCE_COLOR", "TZ", "LS_COLORS",
        "LSCOLORS", "GREP_COLOR", "GREP_COLORS", "GCC_COLORS", "TIME_STYLE",
        "BLOCK_SIZE", "BLOCKSIZE", "COLUMNS", "LINES", "CLICOLOR", "CLICOLOR_FORCE",
        "CI", "DEBIAN_FRONTEND", "GIT_TERMINAL_PROMPT",
    }
)  # fmt: skip
# 除外に一致しても sandbox に残る先頭語 (公式 settings reference の sandbox.excludedCommands)。
SANDBOXED_HEADS = frozenset({"cd", "pushd", "popd", "sudo", "eval", "xargs"})
# `git -C` / `-c` / `--git-dir` は `git *` に一致しても sandbox に残る (anthropics/claude-code#95455)。
GIT_SANDBOXED_OPTION = re.compile(r"^(?:-C|-c|--git-dir(?:=|$))")
CONTROL_WORDS = frozenset(
    {"if", "then", "elif", "else", "fi", "while", "until", "for", "select", "do"}
    | {"done", "case", "esac", "function", "[[", "]]"}
)
_HEREDOC = re.compile(r"<<")
_QUOTED = re.compile(r'"(?:\\[\s\S]|[^"\\])*"|\'[^\']*\'')
_QUOTED_BREAKERS = re.compile(r"[\s;|&(){}#<>$`\\]")
# a quoted command name stays sandboxed, so it must not match a pattern
_QUOTE_MARK = "\x01"
_SUBSTITUTION = re.compile(r"\$\(|`")
_BRACED_VAR = re.compile(r"\$\{[^}]*\}")
_FD_DUP = re.compile(r"\d*[<>]&(?:\d+|-)(?![^\s;|&])")
_COMMENT = re.compile(r"(?:^|(?<=\s))#[^\n]*")
_SANDBOXED_SHAPE = re.compile(r"[<>(){}]")
_TOKEN = re.compile(r"\|&|&&|\|\||[;|&\n]|[^\s;|&]+")
_SEPARATORS = frozenset({"&&", "||", "|", "|&", ";", "&", "\n"})
_ASSIGNMENT = re.compile(r"^([A-Za-z_]\w*)(?:\[[^\]]*\])?\+?=")
_TIMEOUT_FLAG = re.compile(
    r"^(?:--(?:foreground|preserve-status|verbose)|-v|--(?:kill-after|signal)=\S+|-[ks]\S+)$"
)
_TIMEOUT_VALUED = frozenset({"--kill-after", "--signal", "-k", "-s"})
_DURATION = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")


def _wrapper_span(tokens: list[str]) -> int:
    """Return how many leading tokens a wrapper Claude Code strips occupies, 0 if none."""
    head, n = tokens[0], 1
    if head == "timeout":
        while n < len(tokens) and _TIMEOUT_FLAG.match(tokens[n]):
            n += 1
        while n + 1 < len(tokens) and tokens[n] in _TIMEOUT_VALUED:
            n += 2
        n += n < len(tokens) and tokens[n] == "--"
        return n + 1 if n < len(tokens) and _DURATION.match(tokens[n]) else 0
    if head == "nice":
        if (
            n + 1 < len(tokens)
            and tokens[n] == "-n"
            and re.match(r"^-?\d+$", tokens[n + 1])
        ):
            n += 2
        elif n < len(tokens) and re.match(r"^-\d+$", tokens[n]):
            n += 1
    elif head == "stdbuf":
        while n < len(tokens) and re.match(r"^-[ioe][LN0-9]+$", tokens[n]):
            n += 1
    elif head == "env":
        # 実測は裸の `env <cmd>` だけ。 option や代入付きの env は剥がさない側に倒す。
        return n if n < len(tokens) and not re.match(r"^-|\w+=", tokens[n]) else 0
    elif head not in ("time", "nohup"):
        return 0
    n += n < len(tokens) and tokens[n] == "--"
    return n


def _statement_command(tokens: list[str]) -> str:
    """Return the command Claude Code matches for one statement, empty when it stays sandboxed."""
    if tokens and tokens[0] == "!":
        tokens = tokens[1:]
    while tokens and (assignment := _ASSIGNMENT.match(tokens[0])):
        if assignment.group(1) not in SAFE_ENV:
            return ""
        tokens = tokens[1:]
    while tokens and (span := _wrapper_span(tokens)):
        tokens = tokens[span:]
    if not tokens or tokens[0] in CONTROL_WORDS or tokens[0] in SANDBOXED_HEADS:
        return ""
    if tokens[0].startswith((_QUOTE_MARK, "$")) or _ASSIGNMENT.match(tokens[0]):
        return ""
    if tokens[0] == "git" and len(tokens) > 1 and GIT_SANDBOXED_OPTION.match(tokens[1]):
        return ""
    return " ".join(tokens)


def host_run(cmd: str, patterns: list[str]) -> str:
    """Return the first excluded command if every command in the call is excluded and no shape keeps it sandboxed."""
    if not patterns or _HEREDOC.search(_QUOTED.sub("_", cmd)):
        return ""
    substituted = False

    def mask(m: re.Match) -> str:
        nonlocal substituted
        text = m.group(0)
        substituted = substituted or (
            text[0] == '"' and bool(_SUBSTITUTION.search(text))
        )
        return _QUOTE_MARK + _QUOTED_BREAKERS.sub("_", text[1:-1])

    scanned = _QUOTED.sub(mask, cmd.replace("\\\n", " "))
    scanned = _COMMENT.sub("", _FD_DUP.sub(" ", _BRACED_VAR.sub("_", scanned)))
    if substituted or _SUBSTITUTION.search(scanned) or _SANDBOXED_SHAPE.search(scanned):
        return ""
    if len(cmd) > SEGMENT_CAP:
        statements = [scanned.split()]
    else:
        statements, current = [], []
        for token in [*_TOKEN.findall(scanned), ";"]:
            if token in _SEPARATORS:
                if current:
                    statements.append(current)
                current = []
            else:
                current.append(token)
    first = ""
    for tokens in statements:
        command = _statement_command(tokens)
        if not any(glob_match(command, p) for p in patterns if command):
            return ""
        first = first or command.replace(_QUOTE_MARK, "")
    return first


def roster_text(patterns: list[str]) -> str:
    """Render the live host-escape roster plus the direct-invocation rule."""
    if not patterns:
        return (
            "この環境の sandbox.excludedCommands は空です。 session 内から sandbox の外へ"
            "出る手段はありません。\n" + BANG_CAVEAT
        )
    listed = " / ".join(f"`{p}`" for p in patterns)
    sample = bare_form(patterns[0])
    git_note = (
        " / `git -C <path> ...` `git -c k=v ...` (anthropics/claude-code#95455)"
        if any(bare_form(p) == "git" for p in patterns)
        else ""
    )
    return (
        f"この環境の sandbox.excludedCommands (設定から生成): {listed}\n"
        "これらは sandbox の外 (host 権限) で走り、 sandbox の filesystem / network "
        "制限を受けません。 ただし Bash 呼び出しが host で走るのは、 呼び出し内の全 command が"
        "一覧に一致し、 かつ sandbox に残る形を含まない時だけです。\n"
        f"host で走る形 (裸名で直指定): `{sample} ...` / `{sample} ... && {sample} ...` / "
        f"`timeout 5 {sample} ...` / `{sample} ... 2>&1`。\n"
        f"sandbox に残る形: `cd x && {sample} ...` (`cd` `pushd` `popd` は位置を問わない) / "
        f"`FOO=1 {sample} ...` (LANG・NODE_ENV など一部の既知変数を除く先頭代入) / "
        f"`{sample} ... | head` `{sample} ...; echo` (一覧外の command を含む) / "
        "`$(...)`・subshell・`if` `for` / `> file`・heredoc (fd 複製以外の redirect) / "
        f"`/usr/bin/{sample} ...` (path 前置) / `sudo {sample} ...` `command {sample} ...` "
        f"`npx {sample} ...` / quote した command 名{git_note}。 "
        "これらは sandbox の制限を受けます。 host が要る操作は、 一覧の command だけを"
        "裸名で並べた別の Bash 呼び出しに分けてください。\n"
        "plugin 由来の CLI も、 一覧にあれば host で走ります。 "
        "「plugin だから sandbox を出られない」 は誤りです。\n" + BANG_CAVEAT
    )


@contextlib.contextmanager
def _settings_fixture(system_settings: dict):
    """Point the module at a throwaway settings tree for the duration."""
    import sys
    from unittest import mock

    with tempfile.TemporaryDirectory() as tmp:
        system = os.path.join(tmp, "managed-settings.json")
        drop_in_dir = os.path.join(tmp, "managed-settings.d")
        os.makedirs(drop_in_dir)
        with open(system, "w", encoding="utf-8") as f:
            json.dump(system_settings, f)
        module = sys.modules[__name__]
        with (
            mock.patch.object(module, "SYSTEM_SETTINGS", system),
            mock.patch.object(
                module, "SYSTEM_SETTINGS_GLOB", os.path.join(drop_in_dir, "*.json")
            ),
            mock.patch.object(
                module, "USER_SETTINGS", os.path.join(tmp, "absent.json")
            ),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            yield {"system": system, "drop_in_dir": drop_in_dir}


class RosterTest(unittest.TestCase):
    """Roster rendering / bare-form derivation. Run: python3 -m unittest sandbox_exclusions"""

    PATTERNS = ["agent-browser *", "gh *", "node *codex-companion.mjs*"]

    def test_roster_lists_every_live_pattern(self):
        text = roster_text(self.PATTERNS)
        for pattern in self.PATTERNS:
            self.assertIn(f"`{pattern}`", text)

    def test_roster_states_the_every_command_rule(self):
        text = roster_text(self.PATTERNS)
        for phrase in (
            "直指定",
            "全 command",
            "path 前置",
            "sudo",
            "別の Bash 呼び出し",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("1 segment でも一致すれば", text)

    def test_roster_marks_cd_and_assignment_forms_as_sandboxed(self):
        text = roster_text(self.PATTERNS)
        host, sandboxed = text.split("sandbox に残る形:", 1)
        for form in ("timeout 5", "2>&1", "&& agent-browser"):
            self.assertIn(form, host)
        for form in (
            "cd x &&",
            "pushd",
            "FOO=1",
            "| head",
            "/usr/bin/",
            "sudo ",
            "npx ",
        ):
            self.assertIn(form, sandboxed)
            self.assertNotIn(form, host)
        self.assertNotIn("git -C", text)
        self.assertIn("git -C", roster_text(["git *"]))

    def test_roster_corrects_the_plugin_misconception(self):
        self.assertIn("plugin", roster_text(self.PATTERNS))

    def test_roster_denies_that_bang_prefix_escapes_the_sandbox(self):
        for text in (roster_text(self.PATTERNS), roster_text([])):
            self.assertIn(
                "`!` prefix での実行を依頼しても sandbox の外には出ません", text
            )
            self.assertIn("auto mode の実行許可だけ", text)
            self.assertIn("Claude Code の外の terminal", text)

    def test_roster_handles_an_empty_list(self):
        text = roster_text([])
        self.assertIn("空です", text)
        self.assertNotIn("裸名", text)

    def test_bare_form_strips_the_glob(self):
        self.assertEqual(bare_form("gh *"), "gh")
        self.assertEqual(bare_form("claude --bg *"), "claude --bg")
        self.assertEqual(bare_form("node *codex-companion.mjs*"), "node")
        self.assertEqual(bare_form("docker"), "docker")

    def test_patterns_are_reread_on_every_call(self):
        with _settings_fixture({"sandbox": {"excludedCommands": ["git *"]}}) as paths:
            self.assertEqual(load_patterns(), ["git *"])
            with open(paths["system"], "w", encoding="utf-8") as f:
                json.dump({"sandbox": {"excludedCommands": ["dsa *"]}}, f)
            self.assertEqual(load_patterns(), ["dsa *"])

    def test_drop_ins_are_scanned_and_unioned(self):
        with _settings_fixture({"sandbox": {"excludedCommands": ["git *"]}}) as paths:
            with open(os.path.join(paths["drop_in_dir"], "a.json"), "w") as f:
                json.dump({"sandbox": {"excludedCommands": ["docker *"]}}, f)
            self.assertEqual(load_patterns(), ["docker *", "git *"])

    def test_sandbox_restricts_commands_reflects_the_managed_switch(self):
        with _settings_fixture({"sandbox": {"enabled": True}}) as paths:
            self.assertTrue(sandbox_restricts_commands())
            with open(paths["system"], "w", encoding="utf-8") as f:
                json.dump({"sandbox": {"enabled": False}}, f)
            self.assertFalse(sandbox_restricts_commands())

    def test_sandbox_disabled_when_no_file_declares_it(self):
        with _settings_fixture({"sandbox": {"excludedCommands": ["git *"]}}):
            self.assertFalse(sandbox_restricts_commands())

    def test_unsandboxed_commands_allowance_lifts_the_restriction(self):
        settings = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": True}}
        with _settings_fixture(settings):
            self.assertFalse(sandbox_restricts_commands())

    def test_an_empty_roster_is_not_read_as_a_disabled_sandbox(self):
        with _settings_fixture({"sandbox": {"enabled": True}}):
            self.assertEqual(load_patterns(), [])
            self.assertTrue(sandbox_restricts_commands())

    def test_managed_settings_outrank_a_drop_in(self):
        with _settings_fixture({"sandbox": {"enabled": True}}) as paths:
            with open(os.path.join(paths["drop_in_dir"], "a.json"), "w") as f:
                json.dump({"sandbox": {"enabled": False}}, f)
            self.assertTrue(sandbox_restricts_commands())

    def test_file_is_executable(self):
        self.assertTrue(os.access(os.path.abspath(__file__), os.X_OK))


class HostRunTest(unittest.TestCase):
    """Where Claude Code runs a Bash call. Run: python3 -m unittest sandbox_exclusions"""

    PATTERNS = ["git *", "gh *", "cargo test *", "node *codex-companion.mjs*"]
    # 2.1.280 で 1 形ずつ別の Bash 呼び出しにして、 git ls-remote が sandbox proxy を通るかで実測した形。
    MEASURED_HOST = (
        "git ls-remote https://example.com/p.git",
        "time git ls-remote u",
        "nice -n 10 git ls-remote u",
        "nohup git ls-remote u",
        "stdbuf -oL git ls-remote u",
        "timeout 5 git ls-remote u",
        "env git ls-remote u",
        "NODE_ENV=test git ls-remote u",
        "LANG=C git ls-remote u",
        "git ls-remote u 2>&1",
        "git --version && git ls-remote u",
        "git ls-remote u || git --version",
        "git --version; git ls-remote u",
        "git ls-remote u | git hash-object --stdin",
        "! git ls-remote u",
    )
    MEASURED_SANDBOX = (
        "FOO=1 git ls-remote u",
        "GIT_PAGER=cat git diff --no-index a b",
        "x=1; git ls-remote u",
        "pushd /repo && git ls-remote u",
        "git -C /repo ls-remote u",
        "git -c core.quotepath=off ls-remote u",
        "command git ls-remote u",
        "git ls-remote u >/dev/null",
        "git ls-remote u <<'EOF'\nx\nEOF",
        '"git" ls-remote u',
        "(git ls-remote u)",
        "{ git ls-remote u; }",
        "if git --version; then git ls-remote u; fi",
        'git ls-remote "$(git config --get remote.origin.url)x"',
        "git ls-remote u | head -1",
        "git ls-remote u; echo rc=$?",
    )
    # 公式 settings reference の列挙と、 一覧外 command を含む呼び出しからの帰結 (未実測)。
    DOCUMENTED_SANDBOX = (
        "",
        "cd x && git push",
        "git push && cd x",
        "popd && git push",
        "VAR=val git push",
        "FOO=1 timeout 5 git push",
        "PATH=/x git push",
        "sudo git push",
        "eval git push",
        "xargs git push",
        "$GIT push",
        "git --git-dir=/r/.git status",
        "git log > out.txt",
        "git log &> out.txt",
        "cat msg | git commit -F -",
        "echo `git status`",
        "VERSION=$(git describe)",
        "for f in a b; do git add $f; done",
        "case x in a) git push;; esac",
        "echo 'git push'",
        "# git push",
        "env -i git push",
        "/usr/bin/git push",
        "gitk",
        "cargo build",
        "node app.js",
    )
    DERIVED_HOST = (
        "git",
        "git commit -F $TMPDIR/msg",
        "git commit -F ${TMPDIR:-/tmp}/msg",
        'git commit -m "a; b > c"',
        "git log 2>&1 | git hash-object --stdin",
        "git commit \\\n  -m x",
        "cargo test foo",
        "node ./codex-companion.mjs run",
        "gh pr view; gh pr checks",
    )

    def test_measured_forms(self):
        for cmd in self.MEASURED_HOST:
            self.assertTrue(host_run(cmd, self.PATTERNS), cmd)
        for cmd in self.MEASURED_SANDBOX:
            self.assertEqual(host_run(cmd, self.PATTERNS), "", cmd)

    def test_documented_and_derived_forms(self):
        for cmd in self.DERIVED_HOST:
            self.assertTrue(host_run(cmd, self.PATTERNS), cmd)
        for cmd in self.DOCUMENTED_SANDBOX:
            self.assertEqual(host_run(cmd, self.PATTERNS), "", cmd)

    def test_returns_the_first_excluded_command_unquoted(self):
        self.assertEqual(
            host_run('git commit -m "x" && gh pr view', self.PATTERNS),
            "git commit -m x",
        )

    def test_no_patterns_means_nothing_runs_on_the_host(self):
        self.assertEqual(host_run("git push", []), "")

    def test_over_the_cap_only_the_leading_form_counts(self):
        filler = "echo x; " * 1300
        self.assertEqual(host_run(filler + "git push", self.PATTERNS), "")
        self.assertTrue(host_run("git push; " + filler, self.PATTERNS))


if __name__ == "__main__":
    unittest.main()
