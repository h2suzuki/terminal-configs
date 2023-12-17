#!/bin/bash

# This script sets up a Debian 12 environment

which fgrep >/dev/null || {
    echo "Cannot find grep"
    exit 1
}
fgrep -qs "Debian GNU/Linux 12 " /etc/issue || {
    echo "This environment does not look like Debian 12"
    exit 1
}
[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}



which tty       >/dev/null || { echo "Cannot find tty";         exit 1; }
which readlink  >/dev/null || { echo "Cannot find readlink";    exit 1; }
which cmp       >/dev/null || { echo "Cannot find cmp";         exit 1; }


TOP_DIR="`dirname ${BASH_SOURCE[0]}`"
TOP_DIR="`readlink -f "$TOP_DIR"`"


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
    FNAME="files/$1"
    DST="$2"

    if [ -e "$DST" ]; then
        if cmp -s "$TOP_DIR/$FNAME" "$DST"; then
            echo -e "=> ${COLOR_YELLOW}$FNAME is already copied${COLOR_CLEAR}\n"
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
    -e '/^alias\ ls=/s/ls\ \$LS_OPTIONS/ls\ --group-directories-first\ \$LS_OPTIONS/' \
    -e '/alias\ tree=/d'
run echo "alias tree=\\'tree --charset ascii --dirsfirst\\'" '>>' ~/.bashrc


[ -d /etc/sudoers.d ] &&
copy sudoers    /etc/sudoers.d/nopasswd
copy gitconfig  /etc/gitconfig
copy inputrc    ~/.inputrc


# Vim, Git and Git-LFS
run apt-get update
run apt-get install -y --no-install-recommends \
vim git git-lfs

copy vimrc.local /etc/vim/vimrc.local

run git lfs install --skip-repo


# img2sixel
run apt-get install -y --no-install-recommends \
libsixel-bin

# END
