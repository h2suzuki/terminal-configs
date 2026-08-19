---
name: memory-sync
description: Inspect and drive the git-backed shared memory clone via the claude_memory_sync CLI (status, pull, retire, full reindex).
when_to_use: TRIGGER when the user asks for memory sync state ("/memory-sync", "sync 状態", "push できてる?", "memory の同期"), wants shared memory entries pulled now, retires a memory entry, or after a diverged/broken clone was fixed. SKIP for writing new memory entries (memory-routing) and for surface precision analysis (memory-surface-analyzer).
---

# Memory Sync

memory entry の canonical store は private GitHub repo で、共有 clone
`/var/lib/claude-rag-memory/memory-repo` はその local buffer。日常の同期は自動
(SessionStart hook が throttled background pull、entry Write 後の gate が
commit + detached push) なので、本 skill は状態確認と手動介入のためにある。

## Process

1. まず状態を見る:

   ```bash
   claude_memory_sync --status
   ```

   clone の有無 / branch / fetch 可否 / push・pull 残数 / 未 commit 数 /
   最終 pull 時刻 / push 失敗 stamp / scope 別 entry 数と index 行数が出る。

2. 必要な操作を選ぶ:

   | 目的 | コマンド |
   |---|---|
   | 今すぐ他デバイスの entry を取り込む | `claude_memory_sync --pull` |
   | entry を退役 (削除 + commit + push + index 削除) | `claude_memory_sync --retire <abs_path>` |
   | index を clone から全再構築 (災害復旧) | `claude_memory_sync --full` |
   | 溜まった未 push commit を再送 | `claude_memory_sync --push-bg` |

3. 実行後は `--status` を再表示して結果 (to push = 0 等) を確認する。

## Rules

- **fail-open を前提に読む**: fetch FAILED / push failing は故障ではなく buffer
  mode。entry の書込・検索は clone だけで動き続け、復旧後の push/pull で追い付く
- **push 失敗が続く時の一次切り分けは `gh auth status`**: https 認証は
  /etc/gitconfig の `gh auth git-credential` helper 経由なので、gh が未認証だと
  pull/push だけが失敗する
- **diverged (pull failed が続く) 時**: 自動 rebase が中断された状態。clone 内で
  `git -C /var/lib/claude-rag-memory/memory-repo pull --rebase --autostash` を
  実行して conflict を手で解消 → `claude_memory_sync --full` で index を揃える
- **clone MISSING/BROKEN**: `install_claude_extensions` の再実行が唯一の復旧手順
  (clone 専用 subcommand は持たない設計)
- **--retire は順序を内蔵**: git rm → commit → push → index --delete の順を CLI
  が保証するので、手で `git rm` と `--delete` を分けて打たない

## Related

- `memory-routing` — entry の新規作成 / 保存先 routing / 書式 (write 側)
- `memory-surface-analyzer` — surface 精度の backtest (読み側の評価)
