# Terminal Configs

A small set of configuration files and scripts that lets you setup the terminal environment quickly.


## How to Use

Run the script that matches your environment as root.

    # ./debian12.sh


## Claude Code Notification Hook

Voicevox-based audio notifications for Claude Code events install to
`/usr/local/bin/voicevox_claude_alerts`. By default the hook produces no logs
(only the WAV cache, managed by `voicevox_paplay`, and ephemeral runtime
files under `$XDG_RUNTIME_DIR/voicevox_claude_alerts/`).

The script also exposes a small CLI: `voicevox_claude_alerts help` for the
full list, `events` to list supported hooks, `log` to view recent
utterances, `say TEXT` to speak text via voicevox.

The hook invokes `voicevox_paplay` in two modes:

- **`--cache` for fixed phrases** (idle warning, permission prompt, subagent
  start/stop fallback, ConfigChange / PreCompact / WorktreeCreate). Each unique
  phrase is synthesized once and stored under `~/.claude/hooks/voicevox-cache/`,
  so subsequent plays are instant.
- **No cache for dynamic Haiku summaries** (Stop with a question whose last
  sentence exceeds 30 chars; SubagentStop). Each summary is unique, so caching
  it would just bloat the directory; the cost is one fresh synthesis per play.

Stop hooks whose last sentence is already ≤30 characters bypass Haiku entirely
and speak the sentence directly (saving the ~6 s cold-start latency); they also
skip the cache because the input is unbounded.

To capture what was spoken and the raw hook payloads (for debugging), enable
`CLAUDE_NOTIFY_DEBUG=1` in either of these ways:

- **One-shot (shell)** — only the next Claude Code session sees it:

      export CLAUDE_NOTIFY_DEBUG=1

- **Persistent (settings.json)** — applied automatically every session. Add an
  `env` block to `~/.claude/settings.json` (the file installed by this repo):

      {
        "env": {
          "CLAUDE_NOTIFY_DEBUG": "1"
        },
        ...other existing keys...
      }

  Remove the entry (or set it to `"0"`) to return to the silent default.

With debug on, two append-only files appear under `~/.claude/hooks/`:

- `dump.jsonl` — every hook payload as line-delimited JSON
- `spoken.log` — TSV of `<timestamp>\t<event>\t<spoken-text>` per utterance

Both grow unbounded; truncate or delete when no longer needed.

Files are split between persistent state and ephemeral runtime (per the XDG
Base Directory spec):

```
$XDG_STATE_HOME/voicevox_claude_alerts/      (or ~/.local/state/...)
├── dump.jsonl                  every payload as JSONL (debug only)
└── spoken.log                  TSV of every utterance (debug only)

$XDG_RUNTIME_DIR/voicevox_claude_alerts/     (or /tmp/...-<uid>, mode 0700)
├── voicevox.lock               flock for serialized voicevox playback
├── haiku.lock                  flock for serialized claude -p calls
├── spoke-recently-<sid>        idle_prompt suppression marker
└── subagent-start-<sid>        30 s SubagentStart inhibition marker

$XDG_CACHE_HOME/voicevox_paplay/             (or ~/.cache/voicevox_paplay)
└── <text>_<hash>.wav           cached fixed-phrase synthesis (managed by
                                voicevox_paplay itself)
```

Anything under `STATE_DIR` and `RUNTIME_DIR` is safe to delete; the script
recreates whatever it needs on the next invocation. Removing `*_<sid>` markers
just resets the corresponding suppression / inhibition for that Claude Code
session. Removing the WAV cache costs you one re-synthesis per fixed phrase
on first play.

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
