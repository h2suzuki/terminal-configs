#!/bin/bash

# This script installs VoiceVox Core + its Claude Code alert hooks as an
# opt-in step after the base setup. The Claude Code alert hooks ship as a
# managed-settings drop-in (`/etc/claude-code/managed-settings.d/voicevox.json`)
# so the base machine — which never ran this script — has no dangling
# references to `/usr/local/bin/voicevox_claude_alerts`.

[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}



# Put $HOME/.local/bin on PATH (uv lives there) so the checks below resolve
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

export LC_ALL=C.UTF-8  # for the voicevox expect script to work



command -v tty       >/dev/null || { echo "Cannot find tty";         exit 1; }
command -v readlink  >/dev/null || { echo "Cannot find readlink";    exit 1; }
command -v cmp       >/dev/null || { echo "Cannot find cmp";         exit 1; }
command -v gh        >/dev/null || { echo "Cannot find gh";          exit 1; }
command -v uv        >/dev/null || { echo "Cannot find uv";          exit 1; }


# Repository root (one level up from extra/)
TOP_DIR=$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")


if tty -s >/dev/null; then
    COLOR_CLEAR="\033[0m"
    COLOR_RED="\033[31m"
    COLOR_GREEN="\033[32m"
    COLOR_YELLOW="\033[33m"
else
    COLOR_CLEAR=
    COLOR_RED=
    COLOR_GREEN=
    COLOR_YELLOW=
fi


run()
{
    local RETVAL

    echo -e "=> ${COLOR_YELLOW}${@}${COLOR_CLEAR}"
    eval "${@}"
    RETVAL=$?

    if [ $RETVAL -eq 0 ]; then
        echo -e "[ ${COLOR_GREEN}OK${COLOR_CLEAR} ]\n"
    else
        echo -e "[ ${COLOR_RED}ERROR($RETVAL)${COLOR_CLEAR} ]\n"
        exit $RETVAL
    fi
}


copy()
{
    BACKUP=1
    [ "$1" = "--nobackup" ] && { BACKUP=0; shift; }

    FNAME="files/$1"
    DST="$2"
    shift 2

    # When the caller did not pass -m, default the mode by extension:
    #   *.md / *.json / *.jsonl  -> 0644 (read-only data)
    #   else                     -> 0755 (matches install's own default;
    #                                     scripts / configs)
    # Security-sensitive targets (sudoers, secrets) must pass -m explicitly.
    case " $* " in
        *" -m "*) ;;
        *)
            case "$FNAME" in
                *.md|*.json|*.jsonl) set -- -m 0644 "$@" ;;
                *)                   set -- -m 0755 "$@" ;;
            esac
            ;;
    esac

    if [ -e "$DST" ]; then
        if cmp -s "$TOP_DIR/$FNAME" "$DST"; then
            echo -e "=> ${COLOR_YELLOW}$FNAME is already copied${COLOR_CLEAR}\n"
        else
            [ $BACKUP -eq 0 -o -e "$DST.org" ] || run install $@ "$DST" "$DST.org"
            run install "$@" "$TOP_DIR/$FNAME" "$DST"
        fi
    else
        run install -D "$@" "$TOP_DIR/$FNAME" "$DST"
    fi
}



# Tools required to drive and play VoiceVox
run apt install -y --no-install-recommends \
expect pulseaudio-utils


# Voicevox Core and Pasimple for PulseAudio Python binding
VV_VER=0.16.4
VV_BIN_DIR=/usr/local/bin
VV_LIB_DIR=/usr/lib/voicevox-core

if [ ! -s $VV_LIB_DIR/models/vvms/0.vvm ]; then

run uv pip install --system --break-system-packages pasimple
run uv pip install --system --break-system-packages \
  https://github.com/VOICEVOX/voicevox_core/releases/download/${VV_VER}/voicevox_core-${VV_VER}-cp310-abi3-manylinux_2_34_x86_64.whl

[ -s /tmp/voicevox_install.sh ] ||
run curl -o /tmp/voicevox_install.sh \
  -fsSL https://github.com/VOICEVOX/voicevox_core/releases/download/$VV_VER/download-linux-x64
chmod u-s,u+x /tmp/voicevox_install.sh

rm -rf $VV_LIB_DIR

echo -e "=> ${COLOR_YELLOW}Installing VoiceVox ...${COLOR_CLEAR}"

# The downloader is a TUI that redraws on the alternate screen buffer, so its progress output never
# lands in the terminal scrollback. Set OMIT_TUI_OUTPUT=1 in the parent shell to silence that relay
export OMIT_TUI_OUTPUT=1

# GH_TOKEN relaxes this downloader's GitHub ratelimit
GH_TOKEN="$(gh auth token)" expect -c '
set timeout 300

if {[info exists env(OMIT_TUI_OUTPUT)] && $env(OMIT_TUI_OUTPUT) eq "1"} { log_user 0; }

spawn /tmp/voicevox_install.sh --output '"$VV_LIB_DIR"' --exclude c-api --models-pattern {[0-9]*.vvm}

expect {
    -ex "qを押してください" { puts "Caught: $expect_out(0,string) => Sending: q"; send "q\r"; sleep 1 }
    timeout                 { puts "タイムアウトしました";  exit 1 }
    eof                     { puts "接続が切れました";      exit 1 }
}
expect {
    -ex "\[y,n,r\]"         { puts "Caught: $expect_out(0,string) => Sending: y"; send "y\r"; sleep 1 }
    timeout                 { puts "タイムアウトしました";  exit 1 }
    eof                     { puts "接続が切れました";      exit 1 }
}
expect {
    timeout                 { puts "タイムアウトしました";  exit 1 }
    eof                     { puts "インストールが完了";    exit 0 }
}
'

    RETVAL=$?
    if [ $RETVAL -eq 0 ]; then
        echo -e "[ ${COLOR_GREEN}OK${COLOR_CLEAR} ]\n"
    else
        echo -e "[ ${COLOR_RED}ERROR($RETVAL)${COLOR_CLEAR} ]\n"
        exit $RETVAL
    fi
fi

run [ -s $VV_LIB_DIR/dict/open_jtalk_dic_utf*/sys.dic ]
run [ -s $VV_LIB_DIR/onnxruntime/lib/libvoicevox_onnxruntime.so* ]
for i in `seq 0 24`; do run [ -s $VV_LIB_DIR/models/vvms/$i.vvm ]; done

copy --nobackup voicevox_paplay ${VV_BIN_DIR}/voicevox_paplay


# Claude Code alert hooks (managed-settings drop-in)
copy --nobackup voicevox_claude_alerts          /usr/local/bin/voicevox_claude_alerts -m 0755
copy --nobackup claude_managed-voicevox.json    /etc/claude-code/managed-settings.d/voicevox.json


# END
