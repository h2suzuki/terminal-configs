#!/bin/bash

# Installs Claude Code extensions as an opt-in step after the base setup. Per-user items
# (npm globals, MCP servers, plugins, skills) are installed for both root and the login
# user. Re-running upgrades each item in place.
#
#   agent-browser  Vercel Labs CLI + Claude Code skill (not an MCP server)
#   playwright     Microsoft @playwright/mcp (stdio; reuses the system Chrome, headless)
#   figma          Anthropic-marketplace plugin (bundles a remote MCP + skills)
#   serena         oraios/serena semantic code MCP (LSP-backed, stdio; telemetry off)
#   codegraph      @colbymchenry/codegraph local code-graph MCP (tree-sitter+SQLite, stdio)
#   cloud-run      Google Cloud Run MCP (stdio; deploy/logs)
#   toolbox        Google MCP Toolbox for Databases (stdio; BigQuery prebuilt -- data/cost)
#   vercel         Vercel CLI + Vercel MCP (remote http) + Vercel plugin (skills/commands)

[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}

command -v sudo >/dev/null || { echo "Cannot find sudo"; exit 1; }


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


run bash -i -c '"node --version && npm --version && npx --version && uvx --version && claude --version"'

# agent-browser
run bash -i -c '"CI=1 npm install -g agent-browser"'
run bash -i -c '"agent-browser install"'
run bash -i -c '"npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes"'

# Playwright MCP
run bash -i -c '"claude mcp remove playwright --scope user >/dev/null 2>&1; claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated"'

# Figma plugin
run bash -i -c '"claude plugin install figma@claude-plugins-official || claude plugin update figma@claude-plugins-official"'

# Serena MCP -- uvx --python: short -p clashes with claude -p past `--`
run bash -i -c '"claude mcp remove serena -s user >/dev/null 2>&1; claude mcp add serena -s user -e SERENA_USAGE_REPORTING=false -- uvx --python 3.13 --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project-from-cwd --enable-web-dashboard false"'

# CodeGraph MCP
run bash -i -c '"npm install -g @colbymchenry/codegraph"'
run bash -i -c '"claude mcp remove codegraph -s user >/dev/null 2>&1; claude mcp add codegraph -s user -- codegraph serve --mcp"'

# Cloud Run + Toolbox MCPs
run bash -i -c '"claude mcp remove cloud-run -s user >/dev/null 2>&1; claude mcp add cloud-run -s user -- npx -y @google-cloud/cloud-run-mcp"'
run bash -i -c '"claude mcp remove toolbox -s user >/dev/null 2>&1; claude mcp add toolbox -s user -- npx -y @toolbox-sdk/server@latest --prebuilt=bigquery --stdio"'

# Vercel CLI + MCP + plugin
run bash -i -c '"npm install -g vercel"'
run bash -i -c '"claude mcp remove vercel -s user >/dev/null 2>&1; claude mcp add -s user --transport http vercel https://mcp.vercel.com"'
run bash -i -c '"CI=1 npx -y plugins add vercel/vercel-plugin"'

run bash -i -c '"claude mcp list"'
run bash -i -c '"claude plugin list"'


LOGIN_USER="$(logname)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"     # Alternative way to find the name
if [ -n "$LOGIN_USER" ] && [ "$LOGIN_USER" != root ]; then
    run sudo -i -u $LOGIN_USER bash -i -c '"node --version && npm --version && npx --version && uvx --version && claude --version"'

    # agent-browser
    run sudo -i -u $LOGIN_USER bash -i -c '"CI=1 npm install -g agent-browser"'
    run sudo -i -u $LOGIN_USER bash -i -c '"agent-browser install"'
    run sudo -i -u $LOGIN_USER bash -i -c '"npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes"'

    # Playwright MCP
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp remove playwright --scope user >/dev/null 2>&1; claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated"'

    # Figma plugin
    run sudo -i -u $LOGIN_USER bash -i -c '"claude plugin install figma@claude-plugins-official || claude plugin update figma@claude-plugins-official"'

    # Serena MCP -- uvx --python: short -p clashes with claude -p past `--`
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp remove serena -s user >/dev/null 2>&1; claude mcp add serena -s user -e SERENA_USAGE_REPORTING=false -- uvx --python 3.13 --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project-from-cwd --enable-web-dashboard false"'

    # CodeGraph MCP
    run sudo -i -u $LOGIN_USER bash -i -c '"npm install -g @colbymchenry/codegraph"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp remove codegraph -s user >/dev/null 2>&1; claude mcp add codegraph -s user -- codegraph serve --mcp"'

    # Cloud Run + Toolbox MCPs
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp remove cloud-run -s user >/dev/null 2>&1; claude mcp add cloud-run -s user -- npx -y @google-cloud/cloud-run-mcp"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp remove toolbox -s user >/dev/null 2>&1; claude mcp add toolbox -s user -- npx -y @toolbox-sdk/server@latest --prebuilt=bigquery --stdio"'

    # Vercel CLI + MCP + plugin
    run sudo -i -u $LOGIN_USER bash -i -c '"npm install -g vercel"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp remove vercel -s user >/dev/null 2>&1; claude mcp add -s user --transport http vercel https://mcp.vercel.com"'
    run sudo -i -u $LOGIN_USER bash -i -c '"CI=1 npx -y plugins add vercel/vercel-plugin"'

    run sudo -i -u $LOGIN_USER bash -i -c '"claude mcp list"'
    run sudo -i -u $LOGIN_USER bash -i -c '"claude plugin list"'
fi


echo ''
echo '*** Post-install sign-in -- run as each user that uses claude: ***'
echo '***   vercel login                                              ***'
echo '***   in claude: /mcp -> figma -> OAuth   (same for vercel)     ***'
echo '***   per repo (one-time): codegraph init                       ***'
echo ''

# END
