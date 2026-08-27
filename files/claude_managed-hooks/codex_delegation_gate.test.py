#!/usr/bin/env python3
"""Acceptance tests for codex_delegation_gate.py (the rewrite that also absorbs codex_worktree_gate.py).

Written by the ordering side before the implementation. Black box: payload on stdin, decision on stdout.

Contract (each claim maps to the tests named test_c<N>_*):
  C1  PreToolUse hook without matcher. allow = no stdout, exit 0. deny = one stdout JSON line
      {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
      "permissionDecisionReason": "codex-delegation-gate: [<id>] ..."}} with exit 0; the reason names the
      corrective action and ends with the sentence that the hook itself changes no file. The corrective
      sentence is rule-specific: [tree] names `git worktree add` and `--cwd`, [same-root] names the
      standalone `cd` and an absolute `--cwd` (its violation sentence also names `env -C`), [isolation]
      names removing isolation, [workflow] names the codex-delegation skill. Fail-open (exit 0, no stdout, one stderr line) for
      unreadable payload, non-dict payload, non-PreToolUse events and any internal exception.
  C2  Launch enumeration is the single funnel every rule reads from: a launch is `node|nodejs <path ending in
      codex-companion.mjs> <sub> <args>` or `codex <sub> <args>` at the program position of a segment
      (segments split on ; && || | & newline ( ) brace groups, backtick and $( ) substitutions — also
      inside double quotes), after peeling assignment words, `timeout N`, env, sudo, exec, nohup, time,
      command, builtin, xargs and shell keywords. Node options before the script are skipped and the
      subcommand is the first non-option token after the script. An assignment in the same command that
      binds NAME to a path ending in codex-companion.mjs makes `node $NAME` / `"$NAME"` / `${NAME}` a
      launch; unbound variables and variables with a path suffix are not. `bash|sh|zsh -c` strings are
      expanded one level; backslash-newline joins a line. Text inside quoted strings, heredoc bodies and
      # comments is never a launch (rg / grep / cat / python heredoc / order-document heredoc); a `#`
      comment is removed before heredoc markers are looked for. Backslash-escaped operators and array
      assignments `name=( ... )` are not segments. Internal placeholders never collide with command text
      (a literal `__CDGQ_ff__` is ordinary text). Every launch in a command is checked and a deny for any
      launch wins over context / warning for another. Shell redirects are not argv, tokens after `--` are
      not options, `-C dir` means `--cwd dir`.
      Node options that take a value (-r/--require, --import, --loader, --experimental-loader,
      -C/--conditions, --input-type, --env-file) consume it before the script is located. Wrapper
      options that take a value are consumed before the program (timeout -s/--signal/-k/--kill-after,
      env -u/--unset, time -f/--format/-o/--output, xargs -I/-i/-L/-n/-P/-d/-a/-E/-s
      and their long forms, sudo -u/-g/-C/-D/-h/-p/-r/-t/-T/-U and their long forms). A short option
      cluster of bash|sh|zsh that contains `c` (-lc, -ec, -cl) is a `-c`; `eval` of literal words is one
      more expansion level. Unquoted backslashes inside a program word are removed before comparison.
      Out of scope (allowed): program words built from variables or substitutions, text piped into a
      shell, `source` / `.`, alias and function bodies, `bash -s` and `env -S`. `command -v|-V name`
      looks a name up and is not a launch. `npx` / `bunx` / `uvx` are wrappers whose operand is the
      program (npx -p/--package/-c/--call take a value). A heredoc delimiter is any quoted or
      backslash-prefixed word (`<<\EOF`, `<<'E.OF'`); `<<<` is a here-string, not a heredoc. A `<<`
      inside quotes is text, and a body ends only on a line equal to the delimiter (leading tabs are
      stripped for `<<-` only).
      `bash -c -- <string>` skips the `--`.
  C3  [route] / [cli]: without agent_id every companion subcommand and every delegating codex CLI form
      (bare `codex`, exec, apply, resume, review, cloud ...) is denied; login / logout / mcp / completion /
      --version / --help pass when the flag comes before the second positional token; `--config` /
      `-c` takes a value. `CODEX_DELEGATION_OK=1` at the segment start passes the CLI only.
      The Monitor tool is checked like Bash. With agent_id the launch passes when agent_type contains
      codex-rescue or is absent; any other agent_type is denied.
  C4  [skill]: delegation surfaces (Agent/Task whose subagent_type contains codex, Skill codex:* other than
      the safe set, companion launches from a subagent) require the codex-delegation checkpoint in
      $HOME/.claude/hooks/state/skill_reminder/active/<session_id>/main.json = {"codex-delegation": {"ts",
      "prompt_id"}}. Main agent: prompt_id must match (no prompt_id in payload: ts within 1800 s).
      Subagent: any codex-delegation record in main.json passes; the subagent's own bucket never counts;
      a missing main.json passes for a subagent and denies the main agent; missing session_id or a corrupt
      file passes.
  C5  [isolation]: Agent/Task delegation with isolation "worktree" is denied.
  C6  [order]: Agent/Task/Skill delegation must carry an order path (a .md token) in prompt/args; Skill
      args with --resume are exempt. A subagent task with --write and without --resume/--resume-last must
      name exactly one order file (--prompt-file wins, else exactly one .md token in the task argv), which
      resolves against --cwd (else payload cwd) to a regular file whose `$CODEX_ORDER_LINT --metadata <abs>`
      output has order_document true and empty findings; a `.md` token followed by `)` `,` `。` `、` still
      counts. A metadata report_path requires --write.
      Lint missing / unparsable output denies the write launch. A read-only launch that names one order
      file runs lint only for the report_path rule (order_document and findings are not enforced, a lint
      failure passes); resume launches never run lint.
      Skill args that are missing or not a string carry no order path.
  C7  [flag]: a task argv option outside the companion's accepted set (--model -m --effort --cwd -C
      --prompt-file --json --write --resume-last --resume --fresh --background) is denied, because the
      companion turns it into prompt text; tokens after `--` are exempt.
  C8  [cjk]: a task whose positional prompt has more than 200 CJK characters and no --prompt-file is denied.
  C9  [tree]: a write-capable task or task-worker (--write / --resume / --resume-last) whose launch cwd
      (--cwd, else payload cwd) is a primary checkout (git-dir == git-common-dir) is denied;
      `CODEX_SHARED_TREE_OK=1` at the segment start passes it and emits additionalContext. The [flag]
      rule stays task-only.
  C10 [same-root]: for task / task-worker / review / adversarial-review the git toplevel of the launch cwd
      must equal the toplevel of the payload cwd (the broker key that SessionEnd tears down). A cd / pushd
      program word before the launch, `env -C dir` / `env --chdir=dir` in front of it, or a --cwd that
      cannot be resolved statically ($var, `...`, ~user, glob characters, backslashes), is the same deny
      and is evaluated before the [tree] rule. A `cd()` function definition is not a cd. Outside a git
      repo, or when git cannot run, the check fails open with one stderr line.
  C11 [workflow]: a Workflow script (or the first 64 KB of scriptPath) whose agent spec names codex
      through agentType / subagent_type / subagentType (key optionally quoted, value in any quote
      including backticks) is denied regardless of the checkpoint. Shell
      text, comments and string prose inside the script are not inspected (a subagent's own Bash and
      Skill calls are gated by this hook).
  C12 Commands without a codex launch produce no output at all (corpus replay: 0 denies).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "codex_delegation_gate.py"
)
COMP = "/opt/plugins/codex/scripts/codex-companion.mjs"
NODE = f'node "{COMP}"'
SESSION = "sess-1"
PROMPT = "prompt-1"
RESCUE = "codex:codex-rescue"
CJK_250 = "検査" * 125
CJK_150 = "検査" * 75

FAKE_LINT = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_LINT_LOG"], "a", encoding="utf-8") as log:
        log.write(" ".join(args) + "\\n")
    path = args[-1]
    with open(path, encoding="utf-8") as fh:
        first = fh.readline().strip()
    if first == "GARBAGE":
        print("not json")
        sys.exit(0)
    findings = ["未記入 が残っています"] if first == "ORDER findings" else []
    report = os.path.join(os.path.dirname(path), "report.md") if first == "ORDER report" else None
    print(json.dumps({"path": os.path.abspath(path), "order_document": first.startswith("ORDER"),
                      "review_kind": "none", "round": None, "scope": None, "methods": [],
                      "has_previous_verdict": False, "report_path": report, "findings": findings}))
    sys.exit(1 if findings else 0)
    """
)


def git(*args: str, cwd: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "GIT_CONFIG_GLOBAL": "/dev/null", "HOME": cwd},
    )


class Fixture:
    """Temp HOME (skill state), a primary repo with one linked worktree, and a fake order lint."""

    def __init__(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="cdg-")
        self.home = os.path.join(self.tmp, "home")
        self.primary = os.path.join(self.tmp, "repo")
        self.worktree = os.path.join(self.primary, "wt")
        self.other = os.path.join(self.tmp, "other")
        self.plain_dir = os.path.join(self.tmp, "plain")
        for path in (self.home, self.primary, self.other, self.plain_dir):
            os.makedirs(path)
        git("init", "-q", cwd=self.primary)
        git("commit", "-q", "--allow-empty", "-m", "root", cwd=self.primary)
        git("worktree", "add", "-q", "wt", cwd=self.primary)
        git("init", "-q", cwd=self.other)
        git("commit", "-q", "--allow-empty", "-m", "root", cwd=self.other)
        self.lint = os.path.join(self.tmp, "fake_lint.py")
        with open(self.lint, "w", encoding="utf-8") as fh:
            fh.write(FAKE_LINT)
        os.chmod(self.lint, 0o755)
        self.lint_log = os.path.join(self.tmp, "lint.log")
        for base in (self.primary, self.worktree):
            os.makedirs(os.path.join(base, "drafts"))
            self.order(base, "drafts/o.md", "ORDER ok")
            self.order(base, "drafts/plain.md", "PLAIN")
            self.order(base, "drafts/bad.md", "ORDER findings")
            self.order(base, "drafts/rep.md", "ORDER report")
            self.order(base, "drafts/garbage.md", "GARBAGE")
            self.order(base, "drafts/o2.md", "ORDER ok")

    def order(self, base: str, rel: str, first_line: str) -> str:
        path = os.path.join(base, rel)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(first_line + "\n# 発注書\n")
        return path

    def seed(
        self,
        bucket: str = "main",
        skill: str = "codex-delegation",
        prompt_id: str = PROMPT,
        ts: float | None = None,
    ) -> None:
        state_dir = os.path.join(
            self.home, ".claude", "hooks", "state", "skill_reminder", "active", SESSION
        )
        os.makedirs(state_dir, exist_ok=True)
        path = os.path.join(state_dir, bucket + ".json")
        state = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                state = json.load(fh)
        state[skill] = {"ts": time.time() if ts is None else ts, "prompt_id": prompt_id}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)

    def corrupt_main(self) -> None:
        state_dir = os.path.join(
            self.home, ".claude", "hooks", "state", "skill_reminder", "active", SESSION
        )
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, "main.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def run_hook(
    payload: object, fx: Fixture, *, raw: str | None = None, lint: str | None = None
) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": fx.home,
        "CODEX_ORDER_LINT": fx.lint if lint is None else lint,
        "FAKE_LINT_LOG": fx.lint_log,
    }
    body = raw if raw is not None else json.dumps(payload, ensure_ascii=False)
    return subprocess.run(
        [sys.executable, HOOK],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
    )


def decision(proc: subprocess.CompletedProcess) -> tuple[str, str]:
    """('allow' | 'deny' | 'context', reason-or-context)."""
    for line in proc.stdout.splitlines():
        data = json.loads(line)
        out = data["hookSpecificOutput"]
        if out.get("permissionDecision"):
            return out["permissionDecision"], out.get("permissionDecisionReason", "")
        if out.get("additionalContext"):
            return "context", out["additionalContext"]
    return "allow", ""


class GateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = Fixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def setUp(self) -> None:
        shutil.rmtree(os.path.join(self.fx.home, ".claude"), ignore_errors=True)
        if os.path.exists(self.fx.lint_log):
            os.remove(self.fx.lint_log)

    # -- payload builders ----------------------------------------------------------------------
    def bash(
        self,
        command: str,
        *,
        cwd: str | None = None,
        tool: str = "Bash",
        agent: str | None = None,
        agent_type: str | None = None,
        prompt: str | None = PROMPT,
        session: str | None = SESSION,
    ) -> dict:
        payload: dict = {
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": {"command": command},
            "cwd": self.fx.worktree if cwd is None else cwd,
        }
        if session is not None:
            payload["session_id"] = session
        if prompt is not None:
            payload["prompt_id"] = prompt
        if agent is not None:
            payload["agent_id"] = agent
        if agent_type is not None:
            payload["agent_type"] = agent_type
        return payload

    def rescue(self, command: str, **kw) -> dict:
        kw.setdefault("agent", "agent-1")
        kw.setdefault("agent_type", RESCUE)
        return self.bash(command, **kw)

    def tool(self, name: str, tool_input: dict, **kw) -> dict:
        payload = self.bash("", **kw)
        payload["tool_name"] = name
        payload["tool_input"] = tool_input
        return payload

    def agent(
        self, prompt: str = "発注書 drafts/o.md に従って実装せよ", **extra
    ) -> dict:
        return self.tool("Agent", {"subagent_type": RESCUE, "prompt": prompt, **extra})

    # -- assertions ----------------------------------------------------------------------------
    def deny(self, payload: dict, rule: str, **kw) -> str:
        proc = run_hook(payload, self.fx, **kw)
        verdict, reason = decision(proc)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            verdict,
            "deny",
            f"{payload['tool_input']!r}: {verdict} {reason} {proc.stderr}",
        )
        self.assertTrue(reason.startswith("codex-delegation-gate: ["), reason)
        self.assertIn(f"[{rule}]", reason)
        self.assertIn("この hook 自身は file を変更しません", reason)
        return reason

    def allow(self, payload: dict, **kw) -> subprocess.CompletedProcess:
        proc = run_hook(payload, self.fx, **kw)
        verdict, reason = decision(proc)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(verdict, "allow", f"{payload['tool_input']!r}: {reason}")
        self.assertEqual(proc.stdout, "", proc.stdout)
        return proc

    # -- C1 ------------------------------------------------------------------------------------
    def test_c1_deny_shape_and_corrective_text(self) -> None:
        reason = self.deny(self.bash(f"{NODE} task --write drafts/o.md"), "route")
        self.assertIn("codex:codex-rescue", reason)
        proc = run_hook(self.bash(f"{NODE} task --write drafts/o.md"), self.fx)
        data = json.loads(proc.stdout.strip())
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(len(proc.stdout.strip().splitlines()), 1)

    def test_c1_fail_open(self) -> None:
        for raw in ("{not json", "[]", "null", ""):
            proc = run_hook(None, self.fx, raw=raw)
            self.assertEqual((proc.returncode, proc.stdout), (0, ""), raw)
        post = self.bash(f"{NODE} task x")
        post["hook_event_name"] = "PostToolUse"
        self.allow(post)
        self.allow(
            self.tool(
                "Write",
                {"file_path": "/x/codex-companion.mjs", "content": "node x task"},
            )
        )
        odd = self.bash("")
        odd["tool_input"] = "not a dict"
        self.allow(odd)

    # -- C2 ------------------------------------------------------------------------------------
    def test_c2_mentions_are_not_launches(self) -> None:
        for command in (
            "rg -n 'codex-companion.mjs' files/claude_managed-hooks/codex_delegation_gate.py",
            "grep -rn codex-companion.mjs ~/.claude/plugins | head",
            "find ~/.claude/plugins -name codex-companion.mjs",
            f"ls -la {COMP}",
            f"cat {COMP} | head -20",
            f"python3 - <<'PY'\nSCRIPT = \"{COMP}\"\nprint(SCRIPT, 'codex exec')\nPY",
            "cat > drafts/policy.md <<'EOF'\ncodex exec で直接叩かない\n"
            f"node {COMP} task を rescue 経由で使う\nEOF",
            "python3 - <<'PYEOF'\nimport re\nRX = re.compile(r\"\\bcodex\\s+exec\\b\")\nPYEOF",
            f"echo 'node {COMP} task'",
            f'git commit -m "gate: node {COMP} task and codex exec are denied" -- todos.md',
            "echo codex exec",
            f"# node {COMP} task --write o.md\nls",
            f"printf '%s\\n' \"{NODE} task\" > note.txt",
            "wc -l files/codex_task_sentinel; grep -c 'codex exec' docs/codex-delegation-policy.md",
        ):
            self.allow(self.bash(command))

    def test_c2_launch_forms_are_found(self) -> None:
        for command in (
            f"{NODE} task --write drafts/o.md",
            f"nodejs {COMP} status --json",
            f'S=$(node {COMP} status --json); echo "$S"',
            f"timeout 30 {NODE} task x",
            f"ls; {NODE} task x",
            f"bash -c '{NODE} task --write drafts/o.md'",
            f'node \\\n  "{COMP}" \\\n  task --write drafts/o.md',
            f"for d in a b; do {NODE} task $d; done",
            f"sudo -E {NODE} task x",
            f"X=1 {NODE} task x",
            f"({NODE} task x)",
            f"echo hi | {NODE} task x",
            f"if {NODE} status --json; then echo up; fi",
            f"while {NODE} status --json; do sleep 1; done",
            f"nohup {NODE} task --background x &",
            f"exec {NODE} task x",
            f"env {NODE} task x",
            f"xargs -0 {NODE} task < args.txt",
            f"{NODE} --help",
            f"{NODE} setup --json",
        ):
            self.deny(self.bash(command), "route")

    def test_c2_redirect_operand_is_not_an_order_argument(self) -> None:
        self.fx.seed()
        self.deny(self.rescue(f"{NODE} task --write inline < drafts/o.md"), "order")
        self.deny(self.rescue(f"{NODE} task --write inline > drafts/o.md"), "order")

    def test_c2_passthrough_tokens_are_prompt_text(self) -> None:
        self.fx.seed()
        self.allow(self.rescue(f"{NODE} task --write drafts/o.md -- --resume"))
        self.allow(self.rescue(f"{NODE} task --write drafts/o.md -- --workspace x"))

    def test_c2_short_cwd_alias(self) -> None:
        self.fx.seed()
        self.allow(
            self.rescue(f"{NODE} task -C {self.fx.worktree} --write drafts/o.md")
        )
        self.deny(self.rescue(f"{NODE} task -C {self.fx.other} x"), "same-root")

    # -- C3 ------------------------------------------------------------------------------------
    def test_c3_main_agent_companion_is_denied_for_every_subcommand(self) -> None:
        self.fx.seed()
        for sub in (
            "task --write drafts/o.md",
            "task-worker --cwd . --job-id j",
            "status --json",
            "result j",
            "cancel j",
            "review --scope working-tree",
            "adversarial-review --wait",
            "setup --json",
            "task-resume-candidate --json",
            "transfer",
            "--help",
        ):
            self.deny(self.bash(f"{NODE} {sub}"), "route")
        self.deny(self.bash(f"{NODE} task x", tool="Monitor"), "route")
        self.deny(
            self.bash(f"CODEX_DELEGATION_OK=1 {NODE} task --write drafts/o.md"), "route"
        )

    def test_c3_bare_cli_forms(self) -> None:
        for command in (
            "codex",
            'codex "fix the failing test"',
            "codex exec 'x'",
            "codex apply x",
            "codex resume",
            "codex review",
            "codex cloud exec x",
            "/usr/local/bin/codex exec x",
            "cd /r && codex exec x",
        ):
            self.deny(self.bash(command), "cli")
        for command in (
            "codex login",
            "codex logout",
            "codex --version",
            "codex -V",
            "codex --help",
            "codex mcp list",
            "codex completion bash",
            "CODEX_DELEGATION_OK=1 codex exec x",
            "codex-something --version",
            "python3 codex_broker_reap --status",
        ):
            self.allow(self.bash(command))
        self.fx.seed()
        self.deny(self.rescue("codex exec x"), "cli")

    def test_c3_subagent_route_by_agent_type(self) -> None:
        self.fx.seed()
        self.allow(self.rescue(f"{NODE} status --json"))
        self.allow(self.rescue(f"{NODE} status --json", agent_type="codex-rescue"))
        self.allow(self.rescue(f"{NODE} status --json", agent_type=None))
        self.deny(
            self.rescue(f"{NODE} status --json", agent_type="general-purpose"), "route"
        )
        self.deny(self.rescue(f"{NODE} task x", agent_type="Explore"), "route")

    # -- C4 ------------------------------------------------------------------------------------
    def test_c4_main_agent_checkpoint_by_prompt_id(self) -> None:
        self.deny(self.agent(), "skill")
        self.fx.seed(prompt_id="other-prompt")
        self.deny(self.agent(), "skill")
        self.fx.seed()
        self.allow(self.agent())
        task = self.agent()
        task["tool_name"] = "Task"
        self.allow(task)

    def test_c4_main_agent_without_prompt_id_uses_window(self) -> None:
        self.fx.seed(ts=time.time() - 60)
        payload = self.agent()
        del payload["prompt_id"]
        self.allow(payload)
        self.fx.seed(ts=time.time() - 3600)
        self.deny(payload, "skill")

    def test_c4_missing_session_or_corrupt_state_passes(self) -> None:
        payload = self.agent()
        del payload["session_id"]
        self.allow(payload)
        self.fx.corrupt_main()
        self.allow(self.agent())

    def test_c4_skill_surface(self) -> None:
        self.deny(
            self.tool("Skill", {"skill": "codex:rescue", "args": "drafts/o.md を実装"}),
            "skill",
        )
        self.fx.seed()
        self.allow(
            self.tool("Skill", {"skill": "codex:rescue", "args": "drafts/o.md を実装"})
        )
        for safe in (
            "codex:status",
            "codex:result",
            "codex:cancel",
            "codex:setup",
            "codex:codex-cli-runtime",
            "codex:codex-result-handling",
            "codex:gpt-5-4-prompting",
        ):
            self.allow(self.tool("Skill", {"skill": safe, "args": ""}, prompt="other"))
        self.allow(
            self.tool(
                "Skill", {"skill": "codex-delegation", "args": ""}, prompt="other"
            )
        )

    def test_c4_subagent_needs_any_main_record(self) -> None:
        self.allow(self.rescue(f"{NODE} task x"))
        self.fx.seed(skill="writing-code")
        self.deny(self.rescue(f"{NODE} task x"), "skill")
        self.fx.seed(prompt_id="an-earlier-prompt")
        self.allow(self.rescue(f"{NODE} task x"))

    def test_c4_subagent_own_bucket_does_not_count(self) -> None:
        self.fx.seed(bucket="agent-1")
        self.fx.seed(bucket="main", skill="writing-code")
        self.deny(self.rescue(f"{NODE} task x"), "skill")

    # -- C5 ------------------------------------------------------------------------------------
    def test_c5_isolation_worktree(self) -> None:
        self.fx.seed()
        self.deny(self.agent(isolation="worktree"), "isolation")
        self.allow(self.agent(isolation="remote"))

    # -- C6 ------------------------------------------------------------------------------------
    def test_c6_agent_and_skill_need_an_order_path(self) -> None:
        self.fx.seed()
        self.deny(self.agent("この bug を直して"), "order")
        self.deny(
            self.tool("Skill", {"skill": "codex:rescue", "args": "この bug を直して"}),
            "order",
        )
        self.allow(
            self.tool("Skill", {"skill": "codex:rescue", "args": "--resume 続きを"})
        )
        self.allow(
            self.tool(
                "Skill",
                {"skill": "codex:rescue", "args": "/abs/drafts/order-x.md --fresh"},
            )
        )

    def test_c6_write_task_requires_one_lintable_order(self) -> None:
        self.fx.seed()
        self.allow(self.rescue(f'{NODE} task --write "発注書 drafts/o.md に従う"'))
        self.allow(self.rescue(f"{NODE} task --write --prompt-file drafts/o.md"))
        self.allow(
            self.rescue(f"{NODE} task --write --cwd {self.fx.worktree} drafts/o.md")
        )
        self.deny(self.rescue(f'{NODE} task --write "この bug を直して"'), "order")
        self.deny(self.rescue(f"{NODE} task --write drafts/o.md drafts/o2.md"), "order")
        self.deny(self.rescue(f"{NODE} task --write drafts/missing.md"), "order")
        self.deny(self.rescue(f"{NODE} task --write drafts/plain.md"), "order")
        self.deny(self.rescue(f"{NODE} task --write drafts/bad.md"), "order")
        self.deny(self.rescue(f"{NODE} task --write drafts/garbage.md"), "order")
        self.deny(self.rescue(f"{NODE} task --write drafts"), "order")
        with open(self.fx.lint_log, encoding="utf-8") as fh:
            calls = fh.read().splitlines()
        self.assertTrue(
            calls and all(c.startswith("--metadata /") for c in calls), calls
        )

    def test_c6_prompt_file_wins_over_mentions(self) -> None:
        self.fx.seed()
        self.allow(
            self.rescue(
                f"{NODE} task --write --prompt-file drafts/o.md drafts/plain.md drafts/bad.md"
            )
        )

    def test_c6_read_only_ignores_findings_and_resume_skips_lint(self) -> None:
        self.fx.seed()
        self.allow(self.rescue(f"{NODE} task drafts/plain.md"))
        self.allow(self.rescue(f"{NODE} task drafts/bad.md"))
        self.allow(self.rescue(f"{NODE} task drafts/garbage.md"))
        self.allow(self.rescue(f"{NODE} task 'この bug を調査して'"))
        self.allow(self.rescue(f"{NODE} task --write --resume-last drafts/o.md"))
        self.allow(self.rescue(f"{NODE} task --write --resume 続き drafts/o.md"))
        calls = []
        if os.path.exists(self.fx.lint_log):
            with open(self.fx.lint_log, encoding="utf-8") as fh:
                calls = fh.read().splitlines()
        self.assertFalse([c for c in calls if c.endswith("o.md")], calls)

    def test_c6_report_requires_write(self) -> None:
        self.fx.seed()
        self.deny(self.rescue(f"{NODE} task drafts/rep.md"), "order")
        self.allow(self.rescue(f"{NODE} task --write drafts/rep.md"))

    def test_c6_lint_failure_denies_write_launch_only(self) -> None:
        self.fx.seed()
        missing = os.path.join(self.fx.tmp, "no-such-lint")
        self.deny(
            self.rescue(f"{NODE} task --write drafts/o.md"), "order", lint=missing
        )
        self.allow(self.rescue(f"{NODE} task drafts/o.md"), lint=missing)

    # -- C7 ------------------------------------------------------------------------------------
    def test_c7_unknown_task_flags(self) -> None:
        self.fx.seed()
        self.deny(
            self.rescue(f"{NODE} task --write drafts/o.md --workspace /x"), "flag"
        )
        self.deny(self.rescue(f"{NODE} task --help"), "flag")
        self.deny(self.rescue(f"{NODE} task --wait drafts/o.md"), "flag")
        self.allow(
            self.rescue(
                f"{NODE} task --write drafts/o.md -m gpt-5.6-sol --effort high --background --fresh"
                f" --json --model=gpt-5.6-luna -C {self.fx.worktree}"
            )
        )
        self.allow(
            self.rescue(
                f"{NODE} adversarial-review --background --base main --scope branch focus"
            )
        )
        self.allow(self.rescue(f"{NODE} review --wait --whatever"))

    # -- C8 ------------------------------------------------------------------------------------
    def test_c8_cjk_inline_prompt(self) -> None:
        self.fx.seed()
        self.deny(self.rescue(f'{NODE} task "{CJK_250}"'), "cjk")
        self.allow(self.rescue(f'{NODE} task "{CJK_150}"'))
        self.allow(self.rescue(f'{NODE} task --prompt-file drafts/o.md "{CJK_250}"'))

    # -- C9 ------------------------------------------------------------------------------------
    def test_c9_write_task_on_primary_checkout(self) -> None:
        self.fx.seed()
        primary = self.fx.primary
        self.deny(self.rescue(f"{NODE} task --write drafts/o.md", cwd=primary), "tree")
        self.deny(
            self.rescue(f"{NODE} task --write --resume-last", cwd=primary), "tree"
        )
        self.deny(self.rescue(f"{NODE} task --resume x", cwd=primary), "tree")
        self.allow(self.rescue(f"{NODE} task drafts/o.md", cwd=primary))
        self.allow(self.rescue(f"{NODE} adversarial-review --wait", cwd=primary))
        self.allow(self.rescue(f"{NODE} task --write drafts/o.md"))
        self.allow(
            self.rescue(
                f"{NODE} task --write o.md",
                cwd=os.path.join(self.fx.worktree, "drafts"),
            )
        )

    def test_c9_shared_tree_escape_hatch(self) -> None:
        self.fx.seed()
        proc = run_hook(
            self.rescue(
                f"CODEX_SHARED_TREE_OK=1 {NODE} task --write drafts/o.md",
                cwd=self.fx.primary,
            ),
            self.fx,
        )
        verdict, context = decision(proc)
        self.assertEqual(verdict, "context", proc.stdout + proc.stderr)
        self.assertIn("共有", context)
        self.deny(
            self.rescue(
                f"{NODE} task --write drafts/o.md CODEX_SHARED_TREE_OK=1",
                cwd=self.fx.primary,
            ),
            "tree",
        )

    # -- C10 -----------------------------------------------------------------------------------
    def test_c10_launch_root_must_match_session_root(self) -> None:
        self.fx.seed()
        wt, primary, other = self.fx.worktree, self.fx.primary, self.fx.other
        self.deny(self.rescue(f"{NODE} task --cwd {wt} x", cwd=primary), "same-root")
        self.deny(self.rescue(f"{NODE} task --cwd {primary} x", cwd=wt), "same-root")
        self.deny(self.rescue(f"{NODE} task --cwd {other} x", cwd=wt), "same-root")
        self.deny(self.rescue(f"{NODE} review --cwd {other}", cwd=wt), "same-root")
        self.deny(
            self.rescue(f"{NODE} adversarial-review --cwd={other} --wait", cwd=wt),
            "same-root",
        )
        self.deny(
            self.rescue(f"{NODE} task-worker --cwd {other} --job-id j", cwd=wt),
            "same-root",
        )
        self.allow(self.rescue(f"{NODE} task --cwd {wt} x", cwd=wt))
        self.allow(self.rescue(f"{NODE} task --cwd ./drafts x", cwd=wt))
        self.allow(
            self.rescue(f"{NODE} task --cwd {os.path.join(wt, 'drafts')} x", cwd=wt)
        )
        self.allow(self.rescue(f"{NODE} status --cwd {other} --json", cwd=wt))
        self.allow(self.rescue(f"{NODE} cancel --cwd {other} j", cwd=wt))

    def test_c10_cd_prefix_and_unresolvable_cwd(self) -> None:
        self.fx.seed()
        wt = self.fx.worktree
        self.deny(self.rescue(f"cd {wt} && {NODE} task x"), "same-root")
        self.deny(
            self.rescue(f"pushd {wt} >/dev/null && {NODE} task x; popd"), "same-root"
        )
        self.deny(self.rescue(f"cd {wt}\n{NODE} task x"), "same-root")
        self.deny(self.rescue(f'{NODE} task --cwd "$WT" x'), "same-root")
        self.deny(self.rescue(f"{NODE} task --cwd $(pwd) x"), "same-root")
        self.deny(self.rescue(f"{NODE} task --cwd ~someone/x x"), "same-root")
        self.allow(self.rescue(f"cd() {{ return 1; }}; {NODE} task x"))
        self.allow(self.rescue(f"{NODE} task x && cd {wt}"))

    def test_c10_fail_open_outside_git(self) -> None:
        self.fx.seed()
        proc = self.allow(self.rescue(f"{NODE} task x", cwd=self.fx.plain_dir))
        self.assertIn("codex-delegation-gate", proc.stderr)
        gone = os.path.join(self.fx.tmp, "gone")
        proc = self.allow(self.rescue(f"{NODE} task x", cwd=gone))
        self.assertIn("codex-delegation-gate", proc.stderr)

    # -- C11 -----------------------------------------------------------------------------------
    def test_c11_workflow_codex_step(self) -> None:
        self.fx.seed()
        script = "await agent('x', {agentType: \"codex:codex-rescue\"})"
        self.deny(self.tool("Workflow", {"script": script}), "workflow")
        self.allow(
            self.tool(
                "Workflow",
                {
                    "script": "export const meta = {description: 'codex 実装を opus がレビュー'}\n"
                },
            )
        )
        path = os.path.join(self.fx.tmp, "wf.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(script)
        self.deny(self.tool("Workflow", {"scriptPath": path}), "workflow")

    # -- C12 -----------------------------------------------------------------------------------
    def test_c12_non_codex_commands_are_silent(self) -> None:
        for command in (
            "git -C /r status --short",
            "git commit -m 'todos: close the item' -- todos.md",
            "python3 - <<'PY'\nimport json\nprint(json.dumps({'a': 1}))\nPY",
            "cat > x.md <<'EOF'\n# title\n- pkill is mentioned here\nEOF",
            "grep -rn 'node ' files/ | head",
            "node build.js && npm test",
            "timeout 300 bash -c 'while true; do sleep 5; done'",
            "ruff check --isolated files/claude_managed-hooks/x.py",
            "ls -la ~/.claude/plugins/cache/",
            "S=$(git rev-parse --show-toplevel); echo $S",
            "cd /tmp && ls",
            "for f in a b; do echo $f; done",
            "npx vite --port 5173",
            "docker compose up -d",
            "python3 -m unittest discover -s tests",
            "printf 'a\\nb\\n' | sort | uniq -c",
            "node -e 'console.log(1)'",
            "bash -c 'echo nested'",
            "sudo cp files/x /etc/claude-code/hooks/x",
            "gh pr view 12 --json state",
        ):
            proc = self.allow(self.bash(command))
            self.assertEqual(proc.stderr, "", command)

    def test_c12_file_is_executable(self) -> None:
        self.assertTrue(os.access(HOOK, os.X_OK), HOOK)

    # -- round 1 corrections (acceptance findings F0-F3 and independent review R1-R11) ---------
    def test_c1_corrective_text_is_rule_specific(self) -> None:
        self.fx.seed()
        reason = self.deny(
            self.rescue(f"{NODE} task --write drafts/o.md", cwd=self.fx.primary), "tree"
        )
        self.assertIn("git worktree add", reason)
        self.assertIn("--cwd", reason)
        reason = self.deny(
            self.rescue(f"cd {self.fx.worktree} && {NODE} task x"), "same-root"
        )
        self.assertIn("単独", reason)
        reason = self.deny(self.rescue(f'{NODE} task --cwd "$WT" x'), "same-root")
        self.assertIn("絶対 path", reason)

    def test_c2_variable_bound_companion_path_is_a_launch(self) -> None:
        for command in (
            f'COMP={COMP}\nnode "$COMP" status --json',
            f"C={COMP}; node $C task --write drafts/o.md",
            f'C={COMP}\nnode "${{C}}" cancel j',
        ):
            self.deny(self.bash(command), "route")
        for command in (
            'G=/x/scripts/require-no-skips.mjs\nnode "$G" --self-test',
            'node "$SCRIPT" status --json',
            f'C={COMP}\nnode "$C/../other.mjs" task',
        ):
            self.allow(self.bash(command))
        self.fx.seed()
        self.allow(self.rescue(f'C={COMP}\nnode "$C" task --write drafts/o.md'))
        self.deny(
            self.rescue(f'C={COMP}\nnode "$C" task --write drafts/plain.md'), "order"
        )

    def test_c2_brace_groups_backticks_and_quoted_substitution(self) -> None:
        self.deny(self.bash(f"{{ {NODE} task x; }}"), "route")
        self.deny(self.bash(f"S=`node {COMP} status --json`; echo $S"), "route")
        self.deny(self.bash(f'echo "$({NODE} task x)"'), "route")

    def test_c2_node_options_and_subcommand_position(self) -> None:
        self.deny(self.bash(f"node --no-warnings {COMP} task x"), "route")
        self.fx.seed()
        self.deny(self.rescue(f"{NODE} --cwd {self.fx.other} task x"), "same-root")
        self.allow(self.rescue(f"{NODE} --cwd {self.fx.worktree} status --json"))

    def test_c2_placeholder_text_escapes_and_arrays(self) -> None:
        self.deny(self.bash(f"{NODE} task __CDGQ_ff__"), "route")
        self.deny(self.bash(f"echo __CDGQ_ff__; {NODE} task x"), "route")
        self.fx.seed()
        proc = self.allow(self.rescue(f"{NODE} task '__CDGQ_ff__ __CDGQ_zz__'"))
        self.assertEqual(proc.stderr, "")
        self.allow(self.bash(f"echo foo\\; node {COMP} task x"))
        self.allow(self.bash(f"args=(node {COMP} task x); echo done"))

    def test_c2_comment_before_heredoc_marker(self) -> None:
        self.deny(self.bash(f"# note <<EOF\n{NODE} task x"), "route")
        self.allow(self.bash(f"cat <<'EOF' # {NODE} task x\nbody\nEOF"))

    def test_c2_every_launch_is_checked(self) -> None:
        self.fx.seed()
        command = (
            f"CODEX_SHARED_TREE_OK=1 {NODE} task --write drafts/o.md; "
            f"{NODE} task --write --resume-last"
        )
        self.deny(self.rescue(command, cwd=self.fx.primary), "tree")

    def test_c6_order_path_followed_by_punctuation(self) -> None:
        self.fx.seed()
        for prompt in (
            "(drafts/o.md)",
            "発注書 drafts/o.md。",
            "drafts/o.md、続き",
            "see drafts/o.md, then",
        ):
            self.allow(self.rescue(f'{NODE} task --write "{prompt}"'))

    def test_c9_task_worker_write_is_checked(self) -> None:
        self.fx.seed()
        self.deny(
            self.rescue(
                f"{NODE} task-worker --write --cwd {self.fx.primary} --job-id j",
                cwd=self.fx.primary,
            ),
            "tree",
        )
        self.allow(
            self.rescue(f"{NODE} task-worker --cwd {self.fx.worktree} --job-id j")
        )

    def test_c10_env_chdir_globs_and_precedence(self) -> None:
        self.fx.seed()
        other = self.fx.other
        self.deny(self.rescue(f"env -C {other} {NODE} task x"), "same-root")
        self.deny(self.rescue(f"env --chdir={other} {NODE} task x"), "same-root")
        self.deny(self.rescue(f"{NODE} task --cwd /tmp/other* x"), "same-root")
        self.deny(self.rescue(f"{NODE} task --cwd /tmp/oth\\er x"), "same-root")
        self.deny(
            self.rescue(
                f"pushd {self.fx.worktree} >/dev/null && {NODE} task --write drafts/o.md",
                cwd=self.fx.primary,
            ),
            "same-root",
        )

    def test_c11_workflow_subagent_type_variants(self) -> None:
        self.fx.seed()
        for key in ("subagent_type", "subagentType"):
            script = f"await agent('x', {{{key}: 'codex:codex-rescue'}})"
            self.deny(self.tool("Workflow", {"script": script}), "workflow")

    # -- round 2 corrections (orderer replay findings P1-P2) ---------------------------------
    def test_c2_quoted_assignment_binds_the_companion_path(self) -> None:
        self.deny(self.bash(f'CJS="{COMP}"; node "$CJS" status --json'), "route")
        self.deny(self.bash(f"CJS='{COMP}'\nnode $CJS task x"), "route")

    def test_c2_nested_substitution_inside_double_quotes(self) -> None:
        command = (
            'echo "--- n: $([ -f "$P" ] && echo "$(wc -l < "$P") lines" || echo absent)"; '
            f"{NODE} task x"
        )
        self.deny(self.bash(command), "route")
        self.allow(
            self.bash(
                'echo "--- n: $([ -f "$P" ] && echo "$(wc -l < "$P") lines" || echo absent)"'
            )
        )

    def test_c2_launch_inside_substitution_after_other_quotes(self) -> None:
        self.deny(self.bash(f'CJS="{COMP}"; OUT="$(node "$CJS" task "y")"'), "route")
        self.deny(
            self.bash(f'X="a"; Y="b"; OUT="$(node "{COMP}" task "y" "z")"'), "route"
        )

    # -- re-entry 1 corrections (independent recheck findings 1-6) ------------------------------
    def test_c2_shell_option_cluster_containing_c(self) -> None:
        self.deny(self.bash("bash -lc 'codex exec'"), "cli")
        self.deny(self.bash(f'sh -ec "{NODE} task x"'), "route")
        self.allow(self.bash("bash -l 'codex exec'"))

    def test_c2_wrapper_value_options_are_consumed(self) -> None:
        for command in (
            "env -u FOO codex exec",
            "timeout --signal TERM 5 codex exec",
            "timeout -s KILL 5 codex exec",
            "timeout -k 3 5 codex exec",
            "/usr/bin/time -f %E codex exec",
            "xargs -I X codex exec X",
            "sudo -u bob codex exec",
        ):
            self.deny(self.bash(command), "cli")

    def test_c2_backslash_inside_a_program_word(self) -> None:
        self.deny(self.bash("\\codex exec"), "cli")
        self.deny(self.bash("co\\dex exec"), "cli")
        self.deny(self.bash(f"no\\de {COMP} task x"), "route")

    def test_c2_node_value_options_before_the_script(self) -> None:
        for option in ("--require setup.js", "-r esm", "--import x", "--loader x"):
            self.deny(self.bash(f"node {option} {COMP} task x"), "route")

    def test_c2_eval_of_literal_words(self) -> None:
        self.deny(self.bash('eval "codex exec"'), "cli")
        self.deny(self.bash("eval codex exec"), "cli")

    def test_c2_dynamic_program_words_are_out_of_scope(self) -> None:
        for command in (
            "CMD=codex; $CMD exec",
            "$(printf codex) exec",
            "echo 'codex exec' | sh",
            "source ./run.sh",
        ):
            self.allow(self.bash(command))

    def test_c6_skill_without_string_args_needs_an_order(self) -> None:
        self.fx.seed()
        self.deny(self.tool("Skill", {"skill": "codex:rescue"}), "order")
        self.deny(self.tool("Skill", {"skill": "codex:rescue", "args": 123}), "order")

    def test_c11_workflow_prose_and_shell_text_are_not_steps(self) -> None:
        self.fx.seed()
        for script in (
            "// codex exec must never be called here\nconsole.log('safe')",
            "console.log('codex exec is forbidden here')",
            f"await agent(`run {NODE} task --write o.md`)",
        ):
            self.allow(self.tool("Workflow", {"script": script}))

    # -- re-entry 1 review corrections (independent review findings) ----------------------------
    def test_c2_command_v_is_a_lookup(self) -> None:
        self.allow(self.bash("command -v codex"))
        self.allow(self.bash("command -V codex >/dev/null 2>&1 || echo missing"))

    def test_c2_package_runners_are_wrappers(self) -> None:
        for command in (
            "npx codex exec hi",
            "npx @openai/codex exec hi",
            "npx -p @openai/codex codex exec hi",
            "bunx codex exec hi",
            "uvx codex exec hi",
        ):
            self.deny(self.bash(command), "cli")
        self.allow(self.bash("npx -p @openai/codex codex --version"))

    def test_c2_heredoc_delimiter_forms(self) -> None:
        self.allow(
            self.bash("cat <<\\EOF > n.md\ncodex exec is the form to avoid\nEOF")
        )
        self.allow(self.bash("cat <<'1EOF'\ncodex exec x\n1EOF"))
        self.allow(self.bash('cat <<< "codex exec hi"'))
        self.deny(
            self.bash("cat <<'E.OF' > n.md\nnotes\nE.OF\ncodex exec \"write it\""),
            "cli",
        )

    def test_c2_double_dash_before_shell_string(self) -> None:
        self.deny(self.bash("bash -c -- 'codex exec hi'"), "cli")

    def test_c3_help_flags_count_only_before_positionals(self) -> None:
        self.allow(self.bash("codex exec --help"))
        self.allow(self.bash("codex --version"))
        self.deny(self.bash("codex exec add -h flag support to the tool"), "cli")

    def test_c3_config_value_is_not_the_subcommand(self) -> None:
        self.allow(self.bash("codex --config sandbox=x login"))
        self.allow(self.bash("codex -c a=b mcp list"))

    def test_c1_env_chdir_reason_names_env(self) -> None:
        reason = self.deny(self.rescue(f"env -C /tmp {NODE} task o.md"), "same-root")
        self.assertIn("env -C", reason)

    # -- final recheck trivial fixes (orderer) -------------------------------------------------
    def test_c2_heredoc_marker_inside_quotes_is_text(self) -> None:
        self.deny(
            self.bash(
                f'git commit -m "docs: describe <<EOF handling" -- docs/x.md\n{NODE} task x'
            ),
            "route",
        )
        self.deny(self.bash("rg -n '<<EOF' docs/\ncodex exec x"), "cli")

    def test_c2_heredoc_ends_only_on_the_exact_delimiter(self) -> None:
        self.allow(self.bash("cat > d.md <<'EOF'\nline\nEOF \ncodex exec 'fix'\nEOF"))
        self.allow(self.bash("cat > d.md <<'EOF'\nline\n  EOF\ncodex exec 'fix'\nEOF"))
        self.deny(
            self.bash("cat > d.md <<-'EOF'\nline\n\tEOF\ncodex exec 'fix'"), "cli"
        )

    def test_c11_workflow_quoted_keys_and_template_values(self) -> None:
        self.fx.seed()
        for script in (
            'await agent("x", {"agentType": "codex:codex-rescue"})',
            "await agent('x', {'subagent_type': 'codex:codex-rescue'})",
            "await agent('x', {agentType: `codex:codex-rescue`})",
        ):
            self.deny(self.tool("Workflow", {"script": script}), "workflow")

    def test_c1_workflow_and_isolation_name_a_correction(self) -> None:
        self.fx.seed()
        script = "await agent('x', {agentType: 'codex:codex-rescue'})"
        reason = self.deny(self.tool("Workflow", {"script": script}), "workflow")
        self.assertIn("codex-delegation skill", reason)
        reason = self.deny(self.agent(isolation="worktree"), "isolation")
        self.assertIn("isolation を外し", reason)


if __name__ == "__main__":
    unittest.main()
