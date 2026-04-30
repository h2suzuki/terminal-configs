[en] [[jp]](README.md)

# Terminal Configs

A small set of configuration files and scripts that lets you setup the terminal environment quickly.


## How to Use

Run the script that matches your environment as root.

    # ./debian12.sh


## Claude Code Notification Hook

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

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
