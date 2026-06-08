#!/usr/bin/env bash
# Smoke harness for the sibling voicevox_claude_alerts hook (run: bash <thisfile>).
# Stubs voicevox_paplay + claude via PATH (claude serves two roles: the
# `agents --json` background probe vs the Haiku `-p` call — the stub dispatches
# on argv so asserts can tell them apart; the probe returns [] = non-background
# so the script speaks). The canonical script runs through a unique-basename
# symlink because it derives locks/state from basename($0) — a unique name
# keeps them private. Audio detaches via `setsid -f`, so we poll spoken.log
# with a bounded retry (no fixed-sleep dependency for correctness).

set -uo pipefail

CANONICAL="${VVOX_SCRIPT:-$(dirname "$(realpath "$0")")/voicevox_claude_alerts}"
[ -r "$CANONICAL" ] || { echo "FATAL: script not readable: $CANONICAL" >&2; exit 2; }

SB="$(mktemp -d)"
PROG_NAME="vvox_smoke_$$"
trap 'rm -rf "$SB"; rm -f "/tmp/$PROG_NAME".*.lock 2>/dev/null' EXIT
BIN="$SB/bin"
mkdir -p "$BIN"

export XDG_STATE_HOME="$SB/state" XDG_RUNTIME_DIR="$SB/run" XDG_CACHE_HOME="$SB/cache"
mkdir -p "$XDG_STATE_HOME" "$XDG_RUNTIME_DIR" "$XDG_CACHE_HOME"
chmod 0700 "$XDG_RUNTIME_DIR"

SCRIPT="$BIN/$PROG_NAME"
ln -s "$CANONICAL" "$SCRIPT"
SPOKEN_LOG="$XDG_STATE_HOME/$PROG_NAME/spoken.log"

# Per-run invocation ledgers the asserts inspect.
CLAUDE_HAIKU_LOG="$SB/claude-haiku-called"
CLAUDE_AGENTS_LOG="$SB/claude-agents-called"
VVOX_LOG="$SB/vvox-called"

# claude stub: `agents` argv → record + emit [] (non-background → speak);
# anything else is the Haiku call → record + echo deterministic katakana.
cat > "$BIN/claude" <<'CLAUDE_EOF'
#!/usr/bin/env bash
for a in "$@"; do
  if [ "$a" = "agents" ]; then
    echo "$*" >> "$CLAUDE_AGENTS_LOG"
    printf '[]\n'
    exit 0
  fi
done
echo "$*" >> "$CLAUDE_HAIKU_LOG"
printf 'サブエージェントヨウヤク\n'
CLAUDE_EOF

cat > "$BIN/voicevox_paplay" <<'VVOX_EOF'
#!/usr/bin/env bash
echo "$*" >> "$VVOX_LOG"
VVOX_EOF

chmod +x "$BIN/claude" "$BIN/voicevox_paplay"
# Export ledger paths so the setsid-detached subshells (fresh env) see them.
export CLAUDE_HAIKU_LOG CLAUDE_AGENTS_LOG VVOX_LOG
export PATH="$BIN:$PATH"

PASS=0 FAIL=0

reset_run() {
  : > "$CLAUDE_HAIKU_LOG"; : > "$CLAUDE_AGENTS_LOG"; : > "$VVOX_LOG"
  rm -f "$SPOKEN_LOG" 2>/dev/null
}

# Feed JSON on stdin, then poll (bounded ~15s) for the case's sid line.
run_hook() {
  local event="$1" payload="$2" sid="$3"
  reset_run
  printf '%s' "$payload" | bash "$SCRIPT" "$event" >/dev/null 2>&1
  for _ in $(seq 1 150); do
    grep -qF "sid=$sid" "$SPOKEN_LOG" 2>/dev/null && break
    sleep 0.1
  done
}

ok()  { PASS=$((PASS+1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL: %s\n' "$1"; }
log_has()      { grep -qF -- "$1" "$SPOKEN_LOG" 2>/dev/null; }
haiku_called() { [ -s "$CLAUDE_HAIKU_LOG" ]; }
haiku_count()  { wc -l < "$CLAUDE_HAIKU_LOG" 2>/dev/null | tr -d ' '; }
vvox_count()   { wc -l < "$VVOX_LOG" 2>/dev/null | tr -d ' '; }
dump()         { printf '    spoken.log: %s\n' "$(tr -d '\r' < "$SPOKEN_LOG" 2>/dev/null || true)"; }

# CASE 1: SubagentStop empty → speak_cached fixed phrase; Haiku NOT invoked
# (guards 1cdc677: empty input must not reach Haiku, which would speak
#  "テキストが提供されていません").
CUR="SubagentStop empty → fixed phrase, no Haiku"
echo "=== $CUR ==="
run_hook SubagentStop '{"hook_event_name":"SubagentStop","session_id":"s1","agent_type":"general-purpose","last_assistant_message":""}' s1
dump
if log_has "サブエージェントから戻りました。" && log_has "haiku=SKIPPED" && ! haiku_called; then ok "$CUR"
else bad "$CUR (haiku_calls=$(haiku_count))"; fi

# CASE 2: SubagentStop whitespace-only → same fixed-phrase fallback.
CUR="SubagentStop whitespace-only → fixed phrase, no Haiku"
echo "=== $CUR ==="
run_hook SubagentStop '{"hook_event_name":"SubagentStop","session_id":"s2","agent_type":"general-purpose","last_assistant_message":"   \n\t  "}' s2
dump
if log_has "サブエージェントから戻りました。" && log_has "haiku=SKIPPED" && ! haiku_called; then ok "$CUR"
else bad "$CUR (haiku_calls=$(haiku_count))"; fi

# CASE 3: SubagentStop non-empty → speak_summary path (Haiku invoked).
CUR="SubagentStop non-empty → speak_summary, Haiku invoked"
echo "=== $CUR ==="
run_hook SubagentStop '{"hook_event_name":"SubagentStop","session_id":"s3","agent_type":"general-purpose","last_assistant_message":"実装を完了しコミットしました"}' s3
dump
if haiku_called && log_has "haiku=OK" && log_has "サブエージェントヨウヤク"; then ok "$CUR"
else bad "$CUR (haiku_calls=$(haiku_count))"; fi

# CASE 4: SubagentStop internal (agent_type="") → is_internal_subagent → silent.
CUR="SubagentStop internal (agent_type empty) → silent, no log, no Haiku"
echo "=== $CUR ==="
run_hook SubagentStop '{"hook_event_name":"SubagentStop","session_id":"s3b","agent_type":"","last_assistant_message":"x"}' s3b
sleep 0.3
dump
if [ ! -s "$SPOKEN_LOG" ] && ! haiku_called; then ok "$CUR"
else bad "$CUR (log_lines=$(wc -l < "$SPOKEN_LOG" 2>/dev/null || echo 0) haiku_calls=$(haiku_count))"; fi

# CASE 5: CwdChanged → speak_cwd, katakana reading attempted (Haiku + vvox fire).
CUR="CwdChanged → speak_cwd, katakana reading attempted"
echo "=== $CUR ==="
run_hook CwdChanged '{"hook_event_name":"CwdChanged","session_id":"s4","cwd":"/tmp/example/work-dir"}' s4
dump
if log_has "CwdChanged" && haiku_called && [ "$(vvox_count)" -ge 1 ]; then ok "$CUR"
else bad "$CUR (haiku_calls=$(haiku_count) vvox=$(vvox_count))"; fi

# CASE 6: ConfigChange branches by .source — correct phrase, no Haiku.
config_case() {
  local label="$1" source_json="$2" expect="$3"
  CUR="ConfigChange source=$label → \"$expect\""
  echo "=== $CUR ==="
  run_hook ConfigChange "{\"hook_event_name\":\"ConfigChange\",\"session_id\":\"sc-$label\",\"source\":$source_json}" "sc-$label"
  dump
  if log_has "$expect" && log_has "haiku=SKIPPED" && ! haiku_called; then ok "$CUR"
  else bad "$CUR"; fi
}
config_case user_settings    '"user_settings"'    "ユーザー設定を変更したよ。"
config_case skills           '"skills"'           "スキルを変更したよ。"
config_case policy_settings  '"policy_settings"'  "ポリシー設定を変更したよ。"
config_case unknown          '"some_future_kind"' "設定をリロードしたよ。"

echo
echo "==================================="
printf 'RESULT: %d passed, %d failed\n' "$PASS" "$FAIL"
echo "==================================="
[ "$FAIL" -eq 0 ]
