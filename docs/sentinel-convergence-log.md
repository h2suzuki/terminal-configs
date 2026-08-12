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
| 構造 refactor | 完了 | 2026-08-13 | 3 段完了: `c067c0b` / `0425a28` / `265ccfe`。256 tests |
| TOCTOU harness | 完了 | 2026-08-13 | `f109f59`。反証可能 oracle・259 tests |
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

### 2026-08-13 — 第 1 段 完了・main 取り込み

fix round は sentinel exit 0、5 件全修正 + 変異 2/2 catch (probe 形 return の検出は行番号付き)。
発注側再検証: gates 全緑 (selftest **253** = 252 + 裁定 27 の新 meta-test / 外部 11 / ruff /
ty / lang lint)。commit `b0ece2f` (wt-p1s1) → cherry-pick **`c067c0b`** で main へ、main 上でも
253 OK。報告書 2 本を drafts/ へ退避後、worktree と branch を削除。

第 1 段の総括: 発注 1 + レビュー 1 (material 0 / minor 5) + fix 1 の **2 round で完了**。
期限 gate 外 return (53 巡ループ最頻クラスの 1 つ・7 件再発) は `finish()` funnel +
meta-test 3 本で構造的に作れなくなった。裁定 18・21・27 が実体のある区分 A になった。

### 2026-08-13 — 第 2 段 (Observation 層) を発注

- 発注書 `drafts/sentinel-refactor-s2-order.md` (lint rc=0・初回)。設計の契約: 読取規律
  (open・pin/hold・bounded read・指紋・3 値・dangling 祖先・解放順序) を単一 primitive へ、
  reader は内容解釈のみ (fd 系 syscall 直呼び禁止 → meta-test を fd 全般へ拡張)。
  公開 signature と戻り値の形は不変 = 既存 test 無改変が挙動保存の証拠。内部 phase A/B/C
  (record → log 系 → artifact) ごとに selftest 確認、失敗 10 本超で停止。変異 5 件は
  発注側選定 (直 os.open / path 再 stat 指紋 / 解放順序逆転 / 3 値の畳み込み / 上限外し)
- 起動: worktree `wt-p1s2` (HEAD `4288762`)、job `task-msqcff4e-0yn399`、record で
  sol / xhigh / write を確認。probe 5 秒。監視 sentinel (estimate 5400s / timeout 14400s)
- 観察 (第 2 段起動と同時刻 02:08:44): main checkout 直下に 0 byte・read-only の untracked
  file 群 (.bashrc / .gitconfig / .claude/{agents,hooks,settings.json,...} / .mcp.json 等
  21 個) が出現。名前の集合は「write job が親 checkout へ実行可能設定を植えるのを防ぐ mask」の
  典型。wt-p1s2 側には無し・mount table に該当なし・**tracked 内容への変更ゼロ**
  (`git diff HEAD` 空)。走行中 job の保護機構の可能性があるため削除は保留 —
  第 2 段の受け入れ時に消滅を確認し、残っていれば削除する
- 訂正 (受け入れ時の再調査): これは disk 残骸ではなく **Bash sandbox の namespace 投影**と
  判定。根拠: 呼び出しごとに git からの可視性が揺れ (untracked 21 個 → 0 個)、別の呼び出しでは
  repo/.claude/ が `~/.claude` の実内容 (worktrees / scheduled_tasks.json 等) を見せた =
  bind mount。削除 loop は 0 件削除で終了 (実 file への操作なし)。全 view で tracked 内容は
  不変。bind 越しに実 `~/.claude` を触るリスクがあるため sandbox 内からの操作は凍結。
  真の disk 状態はユーザーが sandbox 外の `git status` で確認できる

### 2026-08-13 — 第 2 段 納品・レビュー結果 (material 3) と fix round

納品は phase A/B/C 完走・既存 test 変更は meta-test 更新 1 本のみ・変異 5/5 catch 申告。
発注側再検証で gates 全緑 (253 / 11 / ruff / ty / lang lint)、開示 6 項 (reader 間の既存差) は
裁定裏付けありとして受理。opus 5 xhigh レビュー (16.7 分・138k tokens) は **material 3 /
minor 2**:

1. (material) open 検査が柱 2 fix round の広い matcher (任意 receiver の `.open`) を**後退**
   させ、dotted 名照合だけに — `codecs.open` が現役 bypass。**「前 round の保護を次の変更が
   静かに外す」= 53 巡ループの形 5 の再演を、レビュー層が捕捉した**
2. (material) Observation class の blanket 免除により、log / record の「指紋を path 再 stat
   から取る」変異が meta-test にも既存 suite にも素通り (artifact のみ挙動 test が捕捉)。
   codex は発注の変異 2 (log 指定) を artifact で代替し無開示 — **自己確認変異の再演** (2 度目)。
   検出盲点自体は HEAD にも在る pre-existing で、退行ではないが担保表記が過大
3. (material) 裁定 31 の B→A 昇格が過大主張 (経由しか検査していない)
4. (minor) 共有 helper `_owners` の意味変更が申告漏れ
5. (minor) `log_lines` wrapper が production caller ゼロ化 (open_regular と非一貫)

fix round 2 を発注 (`drafts/sentinel-refactor-s2-fixes.md`、lint rc=0・初回)。変異 6 件は
発注側選定。**「指定変異は指定対象で実行し、fail しなければ検出されないと開示」の規律を
発注書に明文化** (代替の無申告を禁止)。初回 resume 起動が queue 直後に無 error で failed →
規律どおり fresh thread で再発注、job `task-msqfc7tt-uob6bs` (sol / xhigh / write 確認済)。
監視 sentinel (estimate 2700s) を background 実行。

### 2026-08-13 — 第 2 段 完了・main 取り込み

fix round 2 は sentinel exit 0。5 件全修正 + **指定 6 変異が指定対象のまま全 catch** (代替なし・
新規の挙動 test 2 本 = log / record の descriptor 指紋 pin を含む)。裁定 31 は B へ戻し担保を
3 分記 (経由 = 構造検査 / 指紋 = 挙動 test / 全数性 = レビュー観点)。受け入れ再検証: gates 全緑
(selftest **255** / 外部 11 / ruff / ty / lang lint)、発注側の独立変異 (`os.fdopen` 直呼び —
codex の 6 件に無い形) も catch。commit `9c3e795` → cherry-pick **`0425a28`** で main へ、
main 上でも 255 OK。報告書 2 本退避後、worktree / branch 削除、codex session 残存 0。

第 2 段の総括: 発注 + レビュー (material 3 / minor 2) + fix の **2 round で完了**。53 巡ループ
最大クラス (読取規律の配り漏れ・forgot 系) の発生源が Observation 層 1 箇所に集約され、
reader からの fd 系 syscall 直呼びは meta-test で構造的に禁止された。レビューが「前 round の
保護の後退」と「自己確認変異」を round 内で捕捉した — 方法論 M4 / 形 5 の対策が機能した実測。

### 2026-08-13 — 第 3 段 (表示 funnel・柱 1 最終段) を発注

- 発注書 `drafts/sentinel-refactor-s3-order.md` (lint rc=0・初回)。stdout / stderr 出力 site の
  全数 audit → 正当な出口へ集約 → print / write 系の allowlist meta-test で pin。裁定 30・32・
  33・36 の担保を 3 分記 (内容 = 挙動 test / 出力 site = meta-test / 残余 = レビュー観点) し、
  過大昇格をしない (裁定 31 の教訓)。変異 3 件は発注側選定・指定対象厳守
- 起動: worktree `wt-p1s3` (HEAD `3f30e1b`)、job `task-msqfydo6-ll9ubx`、record で
  sol / xhigh / write を確認。監視 sentinel (estimate 2700s) を background 実行

### 2026-08-13 — 第 3 段 完了・構造 refactor (柱 1) 全段完了

- 第 3 段は最小納品で完了: audit の結果、**表示は既に finish() 1 site に集約済み** (第 1 段の
  副産物) で、production 変更ゼロ・追加は audit 表 + meta-test 1 本 (9 行・`_bad_call_lines`
  再利用)。裁定 30/32/33/36 は昇格なしで担保 3 分記 — 裁定 31 の過大昇格の教訓が実装側に
  効いた。変異 3/3 catch (指定対象のまま)
- 受け入れ: gates 全緑 (selftest **256** / 外部 11 / ruff / ty / lang lint)、発注側の独立変異
  (別関数への print 追加) も catch。**この段のみ opus レビューを省略し発注側レビューで代替**
  — 13 行の diff に単独レビュー round は不釣合いと判断 (認定巡が全体を掃く)。残余として
  `os.write(1, ...)` 型の exotic 出力は meta-test の対象外 (audit で開示済みの設計判断)
- commit `dc60c2f` → cherry-pick **`265ccfe`** で main へ、main 上でも 256 OK。worktree 削除

**柱 1 の総括**: 3 段 × 各 2 round 以内で完了。53 巡ループの 3 大構造要因 — 期限 gate の
手書き 12 箇所 (→ finish() 1 箇所)・読取規律の 4 経路手配り (→ Observation 1 層)・表示出口
(→ meta-test で pin) — がすべて単一 site + 機械検査になった。meta-test は柱 2 の 6 本 +
柱 1 の 6 本 = **12 本**。裁定の実効区分: A 8 件 (3/9/47/18/21/27/20 入口/40 入口)。

### 2026-08-13 — 柱 3 (TOCTOU enumerator) を発注

- 発注書 `drafts/sentinel-p3-order.md` (lint rc=0・初回)。harness 契約を発注側が設計:
  注入点 = Observation の syscall 入口 (test 側 shim のみ・実装 hook 不可) / 摂動 5 種 ×
  観測 index の全列挙 (small-scope・silent cap 禁止) / oracle 4 条 (無例外・契約 exit・
  確信的誤りなし [偽 exit 0 / 目撃後 exit 6 / 期限後の非 7]・決定性) / **shim の sanity
  check を harness に内蔵** (空振り防止) / oracle 違反は修正せず「発見」節へ (裁定は発注側)
- 起動: worktree `wt-p3` (HEAD `a1cc313`)、job `task-msqgjcm8-rvmmaa`、record で
  sol / xhigh / write を確認。監視 sentinel (estimate 5400s) を background 実行

### 2026-08-13 — 柱 3 納品受領・full sweep・レビュー起動

- 納品: harness 404 行 (test 側のみ・production 変更ゼロ)。shim = os.open/fstat/lstat/stat +
  fdopen handle の read/readline を test 中だけ patch、sanity check 二重内蔵。4 scenario 族 ×
  摂動 5 種、全 400 組合せのうち suite 所要制約 (3 倍規則) で 115 を選定実行 (**抑制 285 は
  明記** — silent cap なし)。**発見 (oracle 違反) は実行分で 0 件**。変異 3/3 catch
  (shim 無効化 → 116 fail = 空振り防止の実証)。逸脱開示 1 件 (開始時に repo root の entry
  一覧を列挙 — 内容 read なし) は受理
- 発注側検証: **scratch copy で選定を全 k に広げ full sweep 実行 — 400/400 組合せ・
  oracle 違反 0・37 秒・258 tests OK**。抑制分も一度は検証済みとなった
- opus 5 xhigh レビューを Workflow (`wf_b7050145-607`) で起動 — false-green 検査
  (期待集合の緩さ・shim の syscall 網羅・fixture 現実性・選定 logic・決定性・scope) の 6 観点

### 2026-08-13 — 柱 3 レビュー結果 (material 5) と oracle 反証可能化の fix round

opus 5 xhigh レビュー (21.1 分・151k tokens・in-memory instrumentation で k→呼び出し元の
完全 map まで実測) は **material 5 / minor 5** — この柱で最も重要な捕捉:

1. log / peer の 50 組合せは期待集合 = 到達可能集合で**反証不能** (fixture の tree_age 0 固定で
   verdict が常に None、log 観測が verdict に影響できない)
2. record の oracle は実質 exit 0 排除のみ — レビューアの実バグ変異 6 件が全部緑。裁定 44 の
   分岐は once=True では到達不能
3. 摂動集合に「同 inode で中身が伸びる」(最も普通の interleave) が無く、suite 全体で唯一
   無被覆の guard (artifact の mtime/size 前後比較) が未被覆のまま
4. 裁定 18/21 の oracle 条項は 0/115 で dead
5. appear 摂動の k が観測点に対応しない (23 組合せが同一 lstat の反復)

shim の忠実性はレビューアの二重計測で完全一致 (堅牢)。**発注側の full sweep 400/400 緑は
反証不能 oracle 上の偽の安心だった** — 「期待値は spec から導く」教訓の harness 規模での
再演であり、受け入れ変異を実装者 (と発注側) が選ぶ限界も 3 度目の露呈。fix round の受け入れ
変異 9 件は**レビューアが実証した evasion をそのまま採用** (選定 bias の排除)。

fix round 発注 (`drafts/sentinel-p3-fixes.md`、lint rc=0・初回): 期待集合の裁定からの導出表を
義務化 / 到達可能集合と一致する期待集合は不合格 / grow 摂動と時間摂動の追加 / 複数周回
fixture で裁定 44 到達 / appear の N 別実測 / 後ろ窓 k の選定。job `task-msqiarbt-qfmt20`
(sol / xhigh / write 確認済)。監視 sentinel (estimate 6300s) を background 実行。

### 2026-08-13 — 柱 3 完了・main 取り込み (全 build 柱完了)

fix round は sentinel exit 0。**導出表は全 singleton の期待 exit を裁定から静的導出** (観測
出力からの逆算でないことを明記)、レビューア実証の evasion 変異 9/9 を全 catch (4〜115
failures)、拡張後も「発見」= 0 — 今度は反証可能な oracle 上のゼロ。受け入れ再検証:
gates 全緑 (selftest **259** / 外部 11 / ruff / ty / lang lint)、発注側で変異 5 (log 縮退) を
独立再現し FAILED (failures=5) が codex 報告と一致。**受け入れ作業中に発注側自身が false
catch を 1 回作った** (splice ミスの SyntaxError による rc=1 を「Ran 259」行の誤読で捕捉と
誤認 → 再実行で発覚。handoff の警告どおりの罠。「Ran 行の存在」は同一 command の出力である
ことまで確認して初めて証拠になる)。commit `aae4478` → cherry-pick **`f109f59`** で main へ。
worktree / branch 削除・報告書 2 本退避。

**全 build 柱が完了**: 裁定の機械化 `55c618e` / 構造 refactor 3 段 `c067c0b`・`0425a28`・
`265ccfe` / TOCTOU harness `f109f59`。selftest 244 → **259**。残りは収束認定巡のみ。

### 2026-08-13 — 収束認定 1 巡目 (r54): material 2 → fix round 発注

r54 レビュー (job `task-msqje4ac-z67te6`・sol xhigh・read-only) は sentinel 完了検知、報告書
退避済 (`drafts/sentinel-review-r54-report.md`)。報告書は gates 全緑 (selftest 259 / 外部 11 /
ruff / ty) を転記し、**material 2 件**。発注側の実機 repro で裁定:

1. **指摘 1 = 縮小採用**: レビューの機構説明 (辞書順で `.` < `Z`) は不成立 — `LOG_TS` の
   capture group は `Z` を含まず、レビューが挙げた「小数なし → 小数あり (同秒)」の例は実機で
   **保持される** (repro で確認)。ただし数値 tie の表現差 (`.100` 直後の `.1`) を文字列比較が
   落とす同類の実欠陥を repro で確認 — 指し示した行の欠陥は実在し、修正案 (数値比較) も正しい。
   **機構の説明が誤りでも行は正しい**事例で、裁定には発注側の決定的 repro が必須だった
2. **指摘 2 = そのまま採用**: `state_roots("")` が既定 root 群を返すことを repro で確認。
   `check_arguments()` の空文字検査に state_root が無いことも実コードで確認

2 件とも旧来 code (53 巡 + 構造改造を生き延びた未疑前提)。新設の funnel / Observation /
harness / weld への指摘は 0 — 発注書観点 2 (一度も疑われていない前提を洗え) の成果。
認定 counter は 0 のまま (r54 不成立)。

fix round: `drafts/sentinel-r54-fixes.md` — 縮小裁定と等値保持 (tie を落とす実装は不成立) を
発注書の裁定節に明記、受け入れ変異 3 件 (文字列比較へ戻す / `if explicit:` へ戻す / 空検査
削除) は発注側選定、red 確認 (修正前 fail) を完了条件化。lint 初回 rc=1 (スコープに挙げた
レビュー報告書 path が報告書 path 検査と衝突) → スコープから外して rc=0。worktree
`wt-r54fix` @ `5711e96`。job `task-msqk36tk-hqzhzn` (record 検証: sol / medium / write /
fresh)。sentinel `bsl7v4i81` (estimate 1650s) を background 監視。

### 2026-08-13 — r54 fix round 完了・main 取り込み (selftest 265・裁定 49)

fix round は sentinel `bsl7v4i81` exit 0 (成果物 + token 確認)。報告書は red 確認
(修正前 code で追加 test 3 件 fail) と変異 3/3 検出を同一 command の `Ran 265` 行付きで転記。
受け入れ: 発注側 gates 再実行 (selftest 265 / 外部 11 / ruff / ty 全緑)、**独立変異 2 件**
(数値比較→文字列比較へ戻す / `if explicit is not None:`→`if explicit:` へ戻す) を exact-string
splice で再現し、いずれも当該 test のみ `FAILED (failures=1)` — codex 報告と一致。diff は
sentinel 1 file 63+/11- のみ (scope 遵守)。wt 内 commit `764696f` → cherry-pick **`f748391`**
で main へ。worktree / branch 削除・報告書退避。裁定 48 (数値比較・等値保持) と裁定 49
(空 `--state-root` 拒否) を `docs/sentinel-rulings.md` へ正本化 (47 → **49 件**)。
次: r55 = 認定 1 巡目のやり直しを新 HEAD から同型発注 (裁定数と test 数を更新)。

### 2026-08-13 — r55 発注ミス (--write 欠落) → exit 5 → fresh 再発注

r55 の初回起動 (`task-msqkp5zs-ezwah3`) を発注側が `--write` なしで実行した。レビュー本体は
完走したが read-only sandbox が報告書の apply_patch を拒否し、sentinel が **exit 5
(成果物なし完了)** で正しく検知 (log 末尾に「報告書は未作成」の自己申告を提示)。r54 の
レビューは write: True で起動していたことを record で確認 — 手順の退行は発注側にある。
resume は sandbox を引き継ぐため fresh + `--write` で再発注 (`task-msql6vwz-suqt2l`、
record 検証: sol / xhigh / write: True / fresh)。sentinel `btgmvwv9c` (estimate 2250s)。
countermeasure: codex-delegation skill の起動節に「報告書を成果物とする発注は read-only
レビューでも `--write` で起動し、record 検証で write flag と発注意図の一致まで見る」を追加
(source 更新済・deploy はユーザー sudo 待ち)。起動時の第一動作も「報告書 file に見出し
1 行を書いて write を確認する」に変更した。

### 2026-08-13 — r55 受領: material 3 (全件 repro 確定) → fix round 発注

r55 再走行 (`task-msql6vwz-suqt2l`・sol xhigh・write) は sentinel exit 0。報告書は gates 全緑
(selftest 265 / 外部 11 / ruff / ty) を転記し **material 3 件**。発注側 repro で全件確定:

1. **1 ns 後退の偽終了行が float 等値で通過** — `stamp_seconds` の binary64 刻み (238 ns @
   2026 年) が後退を等値に潰す。repro: 等値 True・偽 `Command completed:` 通過・pending 空。
   **r54 修正が開けた窓** (旧文字列比較は落としていた) = 形 5 の新体制初例として台帳へ記録
2. **成果物鮮度の float 比較が 1 ns stale を fresh 誤認** — repro: `st_mtime < since` False
3. **`version_key()` の `isdigit`≠`int` 受理集合** — repro: `²` 入り path で ValueError。
   発注側の初回 repro は path 形の誤りで空振り → 正しい形で再現 (repro 自体も検証対象)

fix round: `drafts/sentinel-r55-fixes.md` (exact 十進比較・`st_mtime_ns`・`isascii` guard、
red 確認 + 発注側選定の変異 3 件)。lint rc=0 初回。worktree `wt-r55fix` @ `767b54d`。
job `task-msqlxf65-ynx4tx` (record 検証: sol / medium / **write: True** — 新 rule どおり
flag と発注意図の一致まで確認)。sentinel `by0g8233d` (estimate 2400s)。

併記: 部分 deploy 検証 — sentinel / extensions.json / guard hook / codex-delegation skill は
diff -q IDENTICAL。managed-settings.json は `codex_task_launch *` 行のみ除いた形で deploy
(launcher 本体は採否合意待ち・ユーザー判断)。

### 2026-08-13 — r55 fix round 完了・main 取り込み (selftest 268・裁定 51)

fix round は sentinel `by0g8233d` exit 0。納品は指示を超える良集約: stamp parse を
`ordered_events()` (Decimal exact・行あたり 1 回) に畳み、`longest_silence` に残っていた
二重 parse (event 行を再 match して stamp を取り直す) も同時に消えた。受け入れ: gates 再実行
(selftest **268** / 外部 11 / ruff / ty 全緑)、**元 repro 3 件の消滅を fix 後 code で直接確認**
(偽終了行→pending 保持 / 1 ns stale→exact で stale / `²`→例外なし)、裁定 48 の tie 保持も
維持を確認。独立変異 2 件 (鮮度 float 戻し / `isascii` 外し) を exact-splice で再現し、
いずれも当該 test のみ fail — codex 報告と一致。wt 内 commit `ff6707e` → cherry-pick
**`3746acb`** で main へ。worktree / branch 削除・報告書退避。裁定 50 (exact 比較)・51
(`isascii`∧`isdigit`) を正本化 (49 → **51 件**)。

deploy 注記: `/usr/local/bin/codex_task_sentinel` は f748391 時点の deploy のまま →
本 fix で再度 DIFFERS (認定完了時にまとめて再 deploy でも可)。
次: r56 = 認定 1 巡目 (3 度目) を新 HEAD から発注 (裁定数 51・test 数 268 に更新)。

### 2026-08-13 — r56 受領: material 3 + oracle 1 (全件確定) → fix round 発注

r56 (`task-msqmjbxn-6mh6y0`・sol xhigh・write) は sentinel exit 0。gates 全緑転記 + 指摘 4 件。
発注側裁定: 指摘 2 (全角 digit 受理・repro) / 指摘 3 (負 epoch -1.9・repro) / 指摘 4 (fixture の
stat assert 欠如・確認) / 指摘 1 (重複 record の exit 14 誤り・該当コードの構造確認 — anonymous
hold の `[0]` 比較が重複判定より先に return)。**指摘 2 は「裁定 51 の機械化を 1 site に留めて
クラスへ配り漏れた」forgot 型** — fix 発注書に受理域クラスの全 site 列挙を義務化した。

fix round: `drafts/sentinel-r56-fixes.md` (lint rc=0 初回)。worktree `wt-r56fix` @ `d165b74`。
job `task-msqnaa9l-3iltdl` (record 検証: sol / medium / write: True / fresh)。sentinel
`bl320xfui` (estimate 3000s)。認定 counter 0 のまま。

観測: 件数は r54: 2 → r55: 3 → r56: 3+1 と横ばいだが、質が変わった — 53 巡時代の主因
(手配り不変条件 73%) は 3 巡連続ゼロで、全指摘が「未疑前提」層 (Unicode 受理域・binary64・
負 epoch・hold 順序・mtime 分解能)。単一障害点化した新設機構 (funnel / Observation /
harness / ordered_events) への指摘もゼロを維持。

### 2026-08-13 — r56 fix round 完了・main 取り込み (selftest 272)

fix round は sentinel `bl320xfui` exit 0。納品は指示 4 件 + 開示付き逸脱 2 件 (いずれも
趣旨内で受理): CLI 数値引数の ASCII 検査 (`ascii_float()` — site 列挙が発見した追加 site) と
非採用候補 descriptor の周回内 release (旧実装の解放漏れの同時修正)。受け入れ: gates 再実行
(selftest **272** / 外部 11 / ruff / ty 全緑)、repro 消滅 5 点を直接確認 (全角 LOG_TS 不一致 /
全角 record None / pre-epoch -0.1 / ascii_float 拒否と正常受理)、独立変異 2 件 (`re.ASCII`
外し / 文字列連結戻し) を splice 再現し当該 test のみ fail — codex 報告と一致。受理域クラスの
site 列挙表 (6 分類) で残 site ゼロを確認。wt 内 commit `042510e` → cherry-pick **`7bff802`**。
worktree / branch 削除・報告書退避。裁定 23 (重複先行)・44 (singleton 限定)・50 (負 epoch +
fixture 保持)・51 (クラス全 site) の本文と担保対応表を更新。
次: r57 = 認定 1 巡目 (4 度目) を新 HEAD から発注。
