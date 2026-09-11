---
name: subagent-gate
description: Before spawning a subagent, verify one of four conditions holds (parallelizable / large output / 3+ query exploration / specialized agent domain); avoid for lookups smaller than the spawn overhead.
when_to_use: TRIGGER when about to spawn an Agent / Task tool, say "subagent で" / "並列に分けて" etc, or uncertain whether to route a large-output task via subagent. SKIP for single-file Read, single-query grep / find, or direct state inspection.
---

# Subagent Gate

subagent 起動には context 切り替え / 結果統合 / token コストの overhead がある。 小さい lookup でこれを払うのは無駄。 以下 4 条件のいずれかに該当する時のみ起動する。

## Rules

### Use subagents when ANY of these holds

- **(a) 並列実行できる独立タスクがある**: 互いに依存しない複数 query をまとめて発射し、 wall time を短縮できる場合。
- **(b) output volume が大きく main context に取り込みたいのは結論だけ**: 巨大ログ / 大量検索結果 / 長い分析を集約し、 結論行だけを return させたい場合。
- **(c) 探索範囲が不明瞭で 3 query 以上の試行錯誤を要する**: どこに何があるか分からず、 複数 grep / Read を組み合わせる必要があるとき。 Explore subagent の出番。
- **(d) 専門 agent の領域**: 例 Explore / security-review / code-reviewer など、 専門 agent が prompt 設計上 main thread より優れている領域。

### Choose the model before spawning

起動する時は `model` を毎回明示する。 未指定は親 model の無検討継承 (最高コスト model で search / review を回す) になる。

- search / grep 集約 / 要約 / 形式的 review: `haiku` か `sonnet`
- 設計判断や難しい root-cause 解析など判断が要る仕事: `opus` 以上、 検討の結果 親と同じ model を選ぶのも可 (その場合も名前を明示する)
- fork (`subagent_type: "fork"`) は親 model 固定なので指定不要

## What to leave out

- 単一ファイルの Read (file path が分かっている)
- 1 query で完結する grep (symbol / 文字列が明確)
- 自分が直接見て即判断したい中間状態 (`git status` / `ls -la` / ファイル先頭 20 行確認 など)

## Related

- **Legacy:** org CLAUDE.md ワークフローの統制 § 4. サブエージェント より
- **Hook 補助:** mechanical proxy 判定は `subagent_gate_warn.py` (PreToolUse:^(Task|Agent)$) / `subagent_gate_suggest.py` (UserPromptSubmit) が補助し、 `subagent_model_gate.py` (PreToolUse:^(Task|Agent)$) が `model` 未指定の spawn を deny する。 hook reminder を見たら本 skill 4 条件 (a-d) のいずれが該当か verbalize する。
