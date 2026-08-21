# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)


## Critical

## High

### 敵対レビュー運用の強制機構 (gate 化)

起票: user 2026-08-21 (「強制が必要な事項 2 つ」の列挙)

Goal: 車輪の再発明・無検問 loop・判断待ちの Task 化漏れを、約束でなく決定的 gate で禁止する。

Exit Criteria:

- [ ] **review 運用の gate 群を実装・smoke・deploy** — (a) 発注書 lint に「既製手段の棚卸し」節
  必須化、(b) review 系 task 発注の経路 gate (既製 `adversarial-review` subcommand か棚卸し節
  つき発注書以外は deny)、(c) **round ごとの verdict 台帳** (前 round の verdict 記録が無いと
  次 round 発注 deny・5 巡到達 = 敗北検出で敗因分析 + ユーザー承認を要求)、(d) `scope:
  diff|artifact` 宣言必須化、(e) G5 = verdict 6 項目 (振り分け / 受入 / 構造 / 由来帰属 /
  上流批評 / **概念診断**) の要求必須化、(f) G6 = fix 発注書の修正方式宣言 + 機構追加の
  failure-mode 列挙表 + **全 fix 所見への掃引節 (欠陥定義 + 機械列挙 + 単一 site 主張にも根拠)**
  — (e) 概念診断と (f) 掃引節は 2026-08-21 transcript 監査の欠落検出をユーザー承認で追加
- [ ] **(g) codex の直接起動を禁止する — 強固に** (2026-08-21 ユーザー決裁 + 同日「強固に
  おこなうべき」で強化) — codex_delegation_gate を「注意喚起」から「deny」へ:
  main agent の Bash からの companion 起動 (全 subcommand・`task-worker` 含む) は**一律 deny**。
  判定は先頭一致でなく command 文字列中の `codex-companion.mjs` の存在で行い、path 前置・
  変数展開・wrapper 包みも捕捉する。許可は codex-rescue subagent 内の実行のみ。
  **model が使える escape hatch は置かない** (解除はユーザーが書く承認 file のみ)。
  deny message は実害台帳 (user memory `feedback_codex_plugin_route_only`) を引用し、
  「大したことない」「thin だからよい」の minimization を message 内で先回りして反証する。
  違反試行は command 全文 + 時刻で永続 log へ**機械が黙って**自動追記する — 位置づけは
  ペナルティーでなく **telemetry** (gate の動作確認と新しい迂回形の検出材料)。
  当初案の「SessionStart での回数表示・台帳追記の弁済要求」は撤回 (2026-08-21 ユーザー指摘:
  可視化は謝罪文の量産になるだけで行動を変えない。行動を変えるのは事前 deny のみ —
  本 session 実測: gate deny 3 回で 3 回とも即時に経路変更・謝罪ゼロ)。
  org CLAUDE.md への禁則追記の提案も同時に撤回 (常時 load 層はほぼ効かない実測に矛盾)
- [ ] **(i) 自作癖の抑制** (2026-08-21 ユーザー決裁: 「すぐ自分でコードを書こうとする。
  ジュニアエンジニアがよくやる悪癖」) — 2 層で: (1) tool-role-delegation skill の「trivial は
  直接編集可」境界を数値で明文化 (例: 単一 file・10 行以内・test 追加なし。超えたら委譲か、
  委譲不採用の理由 1 行の記録を必須)、(2) warn-tier hook = session 内の main tree への
  source 追加行数を累積計測し、しきい値超過かつ session 内に rescue job が無い場合に
  stop_checks が「自作癖 checkpoint」を提示する。導入は warn tier → 実測 → 調整
- [ ] **(h) codex-delegation skill と関連 memory entry を plugin-route 前提に改訂する** —
  現 skill は companion 直接起動の command 形を規定しており (launcher 不採用裁定 2026-08-13 の
  「直接起動へ一本化」)、これが直接起動 pattern を制度化していた。発注書規律・worktree 隔離・
  監視規律は rescue 経由でも維持する形で書き直す。(g) と同時に land しないと skill が gate 違反を
  指示し続ける
- [ ] **判断待ちの Task 化を強制する hook family** — 型付き命名規約 (判断待ち Task は名前に
  `採否待ち|判断待ち|決裁待ち` を含める) を前提に、最終行が質問 (`?`/`？` 終端・絵文字非依存)
  の turn は「open な decision 型 Task が 1 件以上 + 直近 K turn 内の作成/更新」を要求する
  stop_checks family。指摘時は open decision Task 一覧を提示して質問との対応を自己照合させる。
  「open Task 0 件」だけの検査は別件 Task 残存時に素通しするため不採用 (2026-08-21 ユーザー
  指摘)。warn tier で導入 → 実 session で誤検知/見逃しを観測 → K 調整 → blocking 化判断。
  併せて intent-without-task family の roster に提案宣言語 (「実装しますか」「採否」等) を追加
- [ ] **決裁受領の記録強制を上記 family に併合** (2026-08-21 transcript 監査で検出・ユーザー
  承認) — decision 型 Task が open の時に短文決裁 (「(a)」「やってください」等) を受けた turn
  は、台帳 / todos への決裁記録を要求する reminder (warn tier)。U1 決裁が transcript にのみ
  残り 8 日消えた class の再発防止
- [ ] 各 gate の canonical (files/) と deploy 先の diff -q 一致 + 発火の live 観測

Work file: 4 gate の設計は本 block と `last-session-handoff.md` 不要 (本 block で自己完結)。
5 巡 breaker の思想は Medium「方法論の実証」block の教訓 (1)〜(6) を参照

### 敵対レビュー方法論の改訂 (このセッションの調査の反映)

起票: user 2026-08-21 (「やり方についての改善」の列挙)

Goal: 本セッションで確定した教訓群を `docs/adversarial-review-methodology.md` へ反映し、
5 巡以内で必ず意思決定に到達する round protocol を正本化する。

Exit Criteria:

- [ ] 教訓 (1)〜(6) (Medium「方法論の実証」block に記録済み: 停止規則 / fix 型制限 /
  品質推定 / 計数と判定の分業 / 統計の適用領域 / round scope 分離) を doc へ反映
- [ ] transcript 監査 (2026-08-21) で確定した doc 行き要素を per-member 対応表つきで反映:
  round 0 の裁定 catalog 先渡し / finding round は read-only (直さず推定表へ) /
  self P0 の rollback 規律 / 終盤 round で機構追加が必要なら 5 巡収束は失敗と判定
  (黙って延長しない) / 裁定→fixture の粒度 pin / strangler 型 (全面 rewrite 不採用) /
  capture-recapture の適用限定 (独立性成立時のみ) / 台帳集計 (分布 summary) の script 化。
  定義済み列挙を doc へ転写する際は要素単位の対応表を必須とする (lossy 転写の禁止)
- [ ] codex 意見書 (`drafts/quality-estimation-opinion-report.md` §5) の 5 巡 protocol と
  突合し、入場条件・round 別の入力/出力/判定・「巡数を黙って延長しない」規律を正本化
- [ ] **fix diff の実物精査** — 認定 era の埋め込み ~10 件を commit diff 水準で分析し、
  「新しく仮定した次元」列挙表 (意見書 §4) の実効性を検証して fix 型制限の設計に反映

Work file: `drafts/quality-estimation-opinion-report.md` (codex 第三者意見書)

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
- [ ] **出口の実行 — 改訂方法論を適用して収束させる** (方向は 2026-08-21 ユーザー列挙
  「sentinel に実際に適用して収束させる」で確定。残る選択 = 確認巡の時間箱設定):
  改訂方法論 (diff round・verdict routing・severity gate) を適用した確認巡を時間箱つきで
  実施し、認定または bounded-risk 受入のどちらかへ**必ず**意思決定して凍結する。
  データ: 認定 23 巡でゼロは r60 の 1 回のみ・巡あたり 1〜4 件で横ばい、charter 後も
  r75=2・r76=1。「あと 1 巡」は counter の形式値であって予測ではない (2026-08-21 再分析)
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
  (4) **分業: 計数は script、LLM は高次元判定** (2026-08-21 ユーザー指摘) — 密度・重なり・
  注入率・分布の集計は決定的 script の仕事。LLM に求めるのは既存ツールにできない判定:
  概念的一貫性 (欠けている抽象の名指し)・要件適合/過剰実装の verdict・
  「この作りでは到達しない、作り直しが早い」の判定・設計 review essay。
  **verdict は欠陥列挙の置換ではなく routing 層** (2026-08-21 ユーザー訂正) — 用途内の明白な
  欠陥は直す。ユースケース外・用途超えの使い方・未依頼機能の実装要求は明示的に拒否する。
  verdict はこの振り分けと受入/構造判断を担う。機能するかは実証ケースで測る (未検証)
  (5) **統計装置は規模の適用領域を確認して選ぶ** (2026-08-21 ユーザー指摘) — 成長曲線・
  残存数統計は issue 1000+ (できれば 10000+) の大規模領域の手法で、小規模 tool には適用外。
  小規模では分布・U/P 分類の少数標本の質的読みに留める。手法は名前でなく使い方まで調べて輸入する
  (6) **レビュー scope は round 種別で設計する** (2026-08-21 ユーザー指摘) — sentinel の 76 巡は
  r1 の全体レビュー書式を cp 継承し続け、実際は「直前 fix の欠陥を最優先」の実質 diff レビューを
  全体 scope の発注で回していた (scope は一度も設計判断されていない)。正しくは fix 検証 =
  diff round (plugin の `/codex:adversarial-review` が既製で適合・plugin 導入 2026-06-13 以来
  利用可能だった) / 在庫掃引 = 全体 round (round 1 と構造変更後のみ) に分離する。分離は由来推定
  (fix 由来 vs 在庫) を構造的に自動化し、52% 自己交絡の再発を防ぐ

Work file: `docs/adversarial-review-methodology.md` (§6 チェックリストを各ケースの入場 gate に使う)
