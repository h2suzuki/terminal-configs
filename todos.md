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

- [x] ユーザーが処遇を決めた — 2026-08-26 決裁「sentinel は本当に有効な最小限まで小さく
  書き直す / 方法論も同じく最小限へ (1 ページ) / ab_probe は廃棄 / 直さない指摘は台帳に書かない」
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
- [ ] 実案件を §5.1 で回し、§5.6 の指標で判定した — ケース 1 = sentinel (変異 0/4・1 巡)、ケース 2 = todos 構造
  gate (再入場 1 回)、ケース 3 = delegation gate (2026-08-27: 変異 0/4、再入場 1 回、再確認の合成入力 P0 3 件は
  bounded-risk 受入)、ケース 4 = order_lint (変異 0/4、3 巡 + trivial fix 2 件)、ケース 5・6 = skill_reminder_gate /
  stop_checks (2026-08-27: 変異 0/4、再確認 1 巡 + trivial fix で打ち止め)。残り = 配備後 2 週間 (1・2 は 〜2026-09-09、
  3〜6 は 〜2026-09-10) の実運用で用途内 P0 が 0 であること。外れたら loop approach を捨てる

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
  同日追加決裁: blocking 昇格 8 件を採用、gate 済み entry 3 件はホストで退役。scope 上限 (org 60) は説明不足の
  一括承認だったため同日 revert
- [x] memory 衛生を機構化した — org 上限 60 は承認不備で 2026-08-26 に revert (`14c568e`)、近接重複の検出は
  corpus 計測で不採用 (score の分離閾値なし)。2026-08-27 決裁「意味不明なキャップはやめろ」で数値 cap 方式は
  廃止。衛生は `claude_memory_sync --reach` の列挙 (配備済み) と退役 protocol の運用で担い、deny は作らない
- [x] 決定的に検出できる教訓 8 件を blocking gate へ昇格し entry を退役した — 2026-08-26 に 7 件を配備
  (`deny_command_patterns.py` 5 規則・`deny_llm_call_in_hook.py`・`playwright_listener_gate.py`、
  E2E で deny を実測、list 形式を覆う v2 も配備) し entry 10 件を退役。8 件目の done_state_ledger の Stop block 化は
  2026-08-27 の stop_checks 書き直し (契約 C5、配備先 IDENTICAL) で閉じた
- [x] 重複 cluster を統合した — 2026-08-26 に 3 組 8 件を org の新 entry 3 本へ統合 Write し旧 8 件を `--retire`
  (`2c85170`〜`908bab7`、push 済み、org 70 → 62 で disk と index が一致)。gate cover 済みの 3 件も同日退役
- [x] 退役の他マシン伝播は SessionStart の pull が担う (実装済み)。通知の要否は 2026-08-27 決裁「認証系エラーだったら
  通知してよい。単なる push 失敗は自動解決」→ push 前 rebase-pull・120 s 超の stray は stash・認証失敗のみ SessionStart で
  nag を実装 (`ce81746`、smoke 44/44、配備先 CLI と hook が IDENTICAL・`--status` に stashed 行を実測)
- [x] 到達経路を測って回す機構を配備した (2026-08-26、aa3c1dd) — surface の (entry, session) 上限 2 回と
  `claude_memory_sync --reach` (30 日 emit 0 / ≥ 20 の列挙。初回: never 70 / hot 6)。30 日後に到達可能
  entry の未到達率が 43% → 25% 未満かで判定
- [ ] 到達率を判定した — 2026-09-25 に `--reach` を再実行し、到達可能 entry の未到達率が 25% 未満かを記録する
- [x] 予告 entry 3 件 (`architecture_before_review` / `self_build_impulse` / `threat_model_in_review_order`) を
  codex_order_lint の `## 処置の種別` gate へ昇格して退役した — 2026-08-27 に閉じた: gate 着地 (order_lint 配備) に
  伴い 2 entry へ部分 cover 注記 (退役はしない — 構造の問い / うっかり基準の判断が固有)、review 雛形に `## 守る相手`
  節を追加。`self_build_impulse` は 2026-08-26 に `feedback_self_build_over_delegation` へ統合済み。retrieval の
  backtest は行わない (発話証跡なし)

Work file: `last-session-handoff.md` (再開手順)、`~/.claude/hooks/memory_surface.py` (surface 方針の実装)、
`/var/lib/claude-rag-memory/memory_index.sqlite3` の `inject_log` (emit / mismatch の実測)

### 肥大化した hook と CLI を新 protocol で最小限へ書き直す

起票: user 2026-08-26 (「敵対レビューで肥大化したスクリプトがあれば、すべて simplify した方がよい」)

Goal: 敵対レビューで膨らんだ 5 本を、契約 test で現行の deny 挙動を固定したうえで最小実装に置き換え、
配備後も実 corpus で誤 deny 0 を保つ。

Exit Criteria:

- [x] 着手順と protocol を合意した (2026-08-26): codex_delegation_gate + codex_worktree_gate → stop_checks →
  skill_reminder_gate → codex_order_lint。契約 test は command 文字列で決まる分岐を実 corpus で、状態依存の
  分岐を合成 case で固定し、固定 4 変異 → codex 実装 → 独立レビュー 1 巡の同 protocol で受け入れる
- [x] codex_delegation_gate (production 1,038 行) と codex_worktree_gate (1,035 行) を書き直し配備した — 2026-08-27、
  1 本 741 行に統合 (契約 C1〜C12・66 test・変異 0/4、実 corpus Bash 29,173 件で非 codex の deny 0)、merge `8ada67f`、
  配備先 IDENTICAL・旧 worktree gate 除去。レビューは初回 → fix → 再確認 → 契約訂正で再入場 → review → fix → 再確認で
  打ち止め、残る指摘は `drafts/reviews/delegation-gate/*-report.md` (bounded-risk 受入)
- [x] stop_checks (2,431 行) を書き直し配備した — 2026-08-27、1,077 行 (family 15、契約 C1〜C19・129 test・変異 0/4、
  done_state_ledger の block 化・warn は最終本文だけ・background 未回収 block を含む)。初回納品は旧 hook の実 block 234 件を
  continuation-claim 0/74 しか捕えず、旧 roster を契約に逐語で載せて訂正 → 61/74・meta-announce 13/15。レビューは初回 →
  fix → 再確認 → 発注側 trivial fix で打ち止め、merge `caf7a70`、IDENTICAL。残る指摘は `drafts/reviews/stop-checks/*-report.md`
- [x] skill_reminder_gate (1,073 行) を書き直し配備した — 2026-08-27、428 行 (契約 C1〜C11・inv1〜9・65 test・変異 0/4、
  実 corpus Write/Edit 6,484 + Bash 30,236 件で旧 allow → 新 deny 0)。レビューは初回 (P0 3) → fix → 再確認 (P0 1) →
  発注側 trivial fix で打ち止め、merge `d448ba7`、IDENTICAL。残る指摘は `drafts/reviews/skill-reminder/*-report.md`
- [x] codex_order_lint (592 行) を書き直し配備した — 「機構追加」の字面で必須節を連鎖要求する判定 (2026-08-26 に
  2 回誤発火) を落とし、fix 発注 3 巡目以降に `## 処置の種別` (閉じた選択肢) を必須にする gate を足した。2026-08-27、
  557 行 (同居 test と --selftest 廃止)、契約 C1〜C17・36 test・変異 0/4・実 corpus 7 本の所見一致、merge `939fb54`、
  `/usr/local/bin` と fix 雛形が IDENTICAL。残る指摘は `drafts/reviews/order-lint-*-report.md`
- [x] stop_checks の契約に足す family 4 つ — Task 常時計画 (新規 prompt に応答する turn で最初の非 Task tool 呼び出し前に
  Task upsert が無ければ block)、読まずに裁定 (subagent / workflow の結果を受けた turn で、最終本文が挙げた entry / path を開く
  tool 呼び出しが無ければ block)、Stop 時 surface (`check:` を持つ entry 限定)、「無駄」reminder の prompt ごと 1 回化
  — 2026-08-27、C6 task-plan-first / C8 ruling-without-reading / C16 memory-reminder (latch は stdout に載った Stop だけ) として配備
- [ ] 配備後 2 週間の実運用で誤 deny 0

Work file: `last-session-handoff.md` (再開手順)、`docs/adversarial-review-methodology.md` (protocol)、
`files/claude_managed-hooks/deny_command_patterns.test.py` (契約 test と変異器の実例)

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
- [x] 同型の欠落が他に無いかを棚卸しした — 2026-08-27 実測: 雛形あり = 発注書 3 種・hook・skill・memory entry・
  handoff 節・todos block。雛形なしで毎回書いている = 契約 test (5 本)・変異器 (8 本)・subagent への発注文・
  Workflow script・docs の報告書 / 規定書。scaffold を足すなら契約 test + 変異器が候補 (書く頻度が最多)
- [x] 効果を実測した — 基準値は取得済み (2026-08-24: 発注書 144 件中 現行規約で所見ゼロ 12 件 = 8%)。
  2026-08-27 再計測 (`drafts/corpus-tools/order_lint_rounds.py`、transcript の lint 呼出と結果を対応付け): 導入後の
  発注書 37 本のうち初回 lint 所見ゼロ 24 本 (65%)、緑までの平均 lint 回数 1.20、未緑 7 本は lint 試験・review 雛形の
  意図的な空欄・変数 path で発注には使っていない

Work file: なし (本 block で自己完結)

### 検問 gate 群の実装・受け入れ・配備

起票: user 2026-08-21 (「強制が必要な事項 2 つ」の列挙)

Goal: 車輪の再発明・無検問 loop・判断待ちの Task 化漏れを、約束でなく決定的 gate で禁止する。

Exit Criteria:

- [x] review 運用の gate 群を実装・smoke・deploy — (a)〜(f) + stateless 化 + warn は fix round 12
  まで回して回帰 filter pass、main merge・deploy 済み (2026-08-22)。warn family の実測は下の統合項目へ
  (誤爆 9 件と凍結判断は Medium「随伴エージェント待ち」block へ集約済み)
- [x] `/codex:adversarial-review` は rescue 経路で代替 — 2026-08-27 決裁「rescue で代替でよい。発注書で
  同等以上のレビューができることをどうやって担保するのかが重要」。担保 = 実測で rescue は review 系 subcommand を
  `task` に変換するため、plugin 同梱 template の姿勢・攻撃面・所見の基準を review 雛形に転記し、review 雛形の発注書を
  rescue に task で渡す経路を skill・policy §7/§8・雛形へ反映して配備 (同日、delegation gate の独立レビュー 3 巡で使用)
- [x] 検問実装への挑戦レビュー (U0 8 / U1 2、2026-08-22) の処置 — 検索コマンド block の決裁「書き直して
  シンプルに refactor した後に、対応を考える」と同扱い。U0 の 6 件は 2026-08-27 の書き直し 5 本の契約 test に吸収、
  U0-7 と U1-2 は廃止済み hook (`8b04b7b`) 宛、U1-1 (harness 側の情報が要る) は bounded-risk 受入で閉じる
  (2026-08-27、異論なしの既定)
- [x] (g) codex の直接起動を禁止する — deny 化・配備・live 実測 2 件 (2026-08-25 close)
- [x] (i) 自作癖の抑制 — skill の数値境界は明文化済み。hook 側は廃止 (`8b04b7b`)、後継は Medium
  「随伴エージェント待ち」block の項目 1
- [x] (h) codex-delegation skill と関連 memory entry を plugin-route 前提に改訂 — 配備済み
  (2026-08-25 close)
- [ ] communication-lint 規則 3〜5 (疑問文に decision Task / 短文決裁の記録 / 質問の自己完結) の live 発火を
  各 1 回記録する — warn は transcript に保存されないので、見た session がその場で日時と本文をここに書く
  (2026-08-27 時点で 3 規則とも未観測。規則 1・2 は同日に観測済み)
- [x] 「無駄」keyword の memory 記録 reminder — Stop family として発注済み (`drafts/gates/warn-family-order.md`)。2026-08-26 実測で
  entry を書くまで毎 Stop 再発火 (noise) → 2026-08-27 決裁「書き直し契約でよい」→ 同日、stop_checks C16 第 2 規則 (prompt boundary の
  identity で latch、stdout に載った Stop だけ書く) として配備 (merge `caf7a70`)
- [x] コミュニケーション規則の hook 強化 — CLAUDE.md は削らない (2026-08-21 決裁)。過去参照語の warn は
  stop_checks C15 規則 5 として 2026-08-27 に配備。判断依頼の書式 template は成果物が無く (skills と
  drafts/gates に不在)、規則 3〜5 が同目的を担うため作らない (2026-08-27、異論なしの既定)
- [x] 発注書 lint の語彙過剰検出を直した — 語で引く 2 検査を無条件必須節へ移行 (2026-08-23、配備済み)
- [x] 各 gate の canonical と deploy 先の diff -q 一致 — 2026-08-27 に managed hook 45 本すべて一致。
  未観測 family (question-self-containment = 規則 5) は上の統合項目へ

Work file: `drafts/gates/` (発注書・verdict・回帰レビュー報告書)

## Medium

### 改造時のバグ作り込みを減らす方策の検討

起票: user 2026-08-22 (「まだ改造による作り込みが多すぎ。改造時にバグ作り込みを避ける方法に
ついて、もっと考えてほしい。品質ゲートとしては機能できたと認識」)

凍結: user 2026-08-27「Fable の週次リミットももうすぐつきるし、今のあなたにはレベル高すぎる
話だろうから、モデルがアップグレードされるまで凍結にするよ」。解除条件は同日の逐語「品質を
上げるには、バグ摘出をもっと頑張りましょう。linter が有効です。みたいなことをあなたが言わなく
なったら、この issue は解凍します」— 検知系 (摘出・lint・test・レビュー) を品質向上策として
出さなくなったとユーザーが判断した時 — 理由は同日の逐語「最新のソフトウェアエンジニアリングの
品質研究を熟知している査証」「その段階になったら、私と議論がかみ合います」。凍結中は本 block に着手しない

Goal: 品質ゲートで「捕まえる」だけでなく、改造時の注入発生率そのものを下げる方策を、
実測 corpus から導出して方法論へ正本化する。

Exit Criteria:

- [x] 注入 corpus を起源 class 別に集計した基礎表を作る — `docs/injection-corpus-baseline.md`
  (2026-08-25: 11 巡 25 件、決定的 gates の捕獲 0 件)
- [x] 発生率を下げる候補方策を提案した — `docs/injection-prevention-proposal.md` (2026-08-26、7 件)
- [ ] どの方策を採るかをユーザーが決める — 推奨案 (契約コード化 / 削除第一 / 変異生存数) への
  2026-08-26 の発話「方策は微妙。作り込まないは、回避であって、検知ではないことが、何度言っても
  理解されないのが遺憾。セッションリセット後に取り組む」。回避 (触る量を減らす) と検知 (作り込んだ
  バグを捕まえる) を分けて再設計する。採用記録はしない
- [ ] 採用された方策を正本化し、次の改造案件で発生率を再実測する
- [ ] 注入 25 件の hunk 遡及 — 既存集約の回避が相関どまりのため。方策の採否で「捨てる」なら不要
- [ ] 機械検査 3 案の実装 — 名前の実在照合 / 直す前後の判定くらべ / わざと壊すテスト。
  2 番目 (`claude_ab_probe`) は廃棄決定 (2026-08-26)。残り 2 案の要否は方策の採否で決める
- [x] 敵対的レビューの位置づけのずれを揃える — skill (高リスク時のみ) と方法論 §7.3 (毎巡) の
  食い違い。方法論の 1 ページ化で解消する — 2026-08-26 の 1 ページ化で §7.3 は消滅し、現行 6 項目 (初回レビューは
  道具本体だけ・fix 1 回・再確認 1 回) は skill の「高リスク時のみ cross-model」と矛盾しない (2026-08-27 確認)

Work file: `last-session-handoff.md` (再開手順)、`docs/injection-corpus-baseline.md`、
`docs/injection-prevention-proposal.md`、`drafts/ruling61/` と `drafts/gates/` (gitignore)

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
