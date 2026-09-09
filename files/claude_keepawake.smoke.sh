#!/usr/bin/env bash
# Smoke harness for the sibling claude_keepawake script (run: bash <thisfile>).
# Stubs powershell.exe via PATH (records argv, exit code from PS_STUB_RC, sleeps
# PS_STUB_SLEEP) and points the WSL guard at a fake /proc/version so the cases
# run on any Linux. The fire is detached via `setsid -f`, so calls are polled
# from the stub's ledger with a bounded retry.

set -uo pipefail

CANONICAL="${KEEPAWAKE_SCRIPT:-$(dirname "$(realpath "$0")")/claude_keepawake}"
[ -r "$CANONICAL" ] || { echo "FATAL: script not readable: $CANONICAL" >&2; exit 2; }

SB="$(mktemp -d)"
trap 'rm -rf "$SB"' EXIT
BIN="$SB/bin"
mkdir -p "$BIN"

export XDG_CACHE_HOME="$SB/cache"
export KEEPAWAKE_PROC_VERSION="$SB/proc_version"
printf 'Linux version 6.0.0-microsoft-standard-WSL2\n' > "$KEEPAWAKE_PROC_VERSION"
STATE="$XDG_CACHE_HOME/claude-keepawake/state"
PS_LOG="$SB/powershell-called"
export PS_LOG PS_STUB_RC=0 PS_STUB_SLEEP=0

cat > "$BIN/powershell.exe" <<'PS_EOF'
#!/usr/bin/env bash
echo "$*" >> "$PS_LOG"
sleep "${PS_STUB_SLEEP:-0}"
exit "${PS_STUB_RC:-0}"
PS_EOF
chmod +x "$BIN/powershell.exe"
install -m 0755 "$CANONICAL" "$BIN/claude_keepawake"
export PATH="$BIN:$PATH"

PASS=0 FAIL=0
ok()  { PASS=$((PASS+1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL: %s\n' "$1"; }
ps_count() { wc -l < "$PS_LOG" 2>/dev/null | tr -d ' '; }
state_get() { awk -F= -v k="$1" '$1 == k { print $2 }' "$STATE" 2>/dev/null; }
# Poll (bounded ~5s) until the ledger holds $1 lines and the state rc is settled.
settle() {
  for _ in $(seq 1 50); do
    [ "$(ps_count)" = "$1" ] && [ "$(state_get rc)" != pending ] && return 0
    sleep 0.1
  done
  return 1
}
dump() { printf '    state: %s | calls=%s\n' "$(tr '\n' ' ' < "$STATE" 2>/dev/null)" "$(ps_count)"; }

CUR="first session claims ownership and fires once"
echo "=== $CUR ==="
: > "$PS_LOG"
claude_keepawake sessA
if settle 1 && [ "$(state_get owner)" = sessA ] && [ "$(state_get rc)" = 0 ]; then ok "$CUR"; else bad "$CUR"; dump; fi

CUR="owner within INTERVAL does not fire again"
echo "=== $CUR ==="
claude_keepawake sessA
sleep 0.5
if [ "$(ps_count)" = 1 ] && [ "$(state_get owner)" = sessA ]; then ok "$CUR"; else bad "$CUR"; dump; fi

CUR="other session yields while the owner is fresh"
echo "=== $CUR ==="
claude_keepawake sessB
sleep 0.5
if [ "$(ps_count)" = 1 ] && [ "$(state_get owner)" = sessA ]; then ok "$CUR"; else bad "$CUR"; dump; fi

CUR="other session takes over after TAKEOVER of owner silence"
echo "=== $CUR ==="
sed -i "s/^last=.*/last=$(( $(date +%s) - 100 ))/" "$STATE"
claude_keepawake sessB
if settle 2 && [ "$(state_get owner)" = sessB ]; then ok "$CUR"; else bad "$CUR"; dump; fi

CUR="powershell exit code lands in the state file"
echo "=== $CUR ==="
sed -i "s/^last=.*/last=$(( $(date +%s) - 40 ))/" "$STATE"
PS_STUB_RC=3 claude_keepawake sessB
if settle 3 && [ "$(state_get rc)" = 3 ]; then ok "$CUR"; else bad "$CUR"; dump; fi

CUR="the fire is one-shot: SetThreadExecutionState without ES_CONTINUOUS, no process left"
echo "=== $CUR ==="
ENC="$(awk '{print $NF}' "$PS_LOG" | tail -1)"
DECODED="$(base64 -d <<< "$ENC" 2>/dev/null | iconv -f UTF-16LE -t UTF-8 2>/dev/null)"
if grep -q 'SetThreadExecutionState(1)' <<< "$DECODED" && ! grep -q 'ES_CONTINUOUS\|2147483648' <<< "$DECODED" \
   && ! pgrep -f "$BIN/powershell.exe" >/dev/null; then ok "$CUR"; else bad "$CUR (decoded: $DECODED)"; fi

CUR="caller returns before the detached powershell finishes"
echo "=== $CUR ==="
sed -i "s/^last=.*/last=$(( $(date +%s) - 40 ))/" "$STATE"
T0="$(date +%s%N)"
PS_STUB_SLEEP=2 claude_keepawake sessB
ELAPSED_MS=$(( ( $(date +%s%N) - T0 ) / 1000000 ))
if [ "$ELAPSED_MS" -lt 1000 ] && settle 4; then ok "$CUR (${ELAPSED_MS} ms)"; else bad "$CUR (${ELAPSED_MS} ms)"; dump; fi

CUR="outside WSL nothing is written or fired"
echo "=== $CUR ==="
rm -rf "$XDG_CACHE_HOME/claude-keepawake"; : > "$PS_LOG"
printf 'Linux version 6.0.0-generic\n' > "$KEEPAWAKE_PROC_VERSION"
claude_keepawake sessA
sleep 0.5
if [ ! -e "$STATE" ] && [ "$(ps_count)" = 0 ]; then ok "$CUR"; else bad "$CUR"; dump; fi

CUR="missing session id is a no-op"
echo "=== $CUR ==="
printf 'Linux version 6.0.0-microsoft-standard-WSL2\n' > "$KEEPAWAKE_PROC_VERSION"
claude_keepawake ""
sleep 0.5
if [ ! -e "$STATE" ] && [ "$(ps_count)" = 0 ]; then ok "$CUR"; else bad "$CUR"; dump; fi

echo
echo "==================================="
printf 'RESULT: %d passed, %d failed\n' "$PASS" "$FAIL"
echo "==================================="
[ "$FAIL" -eq 0 ]
