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



[ -e ~/.bashrc ] &&
run sed -i ~/.bashrc \
    -e '/export\ LS_OPTIONS/s/^\ *#*\ *//' \
    -e 's/xterm-color[^\)]*/xterm-color\|\*-256color/' \
    -e '/eval\ \"\`dircolor/s/^\ *#*\ *//' \
    -e '/alias\ ls=/s/^\ *#*\ *//' \
    -e '/^alias\ ls=/s/ls\ \$LS_OPTIONS/ls\ --group-directories-first\ \$LS_OPTIONS/' \
    -e '/alias\ tree=/d' \
    -e '/alias\ pushd=/d' \
    -e '/alias\ popd=/d' \
    -e '/alias\ dirs=/d' \
    -e '/alias\ diffy=/d' \
    -e '/alias\ rg=/d' \
    -e '/alias\ node-x=/d' \
    -e '/grip\(\)\ /d' \
    -e '/export\ EDITOR=/d' \
    -e '/export\ VISUAL=/d' \
    -e '/export\ BROWSER=/d' \
    -e '/export\ PATH=.*\.local.bin:\$PATH/d' \
    -e '/share_ssh_x11forwarding/d' \
    -e '/NVM_DIR/d'

run echo "alias tree=\\'tree --dirsfirst --noreport -I __pycache__\\'" '>>' ~/.bashrc
run echo "alias pushd=\\'pushd \\>/dev/null\\'" '>>' ~/.bashrc
run echo "alias popd=\\'popd \\>/dev/null\\'" '>>' ~/.bashrc
run echo "alias dirs=\\'dirs -v\\'" '>>' ~/.bashrc
run echo "alias diffy=\\'git diff --no-index\\'" '>>' ~/.bashrc
run echo "alias rg=\\'rg --sort path --smart-case\\'" '>>' ~/.bashrc
run echo "alias node-x=\\'NODE_DEBUG=module,fs,net node\\'" '>>' ~/.bashrc
run echo 'grip\(\) \{ rg --sort path --smart-case --json -C 2 \"\$@\" \| delta\; \}' '>>' ~/.bashrc
run echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' '>>' ~/.bashrc


[ -d /etc/sudoers.d ] &&
copy sudoers    /etc/sudoers.d/nopasswd
copy gitconfig  /etc/gitconfig
copy inputrc    ~/.inputrc
copy share_ssh_x11forwarding  ~/.share_ssh_x11forwarding


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
vdpau-driver-all va-driver-all expect


# PulseAudio server to proxy audio streaming
# from 24713/tcp to WSLg's PulseAudio server
run apt install -y --no-install-recommends \
pulseaudio pulseaudio-utils alsa-utils

copy --nobackup pulseaudio-proxy.pa         /etc/pulse/proxy.pa
copy --nobackup pulseaudio-proxy.service    /etc/systemd/system/pulseaudio-proxy.service

# HomeDir is hard-coded in PulseAudio (a kind of bug IMHO)
run usermod -d /var/run/pulse pulse

run systemctl daemon-reload
run systemctl start pulseaudio-proxy.service
run systemctl enable pulseaudio-proxy.service

# To test the audio facility, set either
#
#   PULSE_SERVER=unix:/mnt/wslg/PulseServer   for WSLg
# or
#   PULSE_SERVER=tcp:localhost:24713          for 24713/tcp
#
# then
#   paplay /usr/share/sounds/alsa/Front_Center.wav



# UV python package manager
[ -s /tmp/uv_install.sh ] ||
run curl -o /tmp/uv_install.sh \
  -fsSL https://astral.sh/uv/install.sh
chmod u-s,o+r /tmp/uv_install.sh

export UV_INSTALL_DIR=/usr/bin
export UV_NO_PROGRESS=true
run bash /tmp/uv_install.sh
run uv self update


# git-delta   ref. https://github.com/dandavison/delta/releases
[ -s /tmp/git-delta.deb ] ||
run curl -o /tmp/git-delta.deb \
  -fsSL https://github.com/dandavison/delta/releases/download/0.18.2/git-delta_0.18.2_amd64.deb
run apt install -y /tmp/git-delta.deb


# mDNS to resolve mDNS .local from Windows host
run apt install -y --no-install-recommends \
avahi-utils avahi-daemon avahi-autoipd libnss-mdns


# OpenSSH
run apt install -y --no-install-recommends \
openssh-server openssh-client


# Docker
run apt remove -y \
docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc

[ -s /tmp/get-docker.sh ] ||
run curl -o /tmp/get-docker.sh -fsSL https://get.docker.com
run sed -i /tmp/get-docker.sh -e 's/sleep\ 20/:/'
run bash /tmp/get-docker.sh

run systemctl enable docker
run systemctl start docker

run docker run --rm hello-world


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


# Voicevox Core and Pasimple for PulseAudio Python binding
VV_VER=0.16.4
VV_BIN_DIR=/usr/local/bin
VV_LIB_DIR=/usr/lib/voicevox-core

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

expect -c '
# GitHub login can relax the ratelimit restriction posed by this downloader
set env(GH_TOKEN) '"$(gh auth token)"'
set timeout 120

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
expect eof
'

run [ -s $VV_LIB_DIR/dict/open_jtalk_dic_utf*/sys.dic ]
run [ -s $VV_LIB_DIR/models/vvms/0.vvm ]
run [ -s $VV_LIB_DIR/onnxruntime/lib//libvoicevox_onnxruntime.so* ]

copy --nobackup voicevox_paplay ${VV_BIN_DIR}/voicevox_paplay


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

copy --nobackup claude_system-CLAUDE.md         /etc/claude-code/CLAUDE.md
copy --nobackup claude_statusline.sh            /etc/claude-code/statusline.sh -m 0755
copy --nobackup claude_system_hooks/claude-md-lint.sh \
                                                /etc/claude-code/claude-md-lint.sh -m 0755
copy --nobackup claude_system_hooks/read_before_edit.py \
                                                /etc/claude-code/hooks/read_before_edit.py -m 0755
copy --nobackup claude_user_hooks/avoid_cd.py   /etc/claude-code/hooks/avoid_cd.py -m 0755
copy --nobackup claude_user_hooks/check_commit_author.py \
                                                /etc/claude-code/hooks/check_commit_author.py -m 0755
copy --nobackup claude_user_hooks/check_commit_format.py \
                                                /etc/claude-code/hooks/check_commit_format.py -m 0755
copy --nobackup claude_user_hooks/detect_cwd_pollution.py \
                                                /etc/claude-code/hooks/detect_cwd_pollution.py -m 0755
copy --nobackup voicevox_claude_alerts          /usr/local/bin/voicevox_claude_alerts -m 0755
copy --nobackup claude_settings.json            ~/.claude/settings.json
#copy --nobackup claude_user-CLAUDE.md           ~/.claude/CLAUDE.md
copy --nobackup claude_system_skills/claude-md-lint.md \
                                                /etc/claude-code/claude-md-lint.md
copy --nobackup claude_system_skills/bash-writing-rules.md \
                                                /etc/claude-code/bash-writing-rules.md
copy --nobackup claude_system_skills/verbalize-before-action.md \
                                                /etc/claude-code/verbalize-before-action.md
copy --nobackup claude_system_skills/scope-mismatch-detector.md \
                                                /etc/claude-code/scope-mismatch-detector.md
copy --nobackup claude_system_skills/subagent-gate.md \
                                                /etc/claude-code/subagent-gate.md
copy --nobackup claude_system_skills/debug-workflow.md \
                                                /etc/claude-code/debug-workflow.md
copy --nobackup claude_system_skills/lost-track-recover.md \
                                                /etc/claude-code/lost-track-recover.md
copy --nobackup claude_system_skills/document-editor.md \
                                                /etc/claude-code/document-editor.md
copy --nobackup claude_user_skills/verify-spec-before-dismissal.md \
                                                /etc/claude-code/verify-spec-before-dismissal.md
copy --nobackup claude_user_skills/verify-before-asserting.md \
                                                /etc/claude-code/verify-before-asserting.md
copy --nobackup claude_user_skills/no-routing-questions.md \
                                                /etc/claude-code/no-routing-questions.md
copy --nobackup claude_user_skills/no-redundant-design-litigation.md \
                                                /etc/claude-code/no-redundant-design-litigation.md
copy --nobackup claude_user_skills/commit-discipline.md \
                                                /etc/claude-code/commit-discipline.md
copy --nobackup claude_user_skills/claude-code-guide.md \
                                                /etc/claude-code/claude-code-guide.md
copy --nobackup claude_user_skills/memory-routing.md \
                                                /etc/claude-code/memory-routing.md

run install -d ~/.claude/skills/claude-md-lint
run install -d ~/.claude/skills/bash-writing-rules
run install -d ~/.claude/skills/verbalize-before-action
run install -d ~/.claude/skills/scope-mismatch-detector
run install -d ~/.claude/skills/subagent-gate
run install -d ~/.claude/skills/debug-workflow
run install -d ~/.claude/skills/lost-track-recover
run install -d ~/.claude/skills/document-editor
run install -d ~/.claude/skills/verify-spec-before-dismissal
run install -d ~/.claude/skills/verify-before-asserting
run install -d ~/.claude/skills/no-routing-questions
run install -d ~/.claude/skills/no-redundant-design-litigation
run install -d ~/.claude/skills/commit-discipline
run install -d ~/.claude/skills/claude-code-guide
run install -d ~/.claude/skills/memory-routing
run ln -sfn /etc/claude-code/claude-md-lint.md  ~/.claude/skills/claude-md-lint/SKILL.md
run ln -sfn /etc/claude-code/bash-writing-rules.md ~/.claude/skills/bash-writing-rules/SKILL.md
run ln -sfn /etc/claude-code/verbalize-before-action.md ~/.claude/skills/verbalize-before-action/SKILL.md
run ln -sfn /etc/claude-code/scope-mismatch-detector.md ~/.claude/skills/scope-mismatch-detector/SKILL.md
run ln -sfn /etc/claude-code/subagent-gate.md ~/.claude/skills/subagent-gate/SKILL.md
run ln -sfn /etc/claude-code/debug-workflow.md ~/.claude/skills/debug-workflow/SKILL.md
run ln -sfn /etc/claude-code/lost-track-recover.md ~/.claude/skills/lost-track-recover/SKILL.md
run ln -sfn /etc/claude-code/document-editor.md ~/.claude/skills/document-editor/SKILL.md
run ln -sfn /etc/claude-code/verify-spec-before-dismissal.md ~/.claude/skills/verify-spec-before-dismissal/SKILL.md
run ln -sfn /etc/claude-code/verify-before-asserting.md ~/.claude/skills/verify-before-asserting/SKILL.md
run ln -sfn /etc/claude-code/no-routing-questions.md ~/.claude/skills/no-routing-questions/SKILL.md
run ln -sfn /etc/claude-code/no-redundant-design-litigation.md ~/.claude/skills/no-redundant-design-litigation/SKILL.md
run ln -sfn /etc/claude-code/commit-discipline.md ~/.claude/skills/commit-discipline/SKILL.md
run ln -sfn /etc/claude-code/claude-code-guide.md ~/.claude/skills/claude-code-guide/SKILL.md
run ln -sfn /etc/claude-code/memory-routing.md ~/.claude/skills/memory-routing/SKILL.md

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
run echo 'export EDITOR=\"$EDITOR\"' '>>' ~/.bashrc
run echo 'export VISUAL=\"$EDITOR\"' '>>' ~/.bashrc

BROWSER="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe start"
run echo 'export BROWSER=\"$BROWSER\"' '>>' ~/.bashrc



# Login user settings
#  1. Change the color of the prompt for the login user: green(32m) -> purple(35m)
#  2. Set EDITOR, VISUAL, and BROWSER environment variables
#  3. Autoload ~/.nvm/nvm.sh
LOGIN_USER="$(logname)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name
if [ -n "$LOGIN_USER" ]; then
    BASHRC="~$LOGIN_USER/.bashrc"
    run [ -s $BASHRC ]
    run sed -i $BASHRC \
            -e '/^\ *PS1=/s/32m/35m/' \
            -e '/alias\ tree=/d' \
            -e '/alias\ pushd=/d' \
            -e '/alias\ popd=/d' \
            -e '/alias\ dirs=/d' \
            -e '/alias\ diffy=/d' \
            -e '/alias\ rg=/d' \
            -e '/alias\ node-x=/d' \
            -e '/grip\(\)\ /d' \
            -e '/export\ EDITOR=/d' \
            -e '/export\ VISUAL=/d' \
            -e '/export\ BROWSER=/d' \
            -e '/export\ PATH=.*\.local.bin:\$PATH/d' \
            -e '/NVM_DIR/d'

    # Handy aliases
    run echo "alias tree=\\'tree --dirsfirst --noreport -I __pycache__\\'" '>>' $BASHRC
    run echo "alias pushd=\\'pushd \\>/dev/null\\'" '>>' $BASHRC
    run echo "alias popd=\\'popd \\>/dev/null\\'" '>>' $BASHRC
    run echo "alias dirs=\\'dirs -v\\'" '>>' $BASHRC
    run echo "alias diffy=\\'git diff --no-index\\'" '>>' $BASHRC
    run echo "alias rg=\\'rg --sort path --smart-case\\'" '>>' $BASHRC
    run echo "alias node-x=\\'NODE_DEBUG=module,fs,net node\\'" '>>' $BASHRC
    run echo 'grip\(\) \{ rg --sort path --smart-case --json -C 2 \"\$@\" \| delta\; \}' '>>' $BASHRC

    # Set the default editor as neovim
    run echo 'export EDITOR=\"$EDITOR\"' '>>' $BASHRC
    run echo 'export VISUAL=\"$EDITOR\"' '>>' $BASHRC

    # Set the default browser as the one on the Windows host
    run echo 'export BROWSER=\"$BROWSER\"' '>>' $BASHRC

    run install --mode 0755 --owner $LOGIN_USER --directory ~$LOGIN_USER/.nvm
    run install --mode 0644 --owner $LOGIN_USER "$HOME/.nvm/nvm.sh" ~$LOGIN_USER/.nvm/nvm.sh

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
    copy --nobackup claude_settings.json ~$LOGIN_USER/.claude/settings.json --owner $LOGIN_USER
    #copy --nobackup claude_user-CLAUDE.md ~$LOGIN_USER/.claude/CLAUDE.md --owner $LOGIN_USER
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/claude-md-lint
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/bash-writing-rules
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/verbalize-before-action
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/scope-mismatch-detector
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/subagent-gate
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/debug-workflow
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/lost-track-recover
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/document-editor
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/verify-spec-before-dismissal
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/verify-before-asserting
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/no-routing-questions
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/no-redundant-design-litigation
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/commit-discipline
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/claude-code-guide
    run install -d -o $LOGIN_USER ~$LOGIN_USER/.claude/skills/memory-routing
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/claude-md-lint.md \
                                         ~$LOGIN_USER/.claude/skills/claude-md-lint/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/bash-writing-rules.md \
                                         ~$LOGIN_USER/.claude/skills/bash-writing-rules/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/verbalize-before-action.md \
                                         ~$LOGIN_USER/.claude/skills/verbalize-before-action/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/scope-mismatch-detector.md \
                                         ~$LOGIN_USER/.claude/skills/scope-mismatch-detector/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/subagent-gate.md \
                                         ~$LOGIN_USER/.claude/skills/subagent-gate/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/debug-workflow.md \
                                         ~$LOGIN_USER/.claude/skills/debug-workflow/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/lost-track-recover.md \
                                         ~$LOGIN_USER/.claude/skills/lost-track-recover/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/document-editor.md \
                                         ~$LOGIN_USER/.claude/skills/document-editor/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/verify-spec-before-dismissal.md \
                                         ~$LOGIN_USER/.claude/skills/verify-spec-before-dismissal/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/verify-before-asserting.md \
                                         ~$LOGIN_USER/.claude/skills/verify-before-asserting/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/no-routing-questions.md \
                                         ~$LOGIN_USER/.claude/skills/no-routing-questions/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/no-redundant-design-litigation.md \
                                         ~$LOGIN_USER/.claude/skills/no-redundant-design-litigation/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/commit-discipline.md \
                                         ~$LOGIN_USER/.claude/skills/commit-discipline/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/claude-code-guide.md \
                                         ~$LOGIN_USER/.claude/skills/claude-code-guide/SKILL.md
    run sudo -i -u $LOGIN_USER ln -sfn /etc/claude-code/memory-routing.md \
                                         ~$LOGIN_USER/.claude/skills/memory-routing/SKILL.md

    run usermod -aG docker "$LOGIN_USER"

else
    echo -e "${COLOR_RED}No login user found... omitting to tweak ~/.bashrc${COLOR_CLEAR}"
    echo -e "${COLOR_RED}No login user found... omitting to include ~/.nvm/nvm.sh${COLOR_CLEAR}"
    echo ""
fi


# Append auto-loading of nvm.sh
run cat ">>" ~/.bashrc <<"EOF"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
EOF

run echo "~/.share_ssh_x11forwarding" '>>' ~/.bashrc


# Resolve mDNS .local addresses by Windows host's DNS
# Note that this is required for networkingMode=NAT
# --------
NSSWITCH="/etc/nsswitch.conf"
[ -s "${NSSWITCH}.org" ] ||
run install "${NSSWITCH}" "${NSSWITCH}.org"

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
