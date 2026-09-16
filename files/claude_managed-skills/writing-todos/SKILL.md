---
name: writing-todos
description: Keep todos.md a short summary of unfinished work that spans sessions — one line per work item with its resume point; details live in last-session-handoff.md (or a GitHub issue when available), in-session work lives in Tasks.
when_to_use: TRIGGER when about to Read / Edit / Write todos.md, record work that will continue in a later session, or write carry-over items while closing open Tasks at handoff. SKIP for projects without todos.md or TODO comments in source code.
---

# Todo Writing

repo top の `todos.md` は、 session を跨いで引き継ぐ未完了作業の概要だけを置く場所。 台帳・backlog・設計メモ置き場にすると肥大化してゴミ溜めになるので、 詳細は別の場所へ置く。

## Process

1. **session 中**: 作業は Task で追う。 todos.md には触らない
2. **handoff で open Task を閉じる時**: 次 session へ持ち越す作業ごとに、 詳細を `last-session-handoff.md` の節へ書き、 todos.md に「未完了」の概要を 1 項目置く (既にあれば再開点を更新する)。 GitHub が使えるなら issue に起こして番号で置いてもよい
3. **作業が終わった時**: 成果物・テスト結果・commit を実際に確かめてから、 todos.md の項目を削除して commit し、 `last-session-handoff.md` の対応節も同時に削除する (`last-session-handoff.md` は gitignore 対象なので commit には入らない)

## Rules

### 置き場所の振り分け

| 内容 | 置き場所 |
|---|---|
| session 内で終わる作業 | Task (TaskCreate / TaskUpdate。 Task tool が gate off なら mytask MCP)。 todos.md に書かない |
| session を跨ぐ未完了作業の概要 | todos.md に 1 項目 |
| その作業の詳細 (状態・次の action・必読・注意) | repo top の `last-session-handoff.md` (handoff skill が書く) |
| GitHub issue が使える repo の作業 | issue に起こして正本にしてよい。 todos.md は issue 番号と再開点の 1 行にする。 GitHub は使えるとは限らないので必須にしない |
| 設計メモ・計測結果・判断の経緯 | commit message / issue / `last-session-handoff.md` |
| 教訓・注意書き | memory entry か skill |
| 完了した作業 | どこにも残さない (項目を削除する。 記録は git 履歴と commit message) |

### 項目の書式

```markdown
# Todos

- drafts/ 対策の git 側 — 再開点: 共通 ignore と pre-commit の採否をユーザーが判断
- #42 タブアイコン退行 — 再開点: 修正案 2 の実機確認から

詳細は last-session-handoff.md
```

- 1 項目は `- <作業名 または #issue 番号> — 再開点: <一言>`。 続きの行は 2 字下げで、 1 項目 3 行まで
- ファイル全体で 30 行まで。 優先度の節・Goal・Exit Criteria・checkbox・起票行・Work file 欄は使わない
- 判断を書くなら、 決裁 / 承認 / 合意 / 採用 を含む項目に「…」のユーザー発話の引用か「提案中」等の非決定 marker を添える
- 上の 3 点は `todos_structure_gate.py` hook が todos.md の commit 時に検査する

## Related

- `handoff` — `last-session-handoff.md` の書式と、 持ち越し項目を todos.md へ置く手順
- `commit-discipline` — todos.md の更新を含む commit の粒度とタイミング
- `verify-before-claim` — 「終わった」と判断して項目を消す前の確認
- `todos_structure_gate.py` hook (PreToolUse:Bash) — todos.md を commit する時にファイル行数・項目行数・判断の引用を検査する
