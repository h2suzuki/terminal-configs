---
name: tool-role-delegation
description: Route work to the right executor when codegraph/codex are available — search/exploration via codegraph, implementation above the delegation boundary via codex (/codex:rescue), bounded work via Claude or a subagent — while Claude owns spec, implementation direction, bug-finding, and review of the result.
when_to_use: TRIGGER when about to search / explore code, write or edit source, start a feature, or say "実装する" / "コードを書く" / "検索" / "探す". SKIP for trivial Q&A, doc-only edits, or when codex / codegraph are unavailable / unauthenticated.
---

# Tool Role Delegation

codegraph / codex が使える環境での役割分担 (managed CLAUDE.md「ツールに役割委譲」の運用)。 codex の駆動法詳細は plugin 同梱 skill (codex-cli-runtime など) と `codex-delegation` skill (発注書・worktree 隔離・監視・受け入れ) が持つので、 本 skill は役割の振り分けと往復手順に絞る。

## Process

1. **検索は codegraph を優先**: コード探索は codegraph を Grep / Read より先に使う。
2. **Claude が仕様・指示を書く**: 何を作るか・どう直すか・受入基準を Claude が明文化する。
3. **委譲判定は境界で決める (既定は委譲しない)**: 2 file 以下かつ 50 行以下かつ 方針一意・検証 1 回・15 分以内 なら委譲しない。 3 file 以上、 100 行以上、 または edit-test-inspect 3 周以上で委譲を開始する。 その間は 6 軸 (能動工数・境界の明確さ・検証可能性・並列化価値・隔離性・文脈可搬性、 各 0–2 点) の合計 10 点以上で委譲する。 10 分未満・単純検索・単一コマンド・小修正は委譲しない。
4. **委譲する時は `/codex:rescue <spec>`**: 定型で境界が狭い仕事は `--model gpt-5.6-luna` (Luna)、 曖昧・横断・高リスクは `--model gpt-5.6-sol` (Sol、 effort の上限は `xhigh`)。 長時間は `--background`、 進捗 `/codex:status`、 結果 `/codex:result`、 中断 `/codex:cancel`。 前回 run の継続は `--resume`、 仕切り直しは `--fresh`。 spec は Goal / Scope / Constraints / Done when / Return の 5 項目で書く。 5 項目に圧縮できず会話文脈の再掲が要る時は `/codex:transfer` をユーザーに提案する (Claude は起動できない)。
5. **委譲しない時の担い手**: Claude が直接処理する。 subagent-gate の 4 条件のいずれかを満たす時だけ subagent を使い、 機械的で境界が明確な作業は sonnet、 設計判断・レビュー・裁定を含む作業は opus。 effort は既定を継承し、 review / judgment 層だけ上げる。
6. **Claude がレビュー**: codex が返したコードを敵対的 / 受け入れレビューし、 バグ・仕様逸脱・副作用を検査する。 patch 反映も Claude が行う (実装でなくレビューの一部)。 回帰レビューは opus subagent (発注書のみ渡す・effort 高) を milestone (機能完成 / test 成功 / commit・PR 形成 / merge 前) で回し、 毎 edit 後には回さない。
7. **高リスク変更は cross-model 第二レビュー**: auth・認可・data-loss・migration・retry・idempotency・race・rollback・cache 整合性に触れる変更は規模不問で `/codex:adversarial-review` (Sol xhigh) を追加する。 ユーザー指示時も同様。 それ以外で codex の敵対レビューを既定にしない。

## Rules

- **codegraph のツール選択**: `codegraph_explore` (自然言語 / symbol 群から関連 source)、 `codegraph_search` (symbol の位置)、 `codegraph_callers` / `codegraph_callees` / `codegraph_impact` (呼出元 / 呼出先 / 変更の波及)、 `codegraph_node` / `codegraph_files` (個別 symbol / file)。 intent に合うものを選ぶ。
- **codex 未認証 / 利用不可時は Claude が直接**: 委譲できないので degrade して Claude が進める。 担い手は Process 5。
- **役割境界を守る**: 委譲した実装は codex、 仕様・指示・バグ出し・レビューは Claude。 patch 反映や review 指摘の修正は「レビューの反映」であって Claude の実装ではない。
- **委譲境界の数値 (2026-08-27 ユーザー決裁)**: 委譲しない = 2 file 以下かつ 50 行以下、 委譲開始 = 3 file 以上または 100 行以上。 gate に載せる決定値は file 数と行数で、 分・周回数は判断指針。 境界を主観で広げる (「これぐらい trivial」) のが自作癖の入口であり、 境界内の作業を委譲して固定費 (発注書・監視・レビュー) を払うのも損。
- **統治原則 (2026-08-21 ユーザー明示)**: 実装 token は本当に価値ある部分に使う。 既に部品があるならそれを使い、 部品の再構築はよほどの理由がある時にユーザー承認を得てから行う (承認なしの再構築は理由の良し悪しに関わらず禁止)。

## Output

検索は codegraph の適切なツール、 境界超えの実装は `/codex:rescue` 委譲 → Claude レビュー、 境界内は Claude 直接か subagent、 高リスクは `/codex:adversarial-review` 追加、 milestone で opus subagent の回帰レビュー。

## Related

- `codex-delegation` — 委譲後の lifecycle (発注書・worktree 隔離・監視・受け入れ)。
- `subagent-gate` — Claude 内 subagent への分岐判定。 本 skill は外部 executor (codegraph / codex) への分岐で同根。
- `make-plan-before-coding` — 委譲前の spec 明文化はこの skill の設計合意に依拠。
- `writing-code` — 永続ファイル汎用 rule (「No dangling-prone references in persistent files」 等)。
