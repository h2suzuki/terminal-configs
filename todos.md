# Todos

CAVEAT: 調査前の推論 (2026-08-29、ユーザーが court バグと同等の重大バグと認定)
調べる前に立てた推論を、 Claude が事実として出力する。 2026-08-28 18:04 〜 2026-08-29 04:48 の
session (inject_log.session_id = ff720c04) で、 確かめずに書いた断定 8 件のうち 7 件が実測に否定された。
残る 1 件「hook が存在しない」は結論だけ当たり、 根拠 (SubagentStop event の実在) を一度も
確かめていなかった — 当たった推論も、 なぜ当たったか言えないなら同じ欠陥。
**測って書いたものも外れる。** 「再発の上位 2 件で約 6 割」は推測でなく測定だった。 除外ゼロで
走査し、 件数表も貼った。 それでも 25 pt 外れた (正しくは 35%) — `grep -c '^### '` の数え方が
対象の形に合っておらず、 書式違いの事例を数え落とし、 2 位の entry を走査対象に入れていなかった。
**読んだ直後でも止まらない。** この CAVEAT を commit した 2 分後、 すぐ下の CAVEAT に「1 年分の
session に届かなくなり」と根拠なく書いた。 止めたのは読み返しではなく、 数字を 1 つ DB に
当てに行ったこと。
緩和策: 「無い」「そうなっている」と書く前に、 走査した空間を名指しで書く — 作業コピーか、
git 履歴か、 DB か、 動いているプロセスか。 除外ゼロで走査し、 出力を貼る。 貼った出力は、
数え方が対象の形 (見出し・箇条書き・複数書式) に合っているかを 1 件だけ目視で照合してから
件数を書く。 出力に自作 script が印字した結論文が混ざっていないか、 貼る前に見る。

CAVEAT: 調査前の推論 — 完了判断での再発 (同じバグの別場面)
完了の判断も推論なので、 調べる前に書けば同じように外れる。
2026-08-27 の要件は「surface hook が when: (prompt / stop / after-subagent) で振り分ける」。
`3b5d077` が「C16 family (`when:` に stop を含む entry だけ) として配備、 配備先で実発火を確認」
と書いて閉じた。 出したものは振り分けそのもので、 欠陥は **3 値のうち 1 値しか作らなかった**こと。
`when: after-subagent` の entry を 1 件置いて subagent を走らせれば済む確認をせず、 「stop だけ」と
自分で書いた文のまま閉じた。 `when:` を置いた 2026-08-27 11:16 から 2026-08-29 まで surface は 0 回。
レビューは 6 巡続いた (同 session の workflow 合計は 858 万 token・49 agent。 うち研究と実装の 2 本
246 万 token・19 agent はレビューではない)。
なお私は、 この CAVEAT を最初に書いたとき閉じた当の commit (`3b5d077`) を開かず、 別 commit を
根拠に「出したのは gate の値域拒否で、 動詞が違う」と書いた。 偽である。 CAVEAT の中で
CAVEAT の言うバグをやった。 敵対レビューが指摘し、 commit を開いて訂正した。
緩和策: 走らせて出力を見ていないものを完了と書かない。 何を閉じたかは、 閉じた commit を開いて
確かめる。

CAVEAT: 要件の動詞と出荷物の動詞がずれたまま閉じた (2026-08-29、敵対レビューで訂正)
要件 `8c504f1` は「surface hook がそれで振り分ける」。 出荷 `6451a19` が出したのは gate の値域拒否
だけで、 振り分けは書かれていない。 `2fb99ff` が項目を Close し、 `f91150f` が block ごと削除した。
その削除された本文自身が「`when:` に stop を含む entry だけ配備」と書いている — **半分だと認める
同じ文の中で、 完了として閉じた。**
実測 (2026-08-29): 失敗 session `ff720c04` の inject_log は emit 23 件・mismatch 12 件で、
`feedback_architecture_before_review` は 0 件。 ただし当時この entry は `when: prompt after-subagent`
で、 出荷済み hook は `when:` を読んでいない —— prompt の候補から外れてはおらず、 届かなかったのは
順位であって route の不在ではない。「route が無いから届かなかった」は私が書いた誤った因果で、
実測の前に因果まで書いた結果である。
緩和策: 閉じる前に、 要件の動詞 (振り分ける / 拒否する / 記録する) と出荷物の動詞を並べて書く。
原因を書くときは、 その原因が無ければ結果が変わったことを実測で示してから書く。

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

### WSL2 で claude 実行中に Windows ホストを寝かせない

起票: user 2026-08-28

Goal: claude が動いている間 (idle 含む) Windows ホストがスリープせず、 数時間後にリモートで
入れる。 抑止を掴んだまま残るプロセスを作らない。

Exit Criteria:

- [ ] owner session 方式で実装 — 共有 1 file に session_id / 最終実行時刻 / 戻り値を書き、
  owner だけが 30 秒経過で powershell を叩く (ユーザー指示 2026-08-29)。 常駐・lease・boot id・
  throttle marker は不要になるので削除する
- [ ] 実機で確認 — 複数 session 下で powershell 発行が 1 つの session からのみ起きること、
  idle session でも継続すること
- [ ] 抑止が生存 session を越えて残らないことを確認する

Work file: branch `wip/lessons-learned-split` に旧実装 (常駐 supervisor 方式) が退避済み。
旧設計の実測 (statusline 描画間隔 最大 12 秒 / 一発叩き 0.30-0.61 秒) はそこの README にある

### lessons-learned repo を public / private に分離する

起票: user 2026-08-28

Goal: 公開 repo に非公開の内容が出ない状態で、 教訓の公開版を持つ。 opt-in で
public / private / both を選べる。

Exit Criteria:

- [ ] 公開 clone へは一切書かない — gate は無条件 deny、 dir は root 所有で非書き込み、
  publish は root の migration コマンドのみ (ユーザー指示 2026-08-29 で設計を置換)
- [ ] memory-routing の最初の書き込みは必ず private。 public 版は蒸留したものを移し private
  から消す。 public のみの構成では新規 entry を書けない
- [ ] 公開への昇格は PR merge 必須 (branch protection + filter を CI 検査 + subagent 観点レビュー)
- [ ] GitHub 側の rename と public 版作成 — 公開対象の一覧を H.S. が見てから実行する
- [ ] extra/lessons-learned.sh が mode と repo 名を引数で取り、 選択を gitignore file に保存する

Work file: branch `wip/lessons-learned-split`。 出荷不可の理由 (漏洩 7 経路のうち 2 件が未閉塞)
は `f03a801` の commit message にある。 置換後の設計では大半が削除対象

### report-in-plain-words skill を仕上げる

起票: user 2026-08-28

Goal: 日常語で書く・報告する形を渡す skill が、 Stop の拒否から呼ばれて機能する。

Exit Criteria:

- [ ] 敵対レビューの残指摘を閉じる (自己採点を復活させている箇所、 反証済み対策の再掲、
  発火経路の欠如)
- [ ] Stop の拒否文が skill の形を手渡す経路を作る — skill 単体では発火できないため
- [ ] 3,400 byte 以下に収める (同種 skill は 2,033 / 2,100 / 3,346 byte)
- [ ] (要相談) 仕上げるか材料から作り直すかを決める — 前 session で「show-me が実際に何をして
  いるか + 再発回数の実測から出発して再設計する」指示が出ており、 上の 3 条件と両立しない

Work file: branch `wip/lessons-learned-split` の
`files/claude_managed-skills/report-in-plain-words/`

### handoff の background 未回収検出が subagent を取りこぼす

起票: opus-5 2026-08-29 (ユーザー指摘「バックグラウンドタスクの待ち合わせか停止が漏れている」)

Goal: handoff 手順が挙げる 4 種類の background すべてで、 未回収のまま session を閉じられない。

Exit Criteria:

- [x] Agent (subagent) の起動を検出する — text block を連結してから先頭を見る
- [x] 完了通知だけが窓にある時に block が warn へ落ちる経路を塞ぐ — subagent の起動が読めた
  結果、 通知だけが残る状態が消えた (決裁 3 の「窓外なら warn」はそのまま)
- [x] 起動文字列が本文に現れただけの行を起動と数えない — 起動行を本文先頭に錨づけ
- [x] id が完了通知と一致しない 2 件も直した — `ID: <id>. Output is…` の `.` を id に含めていた、
  現行 CLI の通知は queue-operation entry の `content` にあり user entry を見ても無い
- [x] Monitor の起動形を実測し、 検出の要否を確定した — 実際に 1 つ起動して確認。 `Monitor started
  (task <id>,` は 3 形式のどれとも一致せず、 通知だけが残る同じ穴だった。 進捗 `<event>` は同じ
  task-id を運ぶので完了と数えない
- [x] 配備した — base setup 実行後、 両 file とも配備先と IDENTICAL。 配備先の hook に対して
  契約 test 170 件 green、 `managed-settings.d/extensions.json` に Stop hook として登録済み
- [x] 契約 test を red-first で追加した — 5 件、 旧実装で全部 red。 実 transcript 5 本の replay で
  未回収 5/1/2/1/9 → 0/0/1/1/0 (残る 2 件は途中で切れた session)
- [x] handoff SKILL.md の Pre-handoff checks 4 に「待ち合わせる」を選択肢として明記した

Work file: `last-session-handoff.md` (再開手順)、`files/claude_managed-hooks/stop_checks.py` の
`_background_sets`、`files/claude_managed-skills/handoff/SKILL.md` の Pre-handoff checks 4

### 中断 session で出た教訓を memory entry にする

起票: opus-5 2026-08-29 (前 session `ff720c04` の未完了項目を引き継ぎ)

Goal: 2026-08-28〜29 の session で出た 5 つの教訓が、 同じ場面へ来た時に surface される形で
保存されている。

Exit Criteria:

- [ ] 不在主張の証明 (「無い」と書く前に走査した空間を名指しする) を entry 化
- [ ] 裁定前の材料の言い直し (subagent の所見だけで外部資料へ裁定を下さない) を entry 化
- [ ] 要件と出荷の動詞照合 (要件の動詞と出荷物の動詞が一致するかを閉じる前に見る) を entry 化
- [ ] 自分が回す loop の停止判断 を entry 化
- [ ] 配備手順は正規手順を読んでから出す を entry 化 — 2026-08-29 に `sudo cp` と
  `claude_user_settings inject` を並べた 6 行を自作した。 正規は base setup 1 本で、
  規則は `last-session-handoff.md` (複数 file・hook 登録変更は base setup) と README
  (末尾で `install_claude_extensions` まで走るので別途実行は不要) の両方に書いてあった
- [ ] 5 件とも `when:` / `check:` を書く — 3 値とも振り分けが動くのでどれを選んでもよい

Work file: todos.md 冒頭の CAVEAT 3 件 (実測の出所)

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

### 試行: 一次ソース確認の指示を codex と同じ形で置いてみる

起票: opus-5 2026-08-29 (ユーザー許可「無駄かもしれないが、悪化はしないだろう。という想定
の下で todo に登録してもよい」)

Goal: 「調査前の推論」バグに対し、 codex で効いている形の指示を Claude 側でも試し、
効いたかどうかを実測する。 効かなければ捨てる。

前提 (ユーザー観測 2026-08-29): codex は AGENTS.md 相当に「必ず一次ソースにあたって裏付けを
とれ」と書くと律儀に守る。 CLAUDE.md とは効きが違う。 このバグは fable でも起きるが codex では
未観測。 hook 化は複数回試して未成功。

Exit Criteria:

- [ ] 置き場所を決める (CLAUDE.md 追加はユーザー承諾が要る。 skill / memory も候補)
- [ ] 置く前に、 効いたと言える判定方法を先に決める — 「確かめずに書いた断定」の件数を
  session ごとに数える形。 置いた後に基準を作らない
- [ ] 一定期間後に件数を比較し、 変化が無ければ削除する (残すことを既定にしない)

Work file: なし。 バグの記述は本 file 冒頭の CAVEAT 3 件

### (要相談) 「先に形を決めて材料を当てはめる」を止める機構

起票: opus-5 2026-08-29 (前 session `ff720c04` の未完了項目を引き継ぎ)

Goal: subagent の所見だけを根拠に外部資料へ裁定を下す経路を、 機構で捕まえるかどうかを決める。

Exit Criteria:

- [ ] (要相談) 作るかどうかをユーザーが決める — 旧設計は誤検出 3/3 で破棄済み。 先に
  `stop_checks.py` の `_ruling` が実際にどの条件で発火しているかを実測してから設計する
- [ ] 採る場合: 実 corpus で誤検出率を測ってから配備する

Work file: `files/claude_managed-hooks/stop_checks.py` の `_ruling`

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
