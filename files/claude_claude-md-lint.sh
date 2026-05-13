#!/bin/bash
# /etc/claude-code/claude-md-lint.sh
#
# SessionStart hook — cross-project lint of auto-loaded CLAUDE.md /
# MEMORY.md / @-imported memory files. Read-only; flags duplications
# with system prompt, internal contradictions, stale references, and
# unclear directives. Output goes into the session as additionalContext.
#
# Re-entry guard: CLAUDE_MD_LINT_PARENT env var. The child `claude -p`
# inherits it; the child's hook sees it and exits silently.
#
# Architecture note: the hook resolves the candidate file paths but
# does NOT inline their contents into the prompt. The skill body
# (/etc/claude-code/claude-md-lint.md) is injected via
# --append-system-prompt and the child claude reads each file itself
# via Read tool. This is required because `claude -p` does not
# auto-resolve `/skill-name` slash commands at the start of a prompt
# — the skill's instructions need to land in the child's system
# prompt explicitly.
#
# Stdin: SessionStart payload JSON (uses .cwd).
# Stdout: SessionStart hook JSON. When the lint ran successfully:
#   - `systemMessage` is always set (visible "completed" confirmation)
#   - `hookSpecificOutput.additionalContext` is added only when findings exist
# When the hook is a no-op (re-entry guard, missing skill body, no candidate
# files, child claude validation failure), stdout is empty.

set -u

# Cache directory follows the same XDG-aware rule as voicevox_paplay:
# $XDG_CACHE_HOME/<prog-name>, falling back to ~/.cache/<prog-name>
# when the env var is unset or empty. The .sh suffix is stripped so
# the cache subdir name reflects the tool's identity rather than its
# implementation language.
readonly PROG_NAME="$(basename "$0" .sh)"
readonly CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/${PROG_NAME}"
readonly SKILL_MD="/etc/claude-code/claude-md-lint.md"
readonly MAX_HOPS=5
# 150 s leaves headroom over the empirically observed ~60–90 s
# variance for --effort high lints; once a result is cached, repeat
# session starts return instantly so the longer cap costs nothing on
# the steady-state path.
readonly TIMEOUT_S=150
# JSON Schema passed to `claude -p --json-schema`. The child model's
# final answer is validated against this and surfaced under
# `.structured_output` in the --output-format json envelope, removing
# the need for ad-hoc fenced-code / substring fallback parsers. The
# shape mirrors what the skill body (/etc/claude-code/claude-md-lint.md)
# specifies for "JSON mode".
readonly JSON_SCHEMA='{"type":"object","properties":{"scanned":{"type":"array","items":{"type":"string"}},"findings":{"type":"array","items":{"type":"string"}}},"required":["scanned","findings"],"additionalProperties":false}'
readonly SYSTEM_MSG='セッション開始時のメモリチェックが完了しました'

# --- re-entry guard ---------------------------------------------------------

if [[ -n "${CLAUDE_MD_LINT_PARENT:-}" ]]; then
  exit 0
fi

# Without the skill body file there is nothing to inject — bail out
# silently rather than firing a degraded lint. -s requires a non-zero
# size (so a half-installed empty file doesn't slip through); -r
# verifies the running uid can actually read it.
[[ -s "$SKILL_MD" && -r "$SKILL_MD" ]] || exit 0

# --- stdin payload → cwd ----------------------------------------------------

payload="$(cat 2>/dev/null || true)"
[[ -z "$payload" ]] && payload='{}'
cwd="$(jq -r '.cwd // empty' <<<"$payload" 2>/dev/null || true)"
[[ -z "$cwd" ]] && cwd="$PWD"

# --- collect input files ----------------------------------------------------

project_id="${cwd//\//-}"
mem_path="${HOME}/.claude/projects/${project_id}/memory/MEMORY.md"

candidates=(
  /etc/claude-code/CLAUDE.md
  "${HOME}/.claude/CLAUDE.md"
  "${cwd}/CLAUDE.md"
  "${cwd}/.claude/CLAUDE.md"
  "${mem_path}"
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
  # then strip the leading '@'. Avoids PCRE lookbehind.
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
    queue_paths+=("$ref_path")
    queue_depths+=($((d + 1)))
  done <<<"$refs"
done

((${#seen[@]} == 0)) && exit 0

# --- cache key (sorted paths + contents + skill body + claude version) ------

sorted_paths="$(printf '%s\n' "${!seen[@]}" | sort)"

key="$(
  {
    claude --version 2>/dev/null || echo unknown
    printf '%s\n' "$JSON_SCHEMA"
    cat "$SKILL_MD" 2>/dev/null
    while IFS= read -r p; do
      printf '%s\0' "$p"
      printf '%s\n' "${content_of[$p]}"
    done <<<"$sorted_paths"
  } | sha256sum 2>/dev/null | cut -c1-16
)"

[[ -z "$key" ]] && exit 0

cache_file="${CACHE_DIR}/${key}.txt"

# --- cache lookup or run lint ----------------------------------------------
#
# Cache file format (text, human-inspectable):
#
#   <ISO 8601 timestamp>
#
#   スキャン対象:
#   - <path1>
#   - <path2>
#
#   -------- <path1> --------
#
#   <content of path1>
#
#   -------- <path2> --------
#
#   <content of path2>
#
#   -------- findings --------
#
#   <findings, one per line, or "なし">
#
# Findings live after the last separator line so they can be extracted by
# tail-after-marker without parsing JSON back. The timestamp is for
# human inspection only — it is NOT part of the cache key (see hash
# above). The reader also accepts the legacy bare "----" separator so
# pre-existing cache files keep parsing after the format change.

findings=""
if [[ -f "$cache_file" ]]; then
  # Cache hit: everything after the last separator line is the findings block.
  # Skip the decorative blank line that always follows the separator, and
  # trim trailing newlines so the result is the findings body alone.
  findings="$(awk '
    /^(----+|-+ .+ -+)$/ { buf = ""; after = 1; next }
    after && /^$/ { next }
    { after = 0; buf = buf $0 "\n" }
    END { sub(/\n+$/, "", buf); printf "%s", buf }
  ' "$cache_file" 2>/dev/null || true)"
else
  # Build a path-list user prompt and a deduplicated --add-dir list for
  # every directory holding a target file. The child claude reads each
  # file via Read tool; --permission-mode bypassPermissions skips the
  # interactive permission prompt that --tools Read would otherwise
  # trigger on first access.
  paths_block=""
  add_dirs=()
  declare -A dir_seen=()
  while IFS= read -r p; do
    paths_block+="- ${p}"$'\n'
    d="$(dirname "$p")"
    if [[ -z "${dir_seen[$d]:-}" ]]; then
      dir_seen[$d]=1
      add_dirs+=(--add-dir "$d")
    fi
  done <<<"$sorted_paths"

  # 出力形式: JSON — keeps the skill body in JSON-mode formatting rules
  # (no markdown headers, no inline newlines per finding). The actual
  # shape is enforced separately by --json-schema below; this line just
  # selects the right branch of the skill's own output spec.
  user_prompt=$'以下のファイルを Read tool で読み、評価観点に従って判定してください。\n\n出力形式: JSON\n\n'"$paths_block"
  skill_body="$(cat "$SKILL_MD" 2>/dev/null)"

  # --effort high: empirically required. low produced 5/5 false-positive
  # findings (the model skipped the 3-axis "適用文脈の検査" step that the
  # skill body mandates and reported soft overlaps as duplicates). medium
  # is correct on judgment but ran ~82 s — uncomfortably close to the
  # 90 s TIMEOUT_S that used to apply. high lands at ~55–60 s with
  # correct judgment.
  #
  # --setting-sources "": load no settings file at all (the empty value
  # is accepted by claude). This blocks user-level SessionStart hooks
  # from re-firing (defence in depth on top of CLAUDE_MD_LINT_PARENT)
  # and stops the user's effortLevel override from leaking in.
  #
  # --output-format json --json-schema "$JSON_SCHEMA": request structured
  # outputs. The agent SDK validates the model's final answer against
  # the schema (retrying on mismatch) and returns one JSON envelope on
  # stdout with the validated payload under .structured_output. This
  # replaces the earlier "prompt-based JSON + best-effort jq recovery"
  # path and makes parsing a single jq filter.
  raw="$(
    CLAUDE_MD_LINT_PARENT=1 timeout "$TIMEOUT_S" \
      claude -p \
        --model claude-haiku-4-5-20251001 \
        --effort high \
        --setting-sources "" \
        --no-session-persistence \
        --strict-mcp-config \
        --tools Read \
        "${add_dirs[@]}" \
        --permission-mode bypassPermissions \
        --append-system-prompt "$skill_body" \
        --output-format json \
        --json-schema "$JSON_SCHEMA" \
        "$user_prompt" </dev/null 2>/dev/null || true
  )"

  [[ -z "$raw" ]] && exit 0

  # Envelope check: bail silently on validation retry exhaustion
  # (subtype = "error_max_structured_output_retries") or any other
  # non-success terminal state. structured_output is only populated on
  # success.
  if ! jq -e '.subtype == "success" and (.structured_output | type == "object")' \
       <<<"$raw" >/dev/null 2>&1; then
    exit 0
  fi

  scanned="$(jq -r '.structured_output.scanned // [] | .[]' <<<"$raw" 2>/dev/null || true)"
  findings_arr="$(jq -r '.structured_output.findings // [] | .[]' <<<"$raw" 2>/dev/null || true)"
  [[ -z "$scanned" ]] && exit 0

  # Build the new cache file content. mkdir before redirect — the temp
  # file write would otherwise fail on first-ever invocation when the
  # cache dir does not yet exist.
  mkdir -p "$CACHE_DIR" 2>/dev/null
  ts="$(date -Iseconds 2>/dev/null || date)"
  {
    printf '%s\n\n' "$ts"
    printf 'スキャン対象:\n'
    while IFS= read -r s; do
      [[ -z "$s" ]] && continue
      printf -- '- %s\n' "$s"
    done <<<"$scanned"
    while IFS= read -r p; do
      [[ -z "$p" ]] && continue
      printf '\n-------- %s --------\n\n' "$p"
      cat -- "$p" 2>/dev/null || true
    done <<<"$sorted_paths"
    printf '\n-------- findings --------\n\n'
    if [[ -z "$findings_arr" ]]; then
      printf 'なし\n'
    else
      printf '%s\n' "$findings_arr"
    fi
  } >"$cache_file.tmp" 2>/dev/null

  if [[ -s "$cache_file.tmp" ]]; then
    mv -f "$cache_file.tmp" "$cache_file" 2>/dev/null || rm -f "$cache_file.tmp"
  else
    rm -f "$cache_file.tmp" 2>/dev/null
  fi

  findings="$findings_arr"
fi

# --- emit hook JSON ---------------------------------------------------------
#
# The lint actually completed at this point (either cache hit or fresh run
# that produced valid structured output), so we always surface a
# `systemMessage` for terminal-side confirmation. When findings exist we
# additionally inject them via `hookSpecificOutput.additionalContext` so the
# parent Claude reports them at the top of its first response.
#
# JSON shape follows the SessionStart hook spec:
#   - systemMessage              → shown to the user (visible)
#   - hookSpecificOutput.*       → injected into Claude's context (hidden)
# Refs: https://code.claude.com/docs/en/hooks (SessionStart fields).

findings="$(printf '%s' "$findings" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"

if [[ -z "$findings" || "$findings" == "なし" ]]; then
  jq -n --arg msg "$SYSTEM_MSG" \
    '{systemMessage: $msg}' 2>/dev/null
  exit 0
fi

greeting=$'## CLAUDE.md / memory lint レポート\n\nsession 起動時に auto-load される memory file 群（CLAUDE.md チェーン、MEMORY.md、`@` 参照）を `/claude-md-lint` skill で lint した結果:\n\n'"$findings"$'\n\n最初のユーザーメッセージへの応答冒頭で、上記レポートを 3 行以内で簡潔に伝えてください（findings list を要約 + 詳細はユーザーが要求した時のみ展開）。それ以降は通常のセッションとして進めてください。'

jq -n --arg ctx "$greeting" --arg msg "$SYSTEM_MSG" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}, systemMessage: $msg}' 2>/dev/null

exit 0
