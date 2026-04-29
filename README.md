# Terminal Configs

A small set of configuration files and scripts that lets you setup the terminal environment quickly.


## How to Use

Run the script that matches your environment as root.

    # ./debian12.sh


## Claude Code Notification Hook

Voicevox-based audio notifications for Claude Code events install to
`/etc/claude-code/notify.sh`. By default the hook produces no logs (only the
WAV cache and runtime locks under `~/.claude/hooks/`).

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

After debugging, the following items under `~/.claude/hooks/` are safe to remove:

| Path | Effect of deletion |
|---|---|
| `dump.jsonl` | Removes the hook-payload log; recreated on next debug run. |
| `spoken.log` | Removes the spoken-text log; recreated on next debug run. |
| `voicevox-cache/*.wav` | First playback of each fixed phrase re-synthesizes (~1s extra latency); subsequent plays are fast again. |
| `state/spoke-recently-*` | Resets idle_prompt suppression for that session id (next idle warning will sound again, even if Stop or permission_prompt just spoke). |
| `state/subagent-start-*` | Resets the 30-second SubagentStart inhibition. |
| `state/voicevox.lock`, `state/haiku.lock` | Empty flock files; recreated on next hook fire. |

The `~/.claude/hooks/` directory itself can be removed entirely; the script
recreates the layout on the next hook invocation.

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
