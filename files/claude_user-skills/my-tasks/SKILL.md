---
name: my-tasks
description: Tracks work items in a session-local JSON file when Claude task tools are gated off.
when_to_use: TRIGGER when work items must be tracked but Task tools are unavailable because of a gate. SKIP when TaskCreate, TaskUpdate, TodoWrite, or equivalent Task tools are available in the session.
---

# My Tasks

Task ツールが gate で使えないセッションに限り、同等の作業追跡を session-local JSON で代替する。

## Process

1. task JSON を書く前後に、`~/.claude/projects/*/${CLAUDE_CODE_SESSION_ID}.jsonl` の各 transcript へ `claude_court_guard <transcript>` を実行する。contamination を検出した場合は H.S. に session reset を促す。
2. `drafts/tasks/${CLAUDE_CODE_SESSION_ID}.json` を読む。ファイルまたは親 directory が無ければ作成する。
3. JSON 配列を read-modify-write し、作業項目を追加または更新する。新規追加時は `created` を現在日時 (`date '+%Y-%m-%d %H:%M'`) で記録する。サブタスクは親 id にダッシュを付けた id (`1-1`, `1-2`) とする。
4. 着手時は対象を `in_progress`、完了時は `completed`、依存待ち等は `blocked` に更新する。
5. 作業一覧の報告は id 昇順で各項目を `<id> <emoji> <content> (<created>)` 形式で出力し、サブタスク (`1-1` 等) は親の下に 2 space 字下げする。emoji は status に対応: 新規(`pending`)=🔳 / 作業中(`in_progress`)=▶️ / ブロック(`blocked`)=🚧 / 完了(`completed`)=✅。

## Rules

- 各要素は `{id, content, status, activeForm, created}`。`status` は `pending`(新規)/`in_progress`(作業中)/`blocked`(ブロック)/`completed`(完了)。id は top-level が `1`,`2`…、サブタスクが `1-1`,`1-2`…。
- TodoWrite semantics に従い、常に `in_progress` は 1 件だけにする。別項目へ着手する前に現在の項目を `completed` にする。
- `drafts/` は gitignore 対象の一時的な追跡領域として扱い、この JSON を commit しない。
