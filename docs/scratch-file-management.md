# Shared scratch file management

<!-- dangling-ref-check: allow (documents intentional scratch paths) -->

Claude Code and Codex use the same `files/workspace_hygiene.py` hook and
`files/shared_skills/scratch-file-management/SKILL.md`. Agent research notes, temporary
reports and intermediate artifacts belong in ignored `drafts/`; they must not be
staged, committed or published. Manual worktrees use `~/worktrees/<repo>/<name>`.

## Installation and activation

Both `debian12.sh` and `ubuntu2404-wsl.sh` call the shared installer. For a targeted
update from the repository, outside the agent sandbox:

```sh
sudo python3 files/install_workspace_hygiene.py
python3 files/install_workspace_hygiene.py --user
```

The targeted installer preserves unrelated settings, hook handlers and files.
It changes only the shared files and relevant registrations; it neither changes
model/sandbox settings nor imports project CLI permissions. Base installers also
preserve additional files in managed skills/hooks/rules trees instead of clearing
those trees. Their canonical configuration files remain owned by terminal-configs.
User skill link conflicts fail with the existing object intact.

| Component | Installed path |
|---|---|
| Command | `/usr/local/bin/workspace_hygiene` |
| Shared code and drafts dependencies | `/usr/local/lib/workspace_hygiene/` |
| Codex skill | `/etc/codex/skills/scratch-file-management/SKILL.md` |
| Claude skill | `/etc/claude-code/skills/scratch-file-management/SKILL.md`, linked from `~/.claude/skills/` |
| Codex registration | `[[hooks.PreToolUse]]` in `/etc/codex/config.toml` |
| Claude registration | `/etc/claude-code/managed-settings.d/extensions.json` |

Record these states separately when deploying:

1. **Not placed:** installed files or registration are absent/different.
2. **Placed, reload pending:** files match, but running clients have not reloaded.
3. **Active:** after restarting, both clients discover `scratch-file-management` and their
   `/hooks` views show the shared PreToolUse command. Verify an isolated denied
   tool call and an ordinary allowed source edit in each client.

OpenAI documents `/etc/codex/skills` as the admin discovery location in
[Build skills](https://learn.chatgpt.com/docs/build-skills). System hooks are
trusted by policy; user/project/plugin hooks need review of their current hash.
Check effective settings, including a possible disabled hooks feature; installing
files is not evidence of activation. See [OpenAI Hooks](https://learn.chatgpt.com/docs/hooks).
This installer does not bypass trust or restart another session.

## Behavior and boundaries

The hook normalizes Claude `Bash.command`, `Write/Edit.file_path`, Codex canonical
`Bash.command`/`apply_patch.command`, raw patch strings and local
`exec_command.cmd/workdir` payloads. It runs no LLM and does not mutate the Git index.

- Drafts: reuse the existing `deny_drafts_commit.py` and `check_dangling_refs.py`
  together, retaining added-reference checks. Add Git pathspec expansion for force
  adds, staged drafts and unchanged tracked drafts in commit candidates. Untracking
  via `git rm --cached` and committing that removal is allowed.
- Placement: check explicit file/patch paths, shell redirections, `mkdir`, `touch`,
  `tee`, copy/move destinations and add/commit candidates against root directories
  in HEAD. Unknown root directories are rejected, even when untracked files already
  exist there. Existing tracked directories and ordinary source changes are allowed.
- A legitimate new root layout requested by the user is declared in a reviewable
  `.workspace-layout.json`: `{"directories":{"tests":"User requested permanent tests"}}`.
  Reuse existing user authorization; no additional confirmation is required. The
  declaration is not proof of authorization and must not be used for scratch.
- Command temp: `workspace_hygiene run -- COMMAND ARGS...` creates a unique directory
  under ignored drafts, sets `TMPDIR` for that child and removes only that directory.
  It propagates the command's status. It does not support background children that
  outlive the command, automatic cleanup after crashes, or broad garbage collection.
- Explicit `mktemp` needs a destination under ignored drafts or permitted `/var/tmp`.
  Empty/root TMPDIR and unresolved TMPDIR writes are rejected. A comment mentioning
  `/var/tmp` cannot exempt an unrouted command.

This is a bounded command checker, not a generic shell interpreter or an isolation
boundary. Scripts, shell functions, aliases, command substitution, complex control
flow and indirect/dynamic paths can escape static inspection. Unsupported syntax or
Git errors report a nonblocking hook error. `git add --pathspec-from-file` is rejected
with guidance to use explicit paths; custom Git directory/index overrides are not
supported. A combined command creating then force-adding unseen files is not fully
simulated. Prefer separate writes, add and commit calls. Publication commands and
archives still require checking their inputs; no claim of universal upload blocking
is made. The sandbox remains the permission boundary.

## Selection of existing policy

| Policy | Decision |
|---|---|
| Drafts commit and dangling-reference helpers | Reuse together; do not copy only one dependency |
| Temp-file-discipline skill | Keep Claude alias pointing to the common skill; short-lived research also uses drafts |
| `tmpdir_scratch_gate.py` | Unregister; Claude string hints falsely reject valid worktree scratch and do not validate TMPDIR |
| `root_dir_guard.py`, `detect_cwd_pollution.py` | Retain Claude behavior; filesystem `/` and failed-cwd diagnostics do not replace the new repository layout check |
| `session_cleanup.py` | Remains Claude-specific; not installed or assumed effective in Codex; its age-based GC is not shared |
| Speech tags, verbal self-check, delegation, recovery gates, model settings | Not transferred |
| Project coordination wrappers, issue/deploy CLI permissions | Stay project-owned |

## Verification

Run from the repository. `GIT_CEILING_DIRECTORIES` keeps legacy non-repository
fixtures from discovering the enclosing checkout when temp lives under drafts.

```sh
mkdir -p drafts/hygiene-checks
export TMPDIR="$PWD/drafts/hygiene-checks"
export GIT_CEILING_DIRECTORIES="$TMPDIR"
python3 tests/workspace_hygiene.test.py
python3 tests/claude_managed-hooks/deny_drafts_commit.test.py
python3 tests/claude_managed-hooks/check_dangling_refs.test.py
bash -n debian12.sh
bash -n ubuntu2404-wsl.sh
bash -n files/install_claude_extensions
```

Fixtures exercise both payload families, forced staging, commits, pathspecs, source
edits, new layouts, TMPDIR and cleanup. Installation is tested twice under an isolated
root, preserving existing model/sandbox values, peer skills and unrelated hooks;
the installed hook bundle is executed there too. These checks prove staged placement
and functionality, not the active configuration of a running client.
