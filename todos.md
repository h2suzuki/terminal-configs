# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)

各 block は 起票 / Goal / Exit Criteria / Work file のみを持つ。経緯・実測・訂正の詳細は
git 履歴 (`git log -p -- todos.md`) と Work file にあり、ここには書かない。

## Critical

## High

### 敵対的レビュー loop の出口 — メタ評価の決裁と実施

起票: fable-5 2026-08-26 (ユーザー依頼「transcript を解析しメタ評価を行い、正しい方向を模索せよ」
から派生)

Goal: 「指摘を直すたびに欠陥を作り込み、総合品質が上がらない」loop を、停止条件と artifact の
大きさを変えることで終わらせる。規則・巡数を足す選択肢は最初から持たない。

Exit Criteria:

- [x] ユーザーが処遇を決めた — 2026-08-26 決裁: sentinel は本当に有効な最小限まで小さく
  書き直す / 方法論も同じく最小限へ (1 ページ) / ab_probe は廃棄 / 直さない指摘は台帳に書かない
- [x] ab_probe を廃棄した — 2026-08-26。`wt-abprobe` と branch を削除、発注書・報告書 31 file は
  `drafts/ab-probe-archive/` に退避
- [x] sentinel を要件から書き直した — 2026-08-26 完了 (8,588 → 231 行、exit 14 種 → 7 種、契約 =
  `files/codex_task_sentinel.test.py` の 17 test、変異器 `files/codex_task_sentinel.mutants.py` で
  0/4 生存、独立レビュー 1 巡 P0 なし、1 巡で終了、merge `8208fe0`)。配備 = base setup 後に
  `/usr/local/bin` と skill が `diff -q` IDENTICAL、実 job record 2 件 (completed / cancelled) で
  verdict done / failed を実測
- [x] 方法論 doc を 6 項目 1 ページに置換し、台帳 3 本に凍結注記を入れた — 2026-08-26
- [x] todos.md の構造 lint を決定的 gate にする — `todos_structure_gate.py` (block ≤ 40 行・項目 ≤ 6 行・
  必須 key 3 つ) を 2026-08-26 に配備、41 行 block の commit が deny されることを E2E で実測
- [x] 台帳の再発防止 — `frozen_docs_gate.py` (HEAD に `凍結 (日付)` 行を持つ file の行数増加 commit を
  deny し、逃がし先 `drafts/journal/` を案内) を 2026-08-26 に配備、凍結 doc +1 行の commit が deny
  されることを E2E で実測
- [ ] 実案件を §5.1 で回し、§5.6 の指標で判定した — ケース 1 = sentinel 書き直し (2026-08-26:
  変異 0/4・1 巡で出荷・配備済み)、ケース 2 = todos 構造 gate (契約の訂正で再入場 1 回)。
  残り = 配備後 2 週間 (〜2026-09-09) の実運用で用途内 P0 が 0 であること。外れたら loop
  approach を捨てる

Work file: `docs/adversarial-loop-meta-evaluation.md` (評価の正本)、
`drafts/loop-exit-opinion-order-report.md` (第三者意見書・gitignore)

### memory surface が予告 entry を届けられなかった機構を直す

起票: fable-5 2026-08-26 (ユーザー指摘「memory surface の機構そのものの否定になっている」から派生)

Goal: 状況に当てはまる教訓が session 中に届き、届いた教訓が行動を変える状態にする。
予告していた entry 3 件が 1 度も surface されず、surface された 18 entry も本文を Read されなかった
実測 (2026-08-25 session) を再現しない。

Exit Criteria:

- [x] ユーザーが対策の方向を決めた (2026-08-26) — (A) Stop 時 advisory surface を削除 (11005b1、配備済み) /
  (B) 予告 entry は `## 処置の種別` の閉じた選択肢 gate へ (合意) / (C) 文章だけの entry を減らす (OK)。
  同日追加決裁: blocking 昇格 8 件と scope 上限 (org 60) を採用、gate 済み entry 3 件はホストで退役
- [ ] memory 衛生を機構化した — `memory_routing_gate` に近接重複の検出 (search score が閾値超なら
  新規 Write を deny して既存 entry への追記を案内)、gate / lint が逐語 cover した entry の退役
  要求、scope 上限 (org 60 超で新規 feedback を deny し `--reach` の never 一覧を印字) を入れる
- [ ] 決定的に検出できる教訓 8 件を blocking gate へ昇格し entry を退役した — Bash pattern gate
  (fuser -k・pkill / 無限 loop / --autosquash / voicevox --loopback / 除外 command の裸名)、hooks 内
  `claude -p` の Write deny、playwright `page.on` 未 off の deny、done_state_ledger の Stop block 化
- [ ] 重複 cluster を統合した — 例: 自己採点系 (`lesson_is_input_not_report` /
  `close_question_before_remorse` / `check_report_verdict_wording`)、規則追加系
  (`rule_violation_means_countermeasure` / `failure_response_adds_rules`)、自作・委譲系
  (`self_build_impulse` / `delegation_failure_no_self_impl` / `inventory_existing_tools_first`)。
  gate で逐語 cover 済みの例: `codex_delegation_skill_skip` (delegation gate が skill invoke を deny で
  強制)、`codex_monitor_job_state` (sentinel が実装)
- [x] 到達経路を測って回す機構を配備した (2026-08-26、aa3c1dd) — surface の (entry, session) 上限 2 回と
  `claude_memory_sync --reach` (30 日 emit 0 / ≥ 20 の列挙。初回: never 70 / hot 6)。30 日後に到達可能
  entry の未到達率が 43% → 25% 未満かで判定
- [ ] 採用した対策を実装し、2026-08-25 session の prompt 列で backtest して予告 entry が届くことを
  確認した (memory-surface-analyzer)

Work file: `~/.claude/hooks/memory_surface.py` (surface 方針の実装)、
`/var/lib/claude-rag-memory/memory_index.sqlite3` の `inject_log` (emit / mismatch の実測)

### 検索コマンドの誤 deny の解消

起票: user 2026-08-23 (「これは対策が打てるなら、打ってよいよ」「検出器のぶっこわれは、今なおします」)

Goal: companion の名前に言及しただけの読み取りコマンドが直接起動として弾かれる誤検出を、
起動の取りこぼしを作らずに解消する。

Exit Criteria:

- [x] 回帰 filter を通した — round 3 は fail、脅威モデルで指摘を選別して決着 (2026-08-23、`fd6ff4b`)
- [x] 残る 1 class (D2 = 一部の行だけ token 化に失敗すると素通し) の扱いをユーザーが決めた —
  2026-08-23 決裁: 現状で merge・配備。実害は heredoc 形と行末継続記号の 2 形のみ
- [ ] 解析そのものの作り直しは却下済み (2026-08-23) — parser library 未導入・bash parser 借用は
  任意コード実行の穴・原理的に決定不能。記録のため残す
- [x] 本線へ merge した — `a65da00`、push 済み
- [ ] 残り 2 形を塞ぐ — heredoc 形は再 token 化で塞げると実測済み、行末継続記号は未検討。
  塞げなければ相談する。2026-08-26 実測: 発注書を書く heredoc が「codex」で始まる行で 3 回
  誤 deny (mention と execution の未区別)
- [x] 配備し実地確認した — 2026-08-23 (hook 34 対 IDENTICAL、読み取り allow / 起動 deny を実測)
- [x] 同型欠陥を class で掃引した — `skill_reminder_gate` の handoff 分岐を `writes_handoff_doc`
  (書込語だけを列挙) へ差し替え (2026-08-24、`bcdea99`、配備済み)
- [ ] 同型欠陥がもう 1 件 — `cd` 検問が `cd() { return 1; }` の関数定義を移動と読む
  (2026-08-24 実測)。実害は小さい。「先頭の語で判定」が使えるかを見て費用対効果で判断

Work file: `drafts/mention-guard/` (発注書 2 通と回帰レビュー 2 通)

### codex plugin の broker がセッション終了後も生き残る

起票: user 2026-08-23 (別デバイスの調査結果を共有・「todo に記載して」)

Goal: session 終了後も生き残り、削除済み worktree を掴んだまま蓄積する broker プロセスと
その残骸を、鍵ずれの解消と状態駆動の回収の両輪で止める。

原因は単一 = 鍵ずれ: 登録は git repo root の hash、回収は session 終了時点の cwd で引くため、
linked worktree への write 委譲では必ず不一致。版は無関係、既製の回収機構は無い (2026-08-23 確定)。

Exit Criteria:

- [ ] 着手時期をユーザーと相談し、対策 A〜D のどれを本端末で実施するか決める
- [ ] 対策 A (鍵ずれ): 発注する session の cwd を worktree に合わせる。効くのは session 終了時点の
  cwd なので 1 session 1 worktree。原因が単一と分かったため本命
- [ ] 対策 B (取りこぼし): worktree 削除の直前に、停止要求 → SIGTERM → SIGKILL の順で session
  単位に回収する
- [x] 対策 C (定期回収): `files/codex_broker_reap` を実装・配備 (2026-08-23)。host 実測 =
  reap 5 / keep 2 / stale 114、孤児 3 本も回収、停止要求だけで全件停止
- [x] 対策 D (upstream 報告): #380 へコメント投稿 (2026-08-24、
  `https://github.com/openai/codex-plugin-cc/issues/380#issuecomment-5388760433`)

Work file: `files/codex_broker_reap` (host 実行・手順は `--help`)、
`drafts/codex-broker-leak-upstream-report.md`、`drafts/broker-leak-repro.sh`、
memory `feedback_codex_broker_outlives_session` (org)

### handoff の lifecycle 同期を hook で担保する

起票: user 2026-08-23 (「handoff protocol / hook の強化が必要?」への回答として提案)

Goal: todos.md の parent block が消えた handoff section が残り続ける class を、規約の文言でなく
機械検査で止める。

Exit Criteria:

- [x] 検査を作るかをユーザーが決めた — 2026-08-23 採用。仕様 = 参照で判定 (どの block からも
  `Work file:` で指されない handoff doc / 実在しない path を warn。見出し名は見ない)
- [x] warn tier で実装・test した — `stop_checks.py` `_handoff_todos_sync_warnings` (2026-08-23、配備済み)
- [ ] 実 session で誤検知と見逃しを観測した — handoff doc を作る session が来るまで測れない
- [x] 現存する stale file を処置した — `last-session-handoff.md` を削除 (2026-08-23、ユーザー承認)

Work file: なし (本 block で自己完結)

### 記憶から書かせない仕組み — 雛形 + 経由の強制 + 空欄設計

起票: user 2026-08-23 (「まず todo に登録して、セッションリセット後に実装へ」)

Goal: 記憶から生成して弾かれる類の成果物について、雛形を複製することが生成の第一手になる
状態を作り、雛形を経由しない生成を止める。

Exit Criteria:

- [x] 発注書の雛形を用意した — 雛形 3 種、空欄は `未記入` sentinel で検査器の所見になる (2026-08-24)
- [x] 実装した — `codex_order_lint --new` と `codex_order_scaffold.py` (2026-08-24、`58bb28d`、配備済み)
- [ ] 実装のリスク 2 件を運用で見る — (a) Bash 経由の作成 (cp / heredoc) には届かない、
  (b) deny しつつ file を作る形が紛れないか
- [x] 雛形を経由しないと生成できない形にした — 記憶からの Write は deny + 骨組み生成 (2026-08-24)
- [ ] 同型の欠落が他に無いかを棚卸しした — 雛形を持たずに毎回書いている成果物の種類を列挙する
- [ ] 効果を実測した — 基準値は取得済み (2026-08-24: 発注書 144 件中 現行規約で所見ゼロ 12 件)。
  比較対象は導入後に書いた発注書の往復回数

Work file: なし (本 block で自己完結)

### 検問 gate 群の実装・受け入れ・配備

起票: user 2026-08-21 (「強制が必要な事項 2 つ」の列挙)

Goal: 車輪の再発明・無検問 loop・判断待ちの Task 化漏れを、約束でなく決定的 gate で禁止する。

Exit Criteria:

- [ ] review 運用の gate 群を実装・smoke・deploy — (a)〜(f) + stateless 化 + warn は fix round 12
  まで回して回帰 filter pass、main merge・deploy 済み (2026-08-22)。残り: warn family の
  発火と誤爆の実測 (誤爆 9 件と凍結判断は Medium「随伴エージェント待ち」block へ集約済み)、
  live finding 1 (task の anchor ずれ、修正 `29f1891`、deploy 待ち)、live finding 2
  (`adversarial-review` command が gate と衝突、例外を設けるかは判断待ち)
- [ ] 検問実装への挑戦レビュー — verdict 受領 2026-08-22 (U0 8 / U1 2)。処置の決定はユーザー判断待ち
- [x] (g) codex の直接起動を禁止する — deny 化・配備・live 実測 2 件 (2026-08-25 close)
- [x] (i) 自作癖の抑制 — skill の数値境界は明文化済み。hook 側は廃止 (`8b04b7b`)、後継は Medium
  「随伴エージェント待ち」block の項目 1
- [x] (h) codex-delegation skill と関連 memory entry を plugin-route 前提に改訂 — 配備済み
  (2026-08-25 close)
- [ ] 判断待ちの Task 化を強制する hook family — 実装・受け入れ済み (`5323179`)。実測・deploy が残
- [ ] 決裁受領の記録強制を同 family に併合 — 実装済み (`5323179`)。実測・deploy が残
- [ ] 「無駄」keyword の memory 記録 reminder — Stop family として発注済み
  (`drafts/gates/warn-family-order.md`)。2026-08-26 実測: 配備済みで発火するが、entry を書くまで
  毎 Stop で再発火する (結論確定前に書けない turn では noise)
- [ ] コミュニケーション規則の hook 強化 — CLAUDE.md は削らない (2026-08-21 決裁)。round 7 で
  実装済み、追加 2 項目 (過去参照語の warn / 判断依頼の書式 template) を同発注書で発注済み。
  実測・deploy が残
- [x] 発注書 lint の語彙過剰検出を直した — 語で引く 2 検査を無条件必須節へ移行 (2026-08-23、配備済み)
- [ ] 各 gate の canonical と deploy 先の diff -q 一致 + 発火の live 観測 — 配備差分ゼロ
  (2026-08-23)。未観測 1 family (question-self-containment) が残

Work file: `drafts/gates/` (発注書・verdict・回帰レビュー報告書)

### codex 利用規定の統一 — 受入れ準備までが scope

起票: user 2026-08-25 (「codex 敵対的レビューは『必ず』ではなくてよい。緩和する方向で統一」)。
scope 限定: user 2026-08-25 (発注ポリシーは別途議論中、持ち込みは別 session)

Goal: 外から持ち込まれる発注ポリシーを、正本 1 箇所の差し替えで反映できる状態にしておく。

方針 (2026-08-25 決裁): リグレッションレビューは opus subagent (発注書のみ・effort 高・同族許容) /
codex の敵対的レビューは指示時と高リスク時のみ / 実装は codex 固定でない。

Exit Criteria:

- [x] 規定箇所の洗い出しと照合が終わった — 6 面・120 件照合 (2026-08-25、
  `drafts/codex-usage-unification.md`、矛盾 3 系統 20 組)
- [x] 置換対象を文言で特定した一覧を用意した — `docs/codex-usage-anchors.md` (25/26 が一意に当たる)
- [x] 緩めない箇所を名指しで除外した — `docs/codex-usage-donottouch.md` (7 分類 38 件)
- [ ] (別 session) 発注ポリシーの持ち込み — ユーザーの別議論の成果を正本へ書き下ろす
- [ ] (別 session) 統一文案を各 file へ反映し、`files/` と配備先の一致まで確認した — 前提
  「ケース 1 完走」は 2026-08-26 に満たされた。残る前提はポリシー確定

Work file: `docs/codex-usage-anchors.md`、`docs/codex-usage-donottouch.md`、
`drafts/codex-usage-unification.md` (矛盾表・統一文案・参考の発注クラス案 D1〜D5)

## Medium

### 改造時のバグ作り込みを減らす方策の検討

起票: user 2026-08-22 (「まだ改造による作り込みが多すぎ。改造時にバグ作り込みを避ける方法に
ついて、もっと考えてほしい。品質ゲートとしては機能できたと認識」)

Goal: 品質ゲートで「捕まえる」だけでなく、改造時の注入発生率そのものを下げる方策を、
実測 corpus から導出して方法論へ正本化する。

Exit Criteria:

- [x] 注入 corpus を起源 class 別に集計した基礎表を作る — `docs/injection-corpus-baseline.md`
  (2026-08-25: 11 巡 25 件、決定的 gates の捕獲 0 件)
- [x] 発生率を下げる候補方策を提案した — `docs/injection-prevention-proposal.md` (2026-08-26、7 件)
- [ ] どの方策を採るかをユーザーが決める — 評価文書 §5.4 の推奨: 契約コード化 (入口限定) /
  削除第一 / 変異生存数 (発注側所有) を採り、他 4 つは捨てる
- [ ] 採用された方策を正本化し、次の改造案件で発生率を再実測する
- [ ] 注入 25 件の hunk 遡及 — 既存集約の回避が相関どまりのため。方策の採否で「捨てる」なら不要
- [ ] 機械検査 3 案の実装 — 名前の実在照合 / 直す前後の判定くらべ / わざと壊すテスト。
  2 番目 (`claude_ab_probe`) は廃棄決定 (2026-08-26)。残り 2 案の要否は方策の採否で決める
- [ ] 敵対的レビューの位置づけのずれを揃える — skill (高リスク時のみ) と方法論 §7.3 (毎巡) の
  食い違い。方法論の 1 ページ化で解消する

Work file: `docs/injection-corpus-baseline.md`、`docs/injection-prevention-proposal.md`、
`drafts/ruling61/` と `drafts/gates/` (注入 corpus の回帰レビュー報告書・gitignore)

### 方法論の実証: 小規模ツール新規作成で敵対レビューの収束を実測する

起票: user 2026-08-13

Goal: 小さな要件の新規ツール作成を数ケース、方法論を適用して実施し、収束の成否・round 数・token を
実測して最終成果を測る。

Exit Criteria:

- [x] 前提: sentinel の出口が決着している — 2026-08-22 決着 (凍結 `97743bd`)。2026-08-26 に
  小さく書き直す決裁へ更新
- [ ] ケース選定と成功基準をユーザーと合意する — ケース 1 = `claude_ab_probe` (合意 2026-08-25)。
  結果 = 7 巡・非収束・巡 7 で指摘倍増、評価は `docs/adversarial-loop-meta-evaluation.md`。
  ケース 2 以降は方法論の 1 ページ化後に §5.1 の protocol で行う
- [ ] 各ケースの結果を方法論へ反映する — 2026-08-21 に確定した教訓 6 点 (機構的排除は loop を
  収束させない / fix しながら埋め込む行動の排除 / レビューは品質推定 / 計数は script /
  統計装置は規模で選ぶ / scope は round 種別で設計) は評価文書 §5.3 の 6 項目へ統合する

Work file: `docs/methodology-case-ledger.md` (ケース 1 の台帳・凍結予定)、
`docs/adversarial-review-methodology.md` (1 ページ版へ置換予定)

### 随伴エージェント待ち — モデル判定へ回す案件 (凍結)

起票: user 2026-08-25 (「随伴エージェント行きを凍結扱いでまとめて」)。
凍結: user 2026-08-23 (随伴エージェントができるまで hook の改善は凍結)

Goal: 語のパターンや代理指標では判定できないと実測で確定した案件を 1 箇所に集め、随伴
エージェントが使えるようになった時点で設計を再開できる状態に保つ。凍結中は誤爆と欠落の
記録だけ続け、regex の語彙追加・しきい値調整・新検査の追加は行わない。

1. 自作癖 — 追加行数という代理指標は 4 点で壊れていた (委譲があると黙る / undercount で鳴る /
   正本の AND 条件を見ていない / subagent の編集が乗らない)。案: diff と発注記録を渡し
   「既存部品があるのに再構築したか」を判定させる
2. 発話の意図判定 — warn 系検査 9 種の誤爆 9 件は 3 型 (語の境界と用法を見ない / 窓が turn 単位で
   狭い / 窓が広すぎ自分の出力を含む)。案: 当該 turn の本文だけを渡し「遂行宣言か説明か引用か」
   「証跡が直近にあるか」を判定させ、警告文に指摘語を載せない。逐語記録は
   `git show 65a4214^:todos.md`
3. 契約転写の乖離 — 散文と実装の意味の一致を語彙照合に落とすと 2 と同じ誤爆になる。案: hunk ごとに
   散文とコードを対で渡し、一致判定だけをさせる
4. 前提の転移 — 変更が暗黙に持ち込む前提は決定的に列挙できない。案: 3 と同じ経路で前提を
   列挙させ、変更後も成り立つかを判定させる

Exit Criteria:

- [ ] 随伴エージェント (別プロジェクトで検討中) が利用可能になり、上の 4 件の設計を再開できる
  状態になった — それまで作業しない
- [ ] (再開後) 4 件それぞれについて、モデルへ渡す単位と判定の出力形を決め、誤爆率を実測する

Work file: `docs/injection-corpus-baseline.md` (項目 3・4 の件数の出所)
