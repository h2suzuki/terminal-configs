#!/bin/bash
# Voicevox notification dispatcher for Claude Code hook events.
# Receives the event JSON on stdin (1st arg = event name) and dispatches per
# event: summarize via Haiku for Stop/SubagentStop, fixed phrases otherwise.
# Voicevox playback and Haiku invocations are serialized via flock so multiple
# concurrent hook firings never overlap.
#
# Env: CLAUDE_NOTIFY_DEBUG=1 enables dump.jsonl + spoken.log under $HOOK_DIR
# (default off — no garbage written in normal operation).

set -u

# Force UTF-8 locale so ${#var} counts characters (not bytes) regardless of
# the parent environment — affects the Haiku-skip threshold in the Stop branch.
export LC_ALL=C.UTF-8

EVENT="${1:-unknown}"
HOOK_DIR="$HOME/.claude/hooks"
STATE_DIR="$HOOK_DIR/state"
CACHE_DIR="$HOOK_DIR/voicevox-cache"

if [ "${CLAUDE_NOTIFY_DEBUG:-0}" = "1" ]; then
  DUMP_LOG="$HOOK_DIR/dump.jsonl"
  SPOKEN_LOG="$HOOK_DIR/spoken.log"
else
  DUMP_LOG=""
  SPOKEN_LOG=""
fi

mkdir -p "$STATE_DIR" "$CACHE_DIR"

# Stale per-session markers accumulate forever otherwise. 1h is well past any
# meaningful suppression window (idle = 60s, subagent inhibition = 30s).
find "$STATE_DIR" -type f \( -name 'spoke-recently-*' -o -name 'subagent-start-*' \) \
  -mmin +60 -delete 2>/dev/null

INPUT="$(cat)"
NOW="$(date +%s)"
TS="$(date -Iseconds)"
SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)"

if [ -n "$DUMP_LOG" ] && printf '%s' "$INPUT" | jq -e . >/dev/null 2>&1; then
  jq -n --arg event "$EVENT" --arg ts "$TS" --argjson payload "$INPUT" \
    '{event: $event, ts: $ts, payload: $payload}' >> "$DUMP_LOG"
fi

SPOKE_MARKER="$STATE_DIR/spoke-recently-$SESSION_ID"
SUBAGENT_MARKER="$STATE_DIR/subagent-start-$SESSION_ID"
PLAY_LOCK="$STATE_DIR/voicevox.lock"
HAIKU_LOCK="$STATE_DIR/haiku.lock"

speak_cached() {
  setsid -f bash -c \
    'log=$5; [ -n "$log" ] && printf "%s\t%s\t%s\n" "$(date -Iseconds)" "$4" "$3" >> "$log"; flock "$1" timeout 30 voicevox_paplay --loopback --speed 1.5 --cache --cache-dir "$2" "$3"' \
    _ "$PLAY_LOCK" "$CACHE_DIR" "$1" "$EVENT" "$SPOKEN_LOG" \
    </dev/null >/dev/null 2>&1
}

age_of() {
  local f="$1"
  [ -f "$f" ] || { echo 999999; return; }
  echo $(( NOW - $(stat -c %Y "$f") ))
}

# Subagent イベントが Claude Code 内部のシステム subagent（auto-dream 等）か判定。
# 観測ベースのヒューリスティック (Claude Code 2.1.123 / 2026-04-30):
#   - ユーザ起動 subagent: agent_type="general-purpose" 等、Start/Stop の対で発火
#   - auto-dream:          agent_type=""、SubagentStop のみ発火（Start は来ない）
# 仕様は API 安定保証なし。将来 agent_type が別値になる、Start も来る、等の変化あり得る。
# 動作が変わったら dump.jsonl の payload 構造を再確認して条件を見直す。
is_internal_subagent() {
  local at
  at=$(printf '%s' "$INPUT" | jq -r '.agent_type // ""' 2>/dev/null)
  [ -z "$at" ]
}

detect_question() {
  printf '%s' "$INPUT" \
    | jq -r '.last_assistant_message // ""' \
    | sed 's/[[:space:]]*$//' \
    | awk 'NF{l=$0} END{print l}' \
    | grep -qE '[？?]$'
}

# Async: speak the given text directly (no Haiku, no cache). Hook returns first.
speak_text_async() {
  local text="$1"
  setsid -f bash -c '
    text=$1
    play_lock=$2
    event=$3
    log=$4
    [ -n "$log" ] && printf "%s\t%s\t%s\n" "$(date -Iseconds)" "$event" "$text" >> "$log"
    flock "$play_lock" timeout 30 voicevox_paplay --loopback --speed 1.5 "$text"
  ' _ "$text" "$PLAY_LOCK" "$EVENT" "$SPOKEN_LOG" </dev/null >/dev/null 2>&1
}

# Async: Haiku summarizes → voicevox speaks. Hook returns before either runs.
speak_summary_async() {
  local prompt="$1"
  local fallback="$2"
  setsid -f bash -c '
    p=$1
    fb=$2
    play_lock=$3
    haiku_lock=$4
    event=$5
    log=$6
    summary=$(cd /tmp && flock "$haiku_lock" timeout 45 claude \
              --model claude-haiku-4-5 \
              --no-session-persistence \
              --disable-slash-commands \
              --tools "" \
              --strict-mcp-config \
              --system-prompt "あなたは日本語の要約専門 AI です。" \
              -p "$p" 2>/dev/null \
              | tr -d "\r\n" | head -c 120)
    [ -z "$summary" ] && summary=$fb
    [ -n "$log" ] && printf "%s\t%s\t%s\n" "$(date -Iseconds)" "$event" "$summary" >> "$log"
    flock "$play_lock" timeout 30 voicevox_paplay --loopback --speed 1.5 "$summary"
  ' _ "$prompt" "$fallback" "$PLAY_LOCK" "$HAIKU_LOCK" "$EVENT" "$SPOKEN_LOG" </dev/null >/dev/null 2>&1
}

case "$EVENT" in
  Stop)
    if detect_question; then
      LAST_MSG=$(printf '%s' "$INPUT" | jq -r '.last_assistant_message // ""')
      LAST_SENTENCE=$(printf '%s' "$LAST_MSG" | tr '\n' ' ' \
        | grep -oE '[^。？！.?!]*[。？！.?!]' | tail -1 | sed 's/^[[:space:]]*//')
      [ -z "$LAST_SENTENCE" ] && LAST_SENTENCE="$LAST_MSG"
      # Already ≤30 chars: skip the ~6s Haiku cold-start and speak as-is.
      # ${#var} is char-count under UTF-8 locale (the Ubuntu default).
      if [ "${#LAST_SENTENCE}" -le 30 ]; then
        speak_text_async "$LAST_SENTENCE"
      else
        PROMPT="次の一文を、意図と意味を保ったまま 30 文字以下の自然な日本語に短縮してください。
出力は短縮した一文のみ。装飾・引用符・改行・前置きなし。

文:
$LAST_SENTENCE"
        speak_summary_async "$PROMPT" "ご返答をお願いします"
      fi
      touch "$SPOKE_MARKER"
    fi
    ;;
  Notification)
    NTYPE=$(printf '%s' "$INPUT" | jq -r '.notification_type // ""')
    case "$NTYPE" in
      idle_prompt)
        if [ "$(age_of "$SPOKE_MARKER")" -ge 90 ]; then
          speak_cached "作業が終わりました。"
        fi
        ;;
      permission_prompt)
        speak_cached "権限が必要です。"
        touch "$SPOKE_MARKER"
        ;;
    esac
    ;;
  SubagentStart)
    is_internal_subagent && exit 0
    if [ "$(age_of "$SUBAGENT_MARKER")" -ge 30 ]; then
      speak_cached "サブエージェントを起動しています。"
      touch "$SUBAGENT_MARKER"
    fi
    ;;
  SubagentStop)
    is_internal_subagent && exit 0
    LAST_MSG=$(printf '%s' "$INPUT" | jq -r '.last_assistant_message // ""')
    PROMPT="以下は AI サブエージェントが最後に出力したテキストです。
このサブエージェントが何を完了・報告したかを、30文字以下の自然な日本語で簡潔に。
出力は要約のみ。装飾・引用符・改行・前置きなし。

応答:
$LAST_MSG"
    speak_summary_async "$PROMPT" "サブエージェントから戻りました"
    ;;
  ConfigChange)
    speak_cached "設定をリロードしたよ。"
    ;;
  PreCompact)
    speak_cached "コンテキストを圧縮します。"
    ;;
  WorktreeCreate)
    speak_cached "ワークツリーを作成します。"
    ;;
esac

exit 0
