#!/bin/bash

# This script sets up a Debian 12 environment

command -v grep >/dev/null || {
    echo "Cannot find grep"
    exit 1
}
grep -Fqs "Debian GNU/Linux 12 " /etc/issue || {
    echo "This environment does not look like Debian 12"
    exit 1
}
[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}



command -v tty       >/dev/null || { echo "Cannot find tty";         exit 1; }
command -v readlink  >/dev/null || { echo "Cannot find readlink";    exit 1; }
command -v cmp       >/dev/null || { echo "Cannot find cmp";         exit 1; }


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


# uv/claude install into $HOME/.local/bin below; put it on PATH so later invocations resolve
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac


# curl is needed below; minimal images lack it and apt lists, so update first
command -v curl >/dev/null || {
    run apt update
    run apt install -y --no-install-recommends curl
}


[ -e ~/.bashrc ] &&
run sed -i ~/.bashrc \
    -e '/export\ LS_OPTIONS/s/^\ *#*\ *//' \
    -e 's/xterm-color[^\)]*/xterm-color\|\*-256color/' \
    -e '/eval\ \"\`dircolor/s/^\ *#*\ *//' \
    -e "/Terminal\ Config/d" \
    -e '/alias\ ls=/s/^\ *#*\ *//' \
    -e '/^alias\ ls=/s/ls\ \$LS_OPTIONS/ls\ --group-directories-first\ \$LS_OPTIONS/' \
    -e '/alias\ tree=/d' \
    -e '/alias\ pushd=/d' \
    -e '/alias\ popd=/d' \
    -e '/alias\ dirs=/d' \
    -e '/alias\ diffy=/d' \
    -e '/alias\ rg=/d' \
    -e '/alias\ node-x=/d' \
    -e '/alias\ mdr=/d' \
    -e '/grip\(\)\ /d' \
    -e '/export\ EDITOR=/d' \
    -e '/export\ VISUAL=/d' \
    -e '/export\ PATH=.*\.local.bin:\$PATH/d' \
    -e '/share_ssh_x11forwarding/d' \
    -e '/NVM_DIR/d'
run sed -i ~/.bashrc -e ':a' -e "'/^[[:space:]]*$/{\$d;N;ba'" -e '}'

run echo -e '\\n\\n# ---- Terminal Config ----' '>>' ~/.bashrc
run echo "alias tree=\\'tree --dirsfirst --noreport -I __pycache__\\'" '>>' ~/.bashrc
run echo "alias pushd=\\'pushd \\>/dev/null\\'" '>>' ~/.bashrc
run echo "alias popd=\\'popd \\>/dev/null\\'" '>>' ~/.bashrc
run echo "alias dirs=\\'dirs -v\\'" '>>' ~/.bashrc
run echo "alias diffy=\\'git diff --no-index\\'" '>>' ~/.bashrc
run echo "alias rg=\\'rg --sort path --smart-case\\'" '>>' ~/.bashrc
run echo "alias node-x=\\'NODE_DEBUG=module,fs,net node\\'" '>>' ~/.bashrc
run echo "alias mdr=markdown-reader" '>>' ~/.bashrc
run echo 'grip\(\) \{ rg --sort path --smart-case --json -C 2 \"\$@\" \| delta\; \}' '>>' ~/.bashrc
run echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' '>>' ~/.bashrc


[ -d /etc/sudoers.d ] &&
copy sudoers    /etc/sudoers.d/nopasswd -m 0440
copy gitconfig  /etc/gitconfig
copy inputrc    ~/.inputrc
copy share_ssh_x11forwarding  ~/.share_ssh_x11forwarding

copy ssh_keepalive.conf   /etc/ssh/ssh_config.d/10-keepalive.conf   -m 0644
copy sshd_keepalive.conf  /etc/ssh/sshd_config.d/10-keepalive.conf  -m 0644
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true

copy pulseaudio-forwarding.sh  /etc/profile.d/pulseaudio-forwarding.sh
run chmod 0644 /etc/profile.d/pulseaudio-forwarding.sh


# Neovim, Git / Git-LFS, tree, ripgrep, shellcheck
run apt update
run apt remove -y vim
run apt install -y --no-install-recommends \
neovim git git-lfs tree ripgrep shellcheck

copy --nobackup sysinit.vim /etc/xdg/nvim/sysinit.vim   # Neovim system-wide init file

run git lfs install --skip-repo


# img2sixel
run apt install -y --no-install-recommends \
libsixel-bin


# markdown-reader (markdown-tui-explorer)   ref. https://github.com/leboiko/markdown-reader/releases
MDR_VER=1.34.70
[ -s /tmp/markdown-reader.tar.gz ] ||
run curl -o /tmp/markdown-reader.tar.gz \
  -fsSL https://github.com/leboiko/markdown-reader/releases/download/v${MDR_VER}/markdown-reader-x86_64-unknown-linux-gnu.tar.gz
run tar -xzf /tmp/markdown-reader.tar.gz -C /tmp
run install -m 0755 /tmp/markdown-reader-${MDR_VER}-x86_64-unknown-linux-gnu/markdown-reader /usr/bin/markdown-reader


# X window forwarding and some small programs for testing
run apt install -y --no-install-recommends \
xauth jq x11-apps mesa-utils vulkan-tools wayland-utils \
vdpau-driver-all va-driver-all



# UV python package manager
[ -s /tmp/uv_install.sh ] ||
run curl -o /tmp/uv_install.sh \
  -fsSL https://astral.sh/uv/install.sh
chmod u-s,o+r /tmp/uv_install.sh

export UV_INSTALL_DIR=/usr/bin
export UV_NO_PROGRESS=true
run bash /tmp/uv_install.sh
run uv self update

# Install Python linter / formatter: ruff (system-wide, standalone installer)
[ -s /tmp/ruff_install.sh ] ||
run curl -o /tmp/ruff_install.sh \
  -fsSL https://astral.sh/ruff/install.sh
chmod u-s,o+r /tmp/ruff_install.sh

export RUFF_INSTALL_DIR=/usr/local/bin
export RUFF_NO_MODIFY_PATH=1
run bash /tmp/ruff_install.sh

# Install Python type checker: ty (system-wide, standalone installer)
[ -s /tmp/ty_install.sh ] ||
run curl -o /tmp/ty_install.sh \
  -fsSL https://astral.sh/ty/install.sh
chmod u-s,o+r /tmp/ty_install.sh

export TY_INSTALL_DIR=/usr/local/bin
export TY_NO_MODIFY_PATH=1
run bash /tmp/ty_install.sh


# git-delta   ref. https://github.com/dandavison/delta/releases
[ -s /tmp/git-delta.deb ] ||
run curl -o /tmp/git-delta.deb \
  -fsSL https://github.com/dandavison/delta/releases/download/0.18.2/git-delta_0.18.2_amd64.deb
run apt install -y /tmp/git-delta.deb


# Chrome
[ -s /tmp/google-chrome.deb ] ||
run curl -o /tmp/google-chrome.deb \
  -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
run apt install -y --fix-missing /tmp/google-chrome.deb
run apt install -y upower 'fonts-ipafont*' 'fonts-ipaexfont*' 'fonts-noto-color-emoji'

run systemctl enable upower
run systemctl start upower
run fc-cache -fv


# GitHub CLI
[ -s /tmp/githubcli.gpg ] ||
run curl -o /tmp/githubcli.gpg \
  -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg
[ -d /etc/apt/keyrings ] ||
run install --mode 0755 --directory /etc/apt/keyrings/
run install --mode 0644 /tmp/githubcli.gpg /etc/apt/keyrings/

cat > /etc/apt/sources.list.d/githubcli.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] \
https://cli.github.com/packages stable main
EOF

run apt update
run apt install -y gh


# Google Cloud CLI
[ -s /tmp/cloud.google.apt-key.gpg ] ||
run curl -o /tmp/cloud.google.apt-key.gpg \
  -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg
run gpg --yes --dearmor -o /tmp/cloud.google.gpg /tmp/cloud.google.apt-key.gpg
[ -d /etc/apt/keyrings ] ||
run install --mode 0755 --directory /etc/apt/keyrings/
run install --mode 0644 /tmp/cloud.google.gpg /etc/apt/keyrings/

cat > /etc/apt/sources.list.d/google-cloud-sdk.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/cloud.google.gpg] \
https://packages.cloud.google.com/apt cloud-sdk main
EOF

run apt update
run apt install -y google-cloud-cli


# Node.js
[ -s /tmp/nvm_install.sh ] ||
run curl -o /tmp/nvm_install.sh \
  -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh
run bash /tmp/nvm_install.sh

. $HOME/.nvm/nvm.sh
run nvm install --lts
run nvm current
run node -v
run npm -v


# Claude Code
npm uninstall -g @anthropic-ai/claude-code || true  # Old one

[ -s /tmp/claude_install.sh ] ||
run curl -o /tmp/claude_install.sh \
  -fsSL https://claude.ai/install.sh
chmod u-s,o+r /tmp/claude_install.sh
run bash /tmp/claude_install.sh

run uv tool install --force claude-monitor #--system --break-system-packages pasimple


# Construct /etc/claude-code/ from scratch
rm -rf /etc/claude-code/
copy --nobackup claude_statusline.sh                        /etc/claude-code/statusline.sh
copy --nobackup claude_managed-CLAUDE.md                    /etc/claude-code/CLAUDE.md
copy --nobackup claude_managed-settings.json                /etc/claude-code/managed-settings.json

# Populate ~/.claude/ (try to preserve the existing contents)
[ -e ~/.claude/CLAUDE.md ] ||
copy --nobackup claude_user-CLAUDE.md                       ~/.claude/CLAUDE.md
copy --nobackup claude_user-settings.json                   ~/.claude/settings.json

# Reset above orphaned the extras: ~/.claude/skills symlinks now dangle, hooks/*.py are stale
run "[ -d ~/.claude/skills ] && find ~/.claude/skills/ -maxdepth 1 -xtype l -delete || true"
run "rm -f ~/.claude/hooks/*.py"

# Warm up Claude Code
run "claude --model haiku --effort low --no-session-persistence --tools \"\" --setting-sources \"\" --disable-slash-commands -p hello || true"

# Tools used by Claude Code (bubblewrap/socat: Sandbox, poppler-utils: PDF reading)
run apt install -y --no-install-recommends \
bubblewrap socat poppler-utils


# Antigravity CLI (https://antigravity.google/)
[ -s /tmp/antigravity_cli_install.sh ] ||
run curl -o /tmp/antigravity_cli_install.sh \
  -fsSL https://antigravity.google/cli/install.sh
chmod u-s,o+r /tmp/antigravity_cli_install.sh

sed -i /tmp/antigravity_cli_install.sh -e '/BINARY_PATH.*CUSTOM_DIR/s#DIR\".*#DIR\" --skip-aliases --skip-path || true#'

rm -f "/usr/local/bin/agy"
run bash /tmp/antigravity_cli_install.sh --dir /usr/local/bin


# Codex CLI (https://github.com/openai/codex, needs Node.js 18+)
run npm install -g @openai/codex


# The current user settings
EDITOR="/usr/bin/nvim"
run echo '' '>>' ~/.bashrc
run echo 'export EDITOR=\"$EDITOR\"' '>>' ~/.bashrc
run echo 'export VISUAL=\"$EDITOR\"' '>>' ~/.bashrc



# Login user settings
#  1. Change the color of the prompt for the login user: green(32m) -> purple(35m)
#  2. Set EDITOR and VISUAL environment variables
#  3. Autoload ~/.nvm/nvm.sh
LOGIN_USER="$(logname)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name
if [ -n "$LOGIN_USER" ]; then
    LOGIN_GROUP="$(id -gn "$LOGIN_USER")"
    LOGIN_HOME="$(getent passwd "$LOGIN_USER" | cut -d: -f6)"
    [ -n "$LOGIN_HOME" ] || LOGIN_HOME="/home/$LOGIN_USER"
    BASHRC="$LOGIN_HOME/.bashrc"

    # files/sudoers grants NOPASSWD to a %group; make sure the login user is in it (secondary group).
    SUDO_GROUP="$(sed -n '/NOPASSWD:/s/^%\([^[:space:]]*\).*/\1/p' "$TOP_DIR/files/sudoers")"
    [ -n "$SUDO_GROUP" ] && run usermod -aG "$SUDO_GROUP" "$LOGIN_USER"
    run [ -s $BASHRC ]
    run sed -i $BASHRC \
            -e '/^\ *PS1=/s/32m/35m/' \
            -e "/Terminal\ Config/d" \
            -e '/alias\ tree=/d' \
            -e '/alias\ pushd=/d' \
            -e '/alias\ popd=/d' \
            -e '/alias\ dirs=/d' \
            -e '/alias\ diffy=/d' \
            -e '/alias\ rg=/d' \
            -e '/alias\ node-x=/d' \
            -e '/alias\ mdr=/d' \
            -e '/grip\(\)\ /d' \
            -e '/export\ EDITOR=/d' \
            -e '/export\ VISUAL=/d' \
            -e '/export\ PATH=.*\.local.bin:\$PATH/d' \
            -e '/NVM_DIR/d'
    run sed -i $BASHRC -e ':a' -e "'/^[[:space:]]*$/{\$d;N;ba'" -e '}'

    # Handy aliases
    run echo -e '\\n\\n# ---- Terminal Config ----' '>>' $BASHRC
    run echo "alias tree=\\'tree --dirsfirst --noreport -I __pycache__\\'" '>>' $BASHRC
    run echo "alias pushd=\\'pushd \\>/dev/null\\'" '>>' $BASHRC
    run echo "alias popd=\\'popd \\>/dev/null\\'" '>>' $BASHRC
    run echo "alias dirs=\\'dirs -v\\'" '>>' $BASHRC
    run echo "alias diffy=\\'git diff --no-index\\'" '>>' $BASHRC
    run echo "alias rg=\\'rg --sort path --smart-case\\'" '>>' $BASHRC
    run echo "alias node-x=\\'NODE_DEBUG=module,fs,net node\\'" '>>' $BASHRC
    run echo "alias mdr=markdown-reader" '>>' $BASHRC
    run echo 'grip\(\) \{ rg --sort path --smart-case --json -C 2 \"\$@\" \| delta\; \}' '>>' $BASHRC

    # Set the default editor as neovim
    run echo 'export EDITOR=\"$EDITOR\"' '>>' $BASHRC
    run echo 'export VISUAL=\"$EDITOR\"' '>>' $BASHRC

    run install --mode 0755 --owner $LOGIN_USER --group $LOGIN_GROUP --directory $LOGIN_HOME/.nvm
    run install --mode 0644 --owner $LOGIN_USER --group $LOGIN_GROUP "$HOME/.nvm/nvm.sh" $LOGIN_HOME/.nvm/nvm.sh

    # Append auto-loading of nvm.sh
    run cat ">>" $BASHRC <<"EOF"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
EOF

    run echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' '>>' $BASHRC

    run sudo -i -u $LOGIN_USER bash -i -c '"nvm install --lts"'    # nvm is a shell function.
    run sudo -i -u $LOGIN_USER bash -i -c '"npm uninstall -g @anthropic-ai/claude-code || true"'
    run sudo -i -u $LOGIN_USER bash -i -c '"bash /tmp/claude_install.sh"'
    run sudo -i -u $LOGIN_USER bash -i -c '"npm install -g @openai/codex"'

    # Pre-create user-owned parents — `install -D/-d --owner` only owners the final component.
    run install --mode 0755 --owner $LOGIN_USER --group $LOGIN_GROUP --directory $LOGIN_HOME/.claude

    # Populate $LOGIN_HOME/.claude/ (try to preserve the existing contents)
    [ -e $LOGIN_HOME/.claude/CLAUDE.md ] ||
    copy --nobackup claude_user-CLAUDE.md                       $LOGIN_HOME/.claude/CLAUDE.md --owner $LOGIN_USER --group $LOGIN_GROUP
    copy --nobackup claude_user-settings.json                   $LOGIN_HOME/.claude/settings.json --owner $LOGIN_USER --group $LOGIN_GROUP

    # Same stale-extras cleanup for the login user
    run "[ -d $LOGIN_HOME/.claude/skills ] && find $LOGIN_HOME/.claude/skills/ -maxdepth 1 -xtype l -delete || true"
    run "rm -f $LOGIN_HOME/.claude/hooks/*.py"

    run sudo -i -u $LOGIN_USER bash -i -c '"claude --model haiku --effort low --no-session-persistence --tools \"\" --setting-sources \"\" --disable-slash-commands -p hello || true"'

else
    echo -e "${COLOR_RED}No login user found... omitting to tweak ~/.bashrc${COLOR_CLEAR}"
    echo -e "${COLOR_RED}No login user found... omitting to include ~/.nvm/nvm.sh${COLOR_CLEAR}"
    echo ""
fi

run echo "~/.share_ssh_x11forwarding" '>>' ~/.bashrc


# END
