#!/bin/bash

# Installs Claude Code extensions as an opt-in step after the base setup.

[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}


# Put $HOME/.local/bin on PATH (claude often lives there) so the checks below resolve
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac


command -v tty      >/dev/null || { echo "Cannot find tty";         exit 1; }
command -v readlink >/dev/null || { echo "Cannot find readlink";    exit 1; }
command -v cmp      >/dev/null || { echo "Cannot find cmp";         exit 1; }
command -v claude   >/dev/null || { echo "Cannot find claude";      exit 1; }


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



copy_dir()
{
    DNAME=files/${1%/}
    DST=${2%/}
    shift 2

    # Pick up --owner from "$@" so we can chown -R after cp (cp -r ignores --owner).
    OWNER=
    prev=
    for a in "$@"; do
        [ "$prev" = "--owner" ] && { OWNER=$a; break; }
        case "$a" in --owner=*) OWNER=${a#--owner=}; break;; esac
        prev=$a
    done

    [ -d "$DST" ] || { rm -rf "$DST"; run install --directory "$@" "$DST"; }
    rm -rf "$DST"/*
    for child in "$TOP_DIR/$DNAME"/*; do
        [ -e "$child" ] || continue   # empty source dir: glob stays literal
        [ "${child##*/}" = __pycache__ ] && continue
        run cp -r "$child" "$DST/"
    done
    [ -n "$OWNER" ] && run chown -R "$OWNER:" "$DST"
}



# Deploy the user hooks
run install --directory ~/.claude/hooks/
run install /etc/claude-code/skel/hooks/check_commit_author.py      ~/.claude/hooks/check_commit_author.py
run install /etc/claude-code/skel/hooks/check_push_prompting.py     ~/.claude/hooks/check_push_prompting.py
run install /etc/claude-code/skel/hooks/memory_surface.py           ~/.claude/hooks/memory_surface.py
run install /etc/claude-code/skel/hooks/subagent_gate_suggest.py    ~/.claude/hooks/subagent_gate_suggest.py

run claude_user_settings inject - < "/etc/claude-code/skel/extensions.json"

run install --directory ~/.claude/skills/

pushd "$TOP_DIR"/files/claude_user-skills >/dev/null
for skill_dir in */; do
    [ -d "$skill_dir" ] || continue
    copy_dir "claude_user-skills/$skill_dir" ~/.claude/skills/$skill_dir
done
popd >/dev/null


# Symlink the managed skills
run install --directory ~/.claude/skills/
for skill_dir in /etc/claude-code/skills/*; do
    [ -d "$skill_dir" ] || continue
    rm -rf ~/.claude/skills/"${skill_dir#/etc/claude-code/skills/}"
    run ln -sfn "$skill_dir" ~/.claude/skills/
done

# Prune dangling symlinks (skills renamed/removed since a prior run)
run find ~/.claude/skills/ -maxdepth 1 -xtype l -delete


run install --mode 2775 --owner root --group ${LOGIN_GROUP:-root} --directory /var/lib/claude-rag-memory
run install --mode 0755 --owner $LOGIN_USER --group $LOGIN_GROUP --directory ~/.claude/hooks/state

run claude_memory_rag_builder

run ~/.claude/hooks/memory_surface.py --rebuild



. $HOME/.nvm/nvm.sh


# Seed the registry first: never-launched users have no marketplace, so bare `update` fails (re-add is idempotent, exit 0)
run claude plugin marketplace add anthropics/claude-plugins-official
run claude plugin marketplace update claude-plugins-official

# LSP servers
run npm install -g typescript-language-server typescript
run npm install -g pyright
run apt install -y --no-install-recommends clangd
# run go install golang.org/x/tools/gopls@latest
# run rustup component add rust-analyzer

# LSP server plugins
run claude plugin install typescript-lsp@claude-plugins-official
run claude plugin install pyright-lsp@claude-plugins-official
run claude plugin install clangd-lsp@claude-plugins-official
#run claude plugin install gopls-lsp@claude-plugins-official
#run claude plugin install rust-analyzer-lsp@claude-plugins-official

# Security-guidance plugin (disabled by default)
run claude plugin install security-guidance@claude-plugins-official
run claude plugin disable security-guidance@claude-plugins-official

# Figma plugin
run claude plugin install figma@claude-plugins-official
run claude plugin update figma@claude-plugins-official

# Agent-browser
run CI=1 npm install -g agent-browser
run agent-browser install --with-deps
run npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes

# Playwright MCP
claude mcp remove playwright --scope user
run claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated

# Codex plugin
run claude plugin marketplace add openai/codex-plugin-cc
run claude plugin install codex@openai-codex

claude mcp remove codex --scope user    # Codex MCP is supersedded by Codex plugin

# CodeGraph MCP
claude mcp remove codegraph --scope user
run npm install -g @colbymchenry/codegraph
run claude mcp add codegraph --scope user -- codegraph serve --mcp

# Cloud Run MCP
claude mcp remove cloud-run --scope user
run claude mcp add cloud-run --scope user -- npx -y @google-cloud/cloud-run-mcp

# Toolbox MCP (launcher derives BIGQUERY_PROJECT, required at startup, from gcloud)
claude mcp remove toolbox --scope user
run claude mcp add toolbox --scope user -- toolbox_bigquery_mcp

# Vercel CLI + plugin (MCP comes from the plugin)
run npm install -g @vercel/vc-native
run CI=1 npx -y plugins add vercel/vercel-plugin --yes
run claude plugin update vercel@claude-plugins-official


run claude mcp list
run claude plugin list


echo ''
echo '*** Post-install login -- type /mcp and /doctor in Claude Code console for OAuth2 ***'
echo ''

# END
