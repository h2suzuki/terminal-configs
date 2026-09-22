# Sandbox and host command diagnosis

This document applies to an operation the user has already authorized. An
`EROFS`, `EACCES`, or `EPERM` result identifies a failed invocation; it does not
by itself prove that the operation is forbidden. A policy denial is a separate
boundary and must be respected. Do not change the sandbox, make a second clone,
or move the operation elsewhere to evade it.

## Diagnose the invocation

Record the exact command, tool working directory, failed path, exit status, and
error text. Inspect any branch, worktree, staged change, or artifact already
created before retrying. Read the current runtime policy and canonical command
procedure. Use the approved executable and the tool's working-directory option
where the tool provides one. Keep required command wrappers; avoid unnecessary
shell prefixes, `cd` chains, pipelines, and command separators because they can
change policy matching. Retry a corrected authorized invocation only when the
preceding inspection justifies it, then verify the target state.

## Runtime-specific checks

| Runtime | Check before concluding that the operation is blocked |
| --- | --- |
| Codex | Compare the complete tool call with the active sandbox and rules. This repository's source rule is [`files/codex_sandbox_exclusions.rules`](../files/codex_sandbox_exclusions.rules), installed as `/etc/codex/rules/terminal-configs-sandbox-exclusions.rules`. Its `claude_memory_sync` prefix applies to the bare executable, including `--pull` and `--write-from`; a shell redirection, combined command, or direct `git pull` is a different invocation. Pass the checkout through the tool's `workdir` argument. |
| Claude Code | Distinguish a Bash filesystem error from an auto-mode classifier denial and inspect the active managed policy and hook decision. The existing `auto-mode-denial-recovery` skill covers explicit classifier denial. Do not treat a generic denial message as permission to alter settings or retry around the classifier. |
| Antigravity or another harness | Inspect that harness's current command policy and documented invocation shape. Do not assume Codex prefix rules or Claude auto-mode behavior apply to it. |

For example, during a memory retirement, `claude_memory_sync --pull` followed by
another command in the same shell invocation failed; a direct `git pull` reported
`Read-only file system`. The installed Codex rule allowed the standalone
`claude_memory_sync --pull`. Running it alone completed the pull. Verification
then found the retired file absent from the local clone and zero rows for its
path in the RAG entry, vector, model-tag, and injection-log tables. The earlier
errors did not establish that the sandbox barred memory synchronization.

## Stop-time memory reminder

The `sandbox-host-recovery` skill is installed from one source file under
`files/shared-skills/` for both clients. The canonical memory entry
`org/feedback_try_host_ops_before_delegating.md` has `when: prompt stop` and
comma-separated keywords for write-failure claims.

Claude Code's existing `stop_checks.py` checks the final assistant text against
those keywords and returns the entry's `check` through `additionalContext`.
The [Claude Code Stop hook reference](https://code.claude.com/docs/en/hooks#stop-decision-control)
says this is non-error feedback that continues the conversation. Codex's
`memory_surface.py --codex-stop` reads the same entry's `check` when its final
message claims it cannot write. The
[Codex Stop hook reference](https://learn.chatgpt.com/docs/hooks)
defines `last_assistant_message` and says `decision: "block"` creates a
continuation prompt rather than rejecting the turn. The Codex hook returns
that decision only for the first Stop; `stop_hook_active`, missing memory,
model mismatch, and unrelated final text pass silently. A quoted error name
alone is not treated as a claim that the work cannot continue.

## If a blocker remains

Before asking the operator to act, report these fields: the original command
and error; the preserved partial state; the applicable current rule or
procedure; the corrected command actually tried and its result; and the exact
remaining boundary. An untried correct invocation is unfinished agent work.
If policy forbids execution or approval was explicitly denied, stop without
retrying around it. When recovery succeeds, continue the original task without
renewed permission and record failure → correction → verified result in its
existing issue. Name a premature operator handoff as such; do not present it as
a permission limit.
