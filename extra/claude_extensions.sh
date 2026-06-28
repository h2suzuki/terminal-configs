#!/bin/bash

# Installs Claude Code extensions as an opt-in step after the base setup.
#
#   Skills/hooks        Guardrail skills + hooks into /etc/claude-code/ and ~/.claude/
#
#   Security plugin     Anthropic official plugin for a security gate
#
#   Figma plugin        Claude-to-figma plugin (a remote MCP + skills)
#
#   Agent-browser CLI   Vercel Labs CLI + Claude Code skill
#   Playwright MCP      Microsoft playwright/mcp (stdio; reuses the system Chrome, headless)
#
#   Codex plugin & MCP  OpenAI codex-plugin-cc and MCP setup (codex itself is MCP)
#   Codegraph MCP       Tree-sitter + SQLite MCP (stdio)
#
#   Cloud-run MCP       Google Cloud Run MCP (stdio; deploy/logs)
#   Toolbox MCP         Google database access MCP (stdio; BigQuery prebuilt)
#   Vercel CLI          Vercel CLI + Vercel MCP (remote http) + Vercel plugin (skills/commands)


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



. $HOME/.nvm/nvm.sh


# Deploy the user hooks
copy claude_user-hooks/check_commit_author.py    ~/.claude/hooks/check_commit_author.py
copy claude_user-hooks/check_push_prompting.py   ~/.claude/hooks/check_push_prompting.py
copy claude_user-hooks/memory_surface.py         ~/.claude/hooks/memory_surface.py
copy claude_user-hooks/subagent_gate_suggest.py  ~/.claude/hooks/subagent_gate_suggest.py

run claude_user_settings inject - < "/etc/claude-code/skel/extensions.json"



# Shared memory-RAG store for root + login user (setgid → login-group; hooks set umask 0o002 → group-writable).
# Model DB is user-independent so build it here; the FTS index is rebuilt from the login user's memory below.
run install --directory --mode 2775 --owner root --group ${LOGIN_GROUP:-root} /var/lib/claude-rag-memory
copy claude_memory_rag_builder                  /usr/local/bin/claude_memory_rag_builder -m 0755
run claude_memory_rag_builder


# Deploy the user skills
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
run "claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated"

# Codex plugin (raw mcp-server は登録しない: 委譲は /codex:rescue 一本)
run claude plugin marketplace add openai/codex-plugin-cc
run claude plugin install codex@openai-codex

claude mcp remove codex --scope user

# System-wide codex config: write-capable non-interactive (rescue の network + 対話 TUI に効く)
copy codex_config.toml                          /etc/codex/config.toml -m 0644

# CodeGraph MCP
claude mcp remove codegraph --scope user
run npm install -g @colbymchenry/codegraph
run "claude mcp add codegraph --scope user -- codegraph serve --mcp"

# Cloud Run MCP
claude mcp remove cloud-run --scope user
run "claude mcp add cloud-run --scope user -- npx -y @google-cloud/cloud-run-mcp"

# Toolbox MCP (launcher derives BIGQUERY_PROJECT, required at startup, from gcloud)
copy toolbox_bigquery_mcp                       /usr/local/bin/toolbox_bigquery_mcp -m 0755
claude mcp remove toolbox --scope user
run "claude mcp add toolbox --scope user -- toolbox_bigquery_mcp"

# Vercel CLI + plugin (MCP comes from the plugin)
run npm install -g @vercel/vc-native
run CI=1 npx -y plugins add vercel/vercel-plugin --yes
run claude plugin update vercel@claude-plugins-official


run claude mcp list
run claude plugin list


# Resolve the login user up-front (shared memory store is group-owned by their primary group).
LOGIN_USER="$(logname 2>/dev/null)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"
if [ -n "$LOGIN_USER" ]; then
    LOGIN_GROUP="$(id -gn "$LOGIN_USER")"
    LOGIN_HOME="$(getent passwd "$LOGIN_USER" | cut -d: -f6)"
    [ -n "$LOGIN_HOME" ] || LOGIN_HOME="/home/$LOGIN_USER"
fi

if [ -n "$LOGIN_USER" ]; then          # resolved up-front near the shared-store setup

    # Pre-create user-owned parents — `install -D/-d --owner` only owners the final component.
    run install --mode 0755 --owner $LOGIN_USER --group $LOGIN_GROUP --directory $LOGIN_HOME/.claude
    run install --mode 0755 --owner $LOGIN_USER --group $LOGIN_GROUP --directory $LOGIN_HOME/.claude/hooks
    run install --mode 0755 --owner $LOGIN_USER --group $LOGIN_GROUP --directory $LOGIN_HOME/.claude/skills

    # Deploy $LOGIN_HOME/.claude/ hooks
    copy claude_user-hooks/check_commit_author.py    $LOGIN_HOME/.claude/hooks/check_commit_author.py  --owner $LOGIN_USER --group $LOGIN_GROUP
    copy claude_user-hooks/check_push_prompting.py   $LOGIN_HOME/.claude/hooks/check_push_prompting.py --owner $LOGIN_USER --group $LOGIN_GROUP
    copy claude_user-hooks/memory_surface.py         $LOGIN_HOME/.claude/hooks/memory_surface.py       --owner $LOGIN_USER --group $LOGIN_GROUP
    copy claude_user-hooks/subagent_gate_suggest.py  $LOGIN_HOME/.claude/hooks/subagent_gate_suggest.py --owner $LOGIN_USER --group $LOGIN_GROUP
    # Feed the fragment on stdin: root opens it here, so the demoted user needs no read access
    run sudo -i -u $LOGIN_USER claude_user_settings inject - < "$TOP_DIR/files/claude_user-extensions.json"

    # Memory-surface hybrid RAG: populate the shared FTS index from the login user's memory
    run install --mode 0755 --owner $LOGIN_USER --group $LOGIN_GROUP --directory $LOGIN_HOME/.claude/hooks/state
    run sudo -i -u $LOGIN_USER bash -c '"~/.claude/hooks/memory_surface.py --rebuild"'

    # Deploy the user skills (dir absent when no user skills exist)
    pushd "$TOP_DIR"/files/claude_user-skills >/dev/null
    for skill_dir in */; do
        [ -d "$skill_dir" ] || continue
        copy_dir "claude_user-skills/$skill_dir" $LOGIN_HOME/.claude/skills/$skill_dir --owner $LOGIN_USER --group $LOGIN_GROUP
    done
    popd >/dev/null

    # Symlink the managed skills
    run install --directory $LOGIN_HOME/.claude/skills/ --owner $LOGIN_USER --group $LOGIN_GROUP
    for skill_dir in /etc/claude-code/skills/*; do
        [ -d "$skill_dir" ] || continue
        rm -rf $LOGIN_HOME/.claude/skills/"${skill_dir#/etc/claude-code/skills/}"
        run ln -sfn "$skill_dir" $LOGIN_HOME/.claude/skills/
        run chown -h $LOGIN_USER:$LOGIN_GROUP $LOGIN_HOME/.claude/skills/"${skill_dir#/etc/claude-code/skills/}"
    done
    # Prune dangling symlinks (skills renamed/removed since a prior run)
    run find $LOGIN_HOME/.claude/skills/ -maxdepth 1 -xtype l -delete

    # Seed the registry first: never-launched users have no marketplace, so bare `update` fails (re-add is idempotent, exit 0)
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin marketplace add anthropics/claude-plugins-official"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin marketplace update claude-plugins-official"'

    # LSP servers
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; npm install -g typescript-language-server typescript"'
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; npm install -g pyright"'
    # run sudo -i -u $LOGIN_USER bash -c '"go install golang.org/x/tools/gopls@latest"'
    # run sudo -i -u $LOGIN_USER bash -c '"rustup component add rust-analyzer"'

    # LSP server plugins
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin install typescript-lsp@claude-plugins-official"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin install pyright-lsp@claude-plugins-official"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin install clangd-lsp@claude-plugins-official"'
    #run sudo -i -u $LOGIN_USER bash -c '"claude plugin install gopls-lsp@claude-plugins-official"'
    #run sudo -i -u $LOGIN_USER bash -c '"claude plugin install rust-analyzer-lsp@claude-plugins-official"'

    # Security-guidance plugin (disabled by default)
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin install security-guidance@claude-plugins-official"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin disable security-guidance@claude-plugins-official"'

    # Figma plugin
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin install figma@claude-plugins-official"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin update figma@claude-plugins-official"'

    # Agent-browser
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; CI=1 npm install -g agent-browser"'
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; agent-browser install --with-deps"'
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes"'

    # Playwright MCP
    sudo -i -u $LOGIN_USER bash -c "claude mcp remove playwright --scope user"
    run sudo -i -u $LOGIN_USER bash -c '"claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated"'

    # Codex plugin (raw mcp-server は登録しない: 委譲は /codex:rescue 一本)
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin marketplace add openai/codex-plugin-cc"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin install codex@openai-codex"'

    sudo -i -u $LOGIN_USER bash -c "claude mcp remove codex --scope user"

    # CodeGraph MCP
    sudo -i -u $LOGIN_USER bash -c "claude mcp remove codegraph --scope user"
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; npm install -g @colbymchenry/codegraph"'
    run sudo -i -u $LOGIN_USER bash -c '"claude mcp add codegraph --scope user -- codegraph serve --mcp"'

    # Cloud Run MCP
    sudo -i -u $LOGIN_USER bash -c "claude mcp remove cloud-run --scope user"
    run sudo -i -u $LOGIN_USER bash -c '"claude mcp add cloud-run --scope user -- npx -y @google-cloud/cloud-run-mcp"'

    # Toolbox MCP
    sudo -i -u $LOGIN_USER bash -c "claude mcp remove toolbox --scope user"
    run sudo -i -u $LOGIN_USER bash -c '"claude mcp add toolbox --scope user -- toolbox_bigquery_mcp"'

    # Vercel CLI
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; npm install -g @vercel/vc-native"'
    run sudo -i -u $LOGIN_USER bash -c '". \$HOME/.nvm/nvm.sh; CI=1 npx -y plugins add vercel/vercel-plugin --yes"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin update vercel@claude-plugins-official"'

    run sudo -i -u $LOGIN_USER bash -c '"claude mcp list"'
    run sudo -i -u $LOGIN_USER bash -c '"claude plugin list"'

else
    echo -e "${COLOR_RED}No login user found... omitting to install extensions for the login user${COLOR_CLEAR}"
    echo ""
fi


echo ''
echo '*** Post-install login -- type /mcp and /doctor in Claude Code console for OAuth2 ***'
echo ''

# END
