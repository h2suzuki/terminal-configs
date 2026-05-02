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
# Stdin: SessionStart payload JSON (uses .cwd).
# Stdout: JSON with hookSpecificOutput.additionalContext, or empty.

set -u

readonly CACHE_DIR="${HOME}/.claude/cache/claude-md-lint"
readonly MAX_HOPS=5
readonly TIMEOUT_S=90

# --- re-entry guard ---------------------------------------------------------

if [[ -n "${CLAUDE_MD_LINT_PARENT:-}" ]]; then
  exit 0
fi

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

# --- cache key (sorted paths + contents + claude version) -------------------

sorted_paths="$(printf '%s\n' "${!seen[@]}" | sort)"

key="$(
  {
    claude --version 2>/dev/null || echo unknown
    while IFS= read -r p; do
      printf '%s\0' "$p"
      printf '%s\n' "${content_of[$p]}"
    done <<<"$sorted_paths"
  } | sha256sum 2>/dev/null | cut -c1-16
)"

[[ -z "$key" ]] && exit 0

cache_file="${CACHE_DIR}/${key}.txt"

# --- cache lookup or run lint ----------------------------------------------

report=""
if [[ -f "$cache_file" ]]; then
  report="$(cat "$cache_file" 2>/dev/null || true)"
else
  prompt_body=""
  while IFS= read -r p; do
    prompt_body+="## ${p}"$'\n\n'"${content_of[$p]}"$'\n\n---\n\n'
  done <<<"$sorted_paths"

  prompt=$'/claude-md-lint\n\n以下が session start で auto-load される memory file 群です。skill の評価観点に従って判定してください。\n\n'"$prompt_body"

  report="$(
    CLAUDE_MD_LINT_PARENT=1 timeout "$TIMEOUT_S" \
      claude -p --model claude-haiku-4-5-20251001 "$prompt" </dev/null 2>/dev/null || true
  )"

  if [[ -n "$report" ]]; then
    mkdir -p "$CACHE_DIR" 2>/dev/null
    printf '%s' "$report" >"$cache_file" 2>/dev/null || true
  fi
fi

# --- emit additionalContext if any findings ---------------------------------

report="$(printf '%s' "$report" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
[[ -z "$report" || "$report" == "なし" ]] && exit 0

greeting=$'## CLAUDE.md / memory lint レポート\n\nsession 起動時に auto-load される memory file 群（CLAUDE.md チェーン、MEMORY.md、`@` 参照）を `/claude-md-lint` skill で lint した結果:\n\n'"$report"$'\n\n最初のユーザーメッセージへの応答冒頭で、上記レポートを 3 行以内で簡潔に伝えてください（findings list を要約 + 詳細はユーザーが要求した時のみ展開）。それ以降は通常のセッションとして進めてください。'

jq -n --arg ctx "$greeting" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}' 2>/dev/null

exit 0
