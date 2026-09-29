---
name: tool-role-delegation
description: Route work to the right executor — search/exploration via codegraph, implementation and tests via the implementer subagent (Sonnet 5.5, xhigh), Codex or Antigravity only when the user asks for a cross-model review — while Claude owns spec, implementation direction, bug-finding, and review of the result.
when_to_use: TRIGGER when about to search / explore code, write or edit source, start a feature, write or run tests, when the user asks for a cross-model review ("クロスモデルレビュー" / "codex でレビュー" / "agy でレビュー"), or say "実装する" / "コードを書く" / "検索" / "探す". SKIP for trivial Q&A or doc-only edits.
---

# Tool Role Delegation

codegraph・implementer subagent・Codex・Antigravity の役割分担。Codex の発注書・worktree 隔離・監視・受け入れは `codex-delegation` skill が持つので、本 skill は担い手の振り分けと往復手順に絞る。

## Process

1. **検索は codegraph を優先**: コード探索は codegraph を Grep / Read より先に使う。
2. **Claude が仕様・指示を書く**: 何を作るか・どう直すか・受入基準を Claude が明文化する。依頼文は目的・触ってよい範囲・完了条件・禁止事項 (commit しない等) を含める。
3. **実装とテストは implementer に任せる (既定)**: 仕様が決まったコード変更、テストの作成と実行、lint・型検査の指摘の修正は `subagent_type: "implementer"` で起動する。定義で Sonnet 5.5・effort xhigh に固定しているので `model` は渡さない (渡すと定義の model を上書きする)。数行の自明な修正や文書だけの編集は Claude が直接行ってよい。独立した部分は複数の implementer を並列に起動し、同じファイルに触れるなら worktree で隔離する。
4. **Claude がレビュー**: implementer が返した差分を敵対的 / 受け入れレビューし、バグ・仕様逸脱・副作用を検査する。テスト結果は報告を鵜呑みにせず、ログか再実行で確かめる。修正は依頼文に所見を書いて implementer に戻すのが既定。回帰レビューは opus subagent (依頼文のみ渡す・effort 高・実装と別 agent) を milestone (機能完成 / test 成功 / commit・PR 形成 / merge 前) で回し、毎 edit 後には回さない。実装・受け入れ・検証設計・認定を同一 agent が兼務しない (兼務は多巡 loop の再発条件)。
5. **高リスク変更は独立レビューを足す**: auth・認可・data-loss・migration・retry・idempotency・race・rollback・cache 整合性に触れる変更は、規模を問わず opus subagent の独立レビューを追加する。クロスモデルレビューが有益だと考えたら、ユーザーに提案してよい (実行はユーザーが求めた時だけ)。
6. **クロスモデルレビューはユーザーが求めた時だけ**: Codex と Antigravity は既定では使わない。求められたら次のどちらかで行う。
   - Codex: review 雛形 (`codex_order_lint --new review`) の発注書を `/codex:rescue` に渡す task。`--model gpt-6-astra --effort high` (Astra high)、報告書を書くため `--write`、code 変更は発注書で禁止する。発注から受け入れまでは `codex-delegation` skill に従う。`/codex:review` と `/codex:adversarial-review` はユーザー起動専用で、rescue subagent は review 系 subcommand を呼ばず task に変換する。
   - Antigravity: `agy -p "<発注書の絶対 path を読み、書かれたとおりにレビューして所見を返せ>" --mode plan` を裸名の単独 Bash で実行する (`agy` は sandbox 除外 command)。`--mode plan` で編集させず、所見は標準出力で受け取る。
   どちらを使うかユーザーの指定が無ければ Codex を使う。

## Rules

- **担い手の決裁 (2026-09-29 ユーザー決裁)**: 実装とテストは Sonnet 5.5 xhigh の subagent が既定。Codex は基本的に使わず、ユーザーがクロスモデルレビューを求めた時だけ使い、その時は Antigravity (`agy`) でもよい。Codex は Astra high (`gpt-6-astra`、effort `high`) を使う。
- **codegraph のツール選択**: `codegraph_explore` (自然言語 / symbol 群から関連 source)、`codegraph_search` (symbol の位置)、`codegraph_callers` / `codegraph_callees` / `codegraph_impact` (呼出元 / 呼出先 / 変更の波及)、`codegraph_node` / `codegraph_files` (個別 symbol / file)。intent に合うものを選ぶ。
- **役割境界を守る**: 実装は implementer、仕様・指示・バグ出し・レビュー・完了の認定は Claude。implementer の結果を Claude が書き直して取り込むのは「レビューの反映」の範囲に留め、実装のやり直しは implementer に戻す。
- **統治原則 (2026-08-21 ユーザー明示)**: 実装 token は本当に価値ある部分に使う。既に部品があるならそれを使い、部品の再構築はよほどの理由がある時にユーザー承認を得てから行う (承認なしの再構築は理由の良し悪しに関わらず禁止)。

## Output

検索は codegraph の適切なツール、実装とテストは implementer → Claude レビュー、数行の自明な修正と文書編集は Claude 直接、高リスクは opus subagent の独立レビュー、クロスモデルレビューはユーザーが求めた時だけ Codex (Astra high) か Antigravity。

## Related

- `subagent-gate` — subagent を起動する条件と model の選び方。implementer はその条件 (e)。
- `codex-delegation` — Codex を使うと決まった後の lifecycle (発注書・worktree 隔離・監視・受け入れ)。
- `make-plan-before-coding` — implementer に渡す仕様の明文化はこの skill の設計合意に依拠。
- `writing-code` — 永続ファイル汎用 rule (「No dangling-prone references in persistent files」 等)。
