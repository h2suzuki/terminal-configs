#!/bin/bash

# This script sets up a Ubuntu 24.04 on WSL2 environment


command -v grep     >/dev/null || { echo "Cannot find grep";        exit 1; }

grep -Fqs WSL /proc/version || {
    echo "This environment does not look like WSL"
    exit 1
}
grep -Fqs "Ubuntu 24.04" /etc/lsb-release || {
    echo "This environment does not look like Ubuntu 24.04"
    exit 1
}
[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}

command -v tty      >/dev/null || { echo "Cannot find tty";         exit 1; }
command -v readlink >/dev/null || { echo "Cannot find readlink";    exit 1; }
command -v cmp      >/dev/null || { echo "Cannot find cmp";         exit 1; }


TOP_DIR=$(dirname "$(realpath "${BASH_SOURCE[0]}")")


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
    BACKUP=0
    [ "$1" = "--backup" ] && { BACKUP=1; shift; }

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



# Install basic utilities
run apt update

run apt -y full-upgrade

run apt install -y --no-install-recommends \
curl gpg \
neovim git git-lfs tree ripgrep shellcheck htop \
libsixel-bin \
xauth jq x11-apps mesa-utils vulkan-tools wayland-utils \
pulseaudio pulseaudio-utils alsa-utils \
avahi-utils avahi-daemon avahi-autoipd libnss-mdns \
openssh-server openssh-client

run apt remove -y vim

run apt -y auto-remove

copy sudoers                        /etc/sudoers.d/terminal-config -m 0440
copy gitconfig                      /etc/gitconfig
copy sysinit.vim                    /etc/xdg/nvim/sysinit.vim               # Neovim system-wide init file
copy htoprc                         /etc/htoprc -m 0644                     # htop system-wide default config
copy inputrc                        /etc/skel/.inputrc


# SSH keepalive so idle sessions survive the WSL2/Hyper-V NAT idle timeout
copy ssh_keepalive_wtsess.conf      /etc/ssh/ssh_config.d/10-keepalive_wtsess.conf  -m 0644
copy sshd_keepalive_wtsess.conf     /etc/ssh/sshd_config.d/10-keepalive_wtsess.conf -m 0644

run systemctl restart ssh.service


# PulseAudio server to proxy audio streaming from 24713/tcp to WSLg's PulseAudio server
copy pulseaudio-proxy.pa            /etc/pulse/proxy.pa
copy pulseaudio-proxy.service       /etc/systemd/system/pulseaudio-proxy.service

run usermod -d /var/run/pulse pulse     # A workaround for warning messages; HomeDir is hard-coded in PulseAudio

run systemctl daemon-reload
run systemctl start pulseaudio-proxy.service
run systemctl enable pulseaudio-proxy.service

# How to test the audio facility
#
# set either
#   PULSE_SERVER=unix:/mnt/wslg/PulseServer   for WSLg
# or
#   PULSE_SERVER=tcp:localhost:24713          for 24713/tcp
#
# then
#   paplay /usr/share/sounds/alsa/Front_Center.wav



# Python package manager: uv
[ -s /tmp/uv_install.sh ] ||
run curl -o /tmp/uv_install.sh \
  -fsSL https://astral.sh/uv/install.sh
chmod u-s,o+r /tmp/uv_install.sh

export UV_INSTALL_DIR=/usr/local/bin
export UV_NO_PROGRESS=true
run bash /tmp/uv_install.sh
run uv self update


# Python linter / formatter: ruff
[ -s /tmp/ruff_install.sh ] ||
run curl -o /tmp/ruff_install.sh \
  -fsSL https://astral.sh/ruff/install.sh
chmod u-s,o+r /tmp/ruff_install.sh

export RUFF_INSTALL_DIR=/usr/local/bin
export RUFF_NO_MODIFY_PATH=1
run bash /tmp/ruff_install.sh


# Python type checker: ty
[ -s /tmp/ty_install.sh ] ||
run curl -o /tmp/ty_install.sh \
  -fsSL https://astral.sh/ty/install.sh
chmod u-s,o+r /tmp/ty_install.sh

export TY_INSTALL_DIR=/usr/local/bin
export TY_NO_MODIFY_PATH=1
run bash /tmp/ty_install.sh


# Chrome
[ -s /tmp/google-chrome.deb ] ||
run curl -o /tmp/google-chrome.deb \
  -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
run apt install -y /tmp/google-chrome.deb
run apt install -y upower 'fonts-ipafont*' 'fonts-ipaexfont*' 'fonts-noto-color-emoji'

run systemctl enable upower
run systemctl start upower
run fc-cache -fv


# GitHub CLI
if [ ! -s /etc/apt/keyrings/githubcli.gpg ]; then
    [ -s /tmp/githubcli.gpg ] ||
    run curl -o /tmp/githubcli.gpg \
      -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg

    [ -d /etc/apt/keyrings ] ||
    run install --mode 0755 --directory /etc/apt/keyrings/
    run install --mode 0644 /tmp/githubcli.gpg /etc/apt/keyrings/
fi

if [ ! -s /etc/apt/sources.list.d/githubcli.list ]; then
    cat > /etc/apt/sources.list.d/githubcli.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] \
https://cli.github.com/packages stable main
EOF
    run apt update
fi

run apt install -y gh


# Google Cloud CLI
if [ ! -s /etc/apt/keyrings/cloud.google.gpg ]; then
    [ -s /tmp/cloud.google.apt-key.gpg ] ||
    run curl -o /tmp/cloud.google.apt-key.gpg \
      -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg

    run gpg --yes --dearmor -o /tmp/cloud.google.gpg /tmp/cloud.google.apt-key.gpg
    [ -d /etc/apt/keyrings ] ||
    run install --mode 0755 --directory /etc/apt/keyrings/
    run install --mode 0644 /tmp/cloud.google.gpg /etc/apt/keyrings/
fi

if [ ! -s /etc/apt/sources.list.d/google-cloud-sdk.list ]; then
    cat > /etc/apt/sources.list.d/google-cloud-sdk.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/cloud.google.gpg] \
https://packages.cloud.google.com/apt cloud-sdk main
EOF
    run apt update
fi

run apt install -y google-cloud-cli



# For Claude Code
rm -rf /etc/claude-code/
copy claude_statusline.sh                        /etc/claude-code/statusline.sh
copy claude_managed-CLAUDE.md                    /etc/claude-code/CLAUDE.md
copy claude_managed-settings.json                /etc/claude-code/managed-settings.json
copy claude_user-CLAUDE.md                       /etc/claude-code/skel/CLAUDE.md
copy claude_user-settings.json                   /etc/claude-code/skel/settings.json

run apt install -y --no-install-recommends \
bubblewrap socat poppler-utils      # Sandbox: bubblewrap/socat, PDF reading: poppler-utilsl

# Sandbox seccomp helper: enables Unix-domain-socket blocking in the Bash sandbox
run npm install -g @anthropic-ai/sandbox-runtime

# AppArmor blocks unprivileged userns; grant bwrap that cap for the Sandbox
USERNS_FLAG=/proc/sys/kernel/apparmor_restrict_unprivileged_userns
if [ -r "$USERNS_FLAG" ] && [ "$(< "$USERNS_FLAG")" = "1" ]; then
    copy claude_apparmor-bwrap                  /etc/apparmor.d/bwrap -m 0644
    run systemctl reload apparmor
fi


# Antigravity CLI
[ -s /tmp/antigravity_cli_install.sh ] ||
run curl -o /tmp/antigravity_cli_install.sh \
  -fsSL https://antigravity.google/cli/install.sh
chmod u-s,o+r /tmp/antigravity_cli_install.sh

sed -i /tmp/antigravity_cli_install.sh -e '/BINARY_PATH.*CUSTOM_DIR/s#DIR\".*#DIR\" --skip-aliases --skip-path || true#'

rm -f "/usr/local/bin/agy"
run bash /tmp/antigravity_cli_install.sh --dir /usr/local/bin



# git-delta   ref. https://github.com/dandavison/delta/releases
[ -s /tmp/git-delta.deb ] ||
run curl -o /tmp/git-delta.deb \
  -fsSL https://github.com/dandavison/delta/releases/download/0.18.2/git-delta_0.18.2_amd64.deb
run apt install -y /tmp/git-delta.deb



# markdown-reader (markdown-tui-explorer)   ref. https://github.com/leboiko/markdown-reader/releases
MDR_VER=1.34.70
[ -s /tmp/markdown-reader.tar.gz ] ||
run curl -o /tmp/markdown-reader.tar.gz \
  -fsSL https://github.com/leboiko/markdown-reader/releases/download/v${MDR_VER}/markdown-reader-x86_64-unknown-linux-gnu.tar.gz
run tar -xzf /tmp/markdown-reader.tar.gz -C /tmp
run install -m 0755 /tmp/markdown-reader-${MDR_VER}-x86_64-unknown-linux-gnu/markdown-reader /usr/local/bin/markdown-reader



echo -e "${COLOR_GREEN}"
echo "----------------------------------------------------------------------------------------------------------------"
echo "        Setup the user environment: root"
echo "----------------------------------------------------------------------------------------------------------------"
echo -e "${COLOR_CLEAR}"

copy nodejs_clean_installer         /usr/local/bin/nodejs_clean_installer
copy setup_user_environment         /usr/local/bin/setup_user_environment
copy share_ssh_x11forwarding        ~/.share_ssh_x11forwarding

nodejs_clean_installer

run sed -i ~/.bashrc \
    -e '/export\ LS_OPTIONS/s/^\ *#*\ *//' \
    -e 's/xterm-color[^\)]*/xterm-color\|\*-256color/' \
    -e '/eval\ \"\`dircolor/s/^\ *#*\ *//' \
    -e '/share_ssh_x11forwarding/d'

setup_user_environment

run echo "~/.share_ssh_x11forwarding" '>>' ~/.bashrc



LOGIN_USER="$(logname 2>/dev/null)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name

if [ -n "$LOGIN_USER" ]; then
    echo -e "${COLOR_GREEN}"
    echo "----------------------------------------------------------------------------------------------------------------"
    echo "        Setup the user environment: ${LOGIN_USER}"
    echo "----------------------------------------------------------------------------------------------------------------"
    echo -e "${COLOR_CLEAR}"

    sudo -i -u $LOGIN_USER nodejs_clean_installer
    sudo -i -u $LOGIN_USER setup_user_environment
fi



echo -e "${COLOR_GREEN}"
echo '----------------------------------------------------------------------------------------------------------------'
echo '        WSL2 specific tweaking'
echo '----------------------------------------------------------------------------------------------------------------'
echo -e "${COLOR_CLEAR}"

# Resolve mDNS .local addresses by Windows host's DNS
# Note that this is required for networkingMode=NAT
NSSWITCH="/etc/nsswitch.conf"
[ -s "${NSSWITCH}.org" ] ||
run install "${NSSWITCH}" "${NSSWITCH}.org"

run "sed -i -e '/^hosts:/s/mdns4_minimal .*dns/dns mdns4_minimal/' $NSSWITCH"


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
