---
name: create-my-task
description: Tracks work items in a session-local JSON file when Claude task tools are gated off.
when_to_use: TRIGGER when work items must be tracked but Task tools are unavailable because of a gate. SKIP when TaskCreate, TaskUpdate, TodoWrite, or equivalent Task tools are available in the session.
---

# Create My Task

Task ツールが gate で使えないセッションに限り、同等の作業追跡を session-local JSON で代替する。

## Process

1. task JSON を書く前後に、`~/.claude/projects/*/${CLAUDE_CODE_SESSION_ID}.jsonl` の各 transcript へ `claude_court_guard <transcript>` を実行する。contamination を検出した場合は H.S. に session reset を促す。
2. `drafts/tasks/${CLAUDE_CODE_SESSION_ID}.json` を読む。ファイルまたは親 directory が無ければ作成する。
3. JSON 配列を read-modify-write し、作業項目を追加または更新する。
4. 着手時は対象を `in_progress`、完了時は `completed` に更新する。

## Rules

- 各要素は `{id, content, status, activeForm}` とし、`status` は `pending`、`in_progress`、`completed` のいずれかにする。
- TodoWrite semantics に従い、常に `in_progress` は 1 件だけにする。別項目へ着手する前に現在の項目を `completed` にする。
- `drafts/` は gitignore 対象の一時的な追跡領域として扱い、この JSON を commit しない。
