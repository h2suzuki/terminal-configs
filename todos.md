# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)


## Critical

## High

### 検索コマンドの誤 deny の解消 (branch 凍結済み・受け入れ未了)

起票: user 2026-08-23 (「これは対策が打てるなら、打ってよいよ」「検出器のぶっこわれは、今なおします」)

Goal: companion の名前に言及しただけの読み取りコマンドが直接起動として弾かれる誤検出を、
起動の取りこぼしを作らずに解消する。

**経過**: codex 委譲で 2 巡回したが、いずれも回帰 filter が fail (1 巡目 = 制御語で始まる塊の
取りこぼし 18 形、2 巡目 = 同じ枝の直し漏れ)。2 巡連続の不通過を構造の signal と読み、
**判定を「塊全体の語」から「前置きを剥がした先頭の語」へ一本化**して発注側で直した。
shell の制御語 (`do` `then` 等) を前置きとして剥がす扱いに変えたので、解析器と判定の両方が
同時に正しくなる。

**実測 (2026-08-23)**: 起動 16 形すべて deny (制御語の後の直接実行・変数に隠した path・
wrapper 前置・`sh -c`・連結・相対 path・`./` 実行を含む)、読み取り 14 形すべて allow
(引数に `node` が混ざる形を含む)。81 tests / ruff / ty / diff-check / 言語 lint すべて緑。
branch `wt-mention` に `129bbaa` で凍結。

Exit Criteria:

- [x] 回帰 filter を通した — **round 3 = fail、指摘を脅威モデルで選別して決着 (2026-08-23)**。
  filter の 27 形のうち、うっかりで踏める形だけを対象に語彙 2 箇所を足して閉じた (`fd6ff4b`)。
  残す形と落とす形の判定は下の criterion に記録。以下は round 3 時点の記録。報告書
  `wt-mention/drafts/mention-guard/fix-3-regression-review.md`。誤検出の揺り戻しは pass
  (読み取り 60 形で r2 allow → cur DENY が 0 形) だが、取りこぼしで fail。
  **発注側で独立に再現済み** (`_direct_companion` を HEAD 版と直接比較): HEAD が deny する
  8 形を `129bbaa` が allow する — 制御語が**条件の位置**にある形 (`while` / `until` / `if`)、
  関数定義 (`run() { … }`)、wrapper 前置 (`watch` / `yarn node`)、pipe、括弧 200 重。
  本体位置の制御語 (`while true; do …`) と読み取り grep は意図どおり (前者 deny・後者 allow)。
  test は 69 → 81 だが round 3 の追加は 0 件で、設計の核を壊す mutation が survive する。
  **穴が「本体の位置」から「条件の位置」へ移っただけ = 3 巡連続の不通過**
- [x] **残る 1 class (D2) の扱いをユーザーが決めた** — **2026-08-23 決裁: 現状で merge・配備**。
  実測で D2 5 形のうち 3 形は `bash -n` が構文エラーで拒否する = そもそも起動しない。
  実害があるのは 2 形 (heredoc で文書を書き出してから起動 / 行末の継続記号) のみ。
  さらに試作で、token 化に失敗した塊を捨てず生の行ごとに再 token 化すると
  **heredoc 形は止まり、文書内に起動例を引用する形は誤 deny しない**ことを実測済み
  (継続記号の形は塞げず未検討)。以下は選別の詳細。2026-08-23 に脅威モデル
  (`feedback_threat_model_in_review_order` = うっかり防止) で 27 形を選別し、語彙 2 箇所
  (`SHELL_KEYWORDS` へ条件側 5 語・`OPTION_WRAPPERS` へ `watch`) を `fd6ff4b` で追加。
  監視 loop 系 5 形は閉じた。**未解決は D2 = 一部の行だけ token 化に失敗すると素通し**の
  5 形で、heredoc で発注書を書きながら同じ command で起動する形・日本語のアポストロフィで
  引用が壊れる形を含み**うっかりで踏める = 対象内**。fail-closed (token 化失敗なら deny) に
  すると、companion に言及する発注書の heredoc が誤 deny に戻るため、単純な締め方は使えない。
  非対象と裁定できるのは backtick 置換 / `make -f /dev/stdin` / 別 runtime (`bun` /
  `python3 -c`) / 括弧 200 重 / 関数定義 / `yarn` 経由。`script -q -c` は wrapper 表の
  operand 剥がし漏れで、D2 とは別口の小穴。
  **fix round 4 目に当たるため、方法論 §7.4 の敗因分析とユーザー承認が要る**
- [ ] 解析そのものの作り直しは **却下済み (2026-08-23)** — parser library 3 種が未導入で
  取得経路も無く、bash の parser 借用は入力を script に埋め込むため任意コード実行の穴
  (実測)、かつ変数展開・間接実行を含めると原理的に決定不能。この criterion は記録のため残す
- [x] 本線へ merge した — `a65da00` (`--no-ff`)。merge 後の main で 83 tests 緑、
  現実的な起動 9 形 DENY / 読み取り 5 形 allow を再測定済み。push は未実施 (main は
  origin から 21 commit ahead・ユーザー承認待ち)
- [ ] 残り 2 形を塞ぐ — heredoc 形は上記の試作で塞げると実測済み、行末の継続記号は未検討。
  塞げなければその時点で相談する
- [x] 配備し、検索コマンドが通り起動が弾かれることを実地で確認した — **2026-08-23 完了**。
  ユーザーが base setup を実行し、`files/` と `/etc` の hook 34 対すべて `diff -q` IDENTICAL
  (差分 0)。配備先の gate に payload を直接与えた実測で、**読み取り 3 形 (grep / cat / find) が
  allow・起動 4 形 (直接実行 / 監視 loop の条件位置 / `watch` 包み / 変数に隠した path) が deny**。
  さらにこの検証コマンド自身が起動の書き方 4 通りを文字列として含んだまま通っており、
  言及と実行の区別が実チェーンで機能している
- [ ] 同型欠陥を class で掃引した — 実測 2026-08-23: `skill_reminder_gate` の handoff doc 分岐が
  同じ「言及と実行を区別しない」形で、`cat` による読み取りと deny message が案内する declare
  CLI 自身を deny する (`mentions_handoff_doc` が command 全文の token 一致・書込経路不問)。
  本 branch の「前置きを剥がした先頭の語で判定」が適用できるかを判定し、できなければ別設計を起票する

Work file: `wt-mention/drafts/mention-guard/` (発注書 2 通と回帰レビュー 2 通 + 本巡の指示書)

### codex plugin の broker がセッション終了後も生き残る (別デバイスからの依頼)

起票: user 2026-08-23 (別セッション/別デバイスの調査結果を共有・「todo に記載して」)

Goal: session 終了後も生き残り、削除済み worktree を掴んだまま蓄積する broker プロセスと
その残骸を、鍵ずれの解消と状態駆動の回収の両輪で止める。

**依頼元の実測 (別デバイス・plugin 1.0.5)**: 生存 broker 38 本 (root 側と scorer 側の両方)・
回収対象 28 session・滞留プロセス 214 (cwd が削除済み)・約 3.9 GB RSS・最古は 2026-07-12 起動で
42 日間生存。生存 38 本はすべて PPID=1 に再親付け。

**本端末の確定実測 (2026-08-23・host で `drafts/codex-broker-reap.py` を実行)**:
**生存 broker 7 本**。内訳 = **reap 5 / keep 2 / stale 114** (計 121 記録)、
回収で解放 **158 MB** / 残す稼働分 114 MB。

- **reap 5 本**は対象の worktree が消滅済み — `wt-codex-review` `wt-opinion` (terminal-configs)、
  `wt-gran2b` `wt-refute` (daily-stock-analyzer)、`wt-research` (claude-design-fe-starter)。
  **3 repo の `git worktree list` に 1 つも登録が無い**ことを確認済み = 回収して安全
- **keep 2 本**は `wt-mention` `wt-ruling61` で worktree が実在。`state.json` の running job は
  **どちらも 0 件**なので稼働中の仕事は無い。ただし両 worktree とも作業自体は決着済みなので、
  worktree を撤去すれば broker も reap 対象へ落ちる (別途判断)
- **sandbox からは 7 本すべてが見えなかった** (`ps` で 0 本・全件 stale 判定)。
  プロセス表が要る判定は host で測る、という制約が実データで裏付けられた

**回収実施と、そこで判明した設計欠陥 (2026-08-23)**: `--apply` で reap 5 本 (5 本とも
停止要求だけで停止・SIGTERM 不要) と stale 114 件を処理し、記録は 121 → 2 件になった。
**その後 `/tmp` に「どの記録も指していない稼働中の broker」が 3 本見つかった** —
`wt-gran1` / `wt-msgfix` / `wt-gran2a` (daily-stock-analyzer・いずれも実体も git 登録も無し・
計 33 MB)。

- **記録を起点にしか探さない回収は、生きたプロセスを永久に取り残す**。依頼元が警告していた
  「取りこぼした子は state file を持たない孤児になり以後どの機構でも拾えない」が実在した
- **前回の `--apply` 自身が孤児を作った可能性がある**: 残骸削除は session dir の `rmdir` に
  失敗しても記録の削除まで進む順序だった (`rmdir` は空でなければ失敗する)。記録が先に消えると
  以後その置き場は辿れない
- 対策として `codex-broker-reap.py` に**孤児走査**を追加した (`cxc-*` の置き場を直接 glob し、
  記録が指していないものを列挙。prefix は `createBrokerSessionDir` の既定を実装で確認)。
  併せて走査先の既定を `$TMPDIR` のみ → **`/tmp` と `$TMPDIR` の両方**に修正
  (`$TMPDIR` だけ見ていたため sandbox では孤児 0 件と誤報していた)
- **root 側は対象なし**を確定 (ユーザーが sudo 実行 → `置き場が無い`)。この端末に `scorer`
  ユーザーは存在せず、codex の記録置き場は `/home/h2suzuki/...` の 1 箇所だけ (除外ゼロで走査)
- **孤児 3 本も回収し、本端末の取り残しはゼロ (2026-08-23)**。最終状態 = `/tmp` の置き場も記録も
  keep の 2 本 (`cxc-XrItUD` / `cxc-gvy5Kx`) だけ、孤児 0 件。
  **回収した 8 本 (reap 5 + 孤児 3) はすべて停止要求だけで停止し、SIGTERM / SIGKILL は
  一度も要らなかった** — 「停止要求を先に送る」順序を守る根拠が実データで得られた
  (いきなり強制終了していれば socket と state file が残り、孤児をさらに増やしていた)
一方 **残骸は 121 件** (`~/.claude/plugins/data` 配下の `broker.json` の全数)。teardown が
ここでも長期間完走していないことを示す。

**訂正 2026-08-23**: 当初「121 件すべてが対象ディレクトリ消滅・存命 0 件」と書いたが**誤り**。
`broker.json` の項目は `endpoint` / `pidFile` / `logFile` / `sessionDir` / `pid` の 5 つで、
**`cwd` フィールドは存在しない** (全 121 件の key を集計して確認)。存否判定に使った式が
無い field を読んでいたため、全件が自動的に「消滅」側へ落ちていた。**あの内訳は測定ではなく
式の不備**。正しい判定は (i) `pid` が生存し (ii) その `/proc/<pid>/cmdline` が broker で
(iii) その `--cwd` が実在するか、で行う必要があり、**プロセス表が要るので host で測る**。
keep / reap / stale の実数は host 実行の結果が出るまで未確定。

**原因 (依頼元の解析)**:

1. **broker に自決手段が無い** — `detached: true` + `unref()` で起動され、idle timeout も
   親死亡監視も watchdog も無い (該当語の検索でヒット 0)。終了経路は SIGTERM/SIGINT handler と
   `broker/shutdown` RPC のみで、停止は SessionEnd hook 一本に依存する
2. **SessionEnd hook の照会鍵がずれている** — 登録側は job の対象ディレクトリ (worktree root) を
   鍵に保存し、teardown 側は session の cwd で引く。ずれると hook は exit 0 のまま何もせず、
   エラーも警告も出ない。使い捨て repo 2 つでの再現 = 登録先と SessionEnd の cwd が一致すれば
   回収、違えば残存 (どちらも exit 0)
3. **write 委譲ではこのずれが正規形** — `codex_worktree_gate.py` が共有 checkout への write を
   deny し「worktree を作ってその path を `--cwd` に渡せ」と要求するため、session の cwd =
   共有 checkout / 登録鍵 = worktree となり**必ず不一致**。read-only task なら一致し leak しない

**手元ソースでの再現確認 (2026-08-23・`~/.claude/plugins/cache/openai-codex/codex/1.0.6`)**:
依頼元がコピペで落とした code block を実物から復元し、解析を照合した。1.0.5 は本端末に無いが、
依頼元が 1.0.6 と `session-lifecycle-hook.mjs` の diff 0 を確認済みなので代替になる。

- **確認 (原因 1)**: `spawnBrokerProcess` は `detached: true` + `child.unref()` で起動し、
  引数に `serve --endpoint <ep> --cwd <dir> --pid-file <pf>` を渡す (`broker-lifecycle.mjs`)。
  **broker 自身が `--cwd` を argv に持つ**ので、対策 C の keep/reap 判定はこの argv から引ける
- **確認 (原因 2)**: `handleSessionEnd` は `loadBrokerSession(cwd)` の **1 点照会**で、
  state root 配下の走査をしない (`session-lifecycle-hook.mjs`)
- **補正 A — 鍵は「cwd」でなく「git リポジトリの root」**: `resolveStateDir(cwd)` は
  `resolveWorkspaceRoot(cwd)` → `ensureGitRepository(cwd)` を通し、その realpath の
  sha256 先頭 16 桁で dir 名を作る (`state.mjs` / `workspace.mjs`)。**帰結が 2 つ**:
  (i) session の cwd が worktree の**子ディレクトリ**でも root が同じなら鍵は一致し leak しない
  (報告の「PWD 不一致」という言い方より条件は狭い)、(ii) 一方 linked worktree はそれ自体が
  別 root なので、共有 checkout との組では**必ず**不一致になる → write 委譲で必ず leak、
  という結論そのものは正しい
- **補正 B — 逃げ道の分岐が存在するが実質死んでいる (報告に無い)**:
  `handleSessionEnd` は鍵照会が空振りした時に環境変数
  `CODEX_COMPANION_APP_SERVER_ENDPOINT` を見る分岐を持つ。しかし grep の結果、この変数を
  **hook のために書き出す経路が無い** (`appendEnvVar` が伝えるのは session id / transcript path /
  plugin data の 3 つだけで、当該変数は読み手 3 箇所のみ)。さらにこの分岐が作るオブジェクトは
  **`pid` と `sessionDir` を持たない**ため、仮に発火しても `teardownBrokerSession` は
  プロセスを kill できず、停止要求の送信しかできない。**upstream 報告に足すべき項目**

**原因は単一 = 鍵ずれ (依頼元が 2026-08-23 に自己訂正)**: 当初は 2 経路 (鍵ずれ 20 本 /
「鍵は一致したが teardown 不発」18 本) としていたが、**後者の分類根拠が誤りだった**。
「一致」と見ていた PWD は**発注の瞬間に `cd` した先のスナップショット**であり、SessionEnd で
効くのは**session 終了時点**の cwd である。依頼元の反証:

- 18 本は 4 session に集中し、1 session が抱えていた worktree は 10 / 5 / 2 / 1 本。
  10 本に発注した session が回収できるのは最後の 1 本だけで、残り 9 本は鍵ずれで漏れる
- `a83cafe8` は transcript の置き場が `-root-scorer-Manufacturing-debian-scripts`、broker の対象が
  `/root/wt/issue-440` で**最初から別**。`6c6591ea` も同様 (`-home-scorer-terminal-configs`)
- `broker.json` が無い state dir は repo root 2 件だけ = 回収に成功したのは root 鍵のみ

→ **「SessionEnd 不発」という別経路を立てる必要はない**。これは対策 A (発注前に worktree へ `cd`)
の評価を上げる訂正である。ただし「1 session = 1 worktree」を守らないと 10 本中 9 本が漏れる形は
そのまま再現する。

**本端末データでの裏取り (2026-08-23)**: state dir 129 件のうち残骸あり 121 / 無し 8。

- **残骸 121 件は 1 件残らず「短命な作業ディレクトリ」を鍵にしている** — `wt-*` 形が 112 件、
  残り 9 件も `agent-*` 4 / `codex-gate-*` / `phase2-work-*` / `phase3-work-*` / `tmp-*` / `wf_*` で、
  いずれも session が居続ける場所ではない。**長命な repo root を鍵にした残骸はゼロ**
- 残骸の無い 8 件は repo root 4 件 (`terminal-configs` / `daily-stock-analyzer` / `iac-web` /
  `claude-design-fe-starter`) と、私が実際にセッションを走らせる worktree 4 件
  (`wt-gates` / `wt-bootsweep` / `wt-legend` / `wt-rebuild`)
- `teardownBrokerSession` は pid file・log・socket・session dir を削除し `broker.json` も消すため、
  **回収成功後の姿は「`jobs` と `state.json` だけ残る」** で、上の 8 件はまさにその姿。
  ただし「broker を一度も起こしていない」場合も同じ姿になるため、file だけでは両者を区別できない
- **依頼元の「回収できたのは root 鍵のみ」は本端末では言い過ぎ**: セッションを終える場所である
  worktree 4 件は綺麗になっている。**鍵が repo root かどうかではなく、session がそこで終わったか
  どうか**が分かれ目、と読むほうが両デバイスのデータに合う (＝訂正後の結論と同じ)

**確認済みの非該当**: 版は無関係 (生存 38 本すべて 1.0.5 の path から起動・1.0.4 は不在)。
1.0.6 へ上げても直らない (`session-lifecycle-hook.mjs` の diff が 0)。既製の回収機構は無い
(plugin の commands 8 / skills 3 / agents 1 と companion の subcommand 集合に broker 停止動詞なし。
cancel は job 対象で、しかも壊れているのと同じ cwd 鍵スコープで動く)。

Exit Criteria:

- [ ] 着手時期をユーザーと相談し、対策 A〜D のどれを本端末で実施するか決める
- [ ] **対策 A (鍵ずれ)**: 発注する session の cwd を worktree に合わせる。hook が受け取る cwd は
  `cd` に追従することは依頼元で実測済み。**効くのは session 終了時点の cwd**であり発注時ではない
  ため、1 session が複数 worktree に発注すると最後の 1 本しか回収されない。複数発注するなら
  worktree ごとに session を分けるか対策 B を併用する。**原因が単一と分かった (上記) ため、
  この対策が本命**。ただし守れなければ「10 本中 9 本が漏れる」形は残るので、対策 B・C は
  取りこぼしの受け皿として引き続き要る
- [ ] **対策 B (取りこぼし)**: worktree 削除の**直前**に broker を回収する。順序と粒度が要点 —
  (i) 削除後は path が消えて `fuser` が引けないので削除前に実行、(ii) 記録から endpoint を読み
  `broker/shutdown` RPC を先に送る (いきなり SIGKILL すると socket と state file が残る)、
  (iii) kill は session 単位で行う (`fuser -k <worktree>` は当該 cwd を持つプロセスしか殺さず、
  依頼元実測で issue-42 は 64 プロセス中 44・issue-440 は 25 中 18 しか掴んでいない。取りこぼした子は
  broker 死亡後に state file を持たない孤児になり以後どの機構でも拾えない)。`fuser` は最後の
  掃き残しチェックとして使う
- [x] **対策 C (定期回収)**: 対策 A を守れなかった分の受け皿として、状態駆動の reaper を入れる
  (当初は「teardown 不発 18 本のため」としていたが、その経路は上記のとおり消えた)。
  判定 3 分岐 = keep (`--cwd` が今も存在) /
  reap (pid 生存だが対象ディレクトリ消滅 → session に SIGTERM → 残れば SIGKILL → state と
  session dir を削除) / stale (pid 既に死亡 → 残骸のみ削除)。依頼元の dry-run 実測で
  28 session / 約 3.9 GB を回収対象と判定し、対象が存命の 10 本は正しく keep した。
  **実装・実測とも完了 2026-08-23**: `drafts/codex-broker-reap.py` (dry-run 既定・`--apply` で実行・
  `--state` で root 側も走査可)。判定は `broker.json` でなく実プロセスで行う — 対象 dir は
  broker 自身の argv の `--cwd` にしかなく、記録には入っていない。停止は
  「停止要求 (plugin と同一の改行区切り JSON `broker/shutdown`) → SIGTERM → SIGKILL」の順で、
  broker が detached 起動のグループ長であることを使い**グループ単位**で送る (長でなければ
  巻き添え回避のため単体)。削除は停止を確認できた時だけ行う。host 実測 = reap 5 / keep 2 /
  stale 114
- [ ] **対策 D (upstream 報告)**: (i) `handleSessionEnd` は cwd 1 点でなく state root 配下を走査して
  回収すべき、(ii) broker に idle timeout か親死亡監視を持たせるべき、(iii) 鍵不一致時に exit 0 で
  黙るのをやめ警告を出すべき、(iv) **環境変数による代替経路は `pid` を持たないので停止要求しか
  送れない — 到達しても回収は完了しない** (上記の補正 B・本端末で確認)、(v) **`teardownBrokerSession`
  は session dir の削除に失敗しても記録の削除まで進むため、失敗すると二度と辿れない孤児が残る**
  — 記録は最後に、かつ置き場の削除が成功した時だけ消すべき (本端末で稼働中の孤児 3 本を実測)。
  **報告時は社内の path と codename を伏せ、機能名で書く**。
  **起草完了 2026-08-24**: `drafts/codex-broker-leak-upstream-report.md` (英文 152 行)。
  5 項目すべて 1.0.6 の現物で file:line つきに再確認済み — 1 点照会
  (`session-lifecycle-hook.mjs:86`)、自決手段なし (`app-server-broker.mjs` 252 行に
  idle/ppid/parent/watchdog/heartbeat が 0 hit・終了経路は `:160` `:236` `:241` のみ)、
  空振り時の無言 exit 0、環境変数経路が `pid`/`sessionDir` を持たない
  (`:87-93` × `broker-lifecycle.mjs:174` の `Number.isFinite` guard)、
  記録の無条件削除 (`rmdirSync` の失敗を握り潰す `broker-lifecycle.mjs:201-207` の後に
  `session-lifecycle-hook.mjs:113` が無条件 `clearBrokerSession`)。
  伏せ字は機械掃引で確認 (内部 path / repo 名 / ユーザー名 / worktree 名とも 0 hit)。
  **残るのは提出先の決定と提出そのもの** (外部公開にあたるためユーザー承認が要る)

Work file: `files/codex_broker_reap` (2026-08-23 に本 repo で実装。依頼元の
`codex-broker-reap.sh` は取り寄せず、判定条件を本文から起こして書き直した)。
**汎用化・恒久化まで完了 (2026-08-23・ユーザー指示)**: `drafts/` の複製は削除し `files/` を正本に、
両 setup script の `copy` 行で `/usr/local/bin/codex_broker_reap` へ配備、
managed settings の `excludedCommands` に `codex_broker_reap*` を追加 (model 自身が host の
プロセスを見て点検できる)。置き場の探索も 3 系統に汎用化した — `$CLAUDE_PLUGIN_DATA/state` /
`~/.claude/plugins/data/*/state` / 未設定時の退避先 `$TMPDIR/codex-companion` (実装で確認)。
`--all-users` で全ユーザー走査。マニュアルは `--help` に内蔵 (host 実行の必要性・停止順序の
理由・置き場 3 系統を明記)。再発時の想起は memory entry
`feedback_codex_broker_outlives_session` (org) が担う。

**欠陥 1 件をユーザー指摘で修正 (2026-08-23・「TMPDIR が空の場合が多いので心配」)**:
`TMPDIR=""` のとき **python の `tempfile.gettempdir()` は cwd を返す** (実測 =
`/home/h2suzuki/terminal-configs`)。一方 broker を置く **node の `os.tmpdir()` は同条件で
`/tmp`** を返す。書く側と読む側がこの場合だけ食い違い、走査先に repo 自身が並んでいた。
`--apply` まで進むと `os.rmdir` / `os.unlink` が repo 配下へ向く経路だった。
修正 = `tempfile` を使わず **node の規則を写す** (`TMPDIR → TMP → TEMP → /tmp`・
空文字は未設定扱い・末尾 `/` を落とす。優先順位は node で実測して確定) + **絶対 path 以外を
走査先に通さない**。回帰は `--selftest` (5 件・`codex_order_lint` と同じ発火形) に固定。

**配備完了 2026-08-23**: 本体・managed settings とも `diff -q` IDENTICAL、hooks 34 対も差分 0。
配備先で `--selftest` 5 件緑。**sandbox 除外の実効性を before / after で実測** — 同一端末・同一
ツールで、配備前 (sandbox 内・path 付き実行) は `keep=0 / stale=2` と**稼働中の 2 本を stale に
誤判定**していたのに対し、配備後の裸名・単独呼び出しでは `keep=2 / stale=0` と正しく判定した。
**model 自身が host のプロセスを見て点検できる状態になった** (従来はユーザーの手を借りるしか
数字が得られなかった)。

### handoff の lifecycle 同期を hook で担保する

起票: user 2026-08-23 (「handoff protocol / hook の強化が必要?」への回答として提案)

Goal: todos.md の parent block が消えた handoff section が残り続ける class を、規約の文言でなく
機械検査で止める。

**根拠 (実測 2026-08-23)**: 規約は既にある (handoff skill §7 と Rules「task block 削除と
handoff section 削除を同 commit に揃える」)。破られた実例は `e905965` (2026-08-12) の 1 件で、
対象 doc と task block を消して handoff section を残した。結果 `last-session-handoff.md` は
11 日間、削除済み doc の review 待ちを指したままだった。**根本原因は commit message 自身が
書いている** —「repo 内からこの文書へのリンクは task block だけだった」。書き手は参照を走査した
上で handoff doc を見落としており、理由は **handoff doc が git 管理外で repo 走査に映らない**こと。
現行 hook 3 種 (open Task 残 / marker 未出力 / skill 未起動) に**突合検査は無い** (grep で確認)。
文言は既に明確なので、文言強化では同じ結果になる。

**訂正 2026-08-23**: 当初もう 1 件 `c2f083a` (2026-08-07) を違反として挙げていたが**誤り**。
commit message は「handoff doc から当該 section が既に失われたので宙に浮いた参照を外す」で、
正しい後始末である。根拠は 2 件でなく 1 件。

Exit Criteria:

- [x] 検査を作るかをユーザーが決めた — **2026-08-23 採用決定**。当初仕様は handoff doc の
  `## <section>` と todos.md の `### <task>` の名前一致だったが、**2026-08-23 に差し替え**
  (ユーザー指摘「仕様が適切か不安」)。名前一致は (a) 根本原因である「git 管理外ゆえ走査に
  映らない」に触れておらず、(b) todos block を改名しただけで生きた section が誤検出に変わる
  (本 session で実際に 1 件改名済み)。**新仕様 = 参照で判定する**: どの todos block からも
  `Work file:` で指されていない handoff doc / 実在しない path を参照している doc を warn。
  見出し名は一切見ないので改名で壊れない
- [x] warn tier で実装・test した — 2026-08-23。`stop_checks.py` に
  `_handoff_todos_sync_warnings` を追加し、worktree cleanup と同じ構造検査系統
  (turn ごと 1 回の latch つき) で配信。回帰 test 7 件は改名で黙ること・block ごと消えた doc を
  拾うこと・消えた path を拾うことを pin。203 tests / ruff / format / ty 緑。
  実 repo (main と wt-gates) で警告ゼロを実測 = 現状に誤検知なし
- [ ] 実 session で誤検知と見逃しを観測した — **配備は 2026-08-23 完了** (`diff -q` IDENTICAL・
  配備先から関数を直叩きして main と wt-gates とも警告ゼロを実測)。残るのは実運用での観測で、
  handoff doc を実際に作る session が来るまで測れない
- [x] 現存する stale file を処置した — `last-session-handoff.md` を 2026-08-23 に削除
  (ユーザー承認)。salvage は除外ゼロの grep で走査し、`SKILL-HOOK-CONTRACT` と
  「確定済みファクト」とも working tree の参照 0 件、本体 657 行と todos block 38 行は
  `e905965` で削除済み = git 履歴から復元可能と確認した

Work file: なし (本 block で自己完結)

### 記憶から書かせない仕組み — 雛形 + 経由の強制 + 空欄設計

起票: user 2026-08-23 (「まず todo に登録して、セッションリセット後に実装へ」)

Goal: 記憶から生成して弾かれる類の成果物について、**雛形を複製することが生成の第一手になる**
状態を作り、雛形を経由しない生成を止める。

**根拠 (実測 2026-08-23)**: 本 session の発注書 5 通で、雛形が無いために記憶で書いて往復した。
同じ repo の skill には雛形があるが、`writing-skills` を 14 回起動して雛形を Read したのは
1 回だけ、hook 用の雛形は 0 回 — **雛形は参照コストを下げるだけで、参照させない**。
注意書きは最弱 (雛形を開いた人にしか届かない) なので、**注意文でなく空欄**で表す。

Exit Criteria:

- [ ] 発注書の雛形を用意した — 検査器が要求する節をすべて空欄として持ち、埋め忘れが機械検査で
  見える形にする (注意文は書かない)
- [ ] 雛形を経由しないと生成できない形にした — 骨組みを出力する経路を作り、それを起点にする
  (参照が生成の一部になり、別の行為でなくなる)。それでも記憶から書き始めた場合は止める
- [ ] 同型の欠落が他に無いかを棚卸しした — 雛形を持たずに毎回書いている成果物の種類を列挙する
- [ ] 効果を実測した — 導入後の発注書で、雛形で防げる類の往復がゼロになったことを確認する

Work file: なし (本 block で自己完結)

### 自作癖の抑制機構 — 廃止済み・後継は随伴エージェント待ちで凍結

起票: user 2026-08-23 (「いまの implementation-checkpoint は廃棄しないとかな。部品として
機能していなさそうなので」)
凍結: user 2026-08-23 (「全く新しい手法である随伴エージェント (別プロジェクトで検討中) が
できるまで、その hook のこれ以上の改善は凍結する」)
廃止実施: user 2026-08-23 (「implementation-checkpoint は廃止する予定だったね、こういうことに
なるから早くやろうね」)

**廃止済み 2026-08-23** (`8b04b7b`・stop_checks.py `+17/-291`): implementation-checkpoint を
test ごと削除した。死んだ helper (`_repo_relative_source` / `_line_count` /
`_tool_added_source_lines` / `_load_session_tail` と定数 2 つ) も同時に落とし、warning family は
6 → 5、上限定数と docstring・該当 test を追随させた。196 tests / ruff / ty 緑。**配備待ち**。

方針: 後継 (編集前 deny) には**着手しない**。要件「既存部品があるなら使う・再構築は承認・
自分で書いてよいのは trivial だけ」は、随伴エージェントが利用可能になった時点でその仕組みの
上に設計し直す。行数という代理指標を磨く方向は、下記の実測が示すとおり筋が悪い。

**廃止時点で判明していた欠陥 (すべて実測 2026-08-23・再設計時の材料)**:

- **抑止条件**: session に codex 委譲が 1 件でもあると以後恒久的に黙る。委譲 39 件の session は
  190 行の直接実装を検出せず、委譲 0 件の session では発火した (両側から確認済み)
- **しきい値の迂回**: 判定式 `added <= 50 and not undercount` により、transcript が 2MB を
  超えて undercount になるとしきい値ごと外れ 1 行でも鳴る。同一の 34 行が `undercount=False`
  で silent・`True` で発火することを関数直叩きで確認。長い session では毎 turn 鳴り続け、
  判定を述べても止まらない。round 9 レビューの「undercount 常時発火の誤誘導」が残存している
- **要件との乖離**: 正本は「単一 file・追加 10 行以内・test 追加なし」の AND だが、実装は
  行数のみを、しかも由来のない 50 行で見る。計測単位も正本の session 累積に対し turn 単位。
  由来調査の結論 = 要件が代理指標にすり替わったまま実装され、レビューは発注書との一致だけを
  見て通した
- **subagent 経路**: Claude subagent の編集は計測にも受け入れ鎖にも乗らない。行数では
  測れないため、再開時は別設計が要る

本 session の直接実装 3 件の委譲不採用理由 (正本が要求する記録): `906ab58` はユーザーの
直接指示、`18f0c6d` は誤発火の原因を特定した同 turn 内の是正、`8b04b7b` は削除のみで新規実装が
ゼロ・検証は「参照ゼロ + test 緑」の機械的 oracle で完結するため。いずれも発注書往復のほうが
高くつくと判断した。

Exit Criteria:

- [x] 廃止を配備した — 2026-08-23 にユーザーが base setup を実行。`files/` と `/etc` の
  `stop_checks.py` は `diff -q` IDENTICAL、配備先の checkpoint 参照は grep で 0 件、
  family 上限も 5 に追随済み。code が存在しないため発火し得ない
- [ ] 随伴エージェント (別プロジェクトで検討中) が利用可能になり、後継の設計を再開できる状態に
  なった — それまで後継の作業は凍結

Work file: なし (再開に要る実測はすべて本 block に inline)

### 検問 gate 群の実装・受け入れ・配備

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
  managed extensions とも `diff -q` IDENTICAL 実測)。
  残る実測対象: warn family 8 種の発火と誤爆。**裁定 2026-08-22**: 計測の出口は blocking
  昇格だけでなく、**agent によるジャッジへの集約**を検討する (計測データは集約後の
  設計材料として残してよい)。
  **誤爆実測 1 (2026-08-22)**: claim-without-evidence が、code の挙動を説明した文中の
  引用語「不明」(= 語そのものへの言及) に発火。語の mention と use を区別しないための誤爆。
  **誤爆実測 2 (2026-08-23)**: continuation-claim が「残り続けます」の部分文字列
  「続けます」に発火。gate の欠陥を説明した文で、遂行宣言ではない。誤爆実測 1 と同型
  (部分文字列一致で語の境界と用法を見ない) であり、mention guard の欠陥とも同じ class。
  **誤爆実測 3 (2026-08-23・上 2 件より重い)**: wind-down 検出器 `HANDOFF_RE` の裸の
  `handoff` 選択肢が、**handoff を話題にした prompt** に発火した。実測 = 本 session の
  prompt 5 本を regex に掛け、終了示唆ゼロの turn 3・4 が MATCH (いずれも一致文字列は
  `handoff`・出所は file 名 `last-session-handoff.md` と語「handoff protocol」)。
  既存 test は「閉じます」の別用途だけを negative corpus に持ち、裸 `handoff` の
  mention は 1 件も無い。誤爆実測 1・2 と同型 (語の境界と用法を見ない) で、これで 3 件目。
  path 形の除外だけでは足りない (同 turn に語としての mention も含むため)。
  当初これを「2 検査の矛盾」として起票したが**誤りと判明** (2026-08-23 ユーザー指摘)。
  真の wind-down なら質問で turn を終えること自体が誤りで、質問は解消するか todos へ
  落としてから閉じる。つまり両検査は衝突しない。往復が起きたのは誤発火した状態で
  質問終わりを続けた本 session の振る舞いによるもので、検査側の欠陥ではない。
  **裁定 2026-08-22: 否定断定の語彙拡張は revert 済み** (`e8e07fa`)。判定は別途検討中の
  agent ジャッジへ移すため、この regex は拡張前の範囲に戻し、**最終的には完全削除を目指す**。
  **誤爆実測 4 (2026-08-23)**: hollow-claims が「教訓として記録しました」に発火。記録は実在し
  (memory entry `c263838`)、当 turn でなく前 turn の Write だったため検出窓から外れた。
  1〜3 が語の言及と用法を見ない型なのに対し、これは**検査窓が turn 単位で、完了済みの
  永続化を跨いで見ない**型。過去形で実在する成果物を指す発話まで空約束として扱う。
  凍結方針どおり記録のみ行い、修正はしない。
  **誤爆実測 5 (2026-08-23)**: meta-announce-silence が「生きた作業に触りません」に発火。
  これは規約遵守の宣言ではなく、**掃除操作の影響範囲を説明した文** (消えたディレクトリ宛の
  残骸しか消さない、という事実の説明)。「〜ません」という否定形を、用法を見ずに不実施宣言と
  読む型で、誤爆実測 1・2 と同じ class。
  **誤爆実測 6 (2026-08-23)**: claim-without-evidence が「(実装例が本 repo に) 存在しません」に
  発火。根拠となる `ls` は**前の turn**で実行済みだった。誤爆実測 4 と同型で、**検査窓が turn 単位**
  ゆえに前 turn で取った根拠を見ない。turn を跨ぐ調査の結論を報告に書くたびに踏むため、
  4 と合わせて「窓が turn 単位」型は 2 件目。いずれも凍結方針どおり記録のみ。
  **誤爆実測 7 (2026-08-23・continuation-claim の 2 回目)**: 「後始末の処理は、置き場の削除に
  失敗しても記録の削除まで進みます」に発火。**他者 (plugin の code) の挙動の説明**であり
  遂行宣言ではない。誤爆実測 2 が部分文字列型だったのに対し、これは**除外処理の主語語彙が
  狭い**型で、機序が違う。`_continuation_line_is_explanatory` は
  `CONTINUATION_SUBJECT_RE` で主語を見るが、認めるのは (a) 英数字の識別子 (b) この/その/本 +
  名詞 (c) 検出語 の 3 形のみ。**同一文・同一動詞で主語の形だけ変えた実測**:
  「後始末の処理は…進みます」= 発火 / 「この処理は…進みます」= 沈黙 /
  「teardown は…進みます」= 沈黙。普通の日本語の名詞句を主語にすると、第三者の動作説明が
  一人称の宣言として読まれる。凍結方針どおり記録のみ。
  **誤爆実測 8 (2026-08-23・meta-announce の 2 回目)**: 「keep の 2 本には触れません」に発火。
  script の処理対象範囲の説明であり、rule 遵守の表明ではない。誤爆実測 5 と同一経路。
  **原因は roster 内の重複**: 同じ動詞が素の形 (`触りません` / `(には|は)触れません`) と
  rule 付きの形 (`rule (に従って|通り).{0,20}触れません` / `scope に従って…触れません`) の
  **2 通り**登録されている。検査の趣旨はコメント「rule 遵守を発話で能動的に話題化する pattern」
  であり、それを表すのは後者だけで、前者は操作範囲を述べた普通の文を全部拾う。
  **実測**: 「2 本には触れません」= 発火 / 「2 本に触れません」= 沈黙 /
  「2 本は対象外です」= 沈黙。**助詞が「には」か「に」かだけで反転し、意味は同じ**。
  凍結解除時は素の 3 形の削除が第一候補 (rule 付きの形は残す)。記録のみ。
  **凍結 2026-08-23 (ユーザー決裁)**: 語のパターンで意図を判定する warn 系検査は、随伴
  エージェント (別プロジェクトで検討中) ができるまで**これ以上改善しない**。対象は
  claim-without-evidence (誤爆実測 1)・continuation-claim (誤爆実測 2)・wind-down の
  `HANDOFF_RE` (誤爆実測 3・本日修正済みでここまで) と、同 block の warn family 群。
  誤爆の記録は続けるが、regex の語彙追加・しきい値調整・新検査の追加は行わない。
  判定を機械の語照合から agent へ移すのが本筋で、代理指標を磨く投資は回収できないため。
  **凍結対象外**: mention guard (companion 直接起動の deny) — warn でなく実害を止める deny
  であり、扱いは別途ユーザー判断待ち。
  Stop の Sonnet 審判 hook は本人未合意の実装だったため **撤去済み 2026-08-22** — repo は
  ユーザー指示で当該 commit ごと履歴から drop、配備側もユーザーが巻き戻し実施
  (`diff -q` IDENTICAL 再実測済み)。再実装は本人合意が成立した場合のみ。
  否定断定 warn 拡張 (依頼 1) の扱いはユーザー確認中。
  **live finding 1 (2026-08-22 実測 → 同日修正 `29f1891`)**: work-without-task と
  decision-question-task が mytask 登録済み session で誤発火 — 根因は**書き手と読み手で
  anchor が違う**こと。書き手 (mytask MCP) は `CLAUDE_PROJECT_DIR` 起点、読み手
  (stop_checks) は payload cwd 起点で `drafts/tasks/<sid>.json` を探すため、subdir で
  作業する session は必ず 0 件になる。実測 = 同一 sid で cwd を repo top にすると records
  31 件・警告 None、subdir だと 0 件・警告発火。修正 = project dir と cwd の全祖先を探索
  (回帰 test 2 件で両 anchor を pin・192 tests 全緑・旧解決に差し替えると 2 件とも fail)。
  **deploy 待ち** (base setup 再実行で反映)。
  **live finding 2 (2026-08-22 実測)**: 検査 (g) の deny が plugin 既製
  adversarial-review command の起動 flow (main agent の Bash) と衝突 — command は model の
  Bash 実行を規定するため、gate 配備後は model からこの command を実行できない。ユーザー
  **訂正 2026-08-22**: 「gate 配備後は model からこの command を実行できない」という当初の
  理由づけは誤り。障壁は 2 層で、第 1 層は plugin 側の `disable-model-invocation: true`
  (gate 導入前から model の自発起動は不可)、第 2 層が本 gate (ユーザー起動後に model が
  走らせる companion 起動を deny — 2026-08-21T18:54:10Z に実 deny を transcript で確認)。
  **裁定 2026-08-22**: 同じことが rescue でできる限り rescue へ一本化し、指示があれば
  ユーザー自身の起動を助ける。ただし第 2 層があるため、ユーザー起動でも現状は完走しない。
  例外を設けるか一本化のままかは判断待ち。例外を作る場合、判定は plugin の起動形でなく
  「そのターンにユーザーの slash 起動があるか」で書く (上流の実装形に縛らない)
- [ ] **検問実装への挑戦レビュー (発注書方式・2026-08-22 ユーザー承認)** — 発注書
  `wt-gates/drafts/gates-challenge-review-order.md` (lint rc=0)・対象 = 検問 line 全 diff
  (3 file・+2210/−173)。**verdict 受領 2026-08-22 = needs-attention・U0 8 / U1 2 / U2 0**
  (報告書 `wt-gates/drafts/gates-challenge-report.md`・検証 190+37 test 全緑を含む)。
  high 3 件: U0-1 warning が active retry で再配達され続け実質 loop (live の
  警告なぎ倒し現象と一致) / U0-2 fix round 番号が directory 全体 namespace で独立案件と
  衝突 / U0-3 shell redirect・`--` 境界の argv 解釈が gate と companion で不一致。
  U0-5 (companion 名の文字列言及まで deny) と U0-7 (checkpoint の cwd scope) は
  live finding 1・2 と同根で独立収束。U1 2 件 (route provenance の信頼境界 /
  checkpoint の対象言語) は人間裁定待ち。**処置の決定はユーザー判断待ち**
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
  gate unittest 65・escape 残骸 0 site)。**deploy 完了 2026-08-22**
  (codex_delegation_gate.py `diff -q` IDENTICAL 実測)。残 = 判定器 round 4 (任意) と live 実測
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
  掃引・監視 = job record 直読・cancel = ユーザー起動へ)。**deploy 完了 2026-08-22**
  (/etc の codex-delegation SKILL.md `diff -q` IDENTICAL 実測)
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
  キーワードに反応して memory する hook があってもよいぐらい」) — ユーザーの発話に
  無駄 / 浪費 / もったいない が含まれる turn に、memory-routing での記録検討を促す
  warn。無駄の実例が entry 化されずに流れる class の防止。**2026-08-22 ユーザー指示で着手**
  — 実装先は UserPromptSubmit でなく Stop family とし (同 turn の memory Write との
  pairing を既存機構で行うため)、発注書 `wt-gates/drafts/warn-family-order.md`
  (両 lint rc=0) で codex へ発注済み。次の 1 件と同一 round
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
  **2026-08-22 ユーザー指示で着手** — (1)(2) を 1 つの family に統合し、上の reminder と
  同じ発注書で codex へ発注済み
- [x] **発注書 lint の語彙過剰検出を直した** (2026-08-23 実測で起票 → 同日修正) — 「状態」
  「state」「latch」等の語が本文にあるだけで別節を要求する検査が、普通の日本語 (「空状態」
  「〜という状態になっている」) に反応していた。本 session の発注書 5 通に返った違反 延べ
  14 件のうち **8 件がこの 1 検査**で、5 通中 4 通が踏んだ。回避のため文章を不自然に書き換えており
  (「空状態」→「何も無い状況」)、検査器が文書を歪めていた。
  **修正方針はユーザー発案 (2026-08-23)**:「雛形がある前提で、文書の構造を雛形と比較すれば
  キーワード非依存にならない?」。実測でこれが成り立つことを確認 — 条件つきで節を要求する検査は
  3 つしかなく、うち 2 つが語で引き (状態機械系・廃止撤去系)、**残り 1 つ (機構追加 → 既存保証の
  監査) は既に「修正方式 節に何を宣言したか」を読む形**で、同じ file 内に前例があった。
  実装 = 2 つを無条件必須節へ移し (`## 全数列挙` / `## 依存閉包棚卸し`、該当しなければ書き手が
  「該当なし」と書く)、`STATE_MACHINE_RE` と `RETIREMENT_RE` を削除。判定が「機械が語から推測」
  から「書き手が宣言」へ移る。selftest 38 件 / ruff / ty 緑。回帰 test で
  「という状態になっている」等 4 例が所見を 1 件も増やさないことを pin。
  実 fix 発注書 6 通で計測すると 4 通は増減ゼロ (既に両節を持つ)、2 通が「該当なし」の追記を
  要する。**配備完了 2026-08-23**: `/usr/local/bin/codex_order_lint` は `diff -q` IDENTICAL、
  配備先で selftest 38 件緑、語で引く 2 検査は grep で 0 件 = 消滅を確認
- [ ] 各 gate の canonical (files/) と deploy 先の diff -q 一致 + 発火の live 観測 —
  **全 35 対の照合 2026-08-22**: IDENTICAL 28 / 実差分 1 (`stop_checks.py`) / 残り 6 は
  非該当 (**2026-08-23 配備完了**: ユーザーが base setup を実行し、`stop_checks.py` と
  `906ab58` の `skill_reminder_gate.py` とも `diff -q` IDENTICAL を実測。配備差分は 0)
  (root 専用の読取不可 1・sandbox が空 overlay で覆う 1・
  root の home が配備先 1・source 側の局所生成物 `.ruff_cache` `__pycache__` `.claude`
  `.gitkeep` と配備側 runtime の `state/` と非配備の test file 3)。
  **再照合 2026-08-23 (本日 2 度目の配備後)**: hooks 34 対 + `codex_order_lint` とも
  `diff -q` IDENTICAL で**配備差分ゼロ**を再確認。廃止済みの自作コード量検査が配備先に
  存在しないことも grep で確認。以下は同日 1 度目の配備時の記録。
  hooks は **34 対すべて IDENTICAL**、
  managed CLAUDE.md / settings.json も IDENTICAL、skills の差は source 側の局所生成物
  (`.claude` / `.ruff_cache`) のみ。**配備差分ゼロ**。
  live 発火の観測は 8 family (continuation-claim / decision-question-task /
  claim-without-evidence / declare-and-proceed / work-without-task / hollow-claims /
  open-tasks-at-wind-down / implementation-checkpoint = 廃止済み) を記録済み。
  **未観測は 2 family** (waste-keyword-memory / question-self-containment) で、これが残

Work file: 4 gate の設計は本 block と `last-session-handoff.md` 不要 (本 block で自己完結)。
5 巡 breaker の思想は Medium「方法論の実証」block の教訓 (1)〜(6) を参照

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
