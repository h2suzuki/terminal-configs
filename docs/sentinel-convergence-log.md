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
| 裁定の機械化 | 完了 | 2026-08-12 | `55c618e` で main へ取り込み (区分 B は refactor 後) |
| 構造 refactor | 進行中 | 2026-08-13 | 第 1 段 (期限 gate funnel 化) を codex sol xhigh へ発注・走行中 |
| TOCTOU harness | 未着手 | — | refactor 完了後 |
| 体制と収束認定 | 未着手 | — | 柱完了後に 54 巡目 |
| 方法論 doc (`docs/adversarial-review-methodology.md`) | 完了 | 2026-08-13 | 発散機構 M1–M6 / 設計 G・L・R / モデル選定 / チェックリスト |
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

### 2026-08-12 — 裁定の機械化を codex へ発注

- 発注書 `drafts/sentinel-pillar2-order.md` (codex_order_lint rc=0。初回 rc=1 —
  「## 成果物」節と「触らない path」の欠落を lint が検出し、発注前に修正)
- 内容: 47 裁定を A (今すぐ機械検査可能) / B (構造変更後に可能) / C (挙動 test) / D (プロセス) に
  分類して `docs/sentinel-rulings.md` に収載 + 区分 A の meta-test (allowlist 方式・行番号付き
  違反報告・最低 5 検査: splitlines 禁止 / EXIT_CONTRACT literal / time.time() allowlist /
  open 系 allowlist / mock.patch 対象の実在) を selftest へ追加 + 1 検査 1 変異の検証。
  実装の挙動変更・既存 test 変更は禁止
- 起動: worktree `wt-p2` (HEAD `84b2f51`)、job `task-msq5cdku-8yvr2b`、
  record の model / effort が `gpt-5.6-sol` / `medium` と発注どおりであることを起動直後に確認。
  write probe は起動 5 秒で出現。監視は `files/codex_task_sentinel` (estimate 2700s /
  stall 900s / timeout 7200s) を background 実行

### 2026-08-12 — 裁定の機械化: 納品受領・受け入れ検証

- 所要は発注の見積もりバンド内 (発注 22:49 → 報告書 22:57)。sentinel は **exit 5
  (成果物なし完了)** で返った — 報告書が `REPORT_COMPLETE\n\n` と token の後に空行 1 行を
  持ち、「最終行は token の 1 行」の契約に厳密不適合のため。not ready 判定は sentinel の
  仕様どおり (書きかけと完成の機械判別)。課題: 発注書に「書き終えたら終端 byte を自己確認する」
  step を入れると、この種の 1 byte 逸脱は納品側で消える
- 納品: `files/codex_task_sentinel` へ末尾追加 186 行のみ (実装・既存 test への変更ゼロを
  `git diff` の hunk 位置で確認)、`docs/sentinel-rulings.md` 全 47 裁定を逐語 + 区分
  (A3 / B12 / C30 / D2) + 担保 test 名で収載
- meta-test 5 本: splitlines 禁止 / EXIT_CONTRACT literal / time.time() allowlist
  ({watch} のみ、deadline_reached・sleep_until の不在も assert) / open 系 allowlist
  (os.open@open_regular のみ) / mock.patch 対象の実在。全て allowlist 方式・違反行番号付き。
  既存 loader (line 1783) が class 名 "WatchTest" を固定しているため、既存 code に触れない
  継承 shadowing (`class WatchTest(WatchTest)`) で 249 tests に載せた
- 変異検証 5/5 catch (報告書に `Ran 249 tests` 行つきで転記)
- 発注側の自己再実行で gates 全緑を確認: selftest **249 OK** (rc=0) / 外部 11 OK / ruff /
  ty / `claude_lang_lint --repo wt-p2 --allow docs/sentinel-rulings.md` rc=0
- codex session 棚卸し: companion status running 0 件
- opus 5 xhigh の敵対レビューを Workflow (`wf_d5afdae3-6f2`) で起動 — 健全性 (alias 迂回・
  _owners 帰属・非走査構文) / 分類の反証 / shadowing 検証 / scope 検証の 4 観点

### 2026-08-12 — 裁定の機械化: 敵対レビュー結果と fix round

opus 5 xhigh のレビュー (10.7 分・122k tokens) が **8 件 (material 3 / minor 5)** を、
全件 replay した evidence 付きで返した:

1. (material) splitlines 検査は receiver が Name の時しか捕まえない —
   `handle.read().splitlines()` / alias / `(body or "").splitlines()` を素通し。
   **実装者 (codex) の変異検証は「自分の検査が捕まえられる唯一の形」だけを試していた**
   (自己確認バイアス。変異の選定を実装者に任せた発注側の課題でもある)
2. (material) rulings doc の裁定 10 の担保 test が誤帰属 — 正しい test
   (`test_an_uncounted_baseline_does_not_license_a_stall`) は実在するのに未引用
3. (material) 裁定 34 も同型の誤帰属 (正しい test は実在・未引用)
4. (minor) open 検査が io.open / codecs.open / Path().open を非走査
5. (minor) patch.object 検査が「対象 object の属性」でなく module 名簿と突合 (現 3 site が
   全て module 対象という偶然で緑) + import 束縛名が名簿に無く将来の正当 patch を誤 fail
6. (minor) _owners の除外が名前一致 (`_state` 等) で、将来の production 同名関数を無条件免除
7. (minor) 裁定 16・31・35 の担保が部分的 (16 は 4 上限中 1 つのみ引用等)
8. (minor) 裁定 11 (strict UTF-8) は今の機構でそのまま機械化可能なのに (C) 止まり —
   区分 (A) が発注書の名指し 3 件ちょうどで止まった

レビューの checked: scope (186 行追加のみ・実装変更ゼロ) / 249 tests 重複なし /
shadowing の意味変化なし — いずれも問題なしと独立確認。

fix round 1 を同 thread resume で発注: `drafts/sentinel-pillar2-fixes.md`
(codex_order_lint rc=0。初回 rc=1: 裁定列挙・kill-by-port 文言・command fence の 3 件を
lint が検出し発注前に修正)。job `task-msq6fa1n-9zh2tb` (sol / medium / write 確認済)。
今回から報告書終端の自己確認 (`tail -c 20`) を発注書の完了条件に追加。

ユーザー指示 (同日): /simplify を都合のよいタイミングで実行する — fix round 受け入れ +
commit 直後に予定 (走行中 codex との moving-target 回避)。

### 2026-08-12 — 裁定の機械化: fix round 受け入れと /simplify

fix round 1 は sentinel **exit 0** で完了 (終端 token の自己確認手順が機能し、前回の
exit 5 と同種の逸脱は再発せず)。受け入れ検証: diff は末尾 1 hunk のまま (計 273 行追加・
削除 0)、selftest **250** (新検査 `test_lossy_decode_call_sites_are_allowlisted` 追加) /
外部 11 / ruff / ty / lang lint 全緑を自己再実行で確認。rulings doc の誤帰属 (裁定 10・34)・
部分担保 (16・31・35) の訂正を列単位で確認。**発注側の独立変異** (codex の list に無い
「呼び出しを伴わない `str.splitlines` 参照」) も catch — 検査の網は列挙形を超えて機能する。
opus 指摘の minor 2 件 (patch.object resolver / _owners) は「誤検出方向にしか壊れない
(fail loud)」ため受容して close。

/simplify (ユーザー指示) を commit 前に実行 — 4 観点並列 (Reuse / Simplification /
Efficiency / Altitude、計 176k tokens)。所見は強く収束: 適用 8 件 (memo 化 / ast 配管廃止 /
allowlist 3 本の骨格統一 / _owners 縮約 / 恒真 assert 削除 / patch-target の runtime 一本化 /
dead AnnAssign 除去 / SourceInvariantTest 分離 + 1 行溶接)、不適用 2 件 (walk 統合は診断価値
優先で efficiency 観点自身が現状維持推奨 / patch.object 非 self-module 分岐の削除は opus
指摘 5 の修正を逆転するため保持)。恒真 assert 2 行は発注書が明示要求したものだが、
独立レビュー 2 観点が「情報量ゼロ」で一致したため削除を裁定 (意図は comment 化)。

round 2 を同 thread resume で発注: `drafts/sentinel-pillar2-simplify.md` (lint rc=0・初回)。
**受け入れ条件 = 全 12 変異の再検証** (整理が網を破っていない証明)。job
`task-msq748d5-l3r8ta` (sol / medium / write 確認済)。

### 2026-08-12 — 裁定の機械化: 完了・main 取り込み

round 2 は sentinel exit 0。A〜H 全適用 (SourceInvariantTest 分離 + 1 行溶接 /
`_bad_call_lines` 統一 / memo 化 / runtime 一本化ほか)、**12 変異すべて再 catch**。
受け入れ再検証: gates 全緑 (selftest 250 / 外部 11 / ruff / ty / lang lint)、追加 hunk は
指示した `import ast` 1 行と末尾 block のみ、発注側の独立変異 (12 件に無い `codecs.open`)
も catch。commit `c8e0fb3` (wt-p2) → cherry-pick `55c618e` で main へ、main 上でも 250 OK。
報告書 3 本を `drafts/` へ退避後、wt-p2 worktree と branch を削除。

3 round の収支: 発注 1 + 敵対レビュー 1 (opus 5 xhigh・8 件) + fix 1 + /simplify 適用 1 で
**指摘残ゼロ・網の後退ゼロ**のまま収束。53 巡ループとの対比: fix が新規指摘を生む前に
同 round 内で変異検証 + 独立変異 + レビューを閉じる運用が機能した。deploy
(`/usr/local/bin/codex_task_sentinel`) は依然ユーザー手動待ち (todos.md 既存 criterion)。

### 2026-08-13 — 方法論 doc の確立と deploy 完了

- `docs/adversarial-review-methodology.md` を執筆 (Fable・effort max)。構成: 実測対比
  (53 巡 vs 3 round) / 発散機構 M1–M6 (スペックのレビュー内発見・site 多重度・
  sampler/enumerator 混同・検証の自己設計・tripwire 不在・自作自演起点) / 収束設計
  (gate G1–G4・運用 L1–L6・役割 R1–R3) / opus 5 の扱い (交絡の明示と write/review path
  分離の測定設計) / UI project への移植 / チェックリスト 11 項
- 品質保証: 数値照合 agent が定量主張 約 69 件を典拠 2 doc + git 実測と突合 — 63 件一致、
  修正 4 件 (所要 2.5h→約 1h [commit 時刻実測] / 「毎巡 2–6 件」を終盤 15 巡に限定 /
  逃げ道 4→3 / 規模数値の典拠を git 実測と明記)。典拠側の内部不整合 1 件 (「self 率は単調
  上昇」— 実表は 73%→50% の谷あり) の引き写しを端点表記に修正。document-editor cleanup
  pass 12 箇所 (jargon 初出定義・label 統一、内容不変)
- deploy 完了 (ユーザー実行・2026-08-13 00:05): `/usr/local/bin/codex_task_sentinel` が
  canonical (meta-test 込み `55c618e`) と `diff -q` IDENTICAL・mode 0755 を確認

### 2026-08-13 — 構造 refactor 第 1 段 (期限 gate funnel 化) を発注

- 発注書 `drafts/sentinel-refactor-s1-order.md` (codex_order_lint rc=0・初回)。方法論を適用:
  段を最小化 (funnel のみ・ついで restructure 禁止) / funnel の契約を発注書に明文化
  (期限後は exit 7 のみ + 裁定 27 の exit 6 例外) / 12 site の差分は「黙って統一せず開示」/
  変異 5 件は発注側が選定 (M4 対策) / 波及 10 test 超なら停止して報告 (r49 対策) /
  正規表現一括置換の禁止 (r48 対策)。meta-test 2 本 (funnel 経由強制・gate 集約) で
  裁定 18・21・27 を B→A 化する
- 起動: worktree `wt-p1s1` (HEAD `fbda658`)、job `task-msqas0pl-36n734`、record で
  **sol / xhigh / write** を確認 (refactor のみ xhigh へ昇格はユーザー承認済)。probe 5 秒。
  監視 sentinel (estimate 4500s / stall 900s / timeout 10800s) を background 実行

### 2026-08-13 — 第 1 段 納品受領・発注側裁定・レビュー起動

- sentinel exit 0 (終端自己確認が 2 round 連続で機能)。納品: 286+/137- (watch() funnel 化 +
  meta-test 2 本 + rulings doc 18/21/27 の B→A)。**変更した既存 test は 0 本** — 250 test が
  無改変で緑のまま、が挙動保存の主証拠。指定 5 変異すべて catch (報告書に `Ran N tests` 付き)
- 受け入れ再検証 (発注側): gates 全緑 (selftest **252** / 外部 11 / ruff / ty / lang lint)、
  独立変異 (到達不能な裸 `return 0` を watch() 冒頭へ) も meta-test が行番号付きで catch
- 開示 5 件への発注側裁定: (1) gate と return の間の時刻窓で挙動が exit 7 側へ変わる境界 —
  **funnel 契約を採用し受理** (裁定 21 の意図どおり。旧挙動が潜在バグ側)。(2) resolved_unknown
  境界の timeout 表示に隣接 site 文面 — 受理。(3) 非終局の継続判定に probe 形
  `finish(deadline, EXIT_ALIVE, (), ())` — 単一 site 維持のトレードオフとして受理
  (使われ方の正誤はレビュー対象に指定)。(4) 手順逸脱 2 件 (初回検索を repo 全体へ・
  py_compile の pyc 一時生成→削除済) — 永続影響なしで受理、記録のみ。(5) 発注書が例示した
  `observed_late` 変数は実在せず (発注側の記述不正確)、codex は rename せず既存分岐を維持 — 適切
- opus 5 xhigh の敵対レビューを Workflow (`wf_9730ce10-9d3`) で起動 — 12 site の意味保存 /
  finish() の pass-through と表示順 / probe の使われ方 / 例外 flag の閉じ / 終局経路の全数 /
  meta-test の AST 強度、の 6 観点。発注側の裁定済み 3 件は指摘対象から除外指定

### 2026-08-13 — 第 1 段 レビュー結果 (material 0) と fix round

opus 5 xhigh レビュー (13.7 分・140k tokens) は **material 0 / minor 5**。checked が厚い —
12 site の 1 対 1 対応表・probe 6 箇所の比較演算子・終局経路の全数 (return 17 箇所すべて
funnel 経由・raise/sys.exit なし)・meta-test の AST 判定を 10 形で in-memory 実測・
表示順の不変・scope、まで独立確認され、**挙動保存はレビューアの実測で確証**。minor 5 件:

1. 期限 gate が旧 code に無かった site は開示された 1 件でなく 3 件 (ambiguous /
   seen-earlier / resolved_unknown) — 2 件の新設文面が未開示で、うち 1 件は `searched:` 行を
   欠き site 間で不揃い
2. probe 使用の開示が 5 件 (実際は 6 件 — site 12 の 1772 が漏れ)
3. 裁定 27 の B→A 昇格に実体なし (exit 6 例外を 1 site に閉じる AST 検査が無い)
4. meta-test 1 が probe 形 return (無音終局) を素通し — 将来の複写事故の穴
5. finish の parameter 名 `verdict` が module 関数 verdict() を shadow

全 5 件の fix round を同 thread resume で発注 (`drafts/sentinel-refactor-s1-fixes.md`、
lint rc=0・初回)。変異 2 件 (probe 形 return / 例外 flag の複製) は発注側選定。
job `task-msqc0nus-w6owj8` (sol / xhigh / write 確認済)。レビューアの指摘 1 と 2 は
「実装者の開示が不完全でもレビューアが全数を数え直す」二重化が機能した実例として記録する。
