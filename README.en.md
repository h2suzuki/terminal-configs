[en] [[jp]](README.md)

# Terminal Configs

Configuration files and setup scripts for terminal and AI coding environments on Debian 12 and Ubuntu 24.04 on WSL2. The target architecture is x86_64.

## What gets installed

| Area | Main components |
|---|---|
| OS settings | Bash, Git, SSH keepalive, Windows Terminal color and image support over SSH and sudo, display and audio forwarding to the SSH client (X11 and PulseAudio, also supported with sudo -i)<br>WSL2: enable systemd, resolve .local names, forward audio to WSLg |
| Development tools | Neovim, ripgrep, delta, libsixel-bin, Node.js LTS through nvm, Chrome |
| AI tools | Claude Code CLI, Codex CLI, Antigravity CLI, Typesafe.ai Jev |
| <div align="right">Tool settings</div> | `/etc/claude-code`, `/etc/codex`, Sandbox settings, and more |
| <div align="right">Hooks</div> | mytask reminders\*, file-read checks before editing\*, commit message format checks\*, unfinished task detection before ending a response (Stop)\*, and more |
| <div align="right">LSP</div> | clangd (C/C++), TypeScript Language Server, Pyright |
| <div align="right">MCP</div> | Chrome DevTools, CodeGraph, Cloud Run, BigQuery (Toolbox), mytask\*, Jev\* |
| <div align="right">Skill</div> | agent-browser, playwright-cli, memory-routing\*, browser-verification\*, workspace-hygiene\*, and more |
| <div align="right">Plugin</div> | Jev, Codex (for Claude Code), security-guidance, agent-coord\* |
| <div align="right">CLI</div> | agent-browser, playwright-cli, GitHub CLI, uv, ruff, ty, Google Cloud CLI, Vercel CLI, agent_coord\*, workspace_hygiene\*, claude_memory_sync\*, jev\* |

\* … Custom scripts maintained in this repository

Voice notifications and SigNoz telemetry are available through [optional setup](#optional-setup).

## Setup

The scripts run `apt full-upgrade`, modify system settings under `/etc`, and change user Bash and Claude Code settings. They overwrite `~/.claude/CLAUDE.md` and `~/.claude/settings.json` with the repository defaults and enable passwordless sudo for the `sudo` group.

Clone the repository and run the command for your OS from a regular terminal:

```bash
git clone https://github.com/h2suzuki/terminal-configs.git
cd terminal-configs
```

| Target OS | Command |
|---|---|
| Debian 12 | `sudo ./debian12.sh` |
| Ubuntu 24.04 on WSL2 | `sudo ./ubuntu2404-wsl.sh` |

Open a new shell when setup finishes. On WSL2, follow the script's instructions to run `wsl -t <distribution-name>` from Windows, then reconnect.

### How the scripts call each other

Both OS scripts install system components, then configure the root and login-user environments. The main steps and script calls are:

```text
debian12.sh or ubuntu2404-wsl.sh (run with sudo)
├── Install system tools and configuration
│   ├── Update OS packages; install Neovim, GitHub CLI and Google Cloud CLI
│   ├── Install uv, ruff, ty, Chrome and Japanese fonts
│   ├── Install Claude Code and Antigravity CLI
│   ├── Deploy shared configuration and sandbox settings for Claude Code and Codex
│   ├── Install the Jev wrapper CLI and SDK runtime
│   └── Place user setup scripts in /usr/local/bin
└── Run for root and the login user (if detected)
    └── setup_user_environment
        ├── Configure the user's Bash and Git
        ├── nodejs_clean_installer             Node.js LTS
        ├── Install Codex CLI and enable remote connections
        ├── Configure the user's Claude Code
        ├── install_claude_extensions          Plugins, MCP, hooks and skills
        └── install_typesafe_extensions        Jev plugins, skills and MCP
```

### Setting up an additional user

On a machine that has already been set up, log in as the new user and run:

```bash
setup_user_environment
```

This runs the steps under `setup_user_environment` in the tree above. Authenticate and configure API keys as that user too.

## Initial authentication and connections

Configure the features you use from a regular terminal, as the OS user who will use them.

### Claude Code

```bash
claude auth login
```

After authentication, start `claude`. Inside Claude Code, use `/mcp` to check MCP connections and `/doctor` for diagnostics.

To use Codex from Claude Code, complete the Codex login below, then run `/codex:setup` inside Claude Code.

### Codex

```bash
codex login
```

For device-code authentication, run `codex login --device-auth` instead.

Setup enables remote connections for each user. To connect remotely, run the following after logging in:

```bash
codex remote-control start
codex remote-control pair
```

Use the code displayed by `pair` to pair your client. See [Remote connections](https://learn.chatgpt.com/docs/remote-connections) for the client instructions.

### Antigravity

```bash
agy
```

A login prompt appears on first launch.

- Local terminal: sign in to your Google account in the browser that opens automatically.
- Over SSH: open the authorization URL printed in the terminal in your local browser, sign in, then paste the resulting authorization code into the SSH terminal.

A valid saved session signs you in automatically. See the [official authentication instructions](https://antigravity.google/docs/cli/install#authentication-workflows).

### GitHub CLI

```bash
gh auth login
```

### Jev

Register your API key, then send a test query to check authentication and connectivity:

```bash
jev api-key set
jev hello
```

Use `jev api-key set` to update the key and `jev api-key clear` to remove it. See the [Jev usage guide](docs/typesafe.md) (Japanese) for agent usage and help interpreting diagnostics.

### CodeGraph

Run this in the repository you want to analyze:

```bash
codegraph init -i
```

### Google Cloud

Authenticate with the account you will use for Cloud Run or BigQuery:

```bash
gcloud auth login
gcloud auth application-default login
```

For the BigQuery MCP connection, also select the project:

```bash
gcloud config set project <PROJECT_ID>
```

## Optional setup

The OS setup scripts do not call these installers. Run the ones you need from the repository root after setup finishes.

### Voice notifications

```bash
sudo ./extra/voicevox.sh
```

Installs VoiceVox Core and Claude Code voice notifications. Run `gh auth login` beforehand to reduce GitHub API rate limiting.

Use `voicevox_claude_alerts say TEXT` to test speech playback. See `voicevox_claude_alerts help` for available commands and [audio troubleshooting](docs/TROUBLE-SHOOTING.md) (Japanese) if audio is not working.

### SigNoz telemetry

```bash
sudo ./extra/signoz.sh
```

Installs Docker and SigNoz to visualize Claude Code OpenTelemetry data. The dashboard is at `http://localhost:14902`; initial credentials are `admin@signoz.localhost` / `At4902.localhost`. Open a new shell after installation to load the telemetry environment variables.

## Updating and changing configuration

Make configuration and script changes in the repository's `files/` directory. You may deploy just the changed files with individual `cp` commands; a single-file change does not require rerunning the entire setup. Follow the target OS installer for destinations, ownership, and permissions, and update every destination when a file is deployed to multiple locations.

For example, after changing only `mytask`, run this from the repository root:

```bash
sudo cp files/shared_cli/mytask /usr/local/bin/mytask
```

If a change also adds dependencies or requires configuration generation or registration, run the corresponding installation steps too. Changes made only to deployed files under `/etc/claude-code/`, `/etc/codex/`, or `/usr/local/bin/` will be overwritten by the next deployment.

To update the entire environment, update the repository and run `sudo ./debian12.sh` or `sudo ./ubuntu2404-wsl.sh`. As shown in the [call tree](#how-the-scripts-call-each-other), this updates the system and the root and login-user environments.

To update an additional user's environment, run `setup_user_environment` as that user. To update an existing voice notification or SigNoz installation, rerun its optional installer.

After updating, restart any shells or affected agents that need to reload the changed files.
