# codex 委譲規定

codex (Claude Code 用 OpenAI Codex plugin) へ仕事を渡すか、渡すなら何をどのモデルへどう渡すかの判断基準。skill / hook / memory entry の codex 委譲に関する文言は本書から写す。

## 1. 位置づけと出典

- 出典: `drafts/claude_code_codex_delegation_guide_ja.pdf` (調査基準日 2026-08-20、plugin v1.0.6 基準) を、2026-08-27 のユーザー決裁 3 点 (非委譲時の担い手 §6 / レビューの担い手と時期 §7 / transfer の扱い §9) で修正したもの。時間・件数・行数は公式制限でなく初期運用値で、§11 の計測で補正する
- 矛盾時の優先順位: pdf > 2026-08-25 決裁 (回帰レビューは opus subagent、codex 敵対レビューは指示時と高リスク時のみ、実装は codex 固定でない) > 現行の skill / hook 文言

## 2. 中核ルール

**既定は委譲しない。** 難しい・時間がかかる・待ちが長いは委譲理由にならない。委譲するのは次の 4 条件を全て満たす仕事だけ。

| 条件 | 内容 |
|---|---|
| 自己完結 | 目的・範囲・制約・完了条件・返却形式を短い発注書 (§10) で表現できる |
| 客観的な検証 | test / build / lint / file:line / 比較表で完了を判定できる |
| 作業の隔離 | read-only、別モジュール、別 worktree で Claude との編集競合を避けられる |
| 並列化の実益 | codex 実行中に Claude が 10 分以上の独立作業を進められる |

正味削減時間 = Claude が直接行う能動工数 − (発注書作成 + 監視 + 成果レビュー + 期待手戻り + 並列化できなかった待ち)。10 分以上見込める時だけ委譲する。

### 初期閾値 (直接実行した場合の能動工数)

| 能動工数 | 原則 |
|---|---|
| 10 分未満 | 委譲しない。検索・単一コマンド・小修正は Claude が処理する |
| 10–25 分 | read-only・検証容易・並列化可能な時だけ委譲する |
| 25–60 分 | 最も効果が出る。background で実行する |
| 60 分超 | 20–45 分の独立単位に分割する。会話文脈が要るなら transfer を提案する (§9) |
| 高リスク変更 | 規模不問で Sol xhigh の独立レビュー (§3 例外) |

### 決定的境界

| 判定 | 条件 |
|---|---|
| 委譲しない | 2 file 以下 **かつ** 50 行以下 **かつ** 方針が一意・検証 1 回・15 分以内 |
| 委譲を開始する | 3 file 以上 **または** 100 行以上 **または** edit-test-inspect が 3 周以上 |

gate に載せる決定値は file 数と行数。分・周回数は判断指針。両行の間 (例: 2 file で 51–99 行) は §3 のスコアで決める。「単一 file・追加 10 行以内・test 追加なし」を境界に使わない。

## 3. 6 軸スコアと例外

| 軸 | 0 点 | 1 点 | 2 点 |
|---|---|---|---|
| 能動工数 | 10 分未満 | 10–25 分 | 25 分超 |
| 境界の明確さ | 探索的・仕様変動 | 一部未確定 | scope と対象外が明確 |
| 検証可能性 | 主観評価のみ | 部分的に検証可能 | test 等で機械判定 |
| 並列化価値 | Claude が待つ | 少量の別作業 | 10 分以上の独立作業 |
| 隔離性 | 同一 file・共有状態 | 競合を管理可能 | read-only または領域分離 |
| 文脈可搬性 | 会話履歴が必須 | 要約が必要 | 5 項目の発注書で十分 |

| 合計 | 判定 |
|---|---|
| 10–12 | 委譲する。通常は background |
| 8–9 | 条件付き。read-only 化・scope 縮小・検証追加で 10 点以上に上げてから委譲する |
| 0–7 | 委譲しない。§6 の担い手で処理するか、transfer を提案する (§9) |

Sol xhigh を選んでも発注・監視・レビューの固定費は減らない。準備度の低い仕事を強いモデルに渡しても損益は改善しない。

### 例外 (スコアに関係なく適用)

| 例外 | 条件 | 処置 |
|---|---|---|
| 独立レビュー | auth・認可・データ更新削除・migration・retry・idempotency・race・cache 整合性に触れる | 規模不問で Sol xhigh のレビュー (§7) |
| 停滞デバッグ | 有力仮説 2 つ失敗 / 1 パッチ失敗 / 15 分進展なし | `rescue --fresh` で独立推論を投入する |
| 会話文脈が重い | 発注書に圧縮すると仕様漏れが起きる | 委譲でなく transfer を提案する (§9) |

## 4. 用途別の閾値

| 用途 | 委譲しない | 委譲開始の目安 | モデル |
|---|---|---|---|
| コード調査 | 正確な検索: rg / LSP / git で 1–3 コマンド、候補 5 file 以下。意味的調査: 単一 stack trace、単一 call chain | 正確な検索: 20 file 以上、3 モジュール以上の棚卸し、結果に意味付けが要る。意味的調査: 3 サブシステム以上、3 仮説以上、または直接 20 分超 | 正確な検索は Luna xhigh。意味的調査は Luna: 証拠収集 / Sol: 統合 |
| コーディング・リファクタリング | 2 file 以下、50 行以下、方針一意、検証 1 回、15 分以内。UI を見ながら数ピクセルずつ直す、仕様判断が頻発する、Claude と同じ file を同時編集する、「作って見てから決める」探索的実装 | 3 file 以上、100 行以上、または edit-test-inspect 3 周以上 | Luna: 既存パターンに沿う API・型変更の伝播・test 追加・反復的移行 / Sol: API・DB・ドメイン横断、transaction、並行処理、auth、migration、複雑な状態機械 |
| デバッグ | Claude の探索が停滞するまでは丸投げしない | 有力仮説 2 つ失敗 / 1 回修正して症状不変 / 15 分原因が狭まらない | Luna: 100% 再現、エラー位置限定、設定・fixture・依存差、log 照合 / Sol: flaky、race、CI のみ、cache・永続状態、複数 process、retry・rollback |
| Web 調査 | 公式 1 ページ、明確な事実 1 件、3 ソース以下 | 5 ソース以上、3 製品・方式以上、release 履歴横断、または直接 20 分超 | Luna: URL・日付・version・対応状況の抽出 / Sol: 矛盾評価・安定性判断・選定。Web Search は既定で cached、最新情報は `web_search = "live"` か `--search` を明示。shell のネットワークは既定で無効 |
| Build・テスト・動作確認 | 1 コマンドを 1 回実行し exit code だけ見る (待ちが長くても能動作業がない) | 3 構成以上、flaky 確認 5 回以上、二分探索、reproduce-inspect-patch-rerun の自律反復 | Luna: matrix・deterministic failure / Sol: flaky・race・複数 service・状態依存 |
| ブラウザ・E2E | 1 フロー、主観的な見た目確認、pixel-perfect 調整 | 3 フロー以上、合計 10 操作以上、3 種類以上の viewport・role・権限 | 機械的な機能確認は codex、視覚判定は Claude か人間。隔離した port / DB / account と DOM・URL・API・DB assertion が前提 |
| コードレビュー: 通常 | 閾値未満の diff | 3 file 以上、100 行以上、public API、永続状態、I/O、非同期、error handling の変更 | 担い手は §7 (opus subagent が既定)。codex に出す時は原則 Luna、複雑変更は Sol |
| コードレビュー: adversarial | — | auth・data loss・rollback・race・retry・idempotency・cache・migration は規模不問 | Sol xhigh (§7) |
| 設計レビュー: 設計比較 | 1 案、可逆、単一 subsystem、30 分未満 | 2 案以上、不可逆性が高い、複数 subsystem、または 30 分超 | Sol xhigh。代替案・失敗モード・移行・rollback まで要求する |

## 5. Luna xhigh と Sol xhigh の使い分け

| 観点 | Luna xhigh (`gpt-5.6-luna`) | Sol xhigh (`gpt-5.6-sol`) |
|---|---|---|
| 向く仕事 | 境界が狭い、反復的、大量処理、既存パターン、客観的検証 | 曖昧、横断的、複数仮説、設計判断、高リスク |
| 開始閾値 | 直接能動工数 15 分以上、または自律 tool loop 3 回以上 | 直接能動工数 30 分以上、loop 5 回以上、または高リスク override |
| 代表例 | evidence map、型変更伝播、test 追加、互換性 matrix、定型調査 | root cause、race、transaction、auth、migration、architecture 比較 |
| 失敗半径 | 限定的。戻しやすい | 広いが、強い推論を正当化する |
| 返却物 | 一覧、差分、実行結果、未処理項目 | 結論、代替案、根拠、tradeoff、残存 risk |

- Luna → Sol の自動エスカレーションはしない。Luna で失敗してから Sol へ再発注すると読込・発注・監視・レビューが二重になる。明らかに Sol 向きなら最初から Sol
- 有効な二段構成: 第 1 段 Luna xhigh で file:line・call path・失敗 log・競合仮説を収集 → 第 2 段 Sol xhigh で証拠を統合し root cause・設計判断・最小安全 patch を決める。Luna を先に使うのは、この read-only 証拠収集を Sol の入力に再利用できる時に限る
- `--model` は俗称 (`luna` / `sol`) でなく正式 id `gpt-5.6-luna` / `gpt-5.6-sol` を渡す (俗称は gate が deny し、API も 400 で弾く)。`--effort` の上限は `xhigh` (`max` は wrapper が起動前に弾く)

## 6. 非委譲時の担い手

codex に委譲しない ≠ Claude が直接書く。subagent-gate skill の 4 条件 = (a) 並列実行できる独立タスク / (b) 出力が大きく結論だけ要る / (c) 探索範囲が不明瞭で 3 query 以上 / (d) 専門 agent の領域 — のいずれかを満たす時だけ subagent を使う。

| 状態 | 担い手 |
|---|---|
| 4 条件のどれも満たさない | Claude が直接処理する |
| 4 条件のいずれかを満たし、機械的で境界が明確 | sonnet subagent |
| 4 条件のいずれかを満たし、設計判断・レビュー・裁定を含む | opus subagent |

effort は既定を継承し、review / judgment 層だけ上げ、機械的作業は下げる。fork は会話文脈を継承して token を食うので短い作業に使わない。

## 7. レビュー規定

| 種類 | 担い手 | 時期 / 条件 |
|---|---|---|
| 回帰レビュー | opus subagent (発注書のみ渡す・effort 高・実装と同族でよい) | milestone (機能完成 / test 成功 / commit・PR 形成 / merge 前) で回す。毎 edit 後には回さない |
| codex 第二レビュー (review 雛形の発注書を rescue に task で渡す) | Sol xhigh | ユーザー指示時、または §3 例外の高リスク領域に触れる時のみ。`/codex:adversarial-review` command はユーザー起動専用 (rescue subagent は review 系 subcommand を呼ばず task に変換する、2026-08-27 実測) |
| continuous review gate (codex:setup の stop-time review gate) | — | 無効のまま。有効化すると Claude / codex の長い loop が usage limit を消費する |

- レビュー開始閾値: 3 file 以上・100 行以上・public API・永続状態・I/O・非同期・error handling の変更のいずれか
- 同族許容は別 agent が前提。実装・受け入れ・検証設計・認定を同一 agent が兼務しない (兼務は多巡 loop の再発条件)

## 8. 実運用フロー

### ルーティング

| 状態 | 選択 |
|---|---|
| 10 分未満、単純検索、単一コマンド、小修正 | Claude が直接処理する |
| 独立・検証可能・15 分以上・定型 | Luna xhigh を background 委譲 |
| 曖昧・横断・30 分以上・高リスク | Sol xhigh を background 委譲 |
| Claude が停滞し、別仮説が必要 | `rescue --fresh` |
| 前回の codex 作業を継続 | `rescue --resume` |
| 会話履歴そのものが必要 | transfer をユーザーに提案する (§9) |
| 完成済み diff の独立確認 | review 雛形の発注書で rescue に task (§7 の条件下) |

### background と監視

- 長時間・複数ステップの task と multi-file review は background が基本。Claude は非重複タスクを進め、統合可能なタイミングで status / result を 1 回確認する
- 数分ごとの polling や中間介入が要る仕事は委譲対象外。単一コマンドの長い待ちは Claude 側の background shell で処理し、codex を起動しない
- 監視・完了判定・受け入れの規律 (job record の file 直読、`codex_task_sentinel`、gates ログの再確認、`claude_lang_lint`) は codex-delegation skill の現行どおり

### 隔離

- write を伴う委譲は repo の worktree 隔離が必須。発注前に単独の `cd` で worktree へ移って session 終了まで留まり、`--cwd` でも作業 dir を明示する (codex-delegation skill)。同一 checkout 内の領域分離では足りない
- read-only の証拠収集・review は隔離不要。同一 file の同時編集・formatter・大規模置換・schema 生成は競合対象

### 代表的な起動形式

起動は codex:rescue skill 経由のみ (companion の直接起動は gate が deny)。review 系も rescue の task で出す (rescue subagent は review 系 subcommand を呼ばず task に変換する — 2026-08-27 実測)。

```
rescue --background --fresh --model gpt-5.6-luna --effort xhigh <bounded task>
rescue --background --fresh --model gpt-5.6-sol --effort xhigh <complex task>
rescue --background --resume <continue the latest codex task>
rescue --background --fresh --write --model gpt-5.6-sol --effort xhigh <review 雛形の発注書 path>
```

## 9. transfer

- `/codex:transfer` は plugin 側 `disable-model-invocation: true` でユーザーだけが起動できる。delegation gate の許可 subcommand (task / task-worker / review / adversarial-review) にも含めない (gate は変えない)
- Claude の役割は適時提案。(1) 5 項目の発注書 (§10) に圧縮できず会話文脈の再掲が要る / (2) 60 分超で 20–45 分単位に分割できない / (3) `rescue --fresh` の後も進展がない — のいずれかを検知した時点で、ユーザーがそのまま実行できる形 (`/codex:transfer` と理由 1 行) で提案する

## 10. 発注書

最小 5 項目を、`codex_order_lint --new plain|fix|review` が出す骨組み (codex-delegation skill の `template-order.md` / `template-fix-order.md` / `template-review-order.md`) の節で満たす。`codex_order_lint` は変更しない。

| 項目 | 内容 | `template-order.md` の節 |
|---|---|---|
| Goal | 達成する結果を 1 文 | 目的 |
| Scope | 対象 dir / file / feature と対象外 | スコープ |
| Constraints | API 維持、依存追加禁止、read-only、最小変更 | 適用される既存裁定、出力言語規約、実行してよい command、作業量上限 |
| Done when | 実行する test / build / lint と期待結果、変更可能範囲 | 完了条件 |
| Return | 結論、変更 file、実行した検証、残存 risk | 成果物、報告書の書式 |

5 項目で書けず、過去の判断や会話を大量に再掲するなら transfer を提案する (§9)。

## 11. 計測

委譲 1 件ごとに記録する: Direct estimate (直接行った場合の能動工数見積り) / Specification time (発注書作成) / Monitoring time (status 確認・介入・再指示) / Review time (成果物の検証・統合) / Rework time (修正・再発注・rollback) / First-pass accepted (初回成果をそのまま採用できたか) / Net saved (実際に削減できた能動時間) / Conflict (同時編集・port・DB・test data の競合) / Model・task class (Sol / Luna、調査 / 実装 / レビュー)。

| 指標 (最初の 20 件) | 合格基準 |
|---|---|
| 初回採用率 | 70% 以上 |
| 委譲 1 件あたり正味削減時間 | 中央値 10 分以上 |
| 監視介入 | 0–1 回 |
| 同時編集・環境衝突 | 0 件 |
| 再発注率 | 20% 以下 |

下回る時はモデルを強くする前に、次の順で改善する: 委譲最小工数を 15 分 → 25 分 / scope を狭める / 完了条件の機械化 / write 委譲を減らす / 会話依存タスクは transfer。
