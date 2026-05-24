#!/bin/bash
# /etc/claude-code/claude-md-lint.sh
#
# SessionStart hook — cross-project lint of the auto-loaded CLAUDE.md
# chain (org / user / project CLAUDE.md and @-imported CLAUDE.md files).
# Auto-memory index files (MEMORY.md / global-memory) are excluded: they
# change almost every session and would make the result cache miss
# perpetually. Read-only judgement; flags duplications with the system
# prompt, internal contradictions, stale references, unclear directives.
#
# Execution model (asynchronous, subscription-billed):
#   - Cache HIT  → read the cached findings synchronously and emit them
#                  (no model call; unchanged fast path).
#   - Cache MISS → dispatch a detached `claude --bg` session that writes
#                  its findings to a per-key staging file, then return at
#                  once. This session surfaces nothing; the findings show
#                  up on the first session start after the bg job ends.
#                  `claude --bg` bills to the subscription plan (unlike
#                  `claude -p`, which moves to separate metering).
#   - Every start runs a reaper that turns a completed staging file into
#     a cache file (deterministic bash layout — the model only produces
#     the findings text, never the cache format) and tears down the
#     finished bg session by its recorded id, guarded by a
#     jobs/<id>/state.json name match. The reaper never enumerates
#     ~/.claude/jobs/*; it acts solely on ids this hook recorded.
#   - A per-key in-flight marker dedups concurrent dispatches.
#
# Recursion guard: CLAUDE_MD_LINT_PARENT is exported into the child and
# `--setting-sources ""` keeps the child from loading the settings file
# that registers this hook (verified primary defence under `--bg`).
#
# The skill body (/etc/claude-code/skills/claude-md-lint/SKILL.md) is injected via
# --append-system-prompt so the child gets the evaluation criteria; the
# child reads each target file itself with the Read tool.
#
# Stdin : SessionStart payload JSON (uses .cwd).
# Stdout: SessionStart hook JSON only when a completed lint is surfaced
#   (a HIT). systemMessage marks completion; additionalContext carries
#   the findings. Every no-op terminal state (re-entry guard, missing
#   skill body, no candidate files, async dispatch, in-flight dedup,
#   stale cleanup) produces empty stdout.

set -u

PROG_NAME="$(basename "$0" .sh)"
readonly PROG_NAME
readonly CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/${PROG_NAME}"
readonly INFLIGHT_DIR="${CACHE_DIR}/.inflight"
readonly STAGING_DIR="${CACHE_DIR}/.staging"
readonly SKILL_MD="/etc/claude-code/skills/claude-md-lint/SKILL.md"
readonly MAX_HOPS=5
# Identifies this hook's background sessions. The reaper only stops/rm's
# a session whose jobs/<id>/state.json "name" equals this exact string.
readonly BG_NAME="claude-md-lint"
# Bounds only the dispatch call (cold-starting the per-user supervisor
# can take tens of seconds); the lint itself then runs detached.
readonly BG_DISPATCH_TIMEOUT_S=60
# An in-flight key whose staging file never appears within this window
# is treated as a dead bg job: its session is reaped and the marker is
# cleared so a later session can re-dispatch. Comfortably above a normal
# ~60-90 s lint, below the ~1 h supervisor idle-retire.
readonly BG_STALE_S=1800
# Delay before the dispatcher's own detached pass runs. It is a single
# safe reap_inflight pass (conditional on staging-present/stale, name-
# guarded, idempotent with the SessionStart reaper), so a finished bg
# session is torn down within this window even when no new session
# starts. Firing too early is a harmless no-op — an unfinished lint has
# no staging file yet, so it is left running and never killed. The
# user-suggested ~3 min is the default; tune freely.
readonly BG_SELF_REAP_S=180
# Mixed into the cache key. Bumping it intentionally invalidates every
# existing cache file — used here because the execution model and cache
# format changed from the synchronous `claude -p` JSON-envelope era.
readonly CACHE_KEY_SALT='claude-md-lint cache v2 (bg/staging)'
readonly SYSTEM_MSG='セッション開始時の CLAUDE.md チェックが完了しました'

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

# Turn completed staging files into cache files and tear down their bg
# sessions. Iterates only this hook's own in-flight markers, never the
# global jobs directory.
reap_inflight() {
  [[ -d "$INFLIGHT_DIR" ]] || return 0
  command -v claude >/dev/null 2>&1 || return 0
  local f ik iid iname its now age staging cf fmt ts
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
    staging="${STAGING_DIR}/${ik}.txt"
    cf="${CACHE_DIR}/${ik}.txt"
    if [[ -f "$staging" ]]; then
      printf -v ts '%(%Y-%m-%dT%H:%M:%S%z)T' -1
      {
        printf '%s\n\n' "$ts"
        printf 'claude-md-lint async result (key %s)\n' "$ik"
        printf '\n-------- findings --------\n\n'
        if [[ -s "$staging" ]]; then
          printf '%s\n' "$(<"$staging")"
        else
          printf 'なし\n'
        fi
      } >"${cf}.tmp" 2>/dev/null
      if [[ -s "${cf}.tmp" ]]; then
        mv -f "${cf}.tmp" "$cf" 2>/dev/null || rm -f "${cf}.tmp" 2>/dev/null
      else
        rm -f "${cf}.tmp" 2>/dev/null
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

# --- detached self-reap entry ----------------------------------------------
#
# The dispatcher spawns `"$0" --reap-pass` via setsid after a delay. This
# mode runs one reap_inflight pass and exits: it never reads stdin, never
# dispatches, and is idempotent with the SessionStart reaper (a session
# already gone leaves no state.json, so _reap_session no-ops; a `claude
# rm` that races a concurrent removal is swallowed by `|| true`).
if [[ "${1:-}" == "--reap-pass" ]]; then
  reap_inflight
  exit 0
fi

# --- re-entry guard ---------------------------------------------------------

if [[ -n "${CLAUDE_MD_LINT_PARENT:-}" ]]; then
  exit 0
fi

# Without the skill body file there is nothing to inject — bail out
# silently rather than firing a degraded lint. -s requires a non-zero
# size; -r verifies the running uid can read it.
[[ -s "$SKILL_MD" && -r "$SKILL_MD" ]] || exit 0

# --- stdin payload → cwd ----------------------------------------------------

payload="$(cat 2>/dev/null || true)"
[[ -z "$payload" ]] && payload='{}'
cwd="$(jq -r '.cwd // empty' <<<"$payload" 2>/dev/null || true)"
[[ -z "$cwd" ]] && cwd="$PWD"

# Process finished/stale background jobs before this run's lookup, so a
# just-completed result can HIT within this same invocation.
reap_inflight

# --- collect input files ----------------------------------------------------

candidates=(
  /etc/claude-code/CLAUDE.md
  "${HOME}/.claude/CLAUDE.md"
  "${cwd}/CLAUDE.md"
  "${cwd}/.claude/CLAUDE.md"
)

declare -A seen=()
declare -A content_of=()
queue_paths=()
queue_depths=()

for f in "${candidates[@]}"; do
  if [[ -f "$f" ]]; then
    queue_paths+=("$f")
    queue_depths+=(0)
  fi
done

while ((${#queue_paths[@]} > 0)); do
  cur="${queue_paths[0]}"
  d="${queue_depths[0]}"
  queue_paths=("${queue_paths[@]:1}")
  queue_depths=("${queue_depths[@]:1}")

  resolved="$(realpath -e "$cur" 2>/dev/null || true)"
  [[ -z "$resolved" ]] && continue
  [[ -n "${seen[$resolved]:-}" ]] && continue
  ((d > MAX_HOPS)) && continue

  body="$(cat "$resolved" 2>/dev/null || true)"
  [[ -z "$body" ]] && continue

  seen[$resolved]=1
  content_of[$resolved]="$body"

  # @ references: extract via grep -E (POSIX), strip leading non-@ chars,
  # then strip the leading '@'. Avoids PCRE lookbehind. (Pre-existing
  # verified extraction — kept as-is under the surgical-change rule.)
  refs="$(grep -oE '(^|[^[:alnum:]_@])@[^[:space:])]+' <<<"$body" 2>/dev/null \
    | sed -E 's/^[^@]*@//')"

  while IFS= read -r ref; do
    [[ -z "$ref" ]] && continue
    if [[ "$ref" == "~"* ]]; then
      ref_path="${ref/#\~/$HOME}"
    elif [[ "$ref" == "/"* ]]; then
      ref_path="$ref"
    else
      ref_path="$(dirname "$resolved")/${ref}"
    fi
    ref_path="$(realpath -e "$ref_path" 2>/dev/null || true)"
    [[ -z "$ref_path" ]] && continue
    [[ "$ref_path" == *.md ]] || continue
    # Auto-memory index files are rewritten almost every session; keying
    # the lint cache on them makes it miss perpetually. Lint the CLAUDE.md
    # chain only — skip @-refs into global-memory / per-project memory.
    case "$ref_path" in
      */global-memory/*|*/projects/*/memory/*) continue ;;
    esac
    queue_paths+=("$ref_path")
    queue_depths+=($((d + 1)))
  done <<<"$refs"
done

((${#seen[@]} == 0)) && exit 0

# --- cache key (claude version + salt + skill body + paths + contents) ------

sorted_paths="$(printf '%s\n' "${!seen[@]}" | sort)"

key="$(
  {
    claude --version 2>/dev/null || echo unknown
    printf '%s\n' "$CACHE_KEY_SALT"
    cat "$SKILL_MD" 2>/dev/null
    while IFS= read -r p; do
      printf '%s\0' "$p"
      printf '%s\n' "${content_of[$p]}"
    done <<<"$sorted_paths"
  } | sha256sum 2>/dev/null | cut -c1-16
)"

[[ -z "$key" ]] && exit 0

cache_file="${CACHE_DIR}/${key}.txt"

# --- cache lookup or async dispatch -----------------------------------------
#
# Cache file (written by the reaper from a completed staging file):
#
#   <timestamp>
#   claude-md-lint async result (key <key>)
#
#   -------- findings --------
#
#   <findings, one per line, or "なし">
#
# The reader only needs the last separator line followed by the findings
# block; per-file content is no longer embedded (the model writes only
# its judgement to the staging file, deterministic layout stays in bash).
# The legacy bare "----" separator is still accepted so any pre-existing
# cache file keeps parsing.

findings=""
if [[ -f "$cache_file" ]]; then
  # Cache hit: everything after the last separator line is the findings
  # block. Skip the decorative blank line, trim trailing newlines.
  findings="$(awk '
    /^(----+|-+ .+ -+)$/ { buf = ""; after = 1; next }
    after && /^$/ { next }
    { after = 0; buf = buf $0 "\n" }
    END { sub(/\n+$/, "", buf); printf "%s", buf }
  ' "$cache_file" 2>/dev/null || true)"
else
  # MISS: dispatch a detached bg lint, record an in-flight marker, and
  # surface nothing this session (the reaper handles the result later).
  command -v claude >/dev/null 2>&1 || exit 0
  mkdir -p "$CACHE_DIR" "$INFLIGHT_DIR" "$STAGING_DIR" 2>/dev/null
  inflight="${INFLIGHT_DIR}/${key}"
  # Atomic claim: under noclobber the redirection creates the marker iff
  # it is absent, so only one of N concurrent SessionStart hooks
  # dispatches a bg job for this key. The subshell scopes the option.
  if ! ( set -o noclobber; : >"$inflight" ) 2>/dev/null; then
    exit 0
  fi

  paths_block=""
  add_dirs=()
  declare -A dir_seen=()
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    paths_block+="- ${p}"$'\n'
    dd="${p%/*}"
    if [[ -z "${dir_seen[$dd]:-}" ]]; then
      dir_seen[$dd]=1
      add_dirs+=(--add-dir "$dd")
    fi
  done <<<"$sorted_paths"

  staging="${STAGING_DIR}/${key}.txt"
  rm -f "$staging" 2>/dev/null
  skill_body="$(cat "$SKILL_MD" 2>/dev/null)"
  user_prompt=$'以下のファイルを Read tool で読み、評価観点に従って判定してください。\n\n出力は stdout でなく Write tool で次のファイルに書いてください:\n'"$staging"$'\n内容は findings を 1 行 1 件、無ければ「なし」の 1 語のみ。JSON や前置き・後置きの散文は書かない。\n\n対象ファイル:\n'"$paths_block"

  # `claude --bg`: detached, subscription-billed. acceptEdits auto-allows
  # the Write tool non-interactively (bypassPermissions needs a one-time
  # interactive disclaimer that a hook cannot give). --setting-sources ""
  # keeps the child from re-registering this hook. The dispatch call
  # returns a short id and exits; the lint runs under the supervisor.
  out="$(
    CLAUDE_MD_LINT_PARENT=1 timeout "$BG_DISPATCH_TIMEOUT_S" \
      claude --bg \
        --name "$BG_NAME" \
        --model claude-haiku-4-5-20251001 \
        --effort high \
        --setting-sources "" \
        --strict-mcp-config \
        --tools Read,Write \
        "${add_dirs[@]}" \
        --add-dir "$STAGING_DIR" \
        --permission-mode acceptEdits \
        --append-system-prompt "$skill_body" \
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
    # setsid fully detaches it from this hook's process group so it
    # survives the hook exiting; a disowned subshell is the fallback.
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
fi

# --- emit hook JSON (reached only on a cache HIT) ---------------------------
#
# A completed lint is being surfaced, so systemMessage always marks
# completion. When findings exist they are injected via
# hookSpecificOutput.additionalContext for the parent Claude to report.
# Refs: https://code.claude.com/docs/en/hooks (SessionStart fields).

findings="$(printf '%s' "$findings" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"

if [[ -z "$findings" || "$findings" == "なし" ]]; then
  jq -n --arg msg "$SYSTEM_MSG" '{systemMessage: $msg}' 2>/dev/null
  exit 0
fi

greeting=$'## CLAUDE.md lint レポート\n\nsession 起動時に auto-load される CLAUDE.md チェーン（org / user / project と @-import）を `/claude-md-lint` で lint した結果:\n\n'"$findings"$'\n\n最初のユーザーメッセージへの応答冒頭で、上記を 3 行以内で簡潔に伝えてください（findings を要約 + 詳細はユーザー要求時のみ）。それ以降は通常のセッションとして進めてください。'

jq -n --arg ctx "$greeting" --arg msg "$SYSTEM_MSG" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}, systemMessage: $msg}' 2>/dev/null

exit 0
