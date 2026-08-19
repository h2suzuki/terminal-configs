---
name: memory-sync
description: Inspect and drive the git-backed shared memory clone via the claude_memory_sync CLI (status, pull, retire, full reindex), and run the one-time migration of legacy local memory into the clone.
when_to_use: TRIGGER when the user asks for memory sync state ("/memory-sync", "sync 状態", "push できてる?", "memory の同期"), wants shared memory entries pulled now, retires a memory entry, after a diverged/broken clone was fixed, or migrating legacy local memory dirs into the clone ("移行", "吸い上げ", "旧メモリ", "~/.claude/memory"). SKIP for writing new memory entries (memory-routing) and for surface precision analysis (memory-surface-analyzer).
---

# Memory Sync

memory entry の canonical store は private GitHub repo で、共有 clone
`/var/lib/claude-rag-memory/claude-lessons-learned` はその local buffer。日常の同期は自動
(SessionStart hook が throttled background pull、entry Write 後の gate が
commit + detached push) なので、本 skill は状態確認と手動介入のためにある。

## Process

1. まず状態を見る:

   ```bash
   claude_memory_sync --status
   ```

   clone の有無 / branch / 最終 fetch 時刻 / fetch 可否 / push・pull 残数 /
   未 commit 数 / scope 別 entry 数と index 行数が出る。
   引数無し実行も同じ出力 (`--help` subcommand は無い)。

2. 必要な操作を選ぶ:

   | 目的 | コマンド |
   |---|---|
   | 今すぐ他デバイスの entry を取り込む | `claude_memory_sync --pull` |
   | entry を退役 (削除 + commit + push + index 削除) | `claude_memory_sync --retire <abs_path>` |
   | index を clone から全再構築 (災害復旧) | `claude_memory_sync --full` |
   | 溜まった未 push commit を再送 | `claude_memory_sync --push-bg` |

3. 実行後は `--status` を再表示して結果 (to push = 0 等) を確認する。

## Legacy migration (旧ローカルメモリの吸い上げ)

installer (clone + 初回 full index) 実行済みのマシンに旧ローカルメモリ
(`~/.claude/memory/`・`~/.claude/projects/<enc>/memory/`) が残っている場合、
以下を **1 entry ずつ** 実施する。一括 move / 一括 import / 一括 re-scope は禁止
(2026-08-19 に bulk 再配置で scope 混乱を起こした実例がある)。

適用判定: 下記が何も出力しなければこのマシンは対象外 (完了済み or 元々未使用) で、
以降の手順は不要。`*.pre-git` だけが出る場合は手順 7 の承認後削除だけが残っている。

```bash
ls -d ~/.claude/memory ~/.claude/memory.pre-git \
      ~/.claude/projects/*/memory ~/.claude/projects/*/memory.pre-git 2>/dev/null
```

0. **環境の最新化**: terminal-configs repo を `git pull` し、base setup
   (ubuntu2404-wsl.sh / debian12.sh) を再実行してから始める — 本 skill・hook・CLI が
   旧版のまま吸い上げると手順の即興と旧形式 project id の混入が起きる。鮮度の機械確認:
   `~/.claude/hooks/memory_surface.py --project-id` が id を 1 行出力すること
   (旧版に無い subcommand なので、error なら未更新)。吸い上げは 1 マシンずつ行い、
   他マシンの memory 書込作業と並行させない
1. **対象の列挙**: 旧 dir の `feedback_*.md` を list する
   (`find ~/.claude/memory ~/.claude/projects/*/memory -name 'feedback_*.md' 2>/dev/null`)。
   `MEMORY.md` / `OLD-MEMORY.md`
   は roster (旧方式の名簿) であって entry ではない。**OLD-MEMORY.md 収載 = 退役済み**
   なので取り込まない
2. **突合**: entry ごとに `~/.claude/hooks/memory_surface.py --search "<要旨>"` で clone の
   既存 entry と比較する (model filter 無しの全 scope 検索)
3. **マージ vs 新規の判断**: hit 候補の reminder と本文を読み、「**同じ行動を正す教訓か**」
   で決める。文言が違っても是正指示が同じ → 既存へマージ (`models:` に観測モデル tag を
   追記し、固有の事例・絶対日付を本文へ追記)。正す行動や状況が異なる → 新規。
   **迷ったら新規** (誤マージの分離は難しいが、重複は後から retire が容易)
4. **保存先の判断**: 新規の scope は memory-routing skill で判定する (org = user 非依存 /
   user = 個人情報を含む / project = project 固有)。反映はすべて memory-routing の
   grant + Write 経由 (auto-sync が commit + push + index まで行う)
5. **project id は --project-id で導出する**: 旧 `~/.claude/projects/<enc>/memory/` の
   `<enc>` は旧方式 (cwd encode)。対応する project dir を引数に
   `~/.claude/hooks/memory_surface.py --project-id <project_dir>` を実行して得た id の
   `project/<id>/` へ入れる (origin URL 正規化形なので user・checkout path に依存しない。
   remote 無し repo・非 git dir では旧 enc と同値に fallback)。暗算で id を導出しない
6. **検証**: 旧 entry 全件が「マージ済 / 新規作成済 / 退役済で対象外」のいずれかに分類し
   尽くされたことを一覧で確認し、`--status` で entries と index の一致を見る
7. **後始末**: 旧 dir を `<dir>.pre-git` に rename し、ユーザー承認を得てから削除する

## Rules

- **fail-open を前提に読む**: fetch FAILED / push failing は故障ではなく buffer
  mode。entry の書込・検索は clone だけで動き続け、復旧後の push/pull で追い付く
- **push 失敗が続く時の一次切り分けは `gh auth status`**: https 認証は
  /etc/gitconfig の `gh auth git-credential` helper 経由なので、gh が未認証だと
  pull/push だけが失敗する
- **diverged (pull failed が続く) 時**: 自動 rebase が中断された状態。clone 内で
  `git -C /var/lib/claude-rag-memory/claude-lessons-learned pull --rebase --autostash`
  を実行して conflict を手で解消 → `claude_memory_sync --full` で index を揃える
- **clone MISSING/BROKEN**: `install_claude_extensions` の再実行が唯一の復旧手順
  (clone 専用 subcommand は持たない設計)
- **--retire は順序を内蔵**: git rm → commit → push → index --delete の順を CLI
  が保証するので、手で `git rm` と `--delete` を分けて打たない

## Related

- `memory-routing` — entry の新規作成 / 保存先 routing / 書式 (write 側)
- `memory-surface-analyzer` — surface 精度の backtest (読み側の評価)
