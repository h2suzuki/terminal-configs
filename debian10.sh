#!/bin/bash

# This script sets up a Debian 10 environment


which tty       >/dev/null || { echo "Cannot find tty";         exit 1; }
which readlink  >/dev/null || { echo "Cannot find readlink";    exit 1; }
which cmp       >/dev/null || { echo "Cannot find cmp";         exit 1; }


TOP_DIR="`dirname ${BASH_SOURCE[0]}`"
TOP_DIR="`readlink -f "$TOP_DIR"`"


if tty -s >/dev/null; then
    COLOR_CLEAR="\033[0m"
    COLOR_RED="\033[31m"
    COLOR_GREEN="\033[32m"
else
    COLOR_CLEAR=
    COLOR_RED=
    COLOR_GREEN=
fi

run()
{
    local RETVAL

    echo '--------------------------------'
    echo "${@}"
    eval "${@}"
    RETVAL=$?
    echo '--------------------------------'

    if [ $RETVAL -eq 0 ]; then
        echo -e "[ ${COLOR_GREEN}OK${COLOR_CLEAR} ]"
    else
        echo -e "[ ${COLOR_RED}ERROR($RETVAL)${COLOR_CLEAR} ]"
        exit $RETVAL
    fi
}


copy()
{
    FNAME="$1"
    DST="$2"

    if [ -e "$DST" ]; then
        if cmp -s "$TOP_DIR/$FNAME" "$DST"; then
            echo "$FNAME is already copied"
        else
            [ -e "$DST.org" ] || run cp "$DST" "$DST.org"
            run cp "$TOP_DIR/$FNAME" "$DST"
        fi
    else
        run cp "$TOP_DIR/$FNAME" "$DST"
    fi
}



[ -e ~/.bashrc ] &&
run sed -i ~/.bashrc \
    -e '/export\ LS_OPTIONS/s/^\ *#*\ *//' \
    -e '/eval\ \"\`dircolor/s/^\ *#*\ *//' \
    -e '/alias\ ls=/s/^\ *#*\ *//' \
    -e '/^alias\ ls=/s/ls\ \$LS_OPTIONS/ls\ --group-directories-first\ \$LS_OPTIONS/'

copy gitconfig /etc/gitconfig
copy inputrc ~/.inputrc

run apt-get update '&&' apt-get install --no-install-recommends vim
copy vimrc.local /etc/vim/vimrc.local
