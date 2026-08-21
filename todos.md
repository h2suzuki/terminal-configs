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
  — (e) 概念診断と (f) 掃引節は 2026-08-21 transcript 監査の欠落検出をユーザー承認で追加。
  **(c) は stateless 設計へ変更 (2026-08-21 ユーザー承認)**: hook 自前の台帳・lock・帳尻機構を
  **削除**し、巡数 = 既存 plugin job 記録 + 発注書の巡番号自己申告 (lint が既存 file 群と突合)、
  前巡 verdict = 次発注書の必須節、review 判定 = lint が parse した metadata を gate が受領
  (gate は発注書を再読しない = 読者の一本化)。3 巡のレビュー指摘群 (lock 残骸・記帳ズレ・
  並行更新・64KB 窓) は修正でなく発生源ごと消滅。残余 = job 記録の prune による古い巡の
  数え漏れ (巡番号突合で補う・うっかり対策としては充分と裁定)。fix round 5 に併せ
  **修正方式「機構追加」の 2 巡連続を lint warn** で検知する (アーキテクチャ再審 trigger の
  機械化・方法論 block の段階設計と対、2026-08-21 設計確定)。
  進捗 2026-08-21: (a)〜(f) + stateless 化 + warn は fix round 5 で実装・受け入れ済み
  (wt-gates branch `bd886d0`・lint selftest 31 / gate 65)。判定器と deploy が残。
  **判定器 round 1 (2026-08-21 ユーザー起動・base main)**: no-ship 4 件 — (高) 承認 file が
  model の Write で偽造可能 + 承認消費が後続 lint も飛ばす (発注書由来の仕様欠陥)、(中)
  review 語彙が review/audit 単体を拾わない、(中) round 7 の warn 4 種が stderr のみで
  model に届かない (additionalContext 未接続)、(中) Stop が全 transcript 走査で O(n²)。
  → fix round 8 で対応: 承認は route 迂回のみに限定 + 承認 path への書込を同 gate が deny +
  後続 lint 維持 / 語彙拡張 + 矛盾 deny / warn の additionalContext 接続 (bounded) /
  transcript 走査に hard budget (全読み廃止・不足分は undercount 明示)。
  **判定器 round 3 (2026-08-21・base main) = needs-attention 5 件**: critical 1 (承認ファイル
  touch/ln 偽造 → 廃止可否のユーザー裁定待ち) + 独立 4 件 (並び順 bypass / lint 故障
  fail-open / blocked turn で warning 消失 / undercount 無言)。verdict 全文は
  `wt-gates/drafts/review-gates-verdict-3.md` へ verbatim 保存 (job log prune 対策)。
  fix round 9 発注書 = `wt-gates/drafts/review-gates-fixes-9.md` (独立 4 件 +
  方向 2 防止機構の lint 4 検査 + 承認機構削除・lint rc=0)。
  **決裁 2026-08-22: 承認ファイル方式は廃止** — ユーザー基準「ユーザー提示のユースケースに
  由来しない機能は廃止」に該当 (出自は解除経路の実装選択・使用実績ゼロ・ユーザーは host 権限で
  同等以上のことが常に可能)。緊急解除は管理者領域の hook 設定変更のみ。code 内に解除経路
  (file / 環境変数 / flag) を置かない — fix round 9 の所見 6 として発注。
  **経過 2026-08-22**: fix round 9 納品 (3 file・+343/-241・~14 分)。受け入れ第 1 段 =
  決定的 gates 発注側再実行で全緑。第 2 段 = **Opus 回帰 filter = findings 8 (high 1)** —
  fail-closed 化が既存 deny を置換で消した (read-only × prompt-file が素通り) / lint 新検査の
  否定形誤検知 (既存 corpus 7/7 が誤 fail) / undercount 常時発火の誤誘導 / passthrough の
  prompt 混入 / **元の判定器指摘 (option 前置) 自体が companion 実装と不一致という前提誤りの
  検出** / FIX_METHOD_RE の片側未拡張 / warning 配達が実質未達 + test が現状固定 / 表層 2 件。
  → loopback fix round 10 を 2 方向分析つき発注書 (deployed lint rc=0) で発注済み
  (`wt-gates/drafts/review-gates-fixes-10.md`・回帰 filter 全文 =
  `wt-gates/drafts/review-gates-fixes-9-regression-review.md`)。防止機構「上流指摘の断定は
  一次ソース照合」を方法論 §7.2 へ正本化 commit 済み。新 lint 4 検査は sentinel loopback
  発注書で初実戦し依存閉包棚卸し節の欠落を正しく検出 (機能確認 1 例)。
  **fix round 10 納品** → 決定的 gates 全緑 (発注側再実行) → **filter round 2 = 前巡 8 件中
  7 解消・1 部分解消 (funnel 外 warning 2 family) + 新規 3 件 (計 findings 4)** —
  passthrough 全捨ての振り子 (companion は `--` 以降を prompt 連結 = 検査の穴) / 偽 comment・
  stale docstring / subTest 外 assert。同段不通過 2 回目 → 構造再審 =「gate の CLI model は
  companion の写し」原則を明記し fix round 11 発注済み
  (`wt-gates/drafts/review-gates-fixes-11.md`・両 lint rc=0・filter round 2 報告 =
  `wt-gates/drafts/review-gates-fixes-10-regression-review.md`)。
  **fix round 11 納品 → 決定的 gates 全緑 → filter round 3 = 前巡 4 件全解消・新規 low 2 件**
  (D: round 11 の funnel 補強枝が production 到達不能 — 前巡「指摘 7 残余」自体が mock 由来の
  誤測と判明・filter が実路検証で自己訂正 / E: comment の latch 極性反転)。指摘推移
  8 → 4 → 2 で収束中と判断し、fix round 12 (到達不能枝の削除 + matrix 実路化 + comment 訂正)
  を発注済み (`wt-gates/drafts/review-gates-fixes-12.md`・両 lint rc=0・filter round 3 報告 =
  `wt-gates/drafts/review-gates-fixes-11-regression-review.md`)。
  **fix round 12 納品 → 決定的 gates 全緑 → filter round 4 = VERDICT: pass (2026-08-22)** —
  推移 8 → 4 → 2 → 0 で**検問 line も回帰 filter 通過**。production mutation 7 種で matrix の
  非 vacuous 性まで確認。**凍結 commit `0a0dc2e`** (`gates: Harden lint checks and warning
  delivery`・3 file・tree clean)。残 = 判定器 round 4 (ユーザー起動) と deploy (最終 step・
  filter 指摘どおり /etc の stop_checks.py は 2026-08-20 版のまま)。
  **main merge 済み 2026-08-22** (`5bb0448`・否定断定語彙拡張 `b5aea25` を含む)。
  **deploy 完了 2026-08-22** (ユーザーが base setup 実行・stop_checks.py / codex_order_lint /
  managed extensions とも `diff -q` IDENTICAL 実測・審判 hook は新規 session から有効)。
  残る実測対象: warn family 4 種 + 否定断定の新語彙 warn (誤爆率 → blocking 昇格判断) +
  Stop の Sonnet 審判 hook `cc607a0` (発火頻度・誤爆 → rubric の締め/緩め調整)
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
  org CLAUDE.md への禁則追記の提案も同時に撤回 (常時 load 層はほぼ効かない実測に矛盾)。
  進捗 2026-08-21: fix round 6 で実装・受け入れ済み (wt-gates branch `1994751`・
  gate unittest 65・escape 残骸 0 site)。判定器と deploy が残
- [ ] **(i) 自作癖の抑制** (2026-08-21 ユーザー決裁: 「すぐ自分でコードを書こうとする。
  ジュニアエンジニアがよくやる悪癖」) — 2 層で: (1) tool-role-delegation skill の「trivial は
  直接編集可」境界を数値で明文化 (例: 単一 file・10 行以内・test 追加なし。超えたら委譲か、
  委譲不採用の理由 1 行の記録を必須)、(2) warn-tier hook = session 内の main tree への
  source 追加行数を累積計測し、しきい値超過かつ session 内に rescue job が無い場合に
  stop_checks が「自作癖 checkpoint」を提示する。導入は warn tier → 実測 → 調整。
  進捗 2026-08-21: (1) は canonical へ明文化・commit 済み (数値境界 + 統治原則)。
  (2) は fix round 7 (warn family 4 種) で発注・実行中
- [ ] **(h) codex-delegation skill と関連 memory entry を plugin-route 前提に改訂する** —
  現 skill は companion 直接起動の command 形を規定しており (launcher 不採用裁定 2026-08-13 の
  「直接起動へ一本化」)、これが直接起動 pattern を制度化していた。発注書規律・worktree 隔離・
  監視規律は rescue 経由でも維持する形で書き直す。(g) と同時に land しないと skill が gate 違反を
  指示し続ける。進捗 2026-08-21: canonical を全面改訂・commit 済み (companion 言及 16 site
  掃引・監視 = job record 直読・cancel = ユーザー起動へ)。/etc への deploy は (g) と同時に最終 step で
- [ ] **判断待ちの Task 化を強制する hook family** — 型付き命名規約 (判断待ち Task は名前に
  `採否待ち|判断待ち|決裁待ち` を含める) を前提とする stop_checks family。
  「open Task 0 件」だけの検査は別件 Task 残存時に素通しするため不採用 (2026-08-21 ユーザー
  指摘)。**corpus 実測済み 2026-08-21** (`drafts/decision-task-corpus-study.md`・5 session
  123 turn): 質問 turn 14 件中 genuine 決裁依頼 12 件に対し、当初案の「直近 K turn 内の
  keyword task 作成/更新」は recall 0/12 (K=3,5)〜1/12 (K=10) で**不成立**。否定形
  (「判断待ちではなく」を含む task 名) への誤 match も実証。**設計改訂**: 窓でなく停止時点の
  状態検査 —「最終行が `?`/`？` 終端の turn は、型付き命名の open decision Task が 1 件以上
  存在すること」(否定形 guard つき・命名規約は 2026-08-21 採用済みで以後の task に適用中)。
  検出語彙に corpus 実測の言い回し (ご判断待ち / ご回答待ち / ご指示待ち) を追加。
  warn tier で導入 → 実 session で誤検知/見逃しを観測 → blocking 化判断。
  併せて intent-without-task family の roster に提案宣言語 (「実装しますか」「採否」等) を追加。
  進捗 2026-08-21: 改訂設計で fix round 7 実装・受け入れ済み (wt-gates branch `5323179`・
  stop_checks unittest 178・warn 接続のみ 0 block site)。実測・deploy が残
- [ ] **決裁受領の記録強制を上記 family に併合** (2026-08-21 transcript 監査で検出・ユーザー
  承認) — decision 型 Task が open の時に短文決裁 (「(a)」「やってください」等) を受けた turn
  は、台帳 / todos への決裁記録を要求する reminder (warn tier)。U1 決裁が transcript にのみ
  残り 8 日消えた class の再発防止。進捗 2026-08-21: round 7 で実装・受け入れ済み
  (`5323179` decision-record family)。実測・deploy が残
- [ ] **「無駄」keyword の memory 記録 reminder** (2026-08-21 ユーザー発案: 「無駄という
  キーワードに反応して memory する hook があってもよいぐらい」) — ユーザーの prompt に
  無駄 / 浪費 / もったいない が含まれる turn に、memory-routing での記録検討を促す
  UserPromptSubmit reminder (warn tier)。無駄の実例が entry 化されずに流れる class の防止
- [ ] **コミュニケーション規則の hook 強化 — CLAUDE.md は削らない** (2026-08-21 ユーザー決裁:
  「stop が効いている実感がまだ無い。hook 強化に倒して本当に守られるようになってから考える。
  効いていない状態で消すと正本が無くなり、ルールの所在が分散して埋もれるだけ」) —
  最終行形式 (結論絵文字 / 質問 ? 終端)・自己採番参照の Stop family を corpus 実測から
  warn tier で導入し、**発火と遵守の実測が揃うまで CLAUDE.md の該当節は正本として維持**する。
  extraction の pair commit (実装 + 即削除) は本件には適用しない — 削除は実証後の別判断。
  進捗 2026-08-21: round 7 で実装・受け入れ済み (`5323179` communication lint family:
  最終行形式 + 自己採番の 2 検査・code block / 引用は除外)。実測・deploy が残。
  **追加 2 項目 (2026-08-21 ユーザー要望「一発目で出せるように改善できたらうれしい」)**:
  (1) 質問文に過去参照語 (「前ターンの」「上記のとおり」「先ほどの」等) が混ざったら warn
  する自己完結性検査、(2) 判断依頼を検知した warn の文面に書式 template (決めてほしいこと
  N 件・問題/やること/承認と却下の帰結・略語封印) を埋め込み、書く瞬間に想起させる。
  次の実装 round で本 family へ追加
- [ ] 各 gate の canonical (files/) と deploy 先の diff -q 一致 + 発火の live 観測

Work file: 4 gate の設計は本 block と `last-session-handoff.md` 不要 (本 block で自己完結)。
5 巡 breaker の思想は Medium「方法論の実証」block の教訓 (1)〜(6) を参照

### 敵対レビュー方法論の改訂 (このセッションの調査の反映)

起票: user 2026-08-21 (「やり方についての改善」の列挙)

Goal: 本セッションで確定した教訓群を `docs/adversarial-review-methodology.md` へ反映し、
5 巡以内で必ず意思決定に到達する round protocol を正本化する。

Exit Criteria:

- [x] 教訓 (1)〜(6) (Medium「方法論の実証」block に記録済み: 停止規則 / fix 型制限 /
  品質推定 / 計数と判定の分業 / 統計の適用領域 / round scope 分離) を doc へ反映 —
  `78a2a80` (§7.1〜7.4 + L4/L7。反映先は commit message の対応表)
- [x] **アーキテクチャレビューの段階設計** (2026-08-21 ユーザー指示 → 同日設計確定 →
  同日 doc 反映 `78a2a80`: G0 新設 + §7.2 常設構造判定 + checklist 13〜16): **巡 0 (実装前)** = 構造のみを 1 巡審査。審査対象は実装 code でなく**詳細を捨てた
  構造記述** — 部品表 (部品・保持状態・読者/書者・既存部品での代替可否)。chart と部品表は
  LLM には等価 (2026-08-21 ユーザー確認: 等価なら入口 2 つで可)。code を対象にしないのは
  詳細が構造の問いを溺れさせるため (実測: code への 3 巡 18 指摘は全て code 水準・構造指摘 0)。
  問いは「この部品は要るか / 既存部品・記録で代替できないか / 持つ状態を減らせるか」の
  3 つ、成果物は構造承認 or 作り直し案の判定のみ。判定器は既製 /codex:adversarial-review。
  5 巡以内の収束保証は巡 0 を通過した構造にのみ適用する。**巡中の常設判定** (2026-08-21
  ユーザー修正: 特定 signal の発火型でなく全指摘対象) = 毎巡の verdict で**全指摘**に
  「アーキテクチャの問題か / 構造の改善 (削除・代替・状態削減) で発生源ごと消せないか」の
  帰属判定を必須とする — G5 構造判定の per-finding 化。機構追加 2 巡連続の lint warn
  (gates block (c)) は集計側 backstop に位置づけ。構造帰属となった指摘は fix round でなく
  構造巡へ回す。根拠 case = gates 3 巡 18 指摘が「台帳って要るの?」の一問で無効化
  (entry feedback_architecture_before_review が doc 反映までの防衛線)
- [x] transcript 監査 (2026-08-21) で確定した doc 行き要素を per-member 対応表つきで反映
  (`78a2a80` — 対応表 8 要素は commit message 本文、G1/G2/§7.2/§7.4/L4 へ分配):
  round 0 の裁定 catalog 先渡し / finding round は read-only (直さず推定表へ) /
  self P0 の rollback 規律 / 終盤 round で機構追加が必要なら 5 巡収束は失敗と判定
  (黙って延長しない) / 裁定→fixture の粒度 pin / strangler 型 (全面 rewrite 不採用) /
  capture-recapture の適用限定 (独立性成立時のみ) / 台帳集計 (分布 summary) の script 化。
  定義済み列挙を doc へ転写する際は要素単位の対応表を必須とする (lossy 転写の禁止)
- [x] codex 意見書 (`drafts/quality-estimation-opinion-report.md` §5) の 5 巡 protocol と
  突合し、入場条件・round 別の入力/出力/判定・「巡数を黙って延長しない」規律を正本化 —
  `78a2a80` §7.4 に inline 化 (drafts への参照は doc 本文に残さない)
- [x] **fix diff の実物精査** — 認定 era の埋め込み ~10 件を commit diff 水準で分析し、
  「新しく仮定した次元」列挙表 (意見書 §4) の実効性を検証して fix 型制限の設計に反映 —
  2026-08-21 実施: 注入 12 件を commit hunk まで遡及 (`drafts/fix-injection-diff-audit.md`
  374 行・AUDIT_COMPLETE)。機構追加型 92% (11/12)。列挙義務は新設系 4 件に有効・
  境界条件の未掃引 4 件は class 掃引・転写ミス 1 件は裁定照合の担当と確定し doc §7.3 へ追記

Work file: `drafts/quality-estimation-opinion-report.md` (codex 第三者意見書)

## Medium

### 改造時のバグ作り込みを減らす方策の検討

起票: user 2026-08-22 (「まだ改造による作り込みが多すぎ。改造時にバグ作り込みを避ける方法に
ついて、もっと考えてほしい。品質ゲートとしては機能できたと認識」)

Goal: 品質ゲート (回帰 filter・全数列挙・lint) で「捕まえる」だけでなく、改造時の注入
発生率そのものを下げる方策を、本日の実測 corpus から導出して方法論へ正本化する。

Exit Criteria:

- [ ] 本日の注入 corpus (fix round 4/4 注入・filter 捕獲 22 件・r81 の 2 件) を起源 class 別に
  集計し、「gate で捕まえた」と「そもそも入らなかった」を分離した基礎表を作る
- [ ] 発生率を下げる候補方策 (例: 変更粒度の縮小・対 site の同時変更を強制する発注書式・
  実装前の contract 差分宣言・delta 専用の設計 review 等) を候補ごとに期待効果と実測根拠
  つきで列挙し、ユーザーへ提案する
- [ ] 採用された方策を方法論 doc / lint / 発注書 template へ正本化し、次の改造案件で
  発生率を再実測する

Work file: `docs/adversarial-review-methodology.md` §7.3 (現行の注入対策の正本)、
`wt-ruling61/drafts/` と `wt-gates/drafts/` の回帰レビュー報告書群 (本日の注入 corpus)

### 方法論の実証: 小規模ツール新規作成で敵対レビューの収束を実測する

Goal: sentinel 級に小さな要件 (またはそこまでブレイクダウンした要件) の新規ツール作成を
数ケース、方法論 (docs/adversarial-review-methodology.md の G/L/R) を適用して実施し、
収束の成否・round 数・token を台帳で実測して最終成果を測る (2026-08-13 ユーザー指示)。

Exit Criteria:

- [x] 前提: sentinel の出口が決着している (認定成立 or 凍結の宣言。build 3 柱は 2026-08-13
  完了済み)。**決着 2026-08-22**: 収束 2/2 成立 (r60 + r82 = ship・U0 ゼロ)・凍結 97743bd・
  main merge・deploy 一致まで完了 (経過の正本 = `docs/sentinel-convergence-log.md` 末尾)
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
