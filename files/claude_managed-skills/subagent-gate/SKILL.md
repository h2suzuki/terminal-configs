---
name: subagent-gate
description: Before spawning a subagent, verify one of five conditions holds (parallelizable / large output / 3+ query investigation via the investigator agent / specialized agent domain / implementation and tests via the implementer agent); avoid for lookups smaller than the spawn overhead.
when_to_use: TRIGGER when about to spawn an Agent / Task tool, say "subagent で" / "並列に分けて" etc, or uncertain whether to route a large-output task via subagent. SKIP for single-file Read, single-query grep / find, or direct state inspection.
---

# Subagent Gate

subagent 起動には context 切り替え / 結果統合 / token コストの overhead がある。 小さい lookup でこれを払うのは無駄。 以下 5 条件のいずれかに該当する時のみ起動する。

## Rules

### Use subagents when ANY of these holds

- **(a) 並列実行できる独立タスクがある**: 互いに依存しない複数 query をまとめて発射し、 wall time を短縮できる場合。
- **(b) output volume が大きく main context に取り込みたいのは結論だけ**: 巨大ログ / 大量検索結果 / 長い分析を集約し、 結論行だけを return させたい場合。
- **(c) 探索範囲が不明瞭で 3 query 以上の試行錯誤を要する**: どこに何があるか分からず、 複数 grep / Read を組み合わせる必要があるとき、 不具合の原因を追うとき、 公式ドキュメントや upstream issue まで確かめるとき。 既定で `investigator` agent に任せる。
- **(d) 専門 agent の領域**: 例 Explore / security-review / code-reviewer など、 専門 agent が prompt 設計上 main thread より優れている領域。
- **(e) 実装とテスト**: 仕様が決まったコード変更・テストの作成と実行は、 既定で `implementer` agent に任せる。 数行の自明な修正や文書だけの編集は親が直接行ってよい。

### Choose the model before spawning

起動する時は `model` を毎回明示する (定義で `model` を固定した investigator・implementer・scout は除く)。 未指定は親 model の無検討継承 (最高コスト model で search / review を回す) になる。 model は版番号つきの ID でなく alias (`haiku` / `sonnet` / `opus` / `fable`) で書く。 alias は Claude Code の更新に合わせて最新版を指す。

- 調査: `subagent_type: "investigator"`。 定義で `sonnet` (Claude Code が指す最新の Sonnet、 現在は Sonnet 5.5)・effort xhigh・編集不可に固定しているので `model` は不要
- 実装・テスト: `subagent_type: "implementer"`。 定義で `sonnet`・effort xhigh に固定しているので `model` は不要
- 対象が決まった読み取りだけの小仕事 (ファイルや symbol の場所の特定、 既知の 1〜数ファイル・ページ・ログからの抜き出し、 範囲の決まった入力の要約・分類・形式的 review): `subagent_type: "scout"`。 定義で `haiku` (現在は Haiku 5.5)・effort high・編集不可に固定しているので `model` は不要。 渡す入力は 100K token を十分下回る量に絞る (Haiku 5.5 は入力が 100K token を超えた要求の単価が 5 倍になる)。 収まらない量や判断が要る仕事は investigator に回す
- 設計判断や難しい root-cause 解析など判断が要る仕事: `opus` 以上、 検討の結果 親と同じ model を選ぶのも可 (その場合も名前を明示する)
- fork (`subagent_type: "fork"`) は親 model 固定なので指定不要
- built-in の Explore・general-purpose は定義に model が無く親 model を継承するので、 使うなら `model` を渡す。 検索の fan-out は scout で足りることが多い

### Choose the effort

- 定義に effort を書いた agent (investigator・implementer・scout) には `effort` を渡さない
- 定義に effort の無い agent を起動するときは、 Agent tool の `effort` を渡してよい (Claude Code v2.1.292 以降)。 渡さなければ model の既定 (Opus 5.5・Sonnet 5.5・Haiku 5.5 は medium) で動く
- Haiku は high を上限の目安にする。 xhigh・max は出力 token が high の約 2〜3 倍に増える割に正答率の上積みが小さい。 それが要る難しさなら investigator に回す

### Keep small jobs off the advisor

subagent は親に設定された advisor (この環境では Fable) を引き継ぎ、 agent ごとに外す設定は無い (anthropics/claude-code#94656。 `disallowedTools` に書いても外れない)。 advisor の 1 回の呼び出しは、 その subagent の会話全体を advisor model の単価で読み直す。 小さな仕事は advisor を呼ばないよう定義した scout に任せ、 定義の無い agent を起動する依頼文にも「advisor を呼ばず、 迷ったら報告して止まる」と書く。

## What to leave out

- 単一ファイルの Read (file path が分かっている)
- 1 query で完結する grep (symbol / 文字列が明確)
- 自分が直接見て即判断したい中間状態 (`git status` / `ls -la` / ファイル先頭 20 行確認 など)

## Related

- **Legacy:** org CLAUDE.md ワークフローの統制 § 4. サブエージェント より
- **Hook 補助:** mechanical proxy 判定は `subagent_gate_warn.py` (PreToolUse:^(Task|Agent)$) / `subagent_gate_suggest.py` (UserPromptSubmit) が補助し、 `subagent_model_gate.py` (PreToolUse:^(Task|Agent)$) が `model` 未指定の spawn を deny する。 hook reminder を見たら本 skill 5 条件 (a-e) のいずれが該当か verbalize する。
