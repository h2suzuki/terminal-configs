---
name: tool-role-delegation
description: Route work to the right executor when codegraph/codex are available — search/exploration via codegraph, implementation via codex (/codex:rescue) — while Claude owns spec, implementation direction, bug-finding, and review of the result.
when_to_use: TRIGGER when about to search / explore code, write or edit non-trivial source, start a feature, or say "実装する" / "コードを書く" / "検索" / "探す". SKIP for trivial Q&A, doc-only edits, or when codex / codegraph are unavailable / unauthenticated.
---

# Tool Role Delegation

codegraph / codex が使える環境での役割分担 (managed CLAUDE.md「ツールに役割委譲」の運用)。 codex の駆動法詳細は plugin 同梱 skill (codex-cli-runtime / codex-result-handling / gpt-5-4-prompting) が持つので、 本 skill は役割の振り分けと往復手順に絞る。

## Process

1. **検索は codegraph を優先**: コード探索は codegraph を Grep / Read より先に使う。
2. **Claude が仕様・指示を書く**: 何を作るか・どう直すか・受入基準を Claude が明文化する (実装そのものは書かない)。
3. **実装は codex へ委譲**: `/codex:rescue <spec>` で codex に渡す (長時間は `--background`、 進捗 `/codex:status`、 結果 `/codex:result`)。 spec に達成条件・制約・対象 file・受入基準を載せる。
4. **Claude がレビュー**: codex が返したコードを敵対的 / 受け入れレビューし、 バグ・仕様逸脱・副作用を検査する。 patch 反映も Claude が行う (実装でなくレビューの一部)。
5. **重要変更は cross-model 第二レビュー**: auth / data-loss / race / rollback 等の高リスク変更は `/codex:adversarial-review` で codex の独立レビューを追加する。

## Rules

- **codegraph のツール選択**: `codegraph_explore` (自然言語 / symbol 群から関連 source)、 `codegraph_search` (symbol の位置)、 `codegraph_callers` / `codegraph_callees` / `codegraph_impact` (呼出元 / 呼出先 / 変更の波及)、 `codegraph_node` / `codegraph_files` (個別 symbol / file)。 intent に合うものを選ぶ。
- **codex 未認証 / 利用不可時は Claude が直接**: 委譲できないので degrade して Claude が進める。
- **役割境界を守る**: 実装は codex、 仕様・指示・バグ出し・レビューは Claude。 patch 反映や review 指摘の修正は「レビューの反映」であって Claude の実装ではない。

## Output

検索は codegraph の適切なツール、 実装は `/codex:rescue` 委譲 → Claude レビュー、 高リスクは `/codex:adversarial-review` 追加。 委譲不可時のみ Claude が直接。

## Related

- `subagent-gate` — Claude 内 subagent への分岐判定。 本 skill は外部 executor (codegraph / codex) への分岐で同根。
- `make-plan-before-coding` — 委譲前の spec 明文化はこの skill の設計合意に依拠。
- `writing-code` — 永続ファイル汎用 rule (「No dangling-prone references in persistent files」 等)。
