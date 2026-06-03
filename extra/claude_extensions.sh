#!/bin/bash

# Installs Claude Code extensions as an opt-in step after the base setup. Every item is
# per-user runtime config written by the claude / npm / skills CLIs (user scope:
# ~/.claude.json and ~/.claude/skills), NOT a files/ -> /etc deploy, so there is no
# canonical source file to keep in sync -- this script itself is the source of truth.
#
#   agent-browser     Vercel Labs CLI + Claude Code skill (NOT an MCP server)
#   @playwright/mcp   Microsoft official Playwright MCP server (reuses the system Chrome)
#   figma             Anthropic official-marketplace plugin (bundles a remote MCP + skills)
#
# GitHub MCP is intentionally NOT installed: redundant with the already-installed gh CLI,
# and the remote server's OAuth is broken on Linux. See the end-of-run notes to add it.
#
# Idempotent: re-running upgrades in place (agent-browser via npm @latest, figma via
# `claude plugin update`, Playwright MCP by re-pinning the current latest release).

[ "$EUID" = 0 ] || {
    echo "Please run as root"
    exit 1
}

command -v sudo >/dev/null 2>&1 || { echo "Cannot find sudo"; exit 1; }


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


# Resolve the login user: claude / npm / skills run as them (not root) so config lands in
# their home and their nvm Node is used.
LOGIN_USER="$(logname 2>/dev/null)"
[ -n "$LOGIN_USER" ] || LOGIN_USER="$SUDO_USER"
[ -n "$LOGIN_USER" ] || {
    echo -e "${COLOR_RED}No login user found${COLOR_CLEAR}"
    exit 1
}


# Run a command as the login user in an interactive login shell so ~/.bashrc loads nvm
# (node/npm/npx) and ~/.local/bin/claude. Same pattern as debian12.sh / ubuntu2404-wsl.sh.
as_user() {
    echo -e "=> ${COLOR_YELLOW}[$LOGIN_USER] $*${COLOR_CLEAR}"
    sudo -i -u "$LOGIN_USER" bash -i -c "$*"
    local rv=$?
    if [ $rv -eq 0 ]; then
        echo -e "[ ${COLOR_GREEN}OK${COLOR_CLEAR} ]\n"
    else
        echo -e "[ ${COLOR_RED}ERROR($rv)${COLOR_CLEAR} ]\n"
        exit $rv
    fi
}


# Confirm the login user's toolchain (node/npm/npx via nvm, claude on PATH).
as_user 'node --version && npm --version && npx --version && claude --version'


# Resolve the current @playwright/mcp release so a re-run re-pins (upgrades) it; fall back
# to a known version when offline.
PW_MCP_VER=$(sudo -i -u "$LOGIN_USER" bash -i -c 'npm view @playwright/mcp version' 2>/dev/null | tail -n1)
case "$PW_MCP_VER" in
    [0-9]*) ;;
    *) PW_MCP_VER=0.0.75 ;;
esac
echo -e "=> ${COLOR_YELLOW}@playwright/mcp target version: $PW_MCP_VER${COLOR_CLEAR}"


# --- agent-browser: Vercel Labs CLI + Claude Code skill (not an MCP server) ---
# @latest upgrades on re-run; CI=1 keeps npm's postinstall non-interactive (it would
# otherwise offer to fetch Chrome).
as_user 'CI=1 npm install -g agent-browser@latest'
# Fetch a known-good browser; the base setup's Google Chrome is auto-detected too. If a
# headless launch later fails on missing libs, re-run as `agent-browser install --with-deps`.
as_user 'agent-browser install'
# Register the skill at user level (~/.claude/skills); --global avoids a project-local copy.
# The CLI does the work; the skill is only discovery metadata for Claude Code.
as_user 'npx -y skills add vercel-labs/agent-browser --skill agent-browser --agent claude-code --global --yes'


# --- Playwright MCP (Microsoft @playwright/mcp): stdio transport, user scope ---
# --browser chrome reuses the system Google Chrome (no Chromium download); --headless for
# WSL2's no-display; --isolated for a fresh profile. remove-then-add re-pins on every run.
as_user "claude mcp remove playwright --scope user >/dev/null 2>&1; claude mcp add --scope user playwright -- npx -y @playwright/mcp@$PW_MCP_VER --browser chrome --headless --isolated"


# --- Figma: Anthropic official-marketplace plugin (bundles remote MCP + skills) ---
# Installed -> update; else install (adding the marketplace only if the plugin is not found).
# claude-plugins-official is auto-available. OAuth is deferred to first interactive use.
echo -e "=> ${COLOR_YELLOW}[$LOGIN_USER] figma plugin${COLOR_CLEAR}"
if sudo -i -u "$LOGIN_USER" bash -i -c 'claude plugin list 2>/dev/null | grep -qi figma'; then
    as_user 'claude plugin update figma@claude-plugins-official'
elif sudo -i -u "$LOGIN_USER" bash -i -c 'claude plugin install figma@claude-plugins-official'; then
    echo -e "[ ${COLOR_GREEN}OK${COLOR_CLEAR} ]\n"
else
    as_user 'claude plugin marketplace add anthropics/claude-plugins-official'
    as_user 'claude plugin install figma@claude-plugins-official'
fi


# --- Verify ---
as_user 'claude mcp list'
as_user 'claude plugin list'


# --- Post-install sign-in (OAuth is intentionally NOT performed by this script) ---
cat <<'EOF'

==================== Claude Code extensions: post-install sign-in ====================

[Figma]      Plugin installed (remote MCP https://mcp.figma.com/mcp). To activate it,
             run `claude`, then `/mcp`, pick the `figma` server and complete the Figma
             "Allow Access" OAuth in the browser. (Full Dev Mode may need a Figma seat.)

[Playwright] MCP server `playwright` added (user scope) -- no sign-in needed; it drives
             the installed Google Chrome headlessly. For logged-in sites, re-add it with a
             persistent profile and log in once in a headed run:
               claude mcp remove playwright --scope user
               claude mcp add --scope user playwright -- npx -y @playwright/mcp@latest \
                 --browser chrome --user-data-dir ~/.cache/ms-playwright-mcp-profile

[agent-browser] CLI + skill installed (no OAuth / API key for the tool itself). Verify the
             skill: run `claude`, then `/skills` (look for `agent-browser`). For logged-in
             sites, run it once and sign in -- the session is then reused:
               agent-browser open <url> --session-name <name>

[GitHub MCP] NOT installed (gh already covers GitHub; the remote server's OAuth is broken
             on Linux). To add it anyway, reusing gh's token:
               claude mcp add --scope user --transport http github \
                 https://api.githubcopilot.com/mcp/ --header "Authorization: Bearer $(gh auth token)"

=====================================================================================
EOF

# END
