---
name: scratch-file-management
description: Choose locations for agent research notes, intermediate outputs, command temporary files, and Git worktrees; check scratch before staging or publishing. Use when creating these files or introducing a repository root directory.
when_to_use: TRIGGER when creating research notes, intermediate outputs, command temporary files, or Git worktrees, when adding a new top-level directory, or before staging, committing, or publishing files. SKIP for ordinary edits to existing source files.
---

# Scratch File Management

- Put agent-created research notes, intermediate artifacts and temporary reports in
  the repository's ignored `drafts/`, even if short-lived. Verify `git check-ignore`
  before writing; add `drafts/` to `.gitignore` if needed. Never stage, commit or
  publish scratch, force-add it, or invent another root directory to evade this rule.
  Final deliverables requested by the user belong in the project's intended layout.
- Continue ordinary source edits in existing directories. When the user requests a
  legitimate new root layout, use that authorization without asking again. Record
  only the requested directory and its reason in `.workspace-layout.json`, e.g.
  `{"directories":{"tests":"User requested a permanent test suite"}}`.
  This declaration is reviewable project configuration, not proof of authorization;
  do not create one for temporary investigation output. It never exempts `drafts/`.
- Put manual worktrees at `~/worktrees/<repo>/<name>` (branch or `issue-N`). Reuse
  the worktree for a continuing task; preserve peers' worktrees and files. This
  location convention does not grant extra sandbox permissions. In Claude Code, use
  `EnterWorktree` with `name`: a WorktreeCreate hook creates or reenters it there. A
  `path` outside `.claude/worktrees/` always asks for approval, so a hook denies it.
- Distinguish command-internal temp from research artifacts. From the worktree,
  run `scratch_file_management run -- COMMAND ARGS...` to give a command a unique ignored
  scratch directory through `TMPDIR`; the helper removes only its own directory
  when the command exits. Do not use it for a background process that outlives the
  command, or for reports that you need to keep.
- For manual temp handling, set a nonempty absolute `TMPDIR` in the same shell call,
  create it first, quote it, and use `${TMPDIR:?}` when writing or cleaning. Never
  assume variables persist between tool calls. Use owned scratch under the worktree,
  or permitted `/var/tmp` for large command-internal temp. Avoid scarce `/tmp`.
- Delete only temporary files you created and no longer need. Do not delete all of
  `drafts/`, sweep peers' files by age, or move/delete pre-existing artifacts. Neither
  client promises cleanup after a crash; the helper has no cross-session garbage collector.

The shared hook checks explicit file/patch paths, common shell writes and Git
add/commit candidates. Dynamic shell code, wrappers and arbitrary scripts are not
fully interpreted. These checks are not a sandbox or a publication filter: inspect
archive/upload inputs yourself, and never include scratch in them.
