---
name: sandbox-host-recovery
description: Diagnose Read-only file system, Permission denied, or Operation not permitted from an already-authorized host operation before declaring it blocked or handing it to the operator.
when_to_use: TRIGGER when an already-authorized command fails with "Read-only file system", "Permission denied", or "Operation not permitted", or before saying the sandbox blocks an operation or handing a command to the operator. SKIP when policy forbids the operation or the user explicitly denied approval.
---

# Read-only file system and Permission denied: fix the invocation first

**For an already-authorized operation, `Read-only file system`, `Permission denied` and
`Operation not permitted` are a reason to diagnose the invocation, not proof of missing permission.**
An approved host command invoked inside the sandbox can fail with these messages.

- **Never conclude "the sandbox prevents this" or hand the command to the operator from that error
  alone.** Diagnose and correct the call yourself before changing the plan.
- **Never invent a workaround:** no second clone, weakened sandbox policy or alternate work location.
- **Recover in order:** (1) capture the command, cwd, failed path and error; (2) inspect and preserve
  any branch/worktree/artifact already created; (3) check the current policy and canonical procedure;
  (4) correct the authorized invocation, retry only if needed, verify the result and continue.
  Do not blindly repeat creation or an unchanged failing command.
- **Use the approved bare executable** (`git`, `gh`, `session_coord`, `stackctl`, etc.) and the tool's
  working-directory option. Prefix/wrapper matching differs by runtime; keep required wrappers
  such as `session_coord worktree sync`. Historical lessons identify patterns, not current authority.
- **Before asking the operator**, report the original failure, preserved partial state, applicable
  rule, corrected command actually tried and its result. An untried correct, authorized invocation
  is unfinished agent work. If policy forbids execution or approval is explicitly denied, report
  that specific boundary without retrying around it; this rule grants no new permission.
- `docs/SANDBOX_AND_HOST_COMMANDS.md` gives the runtime-specific diagnosis and blocker-report fields.
  On recovery, continue without renewed permission; record failure → correction → verified result
  in the existing issue, distinguishing self-recovery from a premature operator handoff.
