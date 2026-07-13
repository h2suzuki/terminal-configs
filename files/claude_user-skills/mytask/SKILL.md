---
name: mytask
description: Tracks work items through the mytask MCP when Claude task tools are gated off.
when_to_use: TRIGGER when work items must be tracked but Task tools are unavailable because of a gate. SKIP when TaskCreate, TaskUpdate, TodoWrite, or equivalent Task tools are available in the session.
---

# My Task

Task ツールが gate で使えないセッションに限り、mytask MCP で同等の作業追跡を行う。データは session-local に保存され commit しない。

## Process

1. `mcp__mytask__TaskCreate` で作業項目を登録する。サブタスクは `parent` に親 id を渡す。
2. 着手時は `mcp__mytask__TaskUpdate` で `in_progress`、依存待ちは `blocked`、完了時は `completed` に更新する。
3. `mcp__mytask__TaskList` で一覧を確認する。court bug の汚染警告が前置されたら、作業を止めて H.S. に session reset を促す。

## Rules

- TodoWrite semantics に従い、常に `in_progress` は 1 件だけにする。`TaskUpdate` で新項目を着手すると、前の `in_progress` は自動で `pending` に降格される。
- rendering・emoji・完了 12h 非表示・court-guard 検査は MCP が内部で行う。この skill 側で再現しない。
