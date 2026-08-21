# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)


## Critical

## High

### codex_task_sentinel: 敵対レビューの収束

起票: user 2026-08-12 以前 (fable-5 が 2026-08-21 に r76 実態へ全面書き直し。旧記述は
git 履歴 582a5d7 以前を参照)

Goal: charter 正本 (`docs/sentinel-use-cases.md`) 基準の敵対レビューで U0 ゼロ計 2 巡
(r60 を 1 巡目と数える) の収束条件を満たし、sentinel を確定版として凍結する。

Exit Criteria:

- [x] 収束対策 build 3 柱の実装 — 裁定の機械化 `55c618e` (08-12) / 構造 refactor 3 段
  `c067c0b`・`0425a28`・`265ccfe` / TOCTOU harness `f109f59` (08-13)。いずれも opus xhigh
  レビュー + fix round を経て main 着地 (`docs/sentinel-convergence-log.md` 柱別 status 表)
- [x] 収束認定巡 r54〜r76 (23 巡・全て 2026-08-13) を実施 — selftest 244 → 325、裁定 47 → 60
  (`LAST_RULING=60` を 2026-08-21 実測)。旧基準 (material ゼロ 2 巡連続) は r60 で 1/2 →
  r61 reset で成立せず (`docs/sentinel-review-analysis.md` §8)
- [x] 収束基準を charter v3 + 裁定 60 (U0/U1/U2) へ再定義 — 2026-08-13 ユーザー承認。根拠の
  遡及実測「r60 以降の採用 28 件中 P0 級 3 件のみ = 旧条件は新規前提の無限発掘を課す構造」。
  新体制 2 巡で「過剰実装検出 (r76 初の削る fix)」と「人間 escalation (U1)」の両方が設計どおり発動
- [x] deploy 一致 — 2026-08-21 実測 `diff -q /usr/local/bin/codex_task_sentinel
  files/codex_task_sentinel` IDENTICAL (325 selftests 版)
- [ ] **ユーザー判断: 出口方式の選択** — (A) (a) 撤去後に r77 を時間箱つき (例: 上限 3 巡)
  で続行し、箱内でゼロ未達なら (B) へ自動移行 / (B) 停止規則を severity-gate へ再々定義
  (P0 級 U0 ゼロで認定・残余 U0 は台帳化して非 blocking) / (C) 現状 (r76 着地・deploy 一致)
  で bounded-risk 凍結。データ: 認定 23 巡でゼロは r60 の 1 回のみ・巡あたり 1〜4 件で
  横ばい (ゼロへ漸近する形ではない)、charter 後も r75=2・r76=1。「あと 1 巡」は counter の
  形式値であって予測ではない (2026-08-21 ユーザー指摘で再分析)
- [ ] **ユーザー判断: U1 決裁「(a) 撤去」の再確認** — 「別 inode 差し替え防御は過剰実装か」に
  2026-08-13 21:21「(a) 撤去 + 裁定 38/39/44/45 改廃」と決裁済みだが、直後の session 途絶で
  未実装・文書未反映 (唯一の一次記録 = transcript 68ddd1bf line 8749。当時の発注側推奨は
  (b) 維持)。8 日経過につき有効性を再確認する
- [ ] 裁定 61 (U1 の帰結) を `docs/sentinel-rulings.md` へ commit + `LAST_RULING` bump して
  から、撤去 round を発注・着地する — ledger-first (決裁を文書に落としてから実装。今回の
  8 日停止の真因 = 決裁が transcript にのみ存在)
- [ ] r77 を発注し、U0 ゼロなら収束 2/2 成立を `docs/sentinel-convergence-log.md` へ記録して
  凍結 — 再開手順は同 log 末尾「ここで停止」節が正本

Work file: `docs/sentinel-convergence-log.md` 末尾「ここで停止」節 (再開点)、
`docs/sentinel-review-analysis.md` §8 (r54〜r76 全記録)、`docs/sentinel-use-cases.md`
(charter 正本)、`docs/sentinel-rulings.md` (裁定 60 まで)、`last-session-handoff.md` の同名 section

## Medium

### 方法論の実証: 小規模ツール新規作成で敵対レビューの収束を実測する

Goal: sentinel 級に小さな要件 (またはそこまでブレイクダウンした要件) の新規ツール作成を
数ケース、方法論 (docs/adversarial-review-methodology.md の G/L/R) を適用して実施し、
収束の成否・round 数・token を台帳で実測して最終成果を測る (2026-08-13 ユーザー指示)。

Exit Criteria:

- [ ] 前提: sentinel の出口が決着している (認定成立 or 凍結の宣言。build 3 柱は 2026-08-13
  完了済み — sentinel block の出口 3 案参照)
- [ ] ケース選定と成功基準をユーザーと合意する — round 上限はユーザー指定済み (2026-08-21):
  **新ツールの敵対レビューは規模にもよるが最大 5 巡以内で収束する方針**が要件。残る合意項目 =
  ケース選定・material 残ゼロの定義・token 量
- [ ] 各ケースの台帳 (由来列つき) を docs/ に記録し、結果を方法論 doc へ反映する。反映必須の
  教訓 (2026-08-21 ユーザー指摘で確定):
  (1) **主因 class の機構的排除は当該 class を止めるが、loop を収束させない** — 敵対 reviewer は
  在庫の消化でなく adaptive な generator であり、収束は code でなく停止規則の設計
  (charter × severity × 時間箱) の性質。根拠 = 柱完成後 23 巡で手配り型 0 件 (柱は効いた) なのに
  ゼロ巡 1 回 (収束はしない)・遡及 P0 級 3/28
  (2) **fix しながら埋め込む行動の排除が収束の必要条件** — 指摘の 52% (r17-53) → 約 2 割
  (r54-76、10/50 前後) が fix 由来で、検出強化 (受け入れバッテリ) では減っても消えなかった。
  排除は fix の型の制限で行う (第一選択 = 仕様縮小、次点 = 削除、最終手段 = 機構追加)。
  機構追加 fix は「追加観測/分岐/資源の列挙 + 各 failure mode の test」必須・site でなく
  class への修正 (helper 化 + 機械列挙した全 site/全層を同 round で掃引。alias family は
  r71 fix の層剥がしで 4 巡消費した実例)。埋め込みには技術力の要素があり、実際の fix diff で
  「どう直してどう埋め込んだか」を精査した対策が要る (2026-08-21 ユーザー指摘・未実施)
  (3) **敵対レビューの目的は品質の推定であり、指摘への個別対応ではない** (2026-08-21
  ユーザー指摘) — 指摘は現在品質を推し量る sample。round ごとに class×severity×由来の分布から
  品質を推定し、「受入 / class 単位の是正 / 構造的やり直し / 仕様縮小」を先に決める。
  per-finding の逐次 fix を既定にしたことが無限非収束の根因。5 巡以内の根拠は cost —
  積み上げ可能な場合、人間の senior engineer のレビューは大抵 5 回以内に指摘が枯れる
  (4) **分業: 計数は script、LLM は高次元判定** (2026-08-21 ユーザー指摘) — 密度・重なり
  (capture-recapture)・注入率・分布の集計は決定的 script の仕事。LLM に求めるのは既存ツールに
  できない判定: 概念的一貫性 (欠けている抽象の名指し)・要件適合/過剰実装の verdict・
  「この作りでは到達しない、作り直しが早い」の判定・設計 review essay。reviewer の主成果物を
  「品質 verdict (指摘は根拠 appendix)」に変える — 指摘 list を主成果物にすると LLM は
  bug 発見器に退化する

Work file: `docs/adversarial-review-methodology.md` (§6 チェックリストを各ケースの入場 gate に使う)
