[en] [[jp]](README.md)

# Terminal Configs

A small set of configuration files and scripts that lets you setup the terminal environment quickly.


## How to Use

Run the script that matches your environment as root.

    # ./ubuntu2404-wsl.sh

or

    # ./debian12.sh

## Setup

The main pieces are:

### 1. Bash environment

Configures both the login user and root.

- Prompt color tweak (login user green → purple)
- Bash aliases tuned and extended (`ls`, `tree`, `diffy`, `grip`, ...)
- Git aliases (`git st`, `git diffc`, `git log1`, `git graph`, ...)
- Suppress the terminal bell (`inputrc`)
- Grant the login user passwordless sudo
- Default editor: Neovim
- Default browser: `powershell.exe start` [WSL2 only]


### 2. Sharing the X display server

- Inherit the login user's X session into root (sets `DISPLAY` and `.Xauthority`)
  - After `sudo -i`, `xeyes` as root shows up on the login user's screen


### 3. SSH adjustments

- Forward audio from SSH sessions to the Windows host [WSL2 only]
  - PulseAudio listens on 24713/tcp and forwards to WSLg (local proxy)
  - Login auto-sets `PULSE_SERVER=tcp:localhost:24713`
- Preserve `PULSE_SERVER` across `sudo -i`


### 4. Core tool installation

- neovim, tree, ssh
- git, git-lfs, GitHub CLI
- ripgrep, bat, delta
- avahi, libnss-mdns
- SIXEL: img2sixel
- UV python package manager: uv
- Node.js LTS: nvm, node
- Chrome
- VoiceVox
- Claude Code


### 5. Claude Code settings

- Japanese translations for Spinner Verbs
- Status line: project / model / context usage / rate limit / current time
- System-wide rules: `/etc/claude-code/CLAUDE.md`
- Notification hook (see below)


### 6. Claude Code MCP / CLI

(TODO)


### 7. Claude Code Notification Hook

Installs `voicevox_claude_alerts`, which speaks Claude Code events
through VoiceVox — idle warnings, subagent completion reports,
questions from Claude Code, and so on.

It also works as a CLI with the following subcommands:

- `voicevox_claude_alerts help` — list all subcommands
- `voicevox_claude_alerts events` — list supported hooks
- `voicevox_claude_alerts log` — show recent utterances
- `voicevox_claude_alerts say TEXT` — speak arbitrary text

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


### 8. WSL2 tweaks [WSL2 only]

- Delegate DNS resolution to the Windows host
  - Lets mDNS (`.local`) work even under WSL2 in NAT networking mode
- Enable systemd
- Pin the hostname

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
