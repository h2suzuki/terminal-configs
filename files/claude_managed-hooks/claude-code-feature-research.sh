#!/bin/bash
# /etc/claude-code/hooks/claude-code-feature-research.sh
#
# SessionStart hook — keeps a versioned research log of Claude Code
# feature deltas (hook events / subagent / plugin / skill / settings /
# MCP / CLI) at
# ${XDG_CACHE_HOME:-~/.cache}/claude-code-feature-research/findings.md.
# Other skills (writing-skills / make-plan-before-coding) Read that
# file when they hit an unfamiliar Claude Code spec point. The hook
# itself surfaces nothing in additionalContext — the file exists for
# pull-by-Read, not push-into-context.
#
# Execution model (asynchronous, subscription-billed):
#   - Version MATCH → findings.md already covers the running CLI's
#                     version (last "## v<X.Y.Z>" heading == claude
#                     --version). Exit 0 silently, no model call.
#   - Version MISS  → dispatch a detached `claude --bg` research
#                     session whose job is to compare the last logged
#                     version against the current CLI, write only a
#                     new section body to a per-key staging file, and
#                     exit. The reaper later prepends that section to
#                     findings.md so newest sits on top.
#   - Initial seed  → no findings.md yet (or no parseable last
#                     version). bg session does a from-cutoff scan
#                     (Anthropic knowledge cutoff = 2026-01) and tags
#                     the section as the first scan.
#   - Every start runs a reaper that turns a completed staging file
#     into a prepend on findings.md and tears down the finished bg
#     session by its recorded id, guarded by a jobs/<id>/state.json
#     name match. The reaper never enumerates ~/.claude/jobs/*; it
#     acts solely on ids this hook recorded.
#   - A per-key in-flight marker dedups concurrent dispatches.
#
# CLI introspection model:
#   - The hook itself runs `claude --help` and `claude <subcmd> --help`
#     for every subcommand surface, and embeds the captured dump into
#     the bg session's user_prompt as `## CLI introspection dump`.
#   - This means the bg session never needs the `Bash` tool to call
#     `claude` — it treats the dump as ground truth and compares it
#     against the public docs via WebFetch. Keeping `Bash` out of the
#     bg session's tool set eliminates the permission-ask escalation
#     observed when `acceptEdits` was combined with `Bash`: detached
#     sessions cannot respond to permission prompts and the prompt
#     bubbled up to the user's interactive session.
#
# Recursion guard: CLAUDE_CODE_FEATURE_RESEARCH_PARENT is exported into
# the child and `--setting-sources ""` keeps the child from loading
# the settings file that registers this hook.
#
# The methodology prompt
# (/etc/claude-code/hooks/claude-code-feature-research-prompt.md) is
# injected via --append-system-prompt so the bg session gets the
# research protocol; the child does its own fetches with the Read /
# WebFetch tools.
#
# Stdin : SessionStart payload JSON (unused, drained for hygiene).
# Stdout: always empty. This hook never surfaces findings via
#   additionalContext; downstream skills Read findings.md on demand.

set -u

PROG_NAME="$(basename "$0" .sh)"
readonly PROG_NAME
readonly CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/${PROG_NAME}"
readonly INFLIGHT_DIR="${CACHE_DIR}/.inflight"
readonly STAGING_DIR="${CACHE_DIR}/.staging"
readonly FINDINGS_MD="${CACHE_DIR}/findings.md"
readonly PROMPT_MD="/etc/claude-code/hooks/claude-code-feature-research-prompt.md"
# Identifies this hook's background sessions. The reaper only stops/rm's
# a session whose jobs/<id>/state.json "name" equals this exact string.
readonly BG_NAME="claude-code-feature-research"
# Bounds only the dispatch call (cold-starting the per-user supervisor
# can take tens of seconds); the research session then runs detached.
readonly BG_DISPATCH_TIMEOUT_S=60
# An in-flight key whose staging file never appears within this window
# is treated as a dead bg job: its session is reaped and the marker is
# cleared so a later session can re-dispatch. Research can plausibly
# take several minutes (multiple WebFetch round-trips), so widen vs
# the lint hook's 30 min.
readonly BG_STALE_S=3600
# Delay before the dispatcher's own detached pass runs. It is a single
# safe reap_inflight pass (conditional on staging-present/stale, name-
# guarded, idempotent with the SessionStart reaper), so a finished bg
# session is torn down within this window even when no new session
# starts. Research is slower than lint — give it 10 min default.
readonly BG_SELF_REAP_S=600

# --- session reap helpers ---------------------------------------------------

# Stop+remove one bg session by id, but only when jobs/<id>/state.json
# records "name" == $2. A missing state.json means the session is
# already gone; a name mismatch means the short id was reused by an
# unrelated session and must not be touched.
_reap_session() {
  local id="$1" want="$2" sj content got
  [[ -z "$id" ]] && return 0
  sj="${HOME}/.claude/jobs/${id}/state.json"
  [[ -f "$sj" ]] || return 0
  content="$(<"$sj")"
  got=""
  [[ "$content" =~ \"name\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]] && got="${BASH_REMATCH[1]}"
  [[ "$got" == "$want" ]] || return 0
  timeout 30 claude stop "$id" </dev/null >/dev/null 2>&1 || true
  timeout 30 claude rm "$id" </dev/null >/dev/null 2>&1 || true
}

# Turn completed staging files into prepended sections on findings.md
# and tear down their bg sessions. Iterates only this hook's own
# in-flight markers, never the global jobs directory.
reap_inflight() {
  [[ -d "$INFLIGHT_DIR" ]] || return 0
  command -v claude >/dev/null 2>&1 || return 0
  local f ik iid iname its now age staging body existing
  printf -v now '%(%s)T' -1
  for f in "$INFLIGHT_DIR"/*; do
    [[ -e "$f" ]] || continue
    ik="${f##*/}"
    iid=""; iname=""; its=""
    IFS=$'\t' read -r iid iname its <"$f" 2>/dev/null || true
    if [[ -z "$iid" ]]; then
      # Claimed but no id recorded (crash between claim and write).
      # Drop the marker once clearly stale so dispatch can retry.
      fmt="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
      (( now - ${fmt:-0} > BG_STALE_S )) && rm -f "$f" 2>/dev/null
      continue
    fi
    staging="${STAGING_DIR}/${ik}.md"
    if [[ -f "$staging" ]]; then
      if [[ -s "$staging" ]]; then
        # Prepend the new section to findings.md so newest sits on
        # top. tmp-then-rename to keep findings.md atomically updated.
        body="$(<"$staging")"
        existing=""
        [[ -f "$FINDINGS_MD" ]] && existing="$(<"$FINDINGS_MD")"
        {
          printf '%s' "$body"
          # Guarantee a blank line between the new section and the
          # previously-newest section.
          [[ -n "$existing" ]] && {
            [[ "$body" == *$'\n\n' ]] || printf '\n'
            printf '%s' "$existing"
          }
        } >"${FINDINGS_MD}.tmp" 2>/dev/null
        if [[ -s "${FINDINGS_MD}.tmp" ]]; then
          mv -f "${FINDINGS_MD}.tmp" "$FINDINGS_MD" 2>/dev/null \
            || rm -f "${FINDINGS_MD}.tmp" 2>/dev/null
        else
          rm -f "${FINDINGS_MD}.tmp" 2>/dev/null
        fi
      fi
      _reap_session "$iid" "$iname"
      rm -f "$staging" "$f" 2>/dev/null
    else
      age=$(( now - ${its:-0} ))
      if (( ${its:-0} > 0 && age > BG_STALE_S )); then
        _reap_session "$iid" "$iname"
        rm -f "$f" 2>/dev/null
      fi
    fi
  done
}

# --- CLI introspection capture ---------------------------------------------
#
# Build the dump that the bg session uses as ground truth. The hook runs
# every `claude <sub> --help` itself so the dispatched session does not
# need the `Bash` tool. Subcommands are parsed from the top-level
# `Commands:` section (commander.js format: 2-space indent, identifier,
# padding, description, blank line ends the section). Each line of the
# dump is prefixed with a fenced `=== claude <sub> --help ===` heading
# so the LLM can locate per-subcommand surfaces inside the prompt.
capture_cli_dump() {
  local top_help line cand sub
  local -a subcommands=()
  top_help="$(claude --help 2>&1 || true)"
  printf '=== claude --help ===\n%s\n' "$top_help"
  local in_commands=0
  while IFS= read -r line; do
    if [[ "$line" == "Commands:" ]]; then
      in_commands=1
      continue
    fi
    if (( in_commands )); then
      [[ -z "${line//[[:space:]]/}" ]] && break
      if [[ "$line" =~ ^[[:space:]]+([a-zA-Z][a-zA-Z0-9_-]*) ]]; then
        cand="${BASH_REMATCH[1]}"
        # Skip the auto-generated `help` entry — `claude help --help`
        # just re-prints the top-level help and adds no surface.
        [[ "$cand" == "help" ]] && continue
        subcommands+=("$cand")
      fi
    fi
  done <<<"$top_help"
  for sub in "${subcommands[@]}"; do
    printf '\n\n=== claude %s --help ===\n' "$sub"
    claude "$sub" --help 2>&1 || true
  done
}

# --- detached self-reap entry ----------------------------------------------
#
# The dispatcher spawns `"$0" --reap-pass` via setsid after a delay. This
# mode runs one reap_inflight pass and exits: it never reads stdin, never
# dispatches, and is idempotent with the SessionStart reaper.
if [[ "${1:-}" == "--reap-pass" ]]; then
  reap_inflight
  exit 0
fi

# --- re-entry guard ---------------------------------------------------------

if [[ -n "${CLAUDE_CODE_FEATURE_RESEARCH_PARENT:-}" ]]; then
  exit 0
fi

# Without the methodology prompt file there is nothing to inject — bail
# out silently rather than dispatching a degraded research session.
[[ -s "$PROMPT_MD" && -r "$PROMPT_MD" ]] || exit 0

# Drain stdin for hygiene (SessionStart payload is unused here).
cat >/dev/null 2>&1 || true

# Process finished/stale background jobs before this run's version
# check, so a just-completed result becomes the current "last
# researched version" in findings.md.
reap_inflight

# --- version check ----------------------------------------------------------

command -v claude >/dev/null 2>&1 || exit 0

# Current CLI version (semver only — strip any prefix / suffix).
current_version="$(claude --version 2>/dev/null \
  | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' \
  | head -1 || true)"
# Fail-open: if --version cannot be parsed (older CLI, broken install,
# unexpected wrapper), there is no reliable way to decide MATCH vs
# MISS — exit silently rather than dispatch on every session.
[[ -z "$current_version" ]] && exit 0

# Last researched version from the top "## v<X.Y.Z>" heading in
# findings.md. pre-1.0 versions ("## v0.x.y") match the same regex.
last_version=""
if [[ -f "$FINDINGS_MD" ]]; then
  last_version="$(grep -m 1 -oE '^## v[0-9]+\.[0-9]+\.[0-9]+' "$FINDINGS_MD" 2>/dev/null \
    | head -1 \
    | sed 's/^## v//' || true)"
fi

# MATCH → no-op.
[[ "$last_version" == "$current_version" ]] && exit 0

# --- async dispatch ---------------------------------------------------------
#
# MISS: dispatch a detached bg research session, record an in-flight
# marker, surface nothing this session. The reaper handles staging→
# findings.md merge on a later SessionStart (or this hook's own
# delayed self-reap pass).

mkdir -p "$CACHE_DIR" "$INFLIGHT_DIR" "$STAGING_DIR" 2>/dev/null

# Cache key = current_version + last_version. Prevents two concurrent
# dispatches for the same version pair, but allows redispatch once a
# new CLI version arrives.
key_input="${current_version}|${last_version:-INITIAL}"
key="$(printf '%s' "$key_input" | sha256sum 2>/dev/null | cut -c1-16)"
[[ -z "$key" ]] && exit 0

inflight="${INFLIGHT_DIR}/${key}"
# Atomic claim: under noclobber the redirection creates the marker iff
# it is absent, so only one of N concurrent SessionStart hooks
# dispatches a bg job for this key. The subshell scopes the option.
if ! ( set -o noclobber; : >"$inflight" ) 2>/dev/null; then
  exit 0
fi

staging="${STAGING_DIR}/${key}.md"
rm -f "$staging" 2>/dev/null

prompt_body="$(cat "$PROMPT_MD" 2>/dev/null)"
cli_dump="$(capture_cli_dump)"

# The methodology prompt is injected via --append-system-prompt. The
# user-prompt block carries the variables the prompt references
# (current / last version, the staging path to Write to) and the
# pre-captured `## CLI introspection dump` so the bg session has the
# ground truth without a Bash call. The cutoff string ("2026-01") is
# the assistant knowledge cutoff and is what the "from-cutoff scan"
# path should compare against on initial seed.
if [[ -z "$last_version" ]]; then
  delta_descr="initial seed: research from the Anthropic Claude Code knowledge cutoff (2026-01) up through v${current_version}. tag the section as the first scan."
else
  delta_descr="delta research: list everything that changed between v${last_version} and v${current_version}."
fi

user_prompt=$'Claude Code feature-delta research session.\n\n'"$delta_descr"$'\n\nWrite ONLY the new section body (single `## v<current> (researched YYYY-MM-DD)` heading followed by the four subsections defined in the methodology prompt) with the Write tool to:\n\n'"$staging"$'\n\nDo not echo to stdout. Do not write anything besides the staging file. No JSON envelope, no prose before/after the staging Write call.\n\ncurrent_version: '"$current_version"$'\nlast_version: '"${last_version:-<none — initial seed>}"$'\nstaging_file: '"$staging"$'\n\n## CLI introspection dump (pre-captured by the SessionStart hook)\n\n'"$cli_dump"

# `claude --bg`: detached, subscription-billed. acceptEdits auto-allows
# Write non-interactively. --setting-sources "" keeps the child from
# re-registering this hook. The `Bash` tool is deliberately omitted:
# every `claude <sub> --help` invocation is pre-captured into
# `cli_dump` above, so the bg session has the ground truth without
# needing Bash, and the permission-ask path that would escalate to
# the user's interactive session is closed.
out="$(
  CLAUDE_CODE_FEATURE_RESEARCH_PARENT=1 timeout "$BG_DISPATCH_TIMEOUT_S" \
    claude --bg \
      --name "$BG_NAME" \
      --model claude-sonnet-4-5-20250929 \
      --effort high \
      --setting-sources "" \
      --strict-mcp-config \
      --tools Read,Write,WebFetch \
      --add-dir "$STAGING_DIR" \
      --permission-mode acceptEdits \
      --append-system-prompt "$prompt_body" \
      "$user_prompt" </dev/null 2>/dev/null || true
)"

bid=""
if [[ "$out" =~ backgrounded[^0-9a-fA-F]*([0-9a-fA-F]{8}) ]]; then
  bid="${BASH_REMATCH[1]}"
fi
if [[ -n "$bid" ]]; then
  printf -v dts '%(%s)T' -1
  printf '%s\t%s\t%s\n' "$bid" "$BG_NAME" "$dts" >"$inflight" 2>/dev/null
  # Detached self-reap: one delayed safe pass so a finished bg session
  # is torn down within ~BG_SELF_REAP_S even if no new session starts.
  self="$(realpath -e "$0" 2>/dev/null || printf '%s' "$0")"
  if command -v setsid >/dev/null 2>&1; then
    setsid bash -c 'sleep "$1"; exec "$2" --reap-pass' _ "$BG_SELF_REAP_S" "$self" \
      </dev/null >/dev/null 2>&1 &
  else
    ( sleep "$BG_SELF_REAP_S"; "$self" --reap-pass ) </dev/null >/dev/null 2>&1 &
    disown
  fi
else
  # Dispatch produced no id → release the claim so a later session
  # can retry instead of the key being stuck in-flight forever.
  rm -f "$inflight" 2>/dev/null
fi

exit 0
