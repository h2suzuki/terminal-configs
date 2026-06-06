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

Each one is re-runnable and upgrades in place.


## What the Base Setup Does

The main pieces are:

### 1. Bash environment

Configures both the login user and root.

- Prompt color tweak (login user green → purple)
- Bash aliases tuned and extended (`tree`, `diffy`, `rg`, `grip`, `mdr`, `node-x`, ...)
- Git aliases (`git st`, `git diffc`, `git log1`, `git graph`, ...)
- Suppress the terminal bell (`inputrc`)
- Grant the login user passwordless sudo
- Default editor: Neovim
- Default browser: `powershell.exe start` [WSL2 only]


### 2. Sharing the X display server

- Inherit the login user's X session into root (sets `DISPLAY` and `.Xauthority`)
  - After `sudo -i`, `xeyes` as root shows up on the login user's screen


### 3. SSH adjustments

- Keepalive so idle sessions survive the WSL2/Hyper-V NAT idle timeout
- Forward audio from SSH sessions to the Windows host [WSL2 only]
  - PulseAudio listens on 24713/tcp and forwards to WSLg (local proxy)
  - Login auto-sets `PULSE_SERVER=tcp:localhost:24713`
- Preserve `PULSE_SERVER` across `sudo -i`


### 4. Core tool installation

- neovim, tree, shellcheck
- git, git-lfs, GitHub CLI (gh)
- ripgrep, git-delta (delta), markdown-reader (mdr)
- openssh-server/client, avahi, libnss-mdns [WSL2 only]
- SIXEL: img2sixel
- Python: uv (package manager), ruff (linter/formatter), ty (type checker)
- Node.js LTS: nvm, node
- Chrome (with Japanese fonts)
- Google Cloud CLI (gcloud)
- Claude Code (+ claude-monitor)
- Claude Code support tools: bubblewrap, socat (Sandbox), poppler-utils (PDF reading)
- Antigravity CLI (agy)
- Codex CLI


### 5. Claude Code base settings

- Japanese translations for Spinner Verbs
- Status line: project / model / context usage / rate limit / current time
- System-wide (org) rules: `/etc/claude-code/CLAUDE.md`
- User settings: `~/.claude/CLAUDE.md` / `~/.claude/settings.json` (auto permission mode, default effort, ...)


### 6. WSL2 tweaks [WSL2 only]

- Delegate DNS resolution to the Windows host
  - Lets mDNS (`.local`) work even under WSL2 in NAT networking mode
- Enable systemd
- Pin the hostname


## What the Optional Add-ons Do

### 7. Claude Code extensions (`extra/claude_extensions.sh`)

Adds Claude Code's "trust-building" machinery plus external tool integrations.

- **Guardrails (hooks / skills)**: hooks that mechanically enforce the `CLAUDE.md` rules (commit discipline, skill firing, memory routing, ...) are deployed to `/etc/claude-code/hooks/` and skills to `/etc/claude-code/skills/`, registered through a managed-settings drop-in. User-side hooks (commit author check, push-prompting detection, memory surfacing, subagent gate) are installed into `~/.claude/hooks/`. See `SKILL-HOOK-CONTRACT.md` for how it works.
- **MCP servers (scope=user)**: Playwright (browser), Serena (LSP), CodeGraph (code knowledge graph), Cloud Run, Toolbox (BigQuery)
- **Plugins**: security-guidance (disabled by default), figma, vercel (Vercel's MCP is provided through this plugin)
- **CLI**: agent-browser (Vercel Labs)

After installing, run `/mcp` and `/doctor` in the Claude Code console to finish OAuth2 authentication.


### 8. Voice notifications (`extra/voicevox.sh`)

Installs VoiceVox Core and `voicevox_claude_alerts`, which speaks Claude Code events
through VoiceVox — idle warnings, subagent completion reports, questions from Claude Code,
and so on. The alert hooks are registered as a managed-settings drop-in
(`/etc/claude-code/managed-settings.d/voicevox.json`), so a base machine that never ran
this script has no dangling references to it.

`voicevox_claude_alerts` also works as a CLI with the following subcommands:

- `voicevox_claude_alerts help` — list all subcommands
- `voicevox_claude_alerts events` — list supported hooks
- `voicevox_claude_alerts log` — show recent utterances
- `voicevox_claude_alerts say TEXT` — speak arbitrary text

It also ships `voicevox_paplay`, which plays back through the local proxy instead of PulseAudio directly.

#### Debug logging

Set `CLAUDE_NOTIFY_DEBUG=1` to record hook payloads and utterances.
Logs land in `~/.local/state/voicevox_claude_alerts/` by default:

- Hook payloads: `dump.jsonl`
- Utterances: `spoken.log`

You can also set the variable in `~/.claude/settings.json`:

    {
      "env": {
        "CLAUDE_NOTIFY_DEBUG": "1"
      }
    }

Both logs grow unbounded; delete them when no longer needed.


### 9. SigNoz telemetry (`extra/signoz.sh`)

Brings up Docker and SigNoz (an observability stack) via docker compose, and builds a
dashboard to visualize Claude Code's OTEL telemetry.

- SigNoz UI listens on 14902/tcp
- A Claude Code dashboard is provisioned automatically
- OTEL environment variables are placed in `/etc/claude-code/env.sh` and sourced from `~/.bashrc`


----

For audio troubleshooting, see [`TROUBLE-SHOOTING.md`](TROUBLE-SHOOTING.md).

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
