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
    -e '/alias\ tree=/d' \
    -e '/alias\ diffy=/d' \
    -e '/grip\(\)\ /d' \
    -e '/export\ XAUTHORITY=/d'
run echo "alias tree=\\'tree --charset ascii --dirsfirst\\'" '>>' ~/.bashrc
run echo "alias diffy=\\'git diff --no-index\\'" '>>' ~/.bashrc
run echo 'grip\(\) \{ rg --json -C 2 \"\$@\" \| delta\; \}' '>>' ~/.bashrc


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


# Rye package manager for Python3
export RYE_INSTALL_OPTION="--yes"
[ -s rye-get.sh ] ||
run curl -o rye-get.sh -fsSL https://rye-up.com/get
run bash ./rye-get.sh
run rye self completion '>' /usr/share/bash-completion/completions/rye


# X window forwarding and some small programs for testing
run apt-get install -y --no-install-recommends \
xauth xxd x11-apps

if [ -z "${DISPLAY}" ]; then
    echo -e "${COLOR_RED}\$DISPLAY is empty.  Please relogin from an SSH client to complete the process. ${COLOR_CLEAR}"
    exit 0
fi
rm -f ~/.Xauthority
install --mode 0600 /dev/null ~/.Xauthority
run xauth add ${DISPLAY} . $(xxd -l 16 -p /dev/urandom)     # Generate ~/.Xauthority


# git-delta   ref. https://github.com/dandavison/delta/releases
[ -s git-delta.deb ] ||
run curl -o git-delta.deb -fsSL https://github.com/dandavison/delta/releases/download/0.16.5/git-delta_0.16.5_amd64.deb
run apt install -y ./git-delta.deb


# Google Chrome     `google-chrome --disable-gpu` to start the browser
[ -s google-chrome.deb ] ||
run curl -o google-chrome.deb -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
run apt install -y --fix-missing ./google-chrome.deb
run apt install -y upower 'fonts-ipafont-nonfree*' 'fonts-ipaexfont*'

run systemctl enable upower
run systemctl start upower
run fc-cache -fv


# Login user settings
#  1. Set ~/.Xauthority
LOGIN_USER="$(logname)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name
if [ -n "$LOGIN_USER" ]; then
    # Generate ~/.Xauthority
    rm -f ~$LOGIN_USER/.Xauthority
    run install --mode 0600 --owner $LOGIN_USER /dev/null ~$LOGIN_USER/.Xauthority
    run sudo -u "$LOGIN_USER" xauth add ${DISPLAY} . $(xxd -l 16 -p /dev/urandom)
    # Refer ~/.Xauthority from this account
    run echo "export XAUTHORITY=$(getent passwd "${LOGIN_USER}" | cut -d : -f 6)/.Xauthority" '>>' ~/.bashrc
else
    echo -e "${COLOR_RED}No login user found... omitting to tweak ~/.bashrc${COLOR_CLEAR}"
    echo ""
fi


# END
