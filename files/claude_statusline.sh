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
# Cache: ${XDG_CACHE_HOME:-~/.cache}/claude-tui-statusline/stdin.json
#   Wrapped as {stdin: <original>, timestamp: <ISO8601>}. Written atomically.
#   Race-condition guard: only overwrites if same session_id OR file is ≥60s old.

set -o pipefail

input="$(cat)"
get() { printf '%s' "$input" | jq -r "$1 // empty"; }

# -- Cache dump --
if [ -n "${XDG_CACHE_HOME:-}" ]; then
    _cache_dir="${XDG_CACHE_HOME}/claude-tui-statusline"
else
    _cache_dir="${HOME}/.cache/claude-tui-statusline"
fi
_cache_file="${_cache_dir}/stdin.json"
mkdir -p "$_cache_dir"

_cur_session="$(get '.session_id')"
_now_iso="$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')"
_do_dump=1

# Obsolete-data guard: if a rate-limit bucket is at 100% AND its resets_at is already
# more than 60 s in the past, the messages API is paused and Claude Code has stopped
# receiving fresh data. Writing this stale snapshot would overwrite a more up-to-date
# entry from an active session, so skip the dump.
# `// now` as default makes the condition false when a field is absent.
# Uses jq's built-in `now` to avoid an extra date(1) spawn.
if jq -e '
  ((.rate_limits.five_hour.used_percentage // 0) >= 100 and (.rate_limits.five_hour.resets_at // now) < now - 60) or
  ((.rate_limits.seven_day.used_percentage // 0) >= 100 and (.rate_limits.seven_day.resets_at // now) < now - 60)
' >/dev/null 2>&1 <<< "$input"; then
    _do_dump=0
fi

if [ -f "$_cache_file" ]; then
    _ex="$(cat "$_cache_file" 2>/dev/null)"
    if [ -n "$_ex" ]; then
        _ex_session="$(jq -r '.stdin.session_id // empty' 2>/dev/null <<< "$_ex")"
        _ex_ts="$(jq -r '.timestamp // empty' 2>/dev/null <<< "$_ex")"
        if [ -n "$_cur_session" ] && [ "$_ex_session" = "$_cur_session" ]; then
            : # (i) same session → dump
        elif [ -n "$_ex_ts" ]; then
            _ex_epoch="$(date -d "$_ex_ts" +%s 2>/dev/null)"
            _now_epoch="$(date +%s)"
            if (( _now_epoch - _ex_epoch < 60 )); then
                _do_dump=0
            fi
        fi
    fi
fi

if (( _do_dump )); then
    _tmp="$(mktemp "${_cache_dir}/.stdin.XXXXXX.json" 2>/dev/null)" || _tmp=""
    if [ -n "$_tmp" ]; then
        trap 'rm -f "$_tmp"' EXIT
        if jq -S --arg ts "$_now_iso" '{stdin: ., timestamp: $ts}' \
                > "$_tmp" 2>/dev/null <<< "$input"; then
            mv "$_tmp" "$_cache_file" 2>/dev/null && trap - EXIT
        fi
    fi
fi
unset _cache_dir _cache_file _cur_session _now_iso _do_dump _ex _ex_session _ex_ts _ex_epoch _now_epoch

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
ctx_pct="$(get '.context_window.used_percentage')"
if [ -n "$ctx_pct" ]; then
    ctx="$(seg 'Context' "$ctx_pct")"
else
    ctx="Context ${empty_bar}   —"
fi

# -- 5H --
h5_pct="$(get '.rate_limits.five_hour.used_percentage')"
h5_at="$(get  '.rate_limits.five_hour.resets_at')"
if [ -n "$h5_at" ]; then
    h5="$(seg '5H' "$h5_pct" "$(date -d "@$h5_at" +%H:%M)")"
else
    h5="5H ${empty_bar}   —"
fi

# -- Weekly --
wk_pct="$(get '.rate_limits.seven_day.used_percentage')"
wk_at="$(get  '.rate_limits.seven_day.resets_at')"
if [ -n "$wk_at" ]; then
    wk="$(seg '1W' "$wk_pct" "$(date -d "@$wk_at" '+%H:%M %A')")"
else
    wk="1W ${empty_bar}   —"
fi

# -- Model + Effort (color by level) --
model="$(get '.model.display_name')"
model="${model#Claude }"        # strip "Claude " if present
model="${model%% (*}"           # drop " (1M context)" suffix
[ -z "$model" ] && model='?'
effort="$(get '.effort.level')"
[ -z "$effort" ] && effort="$(get '.effort_level')"
[ -z "$effort" ] && effort="$(get '.effortLevel')"
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
proj_dir="$(get '.workspace.project_dir')"
[ -z "$proj_dir" ] && proj_dir="$(get '.cwd')"

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

# Terminal width: COLUMNS > stty > tput > default 200.
# Suppress the whole group's stderr so a missing controlling tty stays silent.
cols="${COLUMNS:-}"
[ -z "$cols" ] && cols="$( { stty size </dev/tty | awk '{print $2}'; } 2>/dev/null )"
[ -z "$cols" ] && cols="$( { tput cols </dev/tty; } 2>/dev/null )"
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
