---
name: subagent-gate
legacy: org CLAUDE.md ワークフローの統制 § 4. サブエージェント より
description: >
  subagent (Agent / Task tool) 起動前に、 4 条件のいずれかに該当するか確認する: 並列実行可能 / output 大量 / 3 query 以上の探索 / 専門 agent 領域。
  起動 overhead (context 切り替え / 結果統合 / token コスト) より小さい lookup には使わない。
  TRIGGER when: Agent / Task tool を spawn しかけた瞬間;
  「subagent で〜」「並列に分けて」「Explore / code-reviewer / security-review / general-purpose を起動」 と書き出そうとしたとき;
  大量 output が予想される処理を main context で受けるか subagent に分離するか迷ったとき。
  SKIP: 単一ファイルの Read; 1 query で完結する grep / find; 自分が直接見て即判断したい中間状態 (git status / ls -la / ファイル先頭数十行 等)。
---

# Subagent Gate

subagent 起動には context 切り替え / 結果統合 / token コストの overhead がある。 小さい lookup でこれを払うのは無駄。 以下 4 条件のいずれかに該当する時のみ起動する。

## Use subagents when ANY of these holds

- **(a) 並列実行できる独立タスクがある**: 互いに依存しない複数 query をまとめて発射し、 wall time を短縮できる場合。
- **(b) output volume が大きく main context に取り込みたいのは結論だけ**: 巨大ログ / 大量検索結果 / 長い分析を集約し、 結論行だけを return させたい場合。
- **(c) 探索範囲が不明瞭で 3 query 以上の試行錯誤を要する**: どこに何があるか分からず、 複数 grep / Read を組み合わせる必要があるとき。 Explore subagent の出番。
- **(d) 専門 agent の領域**: 例 Explore / security-review / code-reviewer など、 専門 agent が prompt 設計上 main thread より優れている領域。

## Don't use subagents for

- 単一ファイルの Read (file path が分かっている)
- 1 query で完結する grep (symbol / 文字列が明確)
- 自分が直接見て即判断したい中間状態 (`git status` / `ls -la` / ファイル先頭 20 行確認 など)
