---
name: tool-role-delegation
description: Route work to the right executor when codegraph/codex are available — search/exploration via codegraph, implementation via codex (/codex:rescue) — while Claude owns spec, implementation direction, bug-finding, and review of the result.
when_to_use: TRIGGER when about to search / explore code, write or edit non-trivial source, start a feature, or say 「実装する」「コードを書く」「検索」「探す」. SKIP for trivial Q&A, doc-only edits, or when codex / codegraph are unavailable / unauthenticated.
---

# Tool Role Delegation

codegraph / codex が使える環境での役割分担 (managed CLAUDE.md「ツールに役割委譲」の運用)。 codex の駆動法詳細は plugin 同梱 skill (codex-cli-runtime / codex-result-handling / gpt-5-4-prompting) が持つので、 本 skill は役割の振り分けと往復手順に絞る。

## Rules

- **検索・コード探索は codegraph を Grep / Read より優先**: codegraph は知識グラフで用途別に複数ツールを持つ — `codegraph_explore` (主: 自然言語 / symbol 群から関連 source を取得)、 `codegraph_search` (symbol の位置)、 `codegraph_callers` / `codegraph_callees` / `codegraph_impact` (呼出元 / 呼出先 / 変更の波及)、 `codegraph_node` / `codegraph_files` (個別 symbol / file 単位)。 intent に合うツールを選ぶ。
- **仕様策定・実装の指示・バグ出しは Claude**: 何を作るか・どう直すかの仕様と指示、 バグの発見に Claude が専念する。
- **実装は codex へ委譲**: コードを書く作業は `/codex:rescue <spec>` で codex に渡す (長時間は `--background`、 進捗 `/codex:status`、 結果 `/codex:result`)。 達成条件・制約・対象 file・受入基準を spec に明文化する。
- **返り実装のレビューは Claude**: codex が返したコードを Claude が敵対的 / 受け入れレビューし、 バグ・仕様逸脱・副作用を検査する。 レビュー結果の patch 反映も Claude が行う (実装でなくレビューの一部)。
- **重要変更は cross-model 第二レビュー**: auth / data-loss / race / rollback 等の高リスク変更は `/codex:adversarial-review` で codex の独立レビューを追加する。
- **codex 未認証 / 利用不可時**: 委譲できないので Claude が直接進める (機能低下時の degrade)。

## Output

検索は codegraph の適切なツール、 実装は `/codex:rescue` 委譲 → Claude レビュー、 高リスクは `/codex:adversarial-review` 追加。 委譲不可時のみ Claude が直接。

## Related

- `subagent-gate` — Claude 内 subagent への分岐判定。 本 skill は外部 executor (codegraph / codex) への分岐で同根。
- `make-plan-before-coding` — 委譲前の spec 明文化はこの skill の設計合意に依拠。
- `writing-code` — 永続ファイル汎用 rule (「No dangling-prone references in persistent files」 等)。
