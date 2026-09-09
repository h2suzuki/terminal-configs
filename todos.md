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
なお私は、 この CAVEAT を最初に書いたとき閉じた当の commit (`3b5d077`) を開かず、 別 commit を
根拠に「出したのは gate の値域拒否で、 動詞が違う」と書いた。 偽である。 CAVEAT の中で
CAVEAT の言うバグをやった。 指摘を受けて commit を開いて訂正した。
緩和策: 走らせて出力を見ていないものを完了と書かない。 何を閉じたかは、 閉じた commit を開いて
確かめる。

CAVEAT: 要件の動詞と出荷物の動詞がずれたまま閉じた (2026-08-29 訂正)
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

- [ ] Stop の拒否文が skill の形を手渡す経路を作る — skill 単体では発火できないため
- [ ] 3,400 byte 以下に収める (同種 skill は 2,033 / 2,100 / 3,346 byte)
- [ ] (要相談) 仕上げるか材料から作り直すかを決める — 前 session で「show-me が実際に何をして
  いるか + 再発回数の実測から出発して再設計する」指示が出ており、 上の 3 条件と両立しない

Work file: branch `wip/lessons-learned-split` の
`files/claude_managed-skills/report-in-plain-words/`

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

### root session で root_dir_guard の報告経路を実地確認する

起票: fable-5 2026-09-10 (H.S. 依頼「root 実行時に / 直下へ一時ファイルを落とす問題を直せ」から派生)

Goal: root で動く Claude Code session で、 host 実行の Bash が / 直下に entry を作った時に
`root_dir_guard.py` の事後層が systemMessage と decision:block で報告する。

Exit Criteria:

- [ ] root session (配備済みの managed hooks が効く環境) で / 直下に entry を 1 つ作る command
  を流し、 画面に `root-dir-guard: / 直下に新しい entry: ...` が出て Claude が報告することを
  確認する。 uid 1000 の session では / に書けないため未確認 (2026-09-10)
- [ ] 確認で作った entry を H.S. の指示で消す (hook は移動も削除もしない設計)

Work file: `last-session-handoff.md` の同名 section (手順と contingency)。 hook 本体は
`files/claude_managed-hooks/root_dir_guard.py`、 test は同 dir の `root_dir_guard.test.py`

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

Work file: 件数の出所だった基礎表 doc は 2026-09-06 に削除、必要なら git 履歴から戻す
