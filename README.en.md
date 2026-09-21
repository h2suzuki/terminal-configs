[en] [[jp]](README.md)

# Terminal Configs

A small set of configuration files and scripts that lets you setup the terminal environment quickly.


## How to Use

### Base setup

Run the script that matches your environment as root.

    # ./ubuntu2404-wsl.sh

or

    # ./debian12.sh

The script ends by running `setup_user_environment` as the login user, which in turn runs
`install_claude_extensions` (the per-user install of Claude Code hooks, skills and the shared memory
clone). There is no separate step to run.

The shared memory clone comes from a repository private to the maintainer. Without access to it, that
one clone is skipped and the setup still runs to completion: only the memory feature is left off,
while the hooks, skills, MCP servers and CLIs all install as usual. If you own that repository and the
clone still fails, run `gh auth login` and re-run `install_claude_extensions`.

### Optional add-ons (opt-in)

After the base setup, run the scripts under `extra/` as root as needed.

    # ./extra/voicevox.sh            # Voice notifications via VoiceVox
    # ./extra/signoz.sh              # Claude Code telemetry via SigNoz

Each one is re-runnable and upgrades in place (the VoiceVox Core itself is skipped if already installed).

### Adding a new user

When you add a user to an already set-up machine, there is no need to re-run the scripts above. Log in as the new user and run:

    $ /usr/local/bin/setup_user_environment

This sets up the per-user portion of the base setup (Bash and Git configuration, Node.js, Claude Code with its extensions, the Codex CLI, and so on) for that user.

### Redeploying after editing `files/`

The canonical copy of every setting lives under `files/`. What sits in `/etc/claude-code/`, `~/.claude/`
and `/usr/local/bin/` is the output of the scripts, so make your change in `files/` and deploy it again.

The most reliable way is to re-run the same script you used for the base setup, as root.

    # ./debian12.sh          # or ./ubuntu2404-wsl.sh

Unchanged files are reported as "already installed" and skipped; only files that differ are overwritten.
The script ends by running `setup_user_environment` as the login user, so per-user destinations such as
`~/.claude/hooks/` and `~/.claude/skills/` are refreshed in the same run.

Per destination:

| What you edited | Deploy command |
|---|---|
| Anything under `files/` | `sudo ./debian12.sh` (or `sudo ./ubuntu2404-wsl.sh`) |
| `files/claude_user-hooks/`, `files/claude_user-skills/` | Run the script above, then other users each run `install_claude_extensions` |
| `files/voicevox_*`, `files/claude_managed-voicevox.json` | `sudo ./extra/voicevox.sh` |
| `files/signoz_*`, `files/claude_env.sh` | `sudo ./extra/signoz.sh` |

To push a single file in a hurry, find its destination on the `copy` line in the script and copy it directly.

    $ grep -n 'copy.*<file>' debian12.sh extra/*.sh
    # cp files/<file> <destination>

None of this can run from inside a Claude Code session: the destinations are owned by root and the Bash
sandbox does not pass sudo through. Run it from a regular terminal.


## What the Base Setup Does

See [workspace hygiene](docs/workspace-hygiene.md) for shared Claude Code / Codex
drafts, TMPDIR and worktree rules, installation, and activation checks.

The main pieces are:

### 1. Bash environment

Configures both the login user and root.

- Prompt color tweak (login user green → purple)
- Bash aliases tuned and extended (`tree`, `diffy`, `rg`, `grip`, `mdr`, `node-x`, ...)
- Git configuration tweaks (aliases `git st`, `git diffc`, `git log1`, `git graph` and so on, readable diffs via delta, GitHub authentication through gh)
- Suppress the terminal bell
- Default editor: Neovim
- Default browser: `powershell.exe start` [WSL2 only]


### 2. Sharing the X display server

- Inherit the login user's X session into root (sets `DISPLAY` and `.Xauthority`)
  - After `sudo -i`, `xeyes` as root shows up on the login user's screen


### 3. SSH adjustments

- Keepalive so idle sessions survive the WSL2/Hyper-V NAT idle timeout
- Forward Windows Terminal's `WT_SESSION` environment variable to the SSH destination
  - Claude Code on the SSH destination also recognizes Windows Terminal and can use extended key input (the Kitty protocol)
  - `/terminal-setup` in Claude Code shows whether Windows Terminal is recognized
- Forward audio from SSH sessions to the Windows host
  - PulseAudio listens on 24713/tcp and forwards to WSLg (local proxy) [WSL2 only]
  - Login auto-sets `PULSE_SERVER=tcp:localhost:24713` [Debian12 only]


### 4. sudo adjustments

- Preserve the `PULSE_SERVER` environment variable across `sudo -i`
- Preserve the `WT_SESSION` environment variable across `sudo -i`
- `sudo scp` / `sudo rsync` can use the login user's SSH agent (preserves `SSH_AUTH_SOCK` and friends)
- Grant `NOPASSWD` to the `sudo` group (run sudo without a password)
  - Add the login user to the `sudo` group


### 5. Core tool installation

- neovim, tree, shellcheck, htop
- git, git-lfs, GitHub CLI (gh)
- ripgrep, git-delta (delta), markdown-reader (mdr)
- openssh-server/client
- avahi, libnss-mdns (mDNS support) [WSL2 only]
- SIXEL (inline terminal images): img2sixel
- Python: uv (package manager), ruff (linter/formatter), ty (type checker)
- Node.js LTS: nvm, node
- Chrome (with Japanese fonts)
- Google Cloud CLI (gcloud)
- Claude Code (+ claude-monitor)
- Claude Code support tools: bubblewrap, socat, sandbox-runtime (Sandbox), poppler-utils (PDF reading)
- Antigravity CLI (agy)
- Codex CLI


### 6. Claude Code base settings

- Japanese translations for Spinner Verbs
- Status line: project / model / context usage / rate limit / current time
- System-wide (org) rules: `/etc/claude-code/CLAUDE.md`
- User settings: `~/.claude/CLAUDE.md` / `~/.claude/settings.json` (auto permission mode, default effort, ...)
- Sandbox policy (`/etc/claude-code/managed-settings.json`): enables the Bash sandbox, limits writable paths, and denies reads of credential files and token environment variables


### 7. WSL2 tweaks [WSL2 only]

- Delegate mDNS (`.local`) name resolution to the Windows host
  - Lets `.local` names resolve even under WSL2 in NAT networking mode
- Enable systemd
- Pin the hostname


### 8. Claude Code extensions

Adds Claude Code's "trust-building" machinery plus external tool integrations.

- **User-side hooks**: commit author check, push-prompting detection, memory surfacing, and subagent gate are installed into `~/.claude/hooks/`, and a per-user RAG memory index is built.
- **LSP**: language servers (clangd via APT in the base setup; typescript-language-server / pyright via npm) and their plugins (clangd-lsp / typescript-lsp / pyright-lsp).
- **MCP servers (scope=user)**: Chrome DevTools (performance and memory investigation; also registered with Codex), CodeGraph (code knowledge graph), Cloud Run, Toolbox (BigQuery)
- **Plugins**: security-guidance (disabled by default), figma, codex (delegation to OpenAI Codex / code review)
- **CLI**: agent-browser (everyday page checks), Playwright CLI (test authoring and reproduction), Vercel CLI. Official browser skills are installed for Claude Code and Codex, and the old Playwright MCP registration is removed.

Claude Code and Codex share the memory-entry index. Codex refreshes the shared
clone at `SessionStart`, then its `UserPromptSubmit` hook passes matching lessons
for the active model as context without blocking the prompt. Installing only the
agent-coord plugin does not install these system hooks; the base setup copies
`files/codex_config.toml` and the memory hook to their system locations.

Chrome DevTools MCP enables headless, isolated, and memory-debugging modes, with usage statistics and URL submission to CrUX disabled. It uses Linux Chrome installed by the base setup.

For repeatable automated tests, install Playwright Test as a development dependency in each target app. If absent, run `npm init playwright@latest` then `npx playwright install --with-deps` in the app directory, configure the target URL, browsers, and expected results, and verify with `npx playwright test`. Preserve existing configuration and package management; keep the configuration, tests, and lockfile in the app.

After setup, complete the authentication / initial setup below (only the MCP servers registered here; `claude mcp list` also shows MCP servers configured elsewhere).

| MCP | Authentication / initial setup |
|---|---|
| codegraph | `codegraph init -i` at the top directory of each repository |
| cloud-run | `gcloud auth login`<br>`gcloud auth application-default login` |
| toolbox | `gcloud config set project <PROJECT_ID>`<br>`gcloud auth application-default login` |
| figma | OAuth2 via `/mcp` in the Claude Code console |

After authenticating, check the connections with `/mcp` and `/doctor`.

The codex plugin is authenticated with `!codex login`, verified with `/codex:setup`, and applied to the current session with `/reload-plugins`.


### 9. Codex and Shared Worktrees

When installing Vercel CLI, `install_claude_extensions` removes the duplicate Codex
plugin `vercel-plugin@plugins-cli`, retaining the installed official catalog version.
This also applies when rerunning setup. Restart Codex to load the changes.

`setup_user_environment` installs Codex CLI. Both OS setup scripts install
`files/codex_config.toml` at `/etc/codex/config.toml`. These are overridable system
defaults: user/project configuration and CLI options take precedence. Check the
effective configuration with `/status` and `/permissions` after starting Codex.

The shared config disables Figma and Canva app tools and their 22 current bundled
skills to reduce the skill catalog. Connections and installations are retained.
Remote catalog plugins use account-managed enablement, so the config targets app
IDs and skill names. Update the names if a plugin upgrade introduces more skills.

- `sandbox_mode = "workspace-write"`: allows writes in the workspace and temporary directories.
- `approval_policy = "never"`: operations outside the boundary without an explicit allow rule fail without an approval prompt.
- `network_access = true`: allows network access for sandboxed commands.
- `writable_roots = ["~/worktrees"]`: allows writes throughout the running user's worktree directory.
- `[tui] status_line`: the items shown in the TUI status line, in order: model, run state,
  working directory, branch, context usage, weekly limit, input/output token counts, task progress.
- `[tui] status_line_use_colors = true`: colorizes the status line.

Use `~/worktrees/<repo>/<name>` for manual worktrees with both Claude Code and Codex.
For `<name>`, prefer the branch name or a GitHub issue identifier such as `issue-123`.
This is a recommendation, not an enforced or automatically validated naming rule.
Keeping `/` in a branch name creates nested directories: `feature/foo` becomes
`~/worktrees/<repo>/feature/foo`.
User setup creates `~/worktrees`. Use the same worktree when handing a task between
tools, and separate worktrees for tasks edited in parallel. Run this example from
the target repository in a host terminal (replace `myrepo` and `task-1`):

```bash
mkdir -p "$HOME/worktrees/myrepo"
git worktree add -b task-1 "$HOME/worktrees/myrepo/task-1"
codex
# Tell this session to work in ~/worktrees/myrepo/task-1.
```

Claude Code allows all of `~/worktrees` through `sandbox.filesystem.allowWrite`,
and Codex through `sandbox_workspace_write.writable_roots`. Both can create and edit
worktrees from a session started in the original repository, without restarting
inside the target worktree. Configuration changes apply to new Codex sessions after
installation. Initial trust confirmation is separate from sandbox write permissions;
review the target before accepting it.

Codex's `workspace-write` protects `.git` and its resolved target, `.agents`, and
`.codex`. Both OS setup scripts install `files/codex_sandbox_exclusions.rules`
at `/etc/codex/rules/terminal-configs-sandbox-exclusions.rules`. Commands matching
an `allow` prefix rule run outside the sandbox without prompting. The shared Claude
Code exclusions are mapped individually:

| Claude exclusion | Codex mapping and rationale |
|---|---|
| `git *` | Allow `git`: Git metadata writes and host authentication. |
| `gh *` | Allow `gh`: GitHub authentication and user configuration. |
| `claude_memory_sync *` | Allow the named CLI: shared memory clone/index writes outside the workspace, also needed when Codex operates shared memory. |
| `docker *` | Allow `docker`: access to the host Docker daemon. |
| `codex *` | Allow `codex`: the child CLI manages its own sandbox and user state. |
| `node *codex-companion.mjs*` | Omit from shared rules: prefix rules cannot match argument globs. Configure `node` plus the companion's exact absolute path locally if needed; do not allow all of `node`. |
| `codex_broker_reap*` | Allow only the actual `codex_broker_reap` executable: requires the host process table to avoid misidentifying active brokers. Do not copy the executable-name wildcard. |
| `agent-browser *` | Allow `agent-browser`: host browsers, sessions, and development servers. |
| `claude --bg *` | Allow only `claude --bg`: background Claude sessions with their own sandbox. |
| `claude agents *` | Allow only `claude agents`: access to the host Claude session registry. |

These permissions do not themselves instruct delegation or external changes.
Excluded commands' children (including Git hooks) also run with host permissions;
Docker provides broad host access. Child Codex/Claude sandbox behavior depends on
the child's configuration and launch arguments. Other commands remain sandboxed.
These rules do not reproduce Claude Code's credential read restrictions.

Project-specific exclusions belong in project-managed drop-ins or each project's
`.claude` / `.codex` configuration, not org policy. Claude drop-ins are not
automatically converted into shared Codex rules.

Restart Codex to load the rules. Invoke commands by bare name; complex shell wrappers
may not match. Other `prompt` / `forbidden` rules or managed constraints take precedence.

References: [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[sandbox protected paths](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots),
[rules for commands outside the sandbox](https://learn.chatgpt.com/docs/agent-configuration/rules).


## What the Optional Add-ons Do

### A. Voice notifications (`extra/voicevox.sh`)

Installs VoiceVox Core and `voicevox_claude_alerts`, which speaks Claude Code events
through VoiceVox — idle warnings, subagent completion reports, questions from Claude Code,
and so on. The alert hooks are registered as a managed-settings drop-in
(`/etc/claude-code/managed-settings.d/voicevox.json`), so a base machine that never ran
this script has no references to hooks that don't exist.

Downloading VoiceVox Core is subject to GitHub API rate limits, so we recommend
running `gh auth login` before this script. The same credentials also serve GitHub
user authentication for `git clone` and friends, delegated through `/etc/gitconfig`.

`voicevox_claude_alerts` also works as a CLI with the following subcommands:

- `voicevox_claude_alerts help` — list all subcommands
- `voicevox_claude_alerts events` — list supported hooks
- `voicevox_claude_alerts log` — show recent utterances
- `voicevox_claude_alerts say TEXT` — speak arbitrary text

It also ships `voicevox_paplay`, a command that plays synthesized audio. The alert hooks
invoke it with an option that plays through the local proxy instead of directly through PulseAudio.

#### Logs

Logs are written to `~/.local/state/voicevox_claude_alerts/` by default:

- Utterances: `spoken.log` (always recorded)
- Hook payloads: `dump.jsonl` (only when the `CLAUDE_NOTIFY_DEBUG=1` environment variable is set)

You can also set the variable in `~/.claude/settings.json`:

    {
      "env": {
        "CLAUDE_NOTIFY_DEBUG": "1"
      }
    }

The logs grow unbounded; delete them when no longer needed.


### B. SigNoz telemetry (`extra/signoz.sh`)

Installs Docker, brings up SigNoz (an observability stack) via docker compose, and builds a
dashboard to visualize Claude Code's OTEL (OpenTelemetry) telemetry.

- SigNoz UI listens on 14902/tcp
- An admin user for login is provisioned automatically (`admin@signoz.localhost` / `At4902.localhost`)
- A Claude Code dashboard is provisioned automatically
- OTEL environment variables are placed in `/etc/claude-code/env.sh` and sourced from `~/.bashrc`


----

For audio troubleshooting, see [`docs/TROUBLE-SHOOTING.md`](docs/TROUBLE-SHOOTING.md).

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
