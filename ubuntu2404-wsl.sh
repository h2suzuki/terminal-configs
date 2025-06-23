#!/bin/bash

# This script sets up a Ubuntu 24.04 on WSL2 environment

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
    -e '/export\ BROWSER=/d' \
    -e '/export\ XAUTHORITY=/d'
run echo "alias tree=\\'tree --charset ascii --dirsfirst\\'" '>>' ~/.bashrc
run echo "alias diffy=\\'git diff --no-index\\'" '>>' ~/.bashrc
run echo 'grip\(\) \{ rg --json -C 2 \"\$@\" \| delta\; \}' '>>' ~/.bashrc


[ -d /etc/sudoers.d ] &&
copy sudoers    /etc/sudoers.d/nopasswd
copy gitconfig  /etc/gitconfig
copy inputrc    ~/.inputrc


# Vim, Git / Git-LFS, tree, ripgrep
run apt update
run apt install -y --no-install-recommends \
vim git git-lfs tree ripgrep

copy vimrc.local /etc/vim/vimrc.local

run git lfs install --skip-repo


# img2sixel
run apt install -y --no-install-recommends \
libsixel-bin


# X window forwarding and some small programs for testing
run apt install -y --no-install-recommends \
xauth xxd x11-apps mesa-utils

run xauth add ${DISPLAY} . $(xxd -l 16 -p /dev/urandom)     # Generate ~/.Xauthority


# git-delta   ref. https://github.com/dandavison/delta/releases
[ -s git-delta.deb ] ||
run curl -o git-delta.deb -fsSL https://github.com/dandavison/delta/releases/download/0.18.2/git-delta_0.18.2_amd64.deb
run apt install -y ./git-delta.deb


# mDNS to resolve mDNS .local from Windows host
run apt install -y --no-install-recommends \
avahi-utils avahi-daemon avahi-autoipd libnss-mdns


# OpenSSH and libsixel-bin for img2sixel
run apt install -y --no-install-recommends \
openssh-server openssh-client


# Chrome
[ -s google-chrome.deb ] ||
run curl -o google-chrome.deb -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
run apt install -y --fix-missing ./google-chrome.deb
run apt install -y upower 'fonts-ipafont*' 'fonts-ipaexfont*' 'fonts-noto-color-emoji'

run systemctl enable upower
run systemctl start upower
run fc-cache -fv


# AWS CLI
run apt install -y --no-install-recommends \
unzip
[ -s awscli2.zip ] ||
run curl -o awscli2.zip -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
rm -rf ./aws/
run unzip -q awscli2.zip
run ./aws/install --update
rm -rf ./aws/


# GitHub CLI
[ -s githubcli.gpg ] ||
run curl -o githubcli.gpg -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg
[ -d /etc/apt/keyrings ] ||
run install --mode 0755 --directory /etc/apt/keyrings/
run install --mode 0644 githubcli.gpg /etc/apt/keyrings/

cat > /etc/apt/sources.list.d/githubcli.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] \
https://cli.github.com/packages stable main
EOF

run apt update
run apt install -y gh


# Claude Code
[ -s nvm.sh ] ||
run curl -o nvm.sh -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh
run bash ./nvm.sh

. $HOME/.nvm/nvm.sh
run nvm install --lts
run nvm current
run node -v
run npm -v
run npm install -g @anthropic-ai/claude-code
run npm install -g ccusage


# Login user settings
#  1. Change the color of the prompt for the login user: green(32m) -> purple(35m)
#  2. Set ~/.Xauthority
#  3. Autoload ~/.nvm/nvm.sh
LOGIN_USER="$(logname)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name
if [ -n "$LOGIN_USER" ]; then
    BASHRC="~$LOGIN_USER/.bashrc"
    run [ -s $BASHRC ]
    run sed -i $BASHRC \
            -e '"/^ *PS1=/s/\[01;32m/[01;35m/"' \
            -e '"/export BROWSER=/d"' \
            -e '"/NVM_DIR/d"'

    # Generate ~/.Xauthority
    rm -f ~$LOGIN_USER/.Xauthority
    run install --mode 0600 --owner $LOGIN_USER /dev/null ~$LOGIN_USER/.Xauthority
    run sudo -u "$LOGIN_USER" xauth add ${DISPLAY} . $(xxd -l 16 -p /dev/urandom)
    # Refer ~/.Xauthority of the login user
    run echo "export XAUTHORITY=$(getent passwd "${LOGIN_USER}" | cut -d : -f 6)/.Xauthority" '>>' ~/.bashrc

    BROWSER="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe start"
    run echo 'export BROWSER=\"$BROWSER\"' '>>' ~/.bashrc
    run echo 'export BROWSER=\"$BROWSER\"' '>>' $BASHRC

    run install --mode 0755 --owner $LOGIN_USER --directory ~$LOGIN_USER/.nvm
    run install --mode 0644 --owner $LOGIN_USER "$HOME/.nvm/nvm.sh" ~$LOGIN_USER/.nvm/nvm.sh

    # Append auto-loading of nvm.sh
    run cat ">>" $BASHRC <<"EOF"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
EOF

    run sudo -u $LOGIN_USER bash -i -c '"nvm install --lts"'    # nvm is a shell function.
    run sudo -u $LOGIN_USER bash -i -c '"npm install -g @anthropic-ai/claude-code"'
    run sudo -u $LOGIN_USER bash -i -c '"npm install -g ccusage"'

else
    echo -e "${COLOR_RED}No login user found... omitting to tweak ~/.bashrc${COLOR_CLEAR}"
    echo -e "${COLOR_RED}No login user found... omitting to include ~/.nvm/nvm.sh${COLOR_CLEAR}"
    echo ""
fi


# Resolve mDNS .local addresses by Windows host's DNS
# Note that this is required for networkingMode=NAT
# --------
NSSWITCH="/etc/nsswitch.conf"
[ -s "${NSSWITCH}.org" ] ||
run cp -f "${NSSWITCH}" "${NSSWITCH}.org"

run "sed -i -e '/^hosts:/s/mdns4_minimal .*dns/dns mdns4_minimal/' $NSSWITCH"
# --------


# Set the hostname and enable systemd
cat > /etc/wsl.conf <<EOF
# See Also:
#  https://learn.microsoft.com/en-us/windows/wsl/wsl-config
#  On Windows, %UserProfile%\.wslconfig

[boot]
systemd = true

[network]
hostname = ubuntu2404-wsl
EOF

echo ''
echo '*** Please execute "wsl -t <this-machine>" on Windows to reflect /etc/wsl.conf ***'
echo ''

# END
