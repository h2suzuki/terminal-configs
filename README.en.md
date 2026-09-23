[en] [[jp]](README.md)

# Terminal Configs

Configuration files and setup scripts for terminal and AI coding environments on Debian 12 and Ubuntu 24.04 on WSL2. The target architecture is x86_64.

## What gets installed

| Area | Main components |
|---|---|
| OS settings | Bash, Git, SSH keepalive, Windows Terminal color and image support over SSH and sudo, display and audio forwarding to the SSH client (X11 and PulseAudio, also supported with sudo -i)<br>WSL2: enable systemd, resolve .local names, forward audio to WSLg |
| Development tools | Neovim, ripgrep, delta, libsixel-bin, Node.js through nvm, Chrome |
| AI tools | Claude Code CLI, Codex CLI, Antigravity CLI, Typesafe.ai Jev |
| <div align="right">Tool settings</div> | `/etc/claude-code`, `/etc/codex`, Sandbox settings, and more |
| <div align="right">Hooks</div> | mytask reminders\*, file-read checks before editing\*, commit message format checks\*, checks against unsupported completion claims and unnecessary permission questions\*, and more |
| <div align="right">LSP</div> | clangd (C/C++), TypeScript Language Server, Pyright |
| <div align="right">MCP</div> | Chrome DevTools, CodeGraph, Cloud Run, BigQuery (Toolbox), mytask\*, Jev\* |
| <div align="right">Skill</div> | agent-browser, playwright-cli, mytask\*, memory-routing\*, browser-testing-guide\*, scratch-file-management\*, and more |
| <div align="right">Plugin</div> | Jev, Codex (for Claude Code), security-guidance, agent-coord (communication between AI agents)\* |
| <div align="right">CLI</div> | agent-browser, playwright-cli, GitHub CLI, uv, ruff, ty, Google Cloud CLI, Vercel CLI, agent_coord\*, scratch_file_management\*, claude_memory_sync\*, jev\* |

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
        ├── nodejs_clean_installer             Node.js
        ├── Install Codex CLI and enable remote connections
        ├── Configure the user's Claude Code
        ├── Configure Antigravity permissions and register remote control (if already signed in)
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

See [Control from your phone (Remote Control)](#control-from-your-phone-remote-control) for controlling this from your phone.

### Antigravity

`setup_user_environment` runs `setup_agy_permissions --sandbox-auto --shared-policy /etc/antigravity-cli/skel/permissions.json` to update `~/.gemini/antigravity-cli/settings.json`: auto-execute inside the sandbox (`toolPermission: proceed-in-sandbox`, `enableTerminalSandbox: true`) and allow the agent-coord server (`mcp(agent-coord_agent_coord/*)`). See the [official sandbox settings](https://www.antigravity.google/docs/sandbox?tab=cli).

`files/antigravity_user-permissions.json` maps the 11 reviewed Codex command exceptions and network access, plus Claude's extra writable paths and credential/socket read denials. `tests/setup_agy_permissions.test.py` detects drift. Matching and deny precedence follow agy's rules; Claude's dynamic auto decisions and environment filtering are not equivalent. No blanket `command(*)`, `mcp(*)`, or unrestricted `node` grant is added.

Existing settings and explicit `deny` / `ask` rules are preserved without duplicating rules on repeated runs. Explicit denials and prompts take precedence over added grants. Permissions do not fix session identity or idle-session wake-up. See the [official permission reference](https://www.antigravity.google/docs/permissions?tab=cli).

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

Enter your API key to verify it with a test query before saving. You can also check connectivity with `jev hello`:

```bash
jev api-key set
jev hello
```

Use `jev api-key status` to check whether a key is saved and usable (sends one test query if saved). Use `jev api-key set` to update the key and `jev api-key clear` to remove it. See the [Jev usage guide](docs/typesafe.md) (Japanese) for agent usage and help interpreting diagnostics.

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

## Control from your phone (Remote Control)

You can operate the Claude Code, Codex, and Antigravity CLIs from your phone. Complete the initial authentication above first, then set this up as the OS user who will use it. Keep the host awake and connected to the network while you operate it.

| CLI | What you open on your phone | How it stays running | One-time setup |
|---|---|---|---|
| Claude Code | **Code** in the Claude app | A running `claude` connects automatically. Or `claude remote-control` | Start `claude` once in the project directory and approve the trust prompt |
| Codex | **Remote** in the ChatGPT app | `codex remote-control start` launches the daemon | Enter the `codex remote-control pair` code with **Pair manually instead** |
| Antigravity | [Remote Control Dashboard](https://antigravity.google.com) in a browser | `agy remote-control start` registers the daemon (starts automatically at machine boot) | None (sign in with the same Google account) |

### Claude Code

The deployed `~/.claude/settings.json` sets `remoteControlAtStartup: true`, so a running `claude` connects to Remote Control automatically. On your phone, open **Code** in the Claude app and choose the session with a green dot.

Beforehand, start `claude` once in the project directory you want to operate and approve the trust prompt. Trust is not saved for the home directory, so start it from the project directory.

If you want to start a new session from your phone, keep the following running in the project directory. Over an SSH connection, run it inside something like `tmux`.

```bash
claude remote-control
```

The first time, it asks `Enable Remote Control? (y/n)`; answer `y`. Press the space bar to show a QR code. If the app isn't installed, running `/mobile` inside Claude Code shows a QR code for installing it.

In the Windows desktop app, **Settings > Claude Code > Enable remote control by default** is the same setting. [Official Remote Control docs](https://code.claude.com/docs/en/remote-control)

### Codex

Setup enables remote control for each user (`codex app-server daemon enable-remote-control`). A stopped daemon does not start automatically, so sign in with `codex login` above first, then run the following.

```bash
codex remote-control start
codex remote-control pair
```

`start` prints `This machine is available for remote control as <hostname>`. While the daemon is running, `pair` prints a short-lived pairing code as `Pairing code: XXXX-XXXX`. With `--json`, the same code is in `manualPairingCode` (along with `pairingCode`, `environmentId`, and `expiresAt`). To restart the daemon, run `codex remote-control stop` and then `start`. [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-remote-control)

Connect from your phone as follows (beta feature; connection confirmed on Debian 12 with Codex 0.156.0, 2026-09-23).

1. Update the ChatGPT app and open **Remote**.
2. Tap **Pair manually instead** and enter the code that `pair` printed. The code expires quickly; run `pair` again if it does.
3. On the OpenAI authorization screen, confirm the same account and workspace and complete any multi-factor authentication.
4. Choose the host name that `start` printed in **Remote**, pick a project, and start a task. You also approve commands and review changes there.

The official documentation only describes setup from the Mac/Windows desktop app, but an OpenAI staff member stated that the CLI's remote control does not need the desktop app and that the documentation is out of date ([openai/codex#44762](https://github.com/openai/codex/issues/44762)). The **Pair manually instead** button name comes from a user report ([openai/codex#27565](https://github.com/openai/codex/issues/27565)). [Codex Remote](https://learn.chatgpt.com/docs/remote)

### Antigravity

`setup_user_environment` registers the daemon only when `agy` is already signed in and the daemon is stopped. The first time, sign in with `agy`, then run the following.

```bash
agy remote-control start
agy remote-control status
```

The daemon is registered as a systemd user service and starts automatically at machine boot. Choose the instance name shown by `status` in the [Remote Control Dashboard](https://antigravity.google.com) opened in your phone's browser (sign in with the same Google account). Adding it to your home screen as a web app lets you receive push notifications.

You can change the name with `agy remote-control start --name <name>` (running it again restarts the daemon). If it doesn't appear in the list, check the logs with `journalctl --user -u antigravity-cli-daemon -n 50`. [Official Remote Control docs](https://antigravity.google/docs/remote-control)

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
