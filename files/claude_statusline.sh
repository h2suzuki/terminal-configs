#!/bin/bash
# Claude Code statusline
#   🏠 project ❯ Model [effort]  Context [████░░░░░░](42%)  5H [██░░░░░░░░](27%)→00:16  1W [██████░░░░](61%)→23:16 Wednesday          YYYY/mm/dd HH:MM
#
# stdin JSON fields used:
#   .session_id
#   .model.display_name
#   .effort.level
#   .context_window.used_percentage
#   .rate_limits.five_hour.{used_percentage,resets_at}   (Pro/Max only)
#   .rate_limits.seven_day.{used_percentage,resets_at}   (Pro/Max only)
#   .workspace.project_dir   (falls back to .cwd)
#
# Cache: ${XDG_CACHE_HOME:-~/.cache}/claude-tui-statusline/<session_id>.json
#   Wrapped as {stdin, timestamp <ISO8601>, session_started_epoch}. Written atomically.
#   Per-session file (no cross-session race). A SessionEnd hook deletes it.

set -o pipefail

input="$(cat)"
# 全 stdin フィールドを 1 回の jq で抽出 (per-field の jq fork を回避)。 読取順は配列順と一致。
{
    read -r _cur_session
    read -r ctx_pct
    read -r h5_pct
    read -r h5_at
    read -r wk_pct
    read -r wk_at
    read -r model
    read -r effort
    read -r proj_dir
} < <(jq -r '[
    .session_id,
    .context_window.used_percentage,
    .rate_limits.five_hour.used_percentage,
    .rate_limits.five_hour.resets_at,
    .rate_limits.seven_day.used_percentage,
    .rate_limits.seven_day.resets_at,
    .model.display_name,
    (.effort.level // .effort_level // .effortLevel),
    (.workspace.project_dir // .cwd)
] | map(. // "") | .[]' <<< "$input")

# -- Cache dump (per session) --
# Dump this session's statusline stdin to
# <cache>/claude-tui-statusline/<session_id>.json, wrapped as
# {stdin, timestamp, session_started_epoch}. Per-session files mean no
# cross-session overwrite race, so the old staleness / same-session guards are gone.
# session_started_epoch is stamped on first render and preserved, letting readers
# (stop_checks.py turn marker) show elapsed-since-session-start. A SessionEnd hook deletes the file.
_cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/claude-tui-statusline"
if [ -n "$_cur_session" ]; then
    mkdir -p "$_cache_dir"
    _cache_file="${_cache_dir}/${_cur_session}.json"
    _now_iso="$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')"
    # Carry the first-render epoch forward; stamp now on first creation or if
    # the stored value is missing/non-numeric (else --argjson would abort the
    # write every render, freezing the cache for the session).
    _started="$(jq -r '.session_started_epoch // empty' "$_cache_file" 2>/dev/null)"
    case "$_started" in ''|*[!0-9]*) _started="$(date +%s)" ;; esac
    _tmp="$(mktemp "${_cache_dir}/.${_cur_session}.XXXXXX.json" 2>/dev/null)" || _tmp=""
    if [ -n "$_tmp" ]; then
        trap 'rm -f "$_tmp"' EXIT
        if jq -S --arg ts "$_now_iso" --argjson st "$_started" \
                '{stdin: ., timestamp: $ts, session_started_epoch: $st}' \
                > "$_tmp" 2>/dev/null <<< "$input"; then
            mv "$_tmp" "$_cache_file" 2>/dev/null && trap - EXIT
        fi
    fi
    unset _cache_file _now_iso _started
fi
unset _cache_dir _cur_session

bar() {
    local width=10 pct filled empty out='[' i
    pct="$(printf '%.0f' "${1:-0}")"
    (( pct < 0   )) && pct=0
    (( pct > 100 )) && pct=100
    filled=$(( pct * width / 100 ))
    empty=$((  width - filled ))
    for (( i=0; i<filled; i++ )); do out+='█'; done
    for (( i=0; i<empty;  i++ )); do out+='░'; done
    out+=']'
    printf '%s' "$out"
}

seg() {
    # $1 label  $2 pct  $3 time suffix (optional)
    local pct_disp
    pct_disp="$(printf '(%.0f%%)' "$2")"
    if [ -n "$3" ]; then
        printf '%s %s%s→%s' "$1" "$(bar "$2")" "$pct_disp" "$3"
    else
        printf '%s %s%s' "$1" "$(bar "$2")" "$pct_disp"
    fi
}

empty_bar='[░░░░░░░░░░]'

# -- Context --
if [ -n "$ctx_pct" ]; then
    ctx="$(seg 'Context' "$ctx_pct")"
else
    ctx="Context ${empty_bar}   —"
fi

# -- 5H --
if [ -n "$h5_at" ]; then
    h5="$(seg '5H' "$h5_pct" "$(date -d "@$h5_at" +%H:%M)")"
else
    h5="5H ${empty_bar}   —"
fi

# -- Weekly --
if [ -n "$wk_at" ]; then
    wk="$(seg '1W' "$wk_pct" "$(date -d "@$wk_at" '+%H:%M %A')")"
else
    wk="1W ${empty_bar}   —"
fi

# -- Model + Effort (color by level) --
model="${model#Claude }"        # strip "Claude " if present
model="${model%% (*}"           # drop " (1M context)" suffix
[ -z "$model" ] && model='?'
[ -z "$effort" ] && effort="$(jq -r '.effortLevel // empty' "$HOME/.claude/settings.json" 2>/dev/null)"

RESET=$'\033[0m'
case "$effort" in
    min|none)    COLOR=$'\033[38;5;39m'  ;;   # blue
    low)         COLOR=$'\033[38;5;41m'  ;;   # green
    medium|mid)  COLOR=$'\033[38;5;220m' ;;   # yellow
    high)        COLOR=$'\033[38;5;208m' ;;   # orange
    xhigh)       COLOR=$'\033[1;38;5;196m' ;; # bold red
    max)         COLOR=$'\033[1;38;5;129m' ;; # bold purple
    *)           COLOR='' ;;
esac

if [ -n "$effort" ]; then
    head="${model} [${COLOR}${effort}${RESET}]"
else
    head="${model}"
fi

# -- Project (workspace) --
HOME_DIR="${HOME:-/home/$(id -un)}"

PROJ_MAX=20
truncate_str() {
    # Char-based truncation (relies on UTF-8 locale for ${#str} / substring).
    local str="$1" max="$2"
    if (( ${#str} > max )); then
        printf '%s…' "${str:0:$((max-1))}"
    else
        printf '%s' "$str"
    fi
}

DIM=$'\033[2;38;5;240m'
if [ -n "$proj_dir" ] && [ "$proj_dir" != "$HOME_DIR" ]; then
    proj_base="$(basename "$proj_dir")"
    proj_name="$(truncate_str "$proj_base" "$PROJ_MAX")"
    proj_color="$(printf '%s' "$proj_base" | cksum | awk '{
        n = split("42 51 75 141 207 215 186", c, " ")
        printf "\033[1;38;5;%dm", c[($1 % n) + 1]
    }')"
    proj_seg="🏠 ${proj_color}${proj_name}${RESET} ${DIM}❯${RESET}"
else
    proj_seg="🏠  ${DIM}❯${RESET}"
fi

# -- Clock --
now="$(date '+%Y/%m/%d %H:%M')"

left="${proj_seg}  ${head}  ${ctx}  ${h5}  ${wk}"

# Terminal width: COLUMNS > stty > tput > parent-chain tty > default 200.
# Suppress the whole group's stderr so a missing controlling tty stays silent.
cols="${COLUMNS:-}"
[ -z "$cols" ] && cols="$( { stty size </dev/tty | awk '{print $2}'; } 2>/dev/null )"
[ -z "$cols" ] && cols="$( { tput cols </dev/tty; } 2>/dev/null )"
# Claude Code TUI spawns this script with stdin/stdout/stderr as pipes and no
# controlling tty, so the /dev/tty paths fail. Walk up the parent chain to find
# a pty (the TUI itself owns one) and stty its dimensions.
if [ -z "$cols" ]; then
    _pid=$$
    for _ in 1 2 3 4 5; do
        _pid="$(awk '/^PPid:/ {print $2}' "/proc/$_pid/status" 2>/dev/null)"
        [ -z "$_pid" ] || [ "$_pid" = 0 ] && break
        _t="$(readlink "/proc/$_pid/fd/0" 2>/dev/null)"
        case "$_t" in
            /dev/pts/*|/dev/tty[0-9]*)
                cols="$(stty -F "$_t" size 2>/dev/null | awk '{print $2}')"
                [ -n "$cols" ] && break
                ;;
        esac
    done
    unset _pid _t
fi
[ -z "$cols" ] && cols=200

# Visible character count excludes ANSI escapes.
# Ambiguous-width chars (U+2588 █, U+2591 ░, U+2192 →) may render as 2 columns on
# some terminals (East-Asian ambiguous = wide). Count them and compensate.
left_visible="$(printf '%s' "$left" | sed $'s/\033\\[[0-9;]*m//g')"
left_chars="$(printf '%s' "$left_visible" | wc -m)"
amb_extra="$(printf '%s' "$left_visible" | grep -oE '→|🏠' | wc -l)"
# Reserve a small margin for any TUI chrome at the right edge.
safety=2
pad=$(( cols - left_chars - ${#now} - amb_extra - safety ))
(( pad < 2 )) && pad=2
printf '%s%*s%s\n' "$left" "$pad" "" "$now"
