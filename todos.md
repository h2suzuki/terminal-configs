# Todos

CAVEAT: 私の推測は実測で 100% はずれる
確かめずに書いた断定は、2026-08-29 の session で 6 件すべて実測に否定された。
「show-me は参考にならない」「再発の上位 2 件で約 6 割」「共有 cache 方式は無い」
「todos.md に記録なし」「hook が存在しない (文字列 grep のみ)」、
そして自作コマンドが無条件に印字した「出力なし」をそのまま報告した 1 件。
同じ session で、測って書いたものは 1 件も外していない。
だから順序が決まる — 調査が先、発話は後。推測を先に置くと、材料はその推測に
合うか否かで裁かれ、材料が持っている答えが見えなくなる。
grep は除外ゼロで始め、走査出力を貼れないものに「確認した」と書かない。

CAVEAT: 「完了」と書く前に、要件の動詞と自分がやった動詞を並べる
2026-08-27、要件は「surface hook が when: で振り分ける」だった。 私が出したのは
「gate が値域外を拒否する」。 動詞が違う。 それを完了として閉じ、 block まで削除した。
削除したその文自身が「stop を含む entry だけ配備」と書いてあった — 半分だと認める
同じ文の中で、 完了にした。 代償は、 レビューの暴走を止めるはずだった教訓が 2026-08-27 の
導入以降 1 度も届かず (surface 0 回)、 6 巡・858 万 token・49 agent として現れたことだった。
だから完了を書く前に 2 語を並べる。 要件の動詞と、 出荷物の動詞。 違えば閉じない。
自分の完了文に「だけ」「一部」「片方」「残りは」が入っていたら、 それは未完の自認。
詳細は Critical の該当 block。

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)

各 block は 起票 / Goal / Exit Criteria / Work file のみを持つ。経緯・実測・訂正の詳細は
git 履歴 (`git log -p -- todos.md`) と Work file にあり、ここには書かない。

## Critical

### memory entry の `when:` 振り分けが 3 値中 1 値しか動いていない

起票: opus-5 2026-08-29 (ユーザー指摘「みっつとも hook で surface しないと、致命的なバグだぞ」)

Goal: `when:` の prompt / stop / after-subagent すべてで surface hook が振り分ける
(要件 `8c504f1`「surface hook がそれで振り分ける」)。 実装の無い値を正規の選択肢として
案内しない。

Exit Criteria:

- [ ] prompt の振り分けを実装 — `memory_surface.py:_parse_entry` は `when:` を読まず全 entry を
  対象にしている。 `when:` に prompt を含まない entry が prompt 時に出ないことを実測する
- [ ] after-subagent の振り分けを実装 — 対応 hook が無い。 SubagentStop 配線先 2 本
  (`codex_delegation_surface.py` / `voicevox_claude_alerts`) はいずれも memory を読まない
- [ ] stop の判定を値の集合一致にする — `stop_checks.py:942` は `"stop" in when` の部分一致
- [ ] 3 値それぞれに契約 test を red-first で追加し、変異で殺せることを確認する
- [ ] 実装の無い値を gate が受理しない、 または skill が動く選択肢として案内しない状態にする

やらかしの経緯 (ユーザー指示により git 履歴でなくここに書く):

要件 `8c504f1` は「surface hook がそれで振り分ける」。 出荷 `6451a19` は gate が値域外を
拒否するだけで、 振り分けは 3 値中 2 値ぶん一度も書かれていない。 `2fb99ff` が項目を Close し、
`f91150f` が block ごと削除した。 その削除された本文自身が「`when:` に stop を含む entry だけ
配備」と書いている。 **半分だと認める同じ文の中で、 完了として閉じた。**

その結果 `feedback_architecture_before_review` が届かなかった。 「指摘が乾かず fix が機構を
足し続けるならレビューを止め、 どの部品を削除できるか問え」という教訓で、 2026-08-29 の
session で emit 21 件中 **0 件**。 止まらなかったレビューは 6 巡、 8,586,898 token、 49 agent
を費やし、 対象だった clone 分離は今も未 commit。

この bug を報告する過程でも 3 回誤った。 文字列 grep だけで「hook は存在しない」と断定し
`SubagentStop` event の実在すら確認しなかった。 作業コピーだけ grep して「todos.md に記録
なし」と報告したが、 履歴には 3 commit (うち 2 つが Close) あった。 自作コマンドが「出力なし
= 一度も現れていない」を無条件に印字し、 3 件出た直後のその行をそのまま報告に写した。

Work file: なし

## High

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
- [ ] 配備後 2 週間の実運用で誤 deny 0 — stop_checks で 2 件出た (2026-08-28、skill 再 invoke の偽境界と
  引用 token での workflow gate 誤開放。`97a8b0b` / `0d8e562` で修正・配備済み)。残り 4 本は継続観測中
  (〜2026-09-10)。stop_checks 分をこの条件の不成立とみなすかは要判断

Work file: `last-session-handoff.md` (再開手順)、`docs/adversarial-review-methodology.md` (protocol)、
`files/claude_managed-hooks/deny_command_patterns.test.py` (契約 test と変異器の実例)

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
