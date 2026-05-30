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
#   - The hook runs `claude --help` and `claude <subcmd> --help` for
#     every subcommand surface, plus fetches the upstream CHANGELOG, and
#     writes both to a per-key ground-truth file under STAGING_DIR that
#     the bg session Reads. Only the file PATH goes in the user_prompt —
#     embedding the dumps inline blew the Linux 128KB single-arg cap
#     (E2BIG), so `claude --bg` silently produced no session.
#   - The bg session has neither `Bash` nor `WebFetch`; it works purely
#     from that pre-captured file. Keeping `Bash` out eliminates the
#     permission-ask escalation seen when `acceptEdits` was combined with
#     `Bash`: detached sessions cannot answer permission prompts and the
#     prompt bubbled up to the user's interactive session.
#
# Recursion guard: the file-based LOCK_FILE check below is the
# authoritative defence. The env var (CLAUDE_CODE_FEATURE_RESEARCH_PARENT)
# and `--setting-sources ""` are best-effort and do NOT reach the `--bg`
# child — the worker inherits the daemon env (not this client's inline
# assignment), and `--setting-sources` cannot drop the *managed* settings
# file that registers this hook.
#
# The methodology prompt
# (/etc/claude-code/hooks/claude-code-feature-research-prompt.md) is
# injected via --append-system-prompt so the bg session gets the
# research protocol; the child Reads the pre-captured ground-truth file
# (Read tool only — no Bash / WebFetch).
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
# First-scan (empty last_version) floor: keep only the most recent
# FIRST_SCAN_FLOOR version sections instead of dumping the whole changelog
# back to 0.2.x. The full ~300-version dump overwhelmed the single research
# agent into compressing away mid-range features; the comprehensive
# post-cutoff baseline is rebuilt out-of-band via a fan-out workflow, so this
# floor is just a bounded safety net for a deleted findings.md.
readonly FIRST_SCAN_FLOOR=30

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
      # Drop the marker (and any orphaned context file) once clearly
      # stale so dispatch can retry.
      fmt="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
      (( now - ${fmt:-0} > BG_STALE_S )) && rm -f "${STAGING_DIR}/${ik}.context.md" "$f" 2>/dev/null
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
      rm -f "$staging" "${STAGING_DIR}/${ik}.context.md" "$f" 2>/dev/null
    else
      age=$(( now - ${its:-0} ))
      if (( ${its:-0} > 0 && age > BG_STALE_S )); then
        _reap_session "$iid" "$iname"
        rm -f "${STAGING_DIR}/${ik}.context.md" "$f" 2>/dev/null
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

# --- changelog capture (CHANGELOG-driven research source) ------------------
#
# Fetch the upstream raw CHANGELOG.md so the bg session has version-delta
# context without WebFetch. Raw GitHub URL is anonymous and plain markdown,
# so no HTML parse. Fail-open: an empty / failed fetch is annotated in the
# dump body and the bg session works from CLI dump alone.
# $1 = last researched version (empty on seed). Changelog is newest-first,
# so dropping from the last-researched heading down keeps only the delta.
capture_changelog() {
  local last="$1" raw url='https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md'
  printf '=== CHANGELOG.md (raw'
  if [[ -n "$last" ]]; then
    printf ', trimmed to versions newer than %s' "$last"
  else
    printf ', most recent %s version sections only (first-scan floor)' "$FIRST_SCAN_FLOOR"
  fi
  printf ') ===\n'
  raw="$(timeout 30 curl -fsSL "$url" 2>/dev/null)"
  if [[ -z "$raw" ]]; then
    printf '(CHANGELOG fetch failed — work from CLI dump alone)\n'
    return 0
  fi
  # Ongoing delta: keep from the top until the last-researched heading.
  # First-scan (empty last): keep only the most recent FIRST_SCAN_FLOOR
  # headings — never the whole changelog (that dump overwhelmed the single
  # agent into compression; see the FIRST_SCAN_FLOOR const comment).
  awk -v last="$last" -v floor="$FIRST_SCAN_FLOOR" '
    /^## / {
      if (last != "" && $2 == last) exit
      if (last == "" && vc++ >= floor) exit
    }
    { print }
  ' <<< "$raw"
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

# File-based recursion guard (authoritative; env-based above is
# best-effort). Observed 2026-05-28 in claude-md-lint that env-based
# guard did not fire in daemon-spawned worker chains, leading to 35+
# cascaded bg sessions. This hook uses the same dispatcher pattern,
# so apply the same guard. The dispatcher touches LOCK_FILE just
# before `claude --bg`; while LOCK_FILE exists with mtime within
# BG_STALE_S, any later SessionStart invocation of this hook —
# including from inside the dispatched child bg session — exits
# without spawning a second dispatch. Stale locks are ignored so a
# crashed dispatcher does not block subsequent runs forever.
LOCK_FILE="${CACHE_DIR}/.dispatch.lock"
if [[ -f "$LOCK_FILE" ]]; then
  lock_mtime="$(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0)"
  printf -v _now '%(%s)T' -1
  if (( _now - lock_mtime < BG_STALE_S )); then
    exit 0
  fi
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

# File-based recursion guard (write): touch the lock file so any
# SessionStart invocation inside the dispatched child bg session
# sees an active dispatch and exits at the re-entry guard above.
# Stale (> BG_STALE_S) locks are ignored upstream, so a crashed
# dispatcher does not block subsequent runs.
: >"$LOCK_FILE" 2>/dev/null

staging="${STAGING_DIR}/${key}.md"
context="${STAGING_DIR}/${key}.context.md"
rm -f "$staging" "$context" 2>/dev/null

# Drop the context file on any exit until dispatch succeeds; afterwards
# the child owns it (Reads it) and the reaper clears it.
trap 'rm -f "$context" 2>/dev/null' EXIT

prompt_body="$(cat "$PROMPT_MD" 2>/dev/null)"

# Cutoff string ("2026-01") is the assistant knowledge cutoff the
# "from-cutoff scan" path compares against on initial seed.
if [[ -z "$last_version" ]]; then
  delta_descr="initial seed: research from the Anthropic Claude Code knowledge cutoff (2026-01) up through v${current_version}. tag the section as the first scan."
else
  delta_descr="delta research: list everything that changed between v${last_version} and v${current_version}."
fi

# Ground truth → file the bg session Reads, not argv: embedding it inline
# blew the Linux 128KB single-arg cap (E2BIG) once the CHANGELOG was added.
{
  printf '## CLI introspection dump (pre-captured by the SessionStart hook)\n\n'
  capture_cli_dump
  printf '\n\n## CHANGELOG.md dump (pre-captured by the SessionStart hook)\n\n'
  capture_changelog "$last_version"
} >"$context" 2>/dev/null

user_prompt=$'Claude Code feature-delta research session.\n\n'"$delta_descr"$'\n\nFirst Read the pre-captured ground-truth file (it holds the `## CLI introspection dump` and `## CHANGELOG.md dump` sections):\n\n'"$context"$'\n\nThen write ONLY the new section body (single `## v<current> (researched YYYY-MM-DD)` heading followed by the four subsections defined in the methodology prompt) with the Write tool to:\n\n'"$staging"$'\n\nDo not echo to stdout. Do not write anything besides the staging file. No JSON envelope, no prose before/after the staging Write call.\n\ncurrent_version: '"$current_version"$'\nlast_version: '"${last_version:-<none — initial seed>}"$'\nground_truth_file: '"$context"$'\nstaging_file: '"$staging"

# `claude --bg`: detached, subscription-billed. acceptEdits auto-allows
# Write non-interactively. --setting-sources "" drops the child's
# user/project/local config but NOT the managed hook (recursion is
# stopped by LOCK_FILE above). Both `Bash` and `WebFetch` are deliberately
# omitted: `claude <sub> --help` and the upstream `CHANGELOG.md` are
# pre-captured into `cli_dump` / `changelog_dump` above, so the bg
# session has the binary surface and the version-delta source without
# needing Bash or WebFetch. The permission-ask path that would
# escalate to the user's interactive session is closed (acceptEdits
# covers Write only — a WebFetch in the bg session would have
# escalated and stalled the dispatch).
err="${CACHE_DIR}/.last-dispatch.err"
out="$(
  CLAUDE_CODE_FEATURE_RESEARCH_PARENT=1 timeout "$BG_DISPATCH_TIMEOUT_S" \
    claude --bg \
      --name "$BG_NAME" \
      --model claude-sonnet-4-5-20250929 \
      --effort high \
      --setting-sources "" \
      --strict-mcp-config \
      --tools Read,Write \
      --add-dir "$STAGING_DIR" \
      --permission-mode acceptEdits \
      --append-system-prompt "$prompt_body" \
      "$user_prompt" </dev/null 2>"$err"
)"
rc=$?

bid=""
if [[ "$out" =~ backgrounded[^0-9a-fA-F]*([0-9a-fA-F]{8}) ]]; then
  bid="${BASH_REMATCH[1]}"
fi
if [[ -n "$bid" ]]; then
  printf -v dts '%(%s)T' -1
  printf '%s\t%s\t%s\n' "$bid" "$BG_NAME" "$dts" >"$inflight" 2>/dev/null
  trap - EXIT
  rm -f "$err" 2>/dev/null
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
  # No id: log why (rc + stderr) instead of swallowing it, release the
  # claim, and let the EXIT trap drop the context file.
  printf -v ets '%(%FT%TZ)T' -1
  {
    printf '[%s] dispatch FAILED rc=%s key=%s\n' "$ets" "$rc" "$key"
    [[ -s "$err" ]] && printf '  stderr: %.500s\n' "$(<"$err")"
  } >>"${CACHE_DIR}/dispatch.log" 2>/dev/null
  rm -f "$inflight" "$err" 2>/dev/null
fi

exit 0
