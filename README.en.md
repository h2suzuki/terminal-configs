[en] [[jp]](README.md)

# Terminal Configs

A small set of configuration files and scripts that lets you setup the terminal environment quickly.


## How to Use

### Base setup

Run the script that matches your environment as root.

    # ./ubuntu2404-wsl.sh

or

    # ./debian12.sh

### Optional add-ons (opt-in)

After the base setup, run the scripts under `extra/` as root as needed.

    # ./extra/claude_extensions.sh   # Claude Code guardrails, MCP servers, plugins
    # ./extra/voicevox.sh            # Voice notifications via VoiceVox
    # ./extra/signoz.sh              # Claude Code telemetry via SigNoz

Each one is re-runnable and upgrades in place (the VoiceVox Core itself is skipped if already installed).


## What the Base Setup Does

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

- neovim, tree, shellcheck
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
- Claude Code support tools: bubblewrap, socat (Sandbox), poppler-utils (PDF reading)
- Antigravity CLI (agy)
- Codex CLI


### 6. Claude Code base settings

- Japanese translations for Spinner Verbs
- Status line: project / model / context usage / rate limit / current time
- System-wide (org) rules: `/etc/claude-code/CLAUDE.md`
- User settings: `~/.claude/CLAUDE.md` / `~/.claude/settings.json` (auto permission mode, default effort, ...)


### 7. WSL2 tweaks [WSL2 only]

- Delegate mDNS (`.local`) name resolution to the Windows host
  - Lets `.local` names resolve even under WSL2 in NAT networking mode
- Enable systemd
- Pin the hostname


## What the Optional Add-ons Do

### A. Claude Code extensions (`extra/claude_extensions.sh`)

Adds Claude Code's "trust-building" machinery plus external tool integrations.

- **Guardrails (hooks / skills)**: hooks that mechanically enforce the `CLAUDE.md` rules (commit discipline, skill firing, memory routing, ...) are deployed to `/etc/claude-code/hooks/` and skills to `/etc/claude-code/skills/`, registered through a managed-settings drop-in (an extra settings file). User-side hooks (commit author check, push-prompting detection, memory surfacing, subagent gate) are installed into `~/.claude/hooks/`. See `SKILL-HOOK-CONTRACT.md` for how it works.
- **MCP servers (scope=user)**: Playwright (browser), Serena (code analysis via LSP), CodeGraph (code knowledge graph), Cloud Run, Toolbox (BigQuery)
- **Plugins**: security-guidance (disabled by default), figma, vercel (Vercel's MCP is provided through this plugin)
- **CLI**: agent-browser (Vercel Labs), Vercel CLI

After installing, run `/mcp` and `/doctor` in the Claude Code console to finish OAuth2 authentication. Using Toolbox (BigQuery) also requires gcloud-side setup: `gcloud config set project <PROJECT_ID>` and `gcloud auth application-default login`.


### B. Voice notifications (`extra/voicevox.sh`)

Installs VoiceVox Core and `voicevox_claude_alerts`, which speaks Claude Code events
through VoiceVox — idle warnings, subagent completion reports, questions from Claude Code,
and so on. The alert hooks are registered as a managed-settings drop-in
(`/etc/claude-code/managed-settings.d/voicevox.json`), so a base machine that never ran
this script has no references to hooks that don't exist.

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


### C. SigNoz telemetry (`extra/signoz.sh`)

Installs Docker, brings up SigNoz (an observability stack) via docker compose, and builds a
dashboard to visualize Claude Code's OTEL (OpenTelemetry) telemetry.

- SigNoz UI listens on 14902/tcp
- An admin user for login is provisioned automatically (`admin@signoz.localhost` / `At4902.localhost`)
- A Claude Code dashboard is provisioned automatically
- OTEL environment variables are placed in `/etc/claude-code/env.sh` and sourced from `~/.bashrc`


----

For audio troubleshooting, see [`TROUBLE-SHOOTING.md`](TROUBLE-SHOOTING.md).

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
