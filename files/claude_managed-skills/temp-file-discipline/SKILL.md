---
name: temp-file-discipline
description: Route temporary research artifacts and command-internal temp using the shared scratch-file-management skill. Use when selecting scratch or intermediate output locations.
when_to_use: TRIGGER when choosing where to put a temporary, scratch or intermediate file ("一時ファイル" / "/tmp に" / "scratch"). SKIP for edits to tracked source files.
---

# Temp file discipline

Read [scratch-file-management](../scratch-file-management/SKILL.md) for the shared Claude Code
and Codex policy. Short-lived research material also belongs in ignored `drafts/`.
Use `scratch_file_management run -- COMMAND` for command-internal `TMPDIR` and cleanup
limited to the directory that invocation created. Do not rely on a session ID
variable, automatic deletion of drafts, or another client's cleanup.
