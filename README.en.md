[en] [[jp]](README.md)

# Terminal Configs

A small set of configuration files and scripts that lets you setup the terminal environment quickly.


## How to Use

Run the script that matches your environment as root.

    # ./debian12.sh

It performs the following setup.


## 1. Bash environment (root and login user)

- Prompt color tweak (login user green → purple)
- Bash aliases tuned and extended (`ls`, `tree`, `diffy`, `grip`, ...)
- Git aliases (`git st`, `git diffc`, `git log1`, `git graph`, ...)
- Suppress the terminal bell (`inputrc`)
- Grant the login user passwordless sudo
- Set the default editor to Neovim
- Set the default browser to `powershell.exe start` [WSL2 only]


## 2. Sharing the X display server

- Inherit the login user's X session into root (DISPLAY and .Xauthority are propagated via `.bashrc`)
  - After `sudo -i`, running `xeyes` as root forwards to the login user's display


## 3. SSH adjustments

- Forward audio from SSH sessions to the Windows host
  - PulseAudio listens on 24713/tcp (local proxy → WSLg) [WSL2 only]
  - Login auto-sets `PULSE_SERVER=tcp:localhost:24713` [non-WSL2]
- Preserve `PULSE_SERVER` across `sudo -i`


## 4. Claude Code settings

- Display Japanese translations for Spinner Verbs
- Status line shows project name / model / context usage / rate limit / current time


## 5. Claude Code MCP / CLI

(TODO)


## 6. Claude Code Notification Hook

Installs `voicevox_claude_alerts` to `/usr/local/bin/` — a notification
script that speaks Claude Code events through Voicevox. It covers idle
warnings, permission prompts, and end-of-response summaries.

The script exposes a small CLI:

- `voicevox_claude_alerts help` — list all subcommands
- `voicevox_claude_alerts events` — list supported hooks
- `voicevox_claude_alerts log` — show recent utterances
- `voicevox_claude_alerts say TEXT` — speak arbitrary text

### Debug logging

Set `CLAUDE_NOTIFY_DEBUG=1` to append every hook payload and every
utterance to `dump.jsonl` and `spoken.log` under
`$XDG_STATE_HOME/voicevox_claude_alerts/` (defaults to
`~/.local/state/voicevox_claude_alerts/`). To keep it on permanently,
add this to `~/.claude/settings.json`:

    {
      "env": {
        "CLAUDE_NOTIFY_DEBUG": "1"
      }
    }

Both logs grow unbounded; delete them when no longer needed.


## 7. WSL2 tweaks [WSL2 only]

- Delegate DNS resolution to the Windows host
  - Lets mDNS (`.local`) work even under WSL2 in NAT networking mode
- Enable systemd

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
