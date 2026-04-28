#!/bin/bash
# Claude Code statusline
#   🏠 project ❯ Model [effort]  Context [████░░░░░░](42%)  5H [██░░░░░░░░](27%)→00:16  1W [██████░░░░](61%)→23:16 Wednesday          YYYY/mm/dd HH:MM
#
# stdin JSON fields used:
#   .model.display_name
#   .effort.level
#   .context_window.used_percentage
#   .rate_limits.five_hour.{used_percentage,resets_at}   (Pro/Max only)
#   .rate_limits.seven_day.{used_percentage,resets_at}   (Pro/Max only)
#   .workspace.project_dir   (falls back to .cwd)

set -o pipefail

input="$(cat)"
get() { printf '%s' "$input" | jq -r "$1 // empty"; }

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
