#!/bin/bash

# Installs Claude Code extensions + cloud CLIs as an opt-in step after the base setup.
# Per-user items (npm globals, MCP servers, plugins, skills) are installed for BOTH root
# and the login user -- mirroring ubuntu2404-wsl.sh, which sets up Claude Code for both.
# The Google Cloud CLI is a system-wide apt package. Re-running upgrades each item in place.
#
#   gcloud         Google Cloud CLI (apt; gcloud + gsutil + bq), system-wide
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
command -v curl >/dev/null || { echo "Cannot find curl"; exit 1; }
command -v gpg  >/dev/null || { echo "Cannot find gpg";  exit 1; }


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


# Google Cloud CLI (apt; provides gcloud, gsutil, bq) -- system-wide, all users.
# curl/gpg are guarded above; ca-certificates is assumed present (same as the base's gh repo).
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


# Per-user toolchain: install for root (this script's user) and the login user.
LOGIN_USER="$(logname 2>/dev/null)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"
USERS=(root)
[ -n "$LOGIN_USER" ] && [ "$LOGIN_USER" != root ] && USERS+=("$LOGIN_USER")

for U in "${USERS[@]}"; do
    echo -e "=> ${COLOR_YELLOW}==== installing for user: $U ====${COLOR_CLEAR}"

    # Confirm the user's toolchain (node/npm/npx via nvm, uvx, claude on PATH).
    run sudo -i -u "$U" bash -i -c '"node --version && npm --version && npx --version && uvx --version && claude --version"'

    # agent-browser: CLI + Claude Code skill (not an MCP server). CI=1 keeps npm non-interactive.
    run sudo -i -u "$U" bash -i -c '"CI=1 npm install -g agent-browser"'
    run sudo -i -u "$U" bash -i -c '"agent-browser install"'
    run sudo -i -u "$U" bash -i -c '"npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes"'

    # Playwright MCP: system Chrome, headless for WSL2, isolated profile. remove-then-add re-pins.
    run sudo -i -u "$U" bash -i -c '"claude mcp remove playwright --scope user >/dev/null 2>&1; claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest --browser chrome --headless --isolated"'

    # Figma: Anthropic-marketplace plugin (bundles remote MCP + skills). OAuth deferred to first use.
    run sudo -i -u "$U" bash -i -c '"claude plugin install figma@claude-plugins-official || claude plugin update figma@claude-plugins-official"'

    # Serena: SERENA_USAGE_REPORTING=false silences telemetry; --enable-web-dashboard false, no browser.
    run sudo -i -u "$U" bash -i -c '"claude mcp remove serena -s user >/dev/null 2>&1; claude mcp add serena -s user -e SERENA_USAGE_REPORTING=false -- uvx -p 3.13 --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project-from-cwd --enable-web-dashboard false"'

    # CodeGraph: global npm CLI + stdio MCP (`codegraph init` per repo builds the index).
    run sudo -i -u "$U" bash -i -c '"npm install -g @colbymchenry/codegraph"'
    run sudo -i -u "$U" bash -i -c '"claude mcp remove codegraph -s user >/dev/null 2>&1; claude mcp add codegraph -s user -- codegraph serve --mcp"'

    # GCP MCP servers (stdio): Cloud Run deploy/logs + MCP Toolbox (BigQuery prebuilt).
    run sudo -i -u "$U" bash -i -c '"claude mcp remove cloud-run -s user >/dev/null 2>&1; claude mcp add cloud-run -s user -- npx -y @google-cloud/cloud-run-mcp"'
    run sudo -i -u "$U" bash -i -c '"claude mcp remove toolbox -s user >/dev/null 2>&1; claude mcp add toolbox -s user -- npx -y @toolbox-sdk/server@latest --prebuilt=bigquery --stdio"'

    # Vercel: CLI + remote MCP (deploy/logs/docs) + plugin (25 skills, 5 slash commands).
    run sudo -i -u "$U" bash -i -c '"npm install -g vercel"'
    run sudo -i -u "$U" bash -i -c '"claude mcp remove vercel -s user >/dev/null 2>&1; claude mcp add -s user --transport http vercel https://mcp.vercel.com"'
    run sudo -i -u "$U" bash -i -c '"CI=1 npx -y plugins add vercel/vercel-plugin"'

    run sudo -i -u "$U" bash -i -c '"claude mcp list"'
    run sudo -i -u "$U" bash -i -c '"claude plugin list"'
done


cat <<'EOF'

==================== Post-install: sign-in & one-time setup ====================

Installed for BOTH root and the login user (run `claude` as whichever you use).

[Google Cloud]  gcloud/gsutil/bq are system-wide. Sign in (interactive):
                  gcloud auth login
                  gcloud auth application-default login   # used by the MCP servers
                  gcloud config set project <PROJECT_ID>
                Cost: enable Billing export to BigQuery in the Cloud Console, then
                the `toolbox` MCP can query it by service / SKU / label.

[Vercel]        CLI + MCP + plugin installed.  vercel login
                Authenticate the remote MCP: run `claude`, `/mcp`, pick `vercel`.

[Figma]         Plugin installed. Activate: run `claude`, `/mcp`, pick `figma`,
                complete the browser OAuth.

[MCP servers]   playwright / serena / codegraph / cloud-run / toolbox / vercel are
                registered at user scope (stdio, spawned on demand per session).
                CodeGraph needs a one-time per-repo index, from the repo root:
                  codegraph init

===============================================================================
EOF

# END
