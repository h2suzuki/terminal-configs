# codex_task_sentinel 収束対策の実行ログ

`files/codex_task_sentinel` の敵対レビュー loop を収束させるための対策の記録である。
巡ごとの指摘の集計は `docs/sentinel-review-analysis.md` にあり、本文書はそれを踏まえた
対策の内容・決定・実行結果を段階ごとに記録する。

**運用**: 決定が出るごと・1 段階終えるごとに、「実行ログ」節へ日付つきで事実 (commit id /
test 数 / 指摘件数) を追記して commit する。発注書・報告書は版管理外の `drafts/` にしか
存在せず、実際に r31〜r51 の報告書を失っている。残すべき判断と結果は必ず本文書か
`docs/sentinel-review-analysis.md` に書く。

## 収束の定義

**レビュー担当 codex (model gpt-5.6-sol / effort xhigh) の 2 巡連続指摘ゼロ** のみを収束と
認定する。これより弱い model / effort のレビューでの指摘ゼロは、見つける力が足りないだけの
「空の合格」でありうるため、収束の根拠にしない。

## 出発点 — 2026-08-12・53 巡終了時点

- code は緑: 244 selftests + 外部 11 tests、ruff / ty 通過。code の最終変更は `cbe3bf2`。
  test に守られていない修正はゼロ。
- loop は非収束: 指摘は 1〜16 巡 33 件 + 17〜53 巡 179 件。修正の効果判定は
  worsened 34 巡 / improved 0 巡、修正が次巡に生んだ指摘 93 件 (179 件の 52%)、
  self 率 (= 指摘のうち自分の修正が作り込んだ欠陥の割合) は 46〜53 巡で 88%。

## 非収束の主因 — 不変量を手で配る構造

実装モデルの能力不足ではなく、「同じ不変量を site ごとに手で配る」構造が主因と判定した。根拠:

| 根拠 | 数字 |
|---|---|
| per-site 配布型の原因タイプ (forgot + contradictory + unfinished) が全指摘の 73% | 131 / 179 件 |
| `deadline_reached()` の手書き check が watch() 内に散在 — 裁定 21 (期限判定は 1 点に集約) と乖離 | 12 箇所 (実測) |
| watch() の return | 22 箇所 (実測) |
| 内容読取経路が 指紋 / hold / 3 値 / dangling を各自実装 (r53 指摘 4 がその食い違いの実例) | 4 経路 |
| 閉じた 14 クラスの決め手はすべて機構化か全数突合 — `time.monotonic()` 化は r17 以降再発なし、patch 対象 27 種の全数突合で test-fixture / imagined は r38 以降停止 | 14 / 14 クラス |
| 癖を memory に記録するだけでは止まらない — r48 と同型の期限 gate 外 return が r52 に再演 | 4 巡後に再発 |

## 対策 (4 本柱)

裁定 (= レビューとの間で確定させた設計判断。53 巡時点で 47 件、発注書に番号つきで収載) を
含め、手配りの規律を機構に置き換える。

1. **裁定の機械化** — 47 裁定を「機械検査可能 / 挙動 test / プロセス」に分類し、機械検査可能な
   もの (splitlines 禁止・watch() 内裸 return 禁止・open() 直呼び禁止 等) を selftest 内の
   AST / grep による決定的検査にする。裁定本文は `docs/` へ移して commit する
   (現状は版管理外の発注書にのみ存在する)。
2. **構造 refactor** — watch() の return 22 箇所を単一の finish() 関数に集約し、期限 gate は
   そこにだけ置く。内容読取 4 経路を単一の Observation 層に統一する。表示は evidence() のみに通す。
3. **TOCTOU enumerator harness** — TOCTOU (= 確認してから使うまでの間に対象が変わる race) を、
   観測点 × 状態遷移 (出現 / 消失 / 差替 / 読取不能) の直積として列挙注入する harness を作る。
4. **実装・レビュー体制** — 実装 = codex (refactor は sol xhigh 推奨・通常巡は sol medium)、
   巡内レビュー = opus 5 xhigh、収束認定は「収束の定義」節のとおり。迷った判断・作れなかった
   fixture・削った行は発注書に開示して裁定を求める (53 巡時点で 6 巡連続、実質的な指摘を
   生んでいる手)。

## 柱別 status

| 対策 | 状態 | 直近更新 | 要約 |
|---|---|---|---|
| 裁定の機械化 | 進行中 | 2026-08-12 | 発注準備中 |
| 構造 refactor | 未着手 | — | 機械化の完了後 |
| TOCTOU harness | 未着手 | — | refactor 完了後 |
| 体制と収束認定 | 未着手 | — | 柱完了後に 54 巡目 |
| 方法論 doc (`docs/adversarial-review-methodology.md`) | 未着手 | 2026-08-12 | 次ターン執筆 |
| traceability 記録 (本 doc) | 進行中 | 2026-08-12 | 運用開始 |

状態が変わるたびこの表と実行ログの両方を更新する。

## 実行順

裁定の機械化 (現状の挙動を固定する meta-test を先行) → 構造 refactor → TOCTOU harness → 54 巡目の再開。

refactor は段階適用とし、1 段ごとに 244 selftest + 変異バッテリ (= バグを故意に埋め込み
test が捕捉するかを確かめる一式) の緑を確認する。一括変更は
しない — r49 の実測で、戻り値の形を変える変更は 24 test 規模の波及を出している。

## 却下した代替案

| 案 | 却下理由 (採ると増える実コスト) |
|---|---|
| 全面書き直し | 244 tests が内部関数名に結合しており、test 資産の作り直しを伴う |
| 仕様縮小 | 確定済み 47 裁定の再審理になる |
| 実装モデルの交換のみ | 最多原因 forgot (47%) を止めた実績が無い |

## 実行ログ

### 2026-08-12 — 立案・ユーザー判断待ち

53 巡の非収束分析 (上記) から 4 本柱を立案した。ユーザー判断待ちは 2 点:

1. 構造 refactor まで踏み込むか (裁定の機械化・TOCTOU harness・体制変更のみで 54 巡目に
   入る選択肢もある)
2. refactor 実装の effort を sol medium から xhigh に上げるか

判断が出るまで 54 巡目は発注しない。

### 2026-08-12 — ユーザー承認・着手

判断待ち 2 点は両方承認された: 構造 refactor を実施する / refactor 実装は codex sol xhigh。
あわせてユーザーから追加要件が 2 点出た:

1. 本 doc による記録の常時更新 (課題・効果・失敗すべて。途中の漏れ・drift を許さない)
2. 無限ループに陥った原因と、最初から収束に向かわせる loop 設計の方法論を
   `docs/adversarial-review-methodology.md` として確立する。今回の loop の起点が
   「opus 5 が codex 関連 skill を読まず自発実装した無計画 code」だった経緯
   (自作自演→無限ループの型) も構造解析の対象とする

裁定の機械化の実装は codex sol medium + opus 5 xhigh レビューと決定した
(refactor と違い自己完結の決定的 test 群のため、xhigh への昇格は不要と判断)。

課題 (柱 0 / traceability): 本 doc の追記を document-editor skill の fork へ 2 回依頼したが、
1 回目は引数の truncation で不発、2 回目は追記指示を実行せず標準 cleanup のみ走った。
追記は main 直接 Edit に切り替えた。skill 側の改善課題として残す
(内容追記の指示形式が fork に伝わらない)。
