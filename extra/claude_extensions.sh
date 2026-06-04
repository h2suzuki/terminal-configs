#!/bin/bash

# Installs Claude Code extensions as an opt-in step after the base setup.
#
#   Figma plugin        Claude-to-figma plugin (a remote MCP + skills)
#
#   Agent-browser CLI   Vercel Labs CLI + Claude Code skill
#   Playwright MCP      Microsoft playwright/mcp (stdio; reuses the system Chrome, headless)
#
#   Serena MCP          LSP (stdio; telemetry off)
#   Codegraph MCP       Tree-sitter + SQLite MCP (stdio)
#
#   Cloud-run MCP       Google Cloud Run MCP (stdio; deploy/logs)
#   Google MCP Toolbox  For Databases (stdio; BigQuery prebuilt)
#   Vercel CLI          Vercel CLI + Vercel MCP (remote http) + Vercel plugin (skills/commands)

[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}



command -v sudo >/dev/null      || { echo "Cannot find sudo"; exit 1; }
command -v claude >/dev/null    || { echo "Cannot find claude"; exit 1; }


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


. $HOME/.nvm/nvm.sh
export PATH="$HOME/.local/bin:$PATH"

# agent-browser
run CI=1 npm install -g agent-browser
run agent-browser install
run npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes

# Playwright MCP
claude mcp remove playwright --scope user
run "claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated"

# Figma plugin
run claude plugin install figma@claude-plugins-official
run claude plugin update figma@claude-plugins-official

# Serena MCP -- uvx --python: short -p clashes with claude -p past `--`
claude mcp remove serena --scope user
run "claude mcp add serena --scope user -e SERENA_USAGE_REPORTING=false -- uvx --python 3.13 --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project-from-cwd --enable-web-dashboard false"

# CodeGraph MCP
claude mcp remove codegraph --scope user
run npm install -g @colbymchenry/codegraph
run "claude mcp add codegraph --scope user -- codegraph serve --mcp"

# Cloud Run MCP
claude mcp remove cloud-run --scope user
run "claude mcp add cloud-run --scope user -- npx -y @google-cloud/cloud-run-mcp"

# Toolbox MCP
claude mcp remove toolbox --scope user
run "claude mcp add toolbox --scope user -- npx -y @toolbox-sdk/server@latest --prebuilt=bigquery --stdio"

# Vercel CLI + plugin (MCP comes from the plugin)
claude mcp remove vercel --scope user
run npm install -g vercel
run CI=1 npx -y plugins add vercel/vercel-plugin --yes
run claude plugin update vercel@claude-plugins-official

run claude mcp list
run claude plugin list


LOGIN_USER="$(logname)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name
if [ -n "$LOGIN_USER" ]; then

    # agent-browser
    run sudo -i -u $LOGIN_USER bash -i -c '"CI=1 npm install -g agent-browser"'
    run sudo -i -u $LOGIN_USER bash -i -c '"agent-browser install"'
    run sudo -i -u $LOGIN_USER bash -i -c '"npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes"'

    # Playwright MCP
    sudo -i -u $LOGIN_USER bash -i -c "claude mcp remove playwright --scope user"
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated"'

    # Figma plugin
    run sudo -i -u $LOGIN_USER bash -i -c '"claude plugin install figma@claude-plugins-official"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude plugin update figma@claude-plugins-official"'

    # Serena MCP -- uvx --python: short -p clashes with claude -p past `--`
    sudo -i -u $LOGIN_USER bash -i -c "claude mcp remove serena --scope user"
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp add serena --scope user -e SERENA_USAGE_REPORTING=false -- uvx --python 3.13 --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project-from-cwd --enable-web-dashboard false"'

    # CodeGraph MCP
    sudo -i -u $LOGIN_USER bash -i -c "claude mcp remove codegraph --scope user"
    run sudo -i -u $LOGIN_USER bash -i -c '"npm install -g @colbymchenry/codegraph"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp add codegraph --scope user -- codegraph serve --mcp"'

    # Cloud Run MCP
    sudo -i -u $LOGIN_USER bash -i -c "claude mcp remove cloud-run --scope user"
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp add cloud-run --scope user -- npx -y @google-cloud/cloud-run-mcp"'

    # Toolbox MCP
    sudo -i -u $LOGIN_USER bash -i -c "claude mcp remove toolbox --scope user"
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp add toolbox --scope user -- npx -y @toolbox-sdk/server@latest --prebuilt=bigquery --stdio"'

    # Vercel CLI + plugin (MCP comes from the plugin)
    sudo -i -u $LOGIN_USER bash -i -c "claude mcp remove vercel --scope user"
    run sudo -i -u $LOGIN_USER bash -i -c '"npm install -g vercel"'
    run sudo -i -u $LOGIN_USER bash -i -c '"CI=1 npx -y plugins add vercel/vercel-plugin --yes"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude plugin update vercel@claude-plugins-official"'

    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp list"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude plugin list"'
else
    echo -e "${COLOR_RED}No login user found... omitting to install extensions for the login user${COLOR_CLEAR}"
    echo ""
fi


echo ''
echo '*** Post-install login -- type /mcp and /doctor in Claude Code console for OAuth2 ***'
echo ''

# END
