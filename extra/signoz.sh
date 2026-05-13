#!/bin/bash

# This script sets up SigNoz on Ubuntu 24.04 on WSL2.
# Run this AFTER ../ubuntu2404-wsl.sh as an opt-in step.

which fgrep >/dev/null || {
    echo "Cannot find grep"
    exit 1
}
fgrep -qs WSL /proc/version || {
    echo "This environment does not look like WSL"
    exit 1
}
fgrep -qs "Ubuntu 24.04" /etc/lsb-release || {
    echo "This environment does not look like Ubuntu 24.04"
    exit 1
}
[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}



which tty       >/dev/null || { echo "Cannot find tty";         exit 1; }
which readlink  >/dev/null || { echo "Cannot find readlink";    exit 1; }
which cmp       >/dev/null || { echo "Cannot find cmp";         exit 1; }
which docker    >/dev/null || { echo "Cannot find docker";      exit 1; }
which git       >/dev/null || { echo "Cannot find git";         exit 1; }
which node      >/dev/null || { echo "Cannot find node";        exit 1; }


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



# sqlite3 is used below to fetch SigNoz's ORG_ID
run apt install -y --no-install-recommends sqlite3


# SigNoz by docker-compose
#   docker compose down       # When to stop
#   docker compose down -v    # When to stop and erase data
if [ -d /opt/signoz/ ]; then
    pushd /opt/signoz/deploy/docker >/dev/null
    docker compose down || true
    popd >/dev/null

    rm -rf /opt/signoz/
fi
run git clone --depth=1 --filter=blob:none --sparse \
  https://github.com/SigNoz/signoz.git /opt/signoz

pushd /opt/signoz >/dev/null
run git sparse-checkout set deploy
run [ -d deploy/docker ]

cd deploy/docker
run [ -f docker-compose.yaml ]

# Set the listen port 14902 and the root user
copy --nobackup signoz_compose-override.yaml docker-compose.override.yaml

# Bring the services up
run docker compose up -d --remove-orphans

SQLITE_PATH=$(sed -n -e '/SIGNOZ_SQLSTORE_SQLITE_PATH/{s/.*=\(.*\)/\1/p;q}' docker-compose.yaml)
run [ -n "$SQLITE_PATH" ]
run docker compose cp signoz:"$SQLITE_PATH" /tmp/signoz.db

ORG_ID=$(sqlite3 /tmp/signoz.db "select id from organizations where name='local';")
run [ -n "$ORG_ID" ]
rm -f /tmp/signoz.db

popd >/dev/null


# Claude Code Dashboard of SigNoz
run node "$TOP_DIR/files/signoz_claude-dashboard.mjs" \
         "$TOP_DIR/files/signoz_claude-dashboard.json" "$ORG_ID"


# OTEL environment variables for Claude Code telemetry to SigNoz
copy --nobackup claude_env.sh                   /etc/claude-code/env.sh

[ -e ~/.bashrc ] &&
run sed -i ~/.bashrc \
    -e '/source\ \\/etc\\/claude-code\\/env\\.sh/d'
run echo "source /etc/claude-code/env.sh" '>>' ~/.bashrc

LOGIN_USER="$(logname)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name
if [ -n "$LOGIN_USER" ]; then
    BASHRC="~$LOGIN_USER/.bashrc"
    run [ -s $BASHRC ]
    run sed -i $BASHRC \
            -e '/source\ \\/etc\\/claude-code\\/env\\.sh/d'
    run echo "source /etc/claude-code/env.sh" '>>' $BASHRC
else
    echo -e "${COLOR_RED}No login user found... omitting to source env.sh from ~/.bashrc${COLOR_CLEAR}"
fi


# END
