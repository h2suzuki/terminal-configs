---
name: codex-delegation
description: Route non-trivial implementation to the Codex plugin while Claude stays on spec, review, and bug-finding; covers the delegate-vs-inline decision and the handoff/review loop.
when_to_use: TRIGGER when about to write / edit non-trivial source code, start a feature implementation, or say 「実装する」「コードを書く」「直す」. SKIP for small / mechanical edits (a few lines), applying Codex's returned patch, fixing review findings, doc / config / test-scaffold edits, or when Codex is unauthenticated / unavailable.
---

# Codex Delegation

codegraph / codex 拡張が入った環境で、 実装は codex へ委譲し Claude は仕様・レビュー・バグ出しに専念する分業を運用する skill。 codex の *駆動法* は plugin 同梱 skill (codex-cli-runtime / codex-result-handling / gpt-5-4-prompting) が持つので、 本 skill は「いつ委譲し、 いつ Claude が直接やるか」の判定と往復手順に絞る。

## Process

1. **検索は codegraph 優先**: コード探索は `codegraph_explore` を grep / 全体 Read より先に使う (codegraph MCP server instructions と同方針)。
2. **委譲 / inline を判定** (下記 Rules)。 委譲なら次へ、 inline なら Claude が直接実装。
3. **spec を書いて codex へ渡す**: 達成条件・制約・対象 file・受入基準を明文化し `/codex:rescue <spec>` で委譲 (長時間なら `--background`、 進捗 `/codex:status`、 結果 `/codex:result`)。 自然文「Codex に〜を頼む」でも起動する。
4. **返り diff を review**: codex の出力を Claude が読み、 仕様適合・バグ・副作用を検査する。 適用 (patch の取り込み) は Claude が行う = inline 編集として正当。
5. **重要変更は第二意見**: auth / data-loss / race / rollback 等の高リスク変更は `/codex:adversarial-review` で codex の独立 cross-model レビューを第二意見として併用する。

## Rules

- **委譲する (codex)**: 新規 file の書き起こし、 まとまった feature 実装、 別 model での再試行が有効な探索的実装。 → `/codex:rescue`。
- **Claude が直接やる (inline)**: 数行の小修正、 codex の返り patch 適用、 review 指摘の修正、 doc / config / test 雛形、 codex 未認証 (codex login 未実行) / 利用不可時。
- **レビューは Claude が主**: 委譲の有無に関わらず最終レビューとバグ出しは Claude が担う。 codex レビュー (`/codex:review` / `/codex:adversarial-review`) は第二意見であって代替ではない。
- **委譲しない理由を verbalize**: 非自明な実装を inline で進めると判断したら、 なぜ委譲しないか (小規模 / 未認証 / ユーザー直指示 等) を 1 文宣言してから書く。

## Output

委譲時は `/codex:rescue` の job を起動し、 返り後に Claude の review 所見を添えて報告する。 inline 時は委譲しない理由の 1 文宣言 + 通常の実装。

## Related

- `subagent-gate` — Claude 内 subagent への分岐判定。 本 skill は外部 agent (codex) への分岐で同根。
- `make-plan-before-coding` — 委譲前の spec 明文化はこの skill の設計合意に依拠。
- `writing-code` — 永続ファイル汎用 rule (「No dangling-prone references in persistent files」 等)。
