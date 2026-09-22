---
name: temp-file-discipline
description: Route temporary research artifacts and command-internal temp using the shared scratch-file-management skill. Use when selecting scratch or intermediate output locations.
---

# Temp file discipline

Read [scratch-file-management](../scratch-file-management/SKILL.md) for the shared Claude Code
and Codex policy. Short-lived research material also belongs in ignored `drafts/`.
Use `scratch_file_management run -- COMMAND` for command-internal `TMPDIR` and cleanup
limited to the directory that invocation created. Do not rely on a session ID
variable, automatic deletion of drafts, or another client's cleanup.
