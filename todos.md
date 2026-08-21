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
  transcript 走査に hard budget (全読み廃止・不足分は undercount 明示)
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
- [x] **ユーザー判断: U1 決裁「(a) 撤去」の再確認** — 「別 inode 差し替え防御は過剰実装か」に
  2026-08-13 21:21「(a) 撤去 + 裁定 38/39/44/45 改廃」と決裁済みだが、直後の session 途絶で
  未実装・文書未反映 (唯一の一次記録 = transcript 68ddd1bf line 8749。当時の発注側推奨は
  (b) 維持)。**2026-08-21 再確認済み**: ユーザー指示「裁定 61 として文書に記録してから
  撤去 round を発注してください」で (a) の有効を確認 (裁定 61 記録 = `c557cde`)
- [ ] 裁定 61 (U1 の帰結) を `docs/sentinel-rulings.md` へ commit + `LAST_RULING` bump して
  から、撤去 round を発注・着地する — ledger-first (決裁を文書に落としてから実装。今回の
  8 日停止の真因 = 決裁が transcript にのみ存在)。進捗 2026-08-21: 裁定 61 記録 `c557cde`
  (main)・撤去 round 受け入れ済み `6b3d2ee` (wt-ruling61 branch・selftest 325→315 全緑)。
  main への取り込みは r77 認定後に行う
- [ ] r77 を発注し、U0 ゼロなら収束 2/2 成立を `docs/sentinel-convergence-log.md` へ記録して
  凍結 — 再開手順は同 log 末尾「ここで停止」節が正本。**r77 実施済み 2026-08-21
  (sol xhigh・verdict 6 項目形式)**: needs-attention U0 2 / U1 1 / U2 0
  (報告書 `wt-ruling61/drafts/sentinel-r77-report.md`)。処置は全て削除・文書整合系:
  旧 test 名の意味反転流用の解消 (撤去 diff 由来・受け入れの名前照合を素通し) +
  未使用 helper 削除 + 裁定表の整合。**経過 2026-08-21**: fix 後の r78 = U0 3 (うち fix 由来 2)
  → pending 1 cadence の導入で是正 (`bd5345f`・red 確認つき) → r79 = **U0 1 件のみ**
  (medium・fix 由来の仕上げ残り: pending の起動条件が分類前の候補数を見るため、読めない候補と
  別 job の同名記録が併存すると 1 cadence 待ちが働かない。処方 = 分類後の一意性で判定・
  数行の縮小修正・新機構不要)。**仕上げ round 実施済み** (`c2a951c`・red 確認・分類直積
  10 組の担保表・selftest 315)。**r80 = needs-attention U0 3 件** (medium 2 + low 1。
  在庫 2: 「見たことがある」flag が非対象確定後も残り終わり方の分類が 1 段ずれる /
  台帳の裁定 23 に撤去済み文言が残存。fix 由来 1: 保留対象の入れ替え時に旧 path を保持)。
  指摘推移 3 → 4 → 1 → 3 で乾いておらず、候補状態の整合という**同 class が 3 巡反復** —
  構造 signal。reviewer の概念診断 =「分類後候補の lifecycle」を不変条件 4 つで一本化すれば
  同源で消える (構造巡の処方あり)。**Opus 5 独立レビュー実験 2026-08-21** (同一凍結版
  c2a951c・codex 報告書は非開示): codex r80 の 3 件中 2 件を Opus も発見 (saw_candidate の
  sticky 化・台帳裁定 23 の残存文言)。codex 固有 1 件 (pending の入れ替え漏れ)。**Opus 固有の
  大物 2 件**: (i) `--once` (単発評価) が pending 発動時に 1 cadence で返らず 30 秒〜最大
  deadline まで block — codex 処方が凍結した test 自体がこの契約破りを固定 (正本 U-5 違反・
  high)、(ii) pending 機構自体が過剰実装 — main poll loop の読取窓が既に裁定 62 の保証を持ち、
  bool 1 個 + 既存 discard 経路で置換して約 45 行削減可 (裁定 61 の「跨ぎ記憶の廃止」と 62 の
  「path 1 件記憶」の境界未定義も指摘)。両者は「分類結果の第一級型 (Resolution)」という同じ
  欠落抽象に到達。+ Opus の削減系 4 件と上流裁定事項 5 点 (--once と裁定 62 の優先・exit 10 は
  名乗り確認済み限定・裁定 62 の記憶単位・裁定 55/23 の担保陳腐化)。
  **次の判断はユーザー**: 構造巡の方向を削減側 (pending 削除 + Resolution 型 + 全数列挙 test)
  へ更新した (A') の発注可否 / (B) bounded-risk 凍結。
  work file: `wt-ruling61/drafts/sentinel-r80-report.md` (codex 側) /
  `wt-ruling61/drafts/sentinel-r80-opus-review.md` (Opus 側・保存済み)
- [ ] **ユーザー裁定 (r77 の U1)**: (1) 裁定 61 の廃止列挙の補完 — **2026-08-21 承認済み**
  (「承知しました」)。裁定表へ反映 commit 済み (61 の列挙拡張 + 35/55 への廃止注記、
  meta-test 13 件緑)。(2) 裁定 42/43 と裁定 61 の衝突 — 同 inode の truncate + 再書込
  (正本 S-9 の正常系) を当該 watch の間 corrupt に固定しうる。reviewer 提案 = (a) 42/43 も
  廃止し次 cadence の安定 snapshot で再判定 / (b) 保持し正本へ理由と期待 exit を明記。
  **2026-08-21 ユーザーから「記憶と合致しない、詳しく」の差し戻し** — 裁定 20 (安定 snapshot の
  parse 不能だけを corrupt とする・truncate 窓を破損に化けさせない) との関係を説明して再判断
  待ち。決裁後に fix round + r78 を 1 回で実施

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
