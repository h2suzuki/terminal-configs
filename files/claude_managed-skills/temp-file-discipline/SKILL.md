---
name: temp-file-discipline
description: Route temporary research artifacts and command-internal temp using the shared workspace-hygiene skill. Use when selecting scratch or intermediate output locations.
---

# Temp file discipline

Read [workspace-hygiene](../workspace-hygiene/SKILL.md) for the shared Claude Code
and Codex policy. Short-lived research material also belongs in ignored `drafts/`.
Use `workspace_hygiene run -- COMMAND` for command-internal `TMPDIR` and cleanup
limited to the directory that invocation created. Do not rely on a session ID
variable, automatic deletion of drafts, or another client's cleanup.
