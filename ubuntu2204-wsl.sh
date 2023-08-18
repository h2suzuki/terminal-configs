#!/bin/bash

# This script sets up a Ubuntu 22.04 on WSL2 environment

which fgrep >/dev/null || {
    echo "Cannot find grep"
    exit 1
}
fgrep -qs WSL /proc/version || {
    echo "This environment does not look like WSL"
    exit 1
}
fgrep -qs "Ubuntu 22.04" /etc/lsb-release || {
    echo "This environment does not look like Ubuntu 22.04"
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

# mDNS to resolve ubuntu2204-wsl.local from Windows host
run apt-get install -y --no-install-recommends \
avahi-utils avahi-daemon avahi-autoipd libnss-mdns

# OpenSSH and libsixel-bin for img2sixel
run apt-get install -y --no-install-recommends \
openssh-server openssh-client

# Wezterm for its multiplexing client running on the remote side
#   https://wezfurlong.org/wezterm/install/linux.html
[ -s wezterm.deb ] ||
run curl -o wezterm.deb -fsSL https://github.com/wez/wezterm/releases/download/20220905-102802-7d4b8249/wezterm-20220905-102802-7d4b8249.Ubuntu22.04.deb
run apt install -y ./wezterm.deb

# Change the color of the prompt for the login user: green(32m) -> purple(35m)
LOGIN_USER="$(logname)"
[ -s "$LOGIN_USER" ] || {
    BASHRC="~$LOGIN_USER/.bashrc"
    run [ -s $BASHRC ]
    run sed -i -e '"/^ *PS1=/s/\[01;32m/[01;35m/"' $BASHRC
}


# AWS CLI
run apt-get install -y --no-install-recommends \
unzip
[ -s awscli2.zip ] ||
run curl -o awscli2.zip -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
rm -rf ./aws/
run unzip -q awscli2.zip
run ./aws/install --update



# Resolve mDNS .local addresses by Windows host's DNS
NSSWITCH="/etc/nsswitch.conf"
[ -s "${NSSWITCH}.org" ] ||
run cp -f "${NSSWITCH}" "${NSSWITCH}.org"

run "sed -i -e '/^hosts:/s/mdns4_minimal .*dns/dns mdns4_minimal/' $NSSWITCH"


# Set the hostname and enable systemd
cat > /etc/wsl.conf <<EOF
# See Also: https://learn.microsoft.com/en-us/windows/wsl/wsl-config

[boot]
systemd = true

[network]
generateHosts = true
generateResolvConf = true
hostname = ubuntu2204-wsl
EOF

echo ''
echo '*** Please execute "wsl -t <this-machine>" on Windows to reflect /etc/wsl.conf ***'
echo ''

# END
