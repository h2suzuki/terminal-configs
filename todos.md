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
  approach を捨てる。ケース 3〜7 = hook / CLI 5 本の書き直し (Medium「方法論の実証」block は
  2026-08-27 決裁で本 block へ併合)

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
  同日追加決裁: blocking 昇格 8 件を採用、gate 済み entry 3 件はホストで退役。scope 上限 (org 60)
  も同枠で採用扱いにしたが、説明不足の一括承認だったため同日 revert (経緯は上の衛生 gate 項目)
- [ ] memory 衛生を機構化した — org 上限 60 は実装・配備まで進めたが、承認不備 (D3 は label への
  一括承認のみ・60 の根拠は未提示) の指摘で 2026-08-26 に revert (`14c568e`。配備側も同日 cp で
  巻き戻し・E2E 済み)。近接重複の検出は corpus 計測で不採用 (dup pair と無関係 pair の score が重なり
  分離閾値なし)。2026-08-27 方向: 衛生 deny は `memory_routing_gate.py` (Write lint gate、revert した cap の
  元の場所) へ統合する。規則と数値は scope 再チェック後に挙動 1 行で承認を取ってから実装
- [ ] 決定的に検出できる教訓 8 件を blocking gate へ昇格し entry を退役した — 2026-08-26 に 7 件を配備
  (`deny_command_patterns.py` 5 規則・`deny_llm_call_in_hook.py`・`playwright_listener_gate.py`、
  E2E で deny を実測) し entry 10 件を退役。残り = done_state_ledger の Stop block 化 (stop_checks の
  書き直しで実装)。list 形式 (`"claude", "-p"`) を覆う v2 も同日 19:56 に配備済み
- [x] 重複 cluster を統合した — 2026-08-26 に 3 組 8 件を org の新 entry 3 本 (`feedback_lesson_to_action_not_report` /
  `feedback_violation_countermeasure_delete_first` / `feedback_self_build_over_delegation`) へ統合 Write し、
  旧 8 件を `claude_memory_sync --retire` で退役 (Bash から直接通った。commit `2c85170`〜`908bab7`、push 済み、
  org 70 → 62 で disk と index が一致)。gate cover 済みの 3 件は同日退役済み
- [ ] 退役の他マシン伝播は SessionStart の pull が担う (実装済み・smoke 38/38)。残り = 未 push / pull 失敗の起動時通知の要否 (未決)
- [x] 到達経路を測って回す機構を配備した (2026-08-26、aa3c1dd) — surface の (entry, session) 上限 2 回と
  `claude_memory_sync --reach` (30 日 emit 0 / ≥ 20 の列挙。初回: never 70 / hot 6)。30 日後に到達可能
  entry の未到達率が 43% → 25% 未満かで判定
- [ ] 予告 entry 3 件 (`architecture_before_review` / `self_build_impulse` / `threat_model_in_review_order`) を
  codex_order_lint の `## 処置の種別` gate へ昇格して退役した (gate は「肥大化した hook と CLI」block の
  order_lint 書き直しに含める。`self_build_impulse` は 2026-08-26 に `feedback_self_build_over_delegation`
  へ統合済みなので gate 着地時は部分 cover 注記に留める。retrieval で届かせる backtest は行わない —
  発話証跡なし。gate 昇格合意 (2026-08-26 00:46「それなら良さそうです」) からの派生であり決裁ではない。要確認)

Work file: `last-session-handoff.md` (再開手順)、`~/.claude/hooks/memory_surface.py` (surface 方針の実装)、
`/var/lib/claude-rag-memory/memory_index.sqlite3` の `inject_log` (emit / mismatch の実測)

### memory surface の有効性 — 効く advise と効かない advise を実測で分ける

起票: user 2026-08-26 (「大多数の advise memory が効かなかったとして、有効な memory もゼロなのでしょうか？」
「効く advise 効かない advise のカテゴリーを知りたい」)

Goal: surface された教訓が行動を変えた event を transcript 実測で数え、効く / 効かない advise の型を分けて、
Stop 時 surface (2026-08-26 に削除) の扱いを根拠つきで決める。

Exit Criteria:

- [x] 実測した — 2026-08-27、全 transcript の surface 1,459 件から 508 件を opus 25 agent が判定・16 agent が反証:
  生存 17 件 (11 entry、全て Stop 時)、prompt 時 0、対照比 順守 +20 pt (Stop 時)、定型文のみ fable-5 85% / opus-5 17%。
  効いた型 = 直前の出力に今すぐ当てられる検査動作を 1 つ指定する reminder (T1 / T2 / T3 / T6)、効かない型 = 態度・文体・否定形
- [x] 報告を docs/ へ正本化した — `docs/memory-surface-efficacy.md` (2026-08-27、計測日・母数・執筆規準 6 点を含む)
- [x] Stop 時 surface の処遇をユーザーが決めた — 2026-08-27 決裁「b 効いた型に限り文言を変えて再導入、memory writing の
  フォーマットチェックで、効かない文面の混入を防止」
- [ ] 実装 1 = memory 書式 gate: entry frontmatter に `check:` (直前の出力に当てる検査動作 1 文・肯定形・100 字以内) を
  新設し、`memory_routing_gate.py` が欠落 / 否定形のみ (「するな」だけで動作なし) を deny する — 挙動 1 行の承認後に実装
- [ ] 実装 2 = Stop 時 surface の再導入: `check:` を持つ entry のみ、文言「抵触するなら修正してから完了。しなければ
  何も書かない」で surface する family を stop_checks 書き直しの契約に含める (旧文言の「確認せよ」は使わない)。
  あわせて entry に `when:` (prompt / stop / after-subagent) を設け、surface hook がそれで振り分ける (ユーザー提案 2026-08-27)
- [ ] 既存 entry の移行: 効いた 11 entry に `check:` を書き、態度・文体だけの entry は `check:` を書かずに Stop 対象外とする

Work file: `last-session-handoff.md` (再開手順)、`docs/memory-surface-efficacy.md` (報告の正本)、`drafts/corpus-tools/` (抽出・sampling・集計 script)

### memory entry の scope 再チェック

起票: user 2026-08-26 (「project/ にあるものも、本当に project 依存か、ちょっと疑わしくなってきた」
「１つずつ、プロジェクト固有か、一般的な話か、再チェックしたほうがよい」)

Goal: project 43 件 + user 2 件の entry を 1 件ずつ本文まで読んで P (固有) / G (一般) を確定し、
G は org へ移動して、scope が実態と一致した状態にする。

Exit Criteria:

- [x] 一次分類を作った — 2026-08-26 reminder 全読、行別 tally (script 検算) で G 候補 17 / G? 5 /
  要精読 9 / P 14 (`drafts/memory-scope-audit.md`)
- [x] 1 件ずつ本文精読で P / G を確定しユーザーと裁定した — opus agent の分類は参考にとどめ、45 件全てを私 (fable-5)
  が本文精読して判定し直し、2026-08-27 決裁「実行してよいです」(表は `drafts/memory-scope-audit.md` 末尾)
- [x] G 確定分を org へ移動した — 2026-08-27: org へ 8 件 (mcp_json_mask_stub / ask_after_rereading_rulings /
  causal_claim_without_reading_source / per_tab_state_localstorage / external_pattern_vocab_annotation /
  lock_terms_be_decisive / report_unexpected_events / sandbox_dotfile_shadow)、user へ 1 件、退役 9 件 (古い reference 3 +
  chat_emoji + 陳腐化 1 + Managed 規則が覆う 4)。旧 path は全て `--retire` 済み・push 済み
- [ ] worktree_order_gitignored_refs の実測 1 回 — worktree 内 session から codex task を起動し、worktree 外の絶対 path が
  読めるかを試す。読めれば reminder を「絶対 path で参照」に書き換えて org へ、読めなければ P のまま

Work file: `drafts/memory-scope-audit.md` (一次分類表)、`last-session-handoff.md` (再開手順)

### 肥大化した hook と CLI を新 protocol で最小限へ書き直す

起票: user 2026-08-26 (「敵対レビューで肥大化したスクリプトがあれば、すべて simplify した方がよい」)

Goal: 敵対レビューで膨らんだ 5 本を、契約 test で現行の deny 挙動を固定したうえで最小実装に置き換え、
配備後も実 corpus で誤 deny 0 を保つ。

Exit Criteria:

- [x] 着手順と protocol を合意した (2026-08-26): codex_delegation_gate + codex_worktree_gate → stop_checks →
  skill_reminder_gate → codex_order_lint。契約 test は command 文字列で決まる分岐を実 corpus で、状態依存の
  分岐を合成 case で固定し、固定 4 変異 → codex 実装 → 独立レビュー 1 巡の同 protocol で受け入れる
- [ ] codex_delegation_gate (production 1,038 行) と codex_worktree_gate (1,035 行) を書き直し配備した
- [ ] stop_checks (2,431 行) を書き直し配備した — 契約に done_state_ledger の Stop block 化 (完了語 +
  commit / push / gate / E2E / merge の欠落で block) と「warn 系は当該 Stop の最終本文だけを走査」
  を含める (turn 全文走査の再警告自走と数量の序数誤検出は 2026-08-26 に hotfix 済み `58149c2`。
  書き直し契約はこの 2 挙動を test で固定して引き継ぐ)。wind-down family に「起動した background task −
  完了通知 ≠ 0 なら block」を足す (handoff lifecycle block から 2026-08-27 に転記)
- [ ] skill_reminder_gate (1,073 行) と codex_order_lint (592 行) を書き直し配備した — order_lint は
  「機構追加」の字面で必須節を連鎖要求する判定 (2026-08-26 に 2 回誤発火) を落とし、fix 発注 3 巡目以降に
  `## 処置の種別` (閉じた選択肢) を必須にする gate を足す
- [ ] stop_checks の契約に足す family 4 つ — Task 常時計画 (新規 prompt に応答する turn で最初の非 Task tool 呼び出し前に
  Task upsert が無ければ block)、読まずに裁定 (subagent / workflow の結果を受けた turn で、最終本文が挙げた entry / path を開く
  tool 呼び出しが無ければ block)、Stop 時 surface (`check:` を持つ entry 限定)、「無駄」reminder の prompt ごと 1 回化
- [ ] 配備後 2 週間の実運用で誤 deny 0

Work file: `last-session-handoff.md` (再開手順)、`docs/adversarial-review-methodology.md` (protocol)、
`files/claude_managed-hooks/deny_command_patterns.test.py` (契約 test と変異器の実例)

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
  誤 deny (mention と execution の未区別)。2026-08-27 決裁: delegation gate の書き直し後に対応を考える
  (現行 1,038 行への patch はしない)
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

原因は単一 = 鍵ずれ (登録 = `--cwd` の git root の hash、回収 = 終了時 cwd の hash の 1 点照会)。
既製の回収機構は無い (2026-08-23 確定)。

Exit Criteria:

- [x] 方式をユーザーが決めた — 2026-08-27 決裁「書き換えるのとセットなら費用が小さく、推奨に変えます。
  → それでお願いします」: 正本を書き換えたうえで下の 4 点を全部載せる。止血として同日
  `codex_broker_reap --apply` で 11 本 (614 MB) を回収済み
- [x] 正本の書き換え — codex-delegation skill L25 / L79 (repo root の session から `--cwd wt-*` へ発注 =
  漏れる形そのもの) を「発注 session は worktree 内 (`cd wt-x && claude`) で起動する」へ改訂 (`ca2f7e9`) し、
  配備先 `diff -q` IDENTICAL を 2026-08-27 に実測。実測 (transcript 全件 2026-08-27): 発注 374 件中 345 件が
  wt-* 宛、session 自身が wt-* 内起動は 13 件
- [ ] deny (鍵ずれの回避): 発注 session の git root ≠ `--cwd` の git root を deny — worktree gate 書き直しの
  契約 claim として実装・配備した
- [ ] 記録 + SessionEnd 回収 (取りこぼし): 発注 hook が session → `--cwd` を記録し、SessionEnd hook が
  その worktree を掴む broker を停止要求 → SIGTERM → SIGKILL で回収した (`codex_broker_reap` に cwd filter)
- [x] worktree 回収時 reap + 台帳: `codex_broker_sweep.py` (SessionStart と `git worktree remove|prune` の PostToolUse
  Bash で `codex_broker_reap --apply`、回収時のみ台帳 `~/.claude/hooks/state/codex_broker_sweep/ledger.jsonl` に追記) を
  契約 test 21 件 + 変異 6 体で固定し配備 (merge `3c56a03`、配備先 2 file IDENTICAL、host smoke exit 0 — 2026-08-27)
- [ ] `codex_broker_reap` に起動中 broker の min-age guard を足す — 2026-08-27 の独立レビュー所見: `cxc-*` dir 作成 →
  `broker.pid` 書込の窓 (node 起動 0.1〜0.5 s) と `broker.json` の非 atomic 書込を stale と誤判定し、削除で永続漏れを作る。
  若い (60 s 未満) 孤児 dir と parse 不能 record は keep 扱いにし、selftest で固定する
- [x] 対策 C (回収 tool): `files/codex_broker_reap` を実装・配備 (2026-08-23)。host 実測 =
  reap 5 / keep 2 / stale 114、孤児 3 本も回収、停止要求だけで全件停止
- [x] 対策 D (upstream 報告): #380 へコメント投稿 (2026-08-24、
  `https://github.com/openai/codex-plugin-cc/issues/380#issuecomment-5388760433`)

Work file: `last-session-handoff.md` (再開手順)、`files/codex_broker_reap` (host 実行・手順は `--help`)、
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
- [x] background 作業の残処理を protocol に足す — 2026-08-27 ユーザー指摘「Background work is running と言われて終了を
  阻害されます。これは handoff protocol にチェックがもれている」(残っていたのは readback 完了待ちの Bash loop)。handoff
  skill の Pre-handoff checks に step 4「Agent / Workflow / Monitor / run_in_background の残りを完了通知で確かめ、残れば
  TaskStop」を追加 (`75486d5`、配備先 `diff -q` IDENTICAL を同日実測)。stop_checks 側の block 条件は「肥大化した hook と
  CLI」block の stop_checks 項目へ契約 claim として転記済み

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
- [x] 同型の欠落が他に無いかを棚卸しした — 2026-08-27 実測: 雛形あり = 発注書 3 種・hook・skill・memory entry・
  handoff 節・todos block。雛形なしで毎回書いている = 契約 test (5 本)・変異器 (8 本)・subagent への発注文・
  Workflow script・docs の報告書 / 規定書。scaffold を足すなら契約 test + 変異器が候補 (書く頻度が最多)
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
  live finding 1 (task の anchor ずれ、修正 `29f1891`、配備済み = stop_checks が IDENTICAL)
- [ ] `/codex:adversarial-review` は rescue 経路で代替 — 2026-08-27 決裁「rescue で代替でよい。発注書で
  同等以上のレビューができることをどうやって担保するのかが重要」。担保 = rescue subagent から companion の
  `adversarial-review` subcommand (plugin 同梱 template) を呼ぶ手順を skill に書き、gate が通すことを 1 回実測
- [ ] 検問実装への挑戦レビュー (U0 8 / U1 2、2026-08-22) の処置 — 検索コマンド block の決裁「書き直して
  シンプルに refactor した後に、対応を考える」と同扱い。U0 の 6 件は書き直し対象 3 script の契約 claim の
  候補、U0-7 と U1-2 は廃止済み hook (`8b04b7b`) 宛、U1-1 は harness 側の情報が要る (bounded-risk 候補)
- [x] (g) codex の直接起動を禁止する — deny 化・配備・live 実測 2 件 (2026-08-25 close)
- [x] (i) 自作癖の抑制 — skill の数値境界は明文化済み。hook 側は廃止 (`8b04b7b`)、後継は Medium
  「随伴エージェント待ち」block の項目 1
- [x] (h) codex-delegation skill と関連 memory entry を plugin-route 前提に改訂 — 配備済み
  (2026-08-25 close)
- [ ] 判断待ちの Task 化を強制する hook family — 実装・受け入れ済み (`5323179`)、配備済み (2026-08-27 に IDENTICAL を実測)。実測が残
- [ ] 決裁受領の記録強制を同 family に併合 — 実装済み (`5323179`)、配備済み。実測が残
- [ ] 「無駄」keyword の memory 記録 reminder — Stop family として発注済み
  (`drafts/gates/warn-family-order.md`)。2026-08-26 実測: 配備済みで発火するが、entry を書くまで
  毎 Stop で再発火する (結論確定前に書けない turn では noise)。2026-08-27 決裁「書き直し契約でよい」→
  prompt ごと 1 回の latch を stop_checks 書き直しの契約へ
- [ ] コミュニケーション規則の hook 強化 — CLAUDE.md は削らない (2026-08-21 決裁)。round 7 で
  実装済み、追加 2 項目 (過去参照語の warn / 判断依頼の書式 template) を同発注書で発注済み。
  実測・deploy が残
- [x] 発注書 lint の語彙過剰検出を直した — 語で引く 2 検査を無条件必須節へ移行 (2026-08-23、配備済み)
- [ ] 各 gate の canonical と deploy 先の diff -q 一致 + 発火の live 観測 — 配備差分ゼロ
  (2026-08-23)。未観測 1 family (question-self-containment) が残

Work file: `drafts/gates/` (発注書・verdict・回帰レビュー報告書)

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
- [ ] どの方策を採るかをユーザーが決める — 推奨案 (契約コード化 / 削除第一 / 変異生存数) への
  2026-08-26 の発話「方策は微妙。作り込まないは、回避であって、検知ではないことが、何度言っても
  理解されないのが遺憾。セッションリセット後に取り組む」。回避 (触る量を減らす) と検知 (作り込んだ
  バグを捕まえる) を分けて再設計する。採用記録はしない
- [ ] 採用された方策を正本化し、次の改造案件で発生率を再実測する
- [ ] 注入 25 件の hunk 遡及 — 既存集約の回避が相関どまりのため。方策の採否で「捨てる」なら不要
- [ ] 機械検査 3 案の実装 — 名前の実在照合 / 直す前後の判定くらべ / わざと壊すテスト。
  2 番目 (`claude_ab_probe`) は廃棄決定 (2026-08-26)。残り 2 案の要否は方策の採否で決める
- [ ] 敵対的レビューの位置づけのずれを揃える — skill (高リスク時のみ) と方法論 §7.3 (毎巡) の
  食い違い。方法論の 1 ページ化で解消する

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
