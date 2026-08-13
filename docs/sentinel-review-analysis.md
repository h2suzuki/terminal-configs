# codex_task_sentinel 敵対レビュー 1〜53 巡 集計

17 巡目より前の 16 巡は **§0** に分ける。この範囲は報告書原文が 16 本すべて現存するため、
件数は復元でなく原文からの直接計数であり、以下 §1〜§7 の 179 件には含まれない。

`files/codex_task_sentinel` に対する 37 巡 (17〜53 巡) の敵対レビューで挙がった 179 件の指摘を、
処理ブロック・原因タイプ・由来 (self / preexisting / unknown) で集計した文書である。
復元元は 報告書原文 (r17〜r30 と r52・r53 のみ現存)、発注書 r17〜r53 の「## 目的」、commit log、および transcript。
**r31〜r51 の報告書原文は失われている** (報告書を worktree 内に書かせ、次巡準備の `git worktree remove --force` で毎回削除していた。51 巡目に発覚し、52 巡目から drafts/ へ退避する手順に変更)。
そのため r31 以降の個別指摘は発注書の要約と commit message からの復元であり、由来が資料に無い箇所は unknown と記した。

**運用**: 1 巡終えるごとに本文書を更新する。手順は (1) worktree を消す前に報告書を `drafts/` へ退避、
(2) 6 つの表 (総数・ブロック・原因・クラス時系列・効果・未検証) にその巡を足す、(3) 次巡の発注書を書く。
`drafts/` は版管理外なので、本文書だけは `docs/` に置いて commit する。

## 0. 1〜16 巡

16 巡・**新規指摘 33 件**。報告書原文 16 本が worktree 内に現存するので、以下はすべて原文からの直接計数である
(§0 に推測は無い)。「新規指摘」は各報告書の `## 新規指摘` 節に番号付きで挙がった件数、
「前巡の検証」は同 `検証結果` 節の見出し語をそのまま数えたもの。

| 巡 | 新規指摘 | 前巡指摘の検証結果 (見出し語のまま) | 収束判定 |
|---:|---:|---|---|
| 1 | **13** | — (初回) | 出荷不可 (収束判定節なし) |
| 2 | 2 | R1 の 13 件: 塞がった 8 / 塞がっていない 4 / 別欠陥に化けた 1 | not converged |
| 3 | 3 | 10 件: 塞がった 9 / 別欠陥に化けた 1 | not converged |
| 4 | 0 | 塞がった 1 / 塞がっていない 1 / 別欠陥に化けた 1 | not converged |
| 5 | 0 | 塞がった 1 / 別欠陥に化けた 1 (「削除は不妥当」) | not converged |
| 6 | 0 | 未修正 1 | 出荷不可・収束不可 |
| 7 | 0 | 塞がった 1 / 不妥当 (material な残存) 1 | not converged |
| 8 | 0 | 具体列は塞がったが同一 key の残存で未修正 1 | not converged |
| 9 | 2 | 直接列は塞がった 1 | not converged |
| 10 | 1 | 直接列は塞がったが修正が残る 2 | not converged |
| 11 | 0 | 脱落は塞がったが R9 経路へ回帰 1 / 「log の読み方だけで閉じる手 — 無し」 | not converged |
| 12 | 2 | 既定の cancel 導線 塞がった・`--trust-log` 等価 / evidence 不十分・skill に契約回帰 | not converged |
| 13 | 2 | 直接欠陥は塞がった 2 (うち 1 は巨大 log で別欠陥に化けた) | not converged |
| 14 | 4 | 6 点中 5 点が解消、同期 test だけ第 13 巡の中心契約が未達 | not converged |
| 15 | 1 | 塞がった 1 / 塞がっていない 2 / 別欠陥に化けた 1 | not converged |
| 16 | 3 | 塞がった 1 / 塞がっていない 1 / 直接経路は塞がった 1 | not converged |
| **計** | **33** | | **16 巡すべて未収束** |

読み取れること (原文にある事実のみ):

- **初回 1 巡で 33 件中 13 件 (39%) が出ている**。2 巡目でその 13 件を検証した内訳は
  塞がった 8 / 塞がっていない 4 / 別欠陥に化けた 1 で、**初回指摘の 5 件が 1 巡では閉じなかった**。
- **4〜8 巡と 11 巡の 6 巡は「新規指摘は無し」と明記している**。ただしいずれも前巡指摘の
  未修正・別欠陥化・material な残存を報告しており、指摘ゼロの巡は 16 巡中 1 巡も無い。
  6 巡の報告書は結論を「出荷不可、収束不可」と書いている。
- **前巡の修正が別欠陥に化けたと見出しに明記された箇所は 5 つ** (R2 #3 / R3 2-b / R4 #1 / R5 #1 / R15 #4)。
  17 巡以降で支配的になる「修正が次巡の指摘を生む」形は、この範囲で既に現れている。
- 4〜8 巡・11 巡が扱った論点は一貫して 1 つ — log 上で「引用された行」と「真正 event」を
  分離できるか。11 巡の報告書は `### log の読み方だけで閉じる手 — 無し` と結論し、
  以後この論点は上流依存 (plugin が per-command lifecycle を record に持たない) として
  新規指摘から外す扱いになった。

16 巡と 17 巡の境目: 16 巡の修正 (`b1d8ed7`) の後に worktree `wt-rev20` で 17 巡目を発注したが、
その job (`task-msl8tq7h-w30qoa`) は報告書を書かないまま session が終わっている
(state record は今も `status: running`、`wt-rev20/adversarial_report_r17.md` は不在、
監視は `無音 919s / しきい値 900s` で exit 14 を返していた)。
§1 以降が典拠とする 17 巡は別 session が改めて実施したもので、その修正 commit は `6a83eff` (08-12) である。

## 1. 総数と推移

37 巡・**179 件**。件数の推移 (r19〜r51 は r52 発注書の推移行、r17 / r18 は r18 / r19 発注書の本文、r52・r53 は報告書原文から):

```
r17..r53: 5 10 12 5 5 4 4 4 5 3 6 4 5 8 5 5 9 7 6 6 4 5 2 3 2 3 2 3 3 5 3 4 4 4 3 6 5
```

| 巡群 | 件数 (巡ごと) | 計 | self | preexisting | unknown | self 率 |
|---|---|---|---|---|---|---|
| 17–20 | 5 / 10 / 12 / 5 | 32 | 14 | 17 | 1 | 44% |
| 21–25 | 5 / 4 / 4 / 4 / 5 | 22 | 16 | 6 | 0 | 73% |
| 26–30 | 3 / 6 / 4 / 5 / 8 | 26 | 13 | 13 | 0 | 50% |
| 31–35 | 5 / 5 / 9 / 7 / 6 | 32 | 18 | 6 | 8 | 56% |
| 36–40 | 6 / 4 / 5 / 2 / 3 | 20 | 13 | 3 | 4 | 65% |
| 41–45 | 2 / 3 / 2 / 3 / 3 | 13 | 10 | 0 | 3 | 77% |
| 46–53 | 5 / 3 / 4 / 4 / 4 / 3 / 6 / 5 | 34 | 30 | 1 | 3 | 88% |
| **計** | | **179** | **114** | **46** | **19** | **64%** |

読み取れること (数値の事実のみ):

- **「preexisting は 39 巡で尽きた」という 51 巡時点の読みは、52 巡で覆った**。r52 指摘 6 (`str.splitlines()` が
  VT・FF・NEL・U+2028 も行末として消す) の該当行は commit `6de685f` に由来する。
  **この commit は 1 巡目の修正である** — 2026-08-08 21:55、sentinel を触った 3 番目の commit で、
  subject は `Stop calling a cancelled run a success`、1 巡目の指摘 1 (failed / cancelled の成功昇格) を閉じたもの
  (2 巡目の報告書 `### 1. failed / cancelled の成功昇格 — 塞がった` が受理を記録)。
  `git log -S'splitlines'` の初出も同 commit である。つまり **1 巡目の修正が入れた欠陥が 52 巡目まで 51 巡ぶん残った**。
  「レビュー開始初期」は正しいが、実際にはレビューの初回そのものである。40〜51 巡に preexisting が
  1 件も出なかったのは「掘り尽くした」からではなく、**発注書が毎巡「直前の修正が生んだ欠陥」を最優先に指定していた**
  ためと読むほうが資料と整合する。
- **self 率は単調に上がり続け、46〜53 巡では 88%**。件数自体は 12 (r19) → 2〜6 に収束したが、
  収束後の指摘の中身は自作欠陥に置き換わった。
- **自作欠陥は直前の巡のものとは限らない**。53 巡の 5 件の出所は r52 が 3 件、**r34 が 1 件、r19 が 1 件**。
  「self = 直前の巡の作り込み」という 51 巡までの読みは粗すぎ、実際には 19 巡・34 巡に埋めた欠陥が
  それぞれ 34 巡・19 巡ぶん残っていた。
- unknown 19 件のうち 13 件が r31〜r44 に集中する。これは報告書原文の欠落範囲と重なり、
  由来が書かれた資料が失われたことの帰結である (r31 は 5 件全部が unknown)。

## 2. 処理ブロック別の集計

| 処理ブロック | 件数 | forgot | imagined | contradictory | unfinished | other |
|---|---:|---:|---:|---:|---:|---:|
| 登録解決 | 35 | 17 | 8 | 3 | 4 | 3 |
| 成果物 | 24 | 10 | 7 | 7 | 0 | 0 |
| record 読取 | 22 | 13 | 6 | 1 | 0 | 2 |
| 表示(evidence) | 21 | 11 | 1 | 7 | 0 | 2 |
| log 走査 | 17 | 8 | 2 | 3 | 0 | 4 |
| 期限(deadline) | 15 | 5 | 0 | 2 | 7 | 1 |
| ツリー | 12 | 8 | 2 | 2 | 0 | 0 |
| 履歴(baseline) | 12 | 7 | 3 | 1 | 1 | 0 |
| 判定(verdict) | 9 | 2 | 0 | 7 | 0 | 0 |
| test-fixture | 7 | 0 | 6 | 1 | 0 | 0 |
| CLI引数 | 4 | 4 | 0 | 0 | 0 | 0 |
| snapshot比較(file_stat) | 1 | 0 | 1 | 0 | 0 | 0 |
| **計** | **179** | **85** | **36** | **34** | **12** | **12** |

ブロックごとの偏り:

| 観察 | 数字 |
|---|---|
| 上位 3 ブロック (登録解決 / 成果物 / record 読取) で全体の **45%** | 81 / 179 |
| 「同じ規律を全 site へ配る」型 (forgot) が支配的なブロック: 登録解決・record 読取・ツリー・CLI引数 | 各ブロックの 49〜100% |
| 「自分の裁定 / docstring / comment と code が食い違う」型 (contradictory) が支配的: 判定 78%、表示 33%、成果物 29% | 判定 7/9、表示 7/21、成果物 7/24 |
| 期限だけが unfinished 中心 (gate を通らない return) | 7 / 15 |
| test-fixture は 7 件中 6 件が imagined (空振り test) | 6 / 7 |

`snapshot比較(file_stat)` は指定語彙に該当が無いため新語を立てた。log・成果物・record の前後比較が共有する
横断 helper で、r30 の 1 件のみ (`(mtime, size)` では replacement が正確に一致しうる)。

## 3. 原因タイプ別の集計と説明

| 原因タイプ | 件数 | 比率 | 一言でいうと |
|---|---:|---:|---|
| forgot | 85 | 47% | 同種の site の一部にしか配っていない |
| imagined | 36 | 20% | 現実に対応しない前提・到達不能な分岐・呼ばれない関数を patch した test |
| contradictory | 34 | 19% | 自分で書いた裁定 / comment / docstring と code が矛盾 |
| other | 12 | 7% | 5 分類に該当語が無い (畳み込み・単位・精度・単調でない時計) |
| unfinished | 12 | 7% | gate を通らない return、解放されない資源 |

### forgot (85 件) — 配り漏れ

同じ規律を「気づいた 1 site」にだけ適用して出荷する形。半分弱を占め、全ブロックに分布する。

- **r28**: 27 巡で入れた `printable()` を evidence の 4 site にしか配らず、headline・成果物行・log / cancel 行・
  登録待ち分岐が制御文字を素通しした。翌 r29 でさらに隣の 3 site が残っていたと再指摘される。
- **r34**: 33 巡で新設した `dangling()` を親 1 階層にしか配らず、root までの祖先に辿れない link があると
  `record_gone` が「消えた」と読んだ。
- **r40**: 39 巡の表示補正が `shown_ready` / `shown_tree` の 2 フィールドだけで、log・履歴・record の 3 site が
  断定表示のまま残った。**この 3 件が 1 巡でまとめて指摘され、r40 の全件を占める**。
- **r53 (最悪の例)**: 34 巡で `record_gone` に「祖先まで辿る」判定を入れた **その同じ巡** に、log と成果物へは
  **leaf だけを見る版**を配った (`7fd75c4` "Distribute dangling to the log and artifact readers")。
  配ったつもりで、直したはずの中身が抜けていた。成果物側は **19 巡後** に r53 指摘 4 として出た。
  log 側は同巡の自己走査で自分で見つけた (レビューには出ていない)。

### imagined (36 件) — 現実に対応しない code

- **r24**: `S_ISREG` guard を `open()` の**後ろ**に置いたため、FIFO では到達せず発火しない分岐だった。
- **r27**: 「不在どうしなら不変」という成り立たない前提。読取中だけ存在した成果物 (不在→出現→不在) を
  ready として exit 0 にできた。
- **r37**: 実装がもう呼ばない `job_record` を patch した test。主張する状況を一度も作らないまま緑だった
  (test-fixture / imagined 6 件の典型で、r26・r27・r28・r36・r37・r38 に 1 件ずつ出続けた)。
- **r52**: `str.splitlines()` を「LF と CRLF で分けるもの」と思って書いていた。実際は VT・FF・NEL・U+2028 も
  境界として消すので、token の後ろにそれらが付いた成果物まで完成品になる。**この 1 件だけが 46〜52 巡で唯一の
  preexisting** で、**1 巡目の修正 (`6de685f`) が入れた行が 51 巡ぶん残っていた** (§1 の注記を参照)。

### contradictory (34 件) — 自分の裁定と code の矛盾

- **r22**: 直前に自分が「破棄 poll は直ちに取り直す」と comment した sleep を無制限のまま残し、
  sleep が期限を越えて期限後の verdict が timeout に勝った。
- **r29**: `run_since()` の docstring が createdAt fallback を約束したまま実装と正反対だった。
  **fallback を削除した当の commit が docstring を残していた**。同巡には成果物上限 comment の同型もあり、
  その 3 箇所目が r30 で再指摘されている (同じ主張の comment 3 箇所を 2 巡かけて 2 箇所しか直せなかった)。
- **r47**: 「成果物も比較が済むまで descriptor で押さえる」と 45 巡で自分が裁定しながら、
  `artifact_view` に hold を実装していなかった。

### other (12 件) — 5 分類に該当語が無いもの

内訳は「畳み込み」6 件、単位・精度 3 件、単調でない時計 1 件、動く EOF への追従 1 件、補正の過剰伝播 1 件。

- **r17**: timeout の期限に wall clock を使い、時計補正で早期終了 / 大幅超過した (単調でない時計)。
  `time.monotonic()` 化以降 51 巡まで再発なし。
- **r24**: byte 予算を「置換後の文字列長」で減算する単位取り違え。不正 byte 1 個が U+FFFD として 3 bytes に膨らみ、
  budget が先に尽きても `whole=True` のままだった。
- **r46**: 掴めなかった理由を identity `(None, None)` に畳み、canonical な exit 10 (消失) / 13 (corrupt) を
  別経路から奪った (2 件)。修正後に裁定 38 として明文化。

### unfinished (12 件) — フローを終えていない

- **r21**: 終局判定を margin つきの期限に対して行い、登録待ちが実期限より最大 1 poll 早く exit 6 を返した。
- **r34**: `MAX_PEERS` の打ち切りを呼び手へ伝えないまま早期 return し、数え切れなかった peer 集合の最大値を
  stall の bar に使った。
- **r47 → r48**: 47 巡で足した pin 失敗の即時 return が期限 gate を通っておらず、翌巡そのまま指摘された。
- **r51 → r52**: 51 巡で足した「周回間の record 差し替え」報告 (`8b43dea`) が同じく期限 gate の外に置かれ、
  期限後でも exit 14 を返した。**同じクラスの同じ形を 4 巡後に再び書いている**。

## 4. クラスの時系列 (block + cause)

37 クラス。**closed 14 / recurring 18 / open 5**。

### open (5 クラス) — 53 巡時点で未収束

52・53 巡の 11 件は **すべて既出クラス**に収まった。37 巡を通じて新しいクラスは 1 つも増えていない。

| クラス | 件数 | 出現巡 | 状況 |
|---|---:|---|---|
| 登録解決 / forgot | 17 | 19,27,28,29,30,31,32,33,47,48,51,52,53 | 全クラス中最多。complete 戻り値・seen_pairs・走査上限・本文 id・掴みの記憶と毎巡 1 段ずつしか配れていない。r53 指摘 1 は「r52 で入れた `resolved_unknown` の持ち越しが、carried でも unknown でもない第三の周で消える」— 修正が半分だった |
| 成果物 / imagined | 7 | 24,27,28,44,52,52,53 | FIFO で到達しない guard / ABA / queued job が成果物を書く前提 / inode 番号再利用。r53 指摘 2 は r52 で入れた読取窓の 3 値化が、外側不在のときだけ実体の指紋を捨てる形 |
| 期限 / unfinished | 7 | 21,33,36,37,48,49,52 | gate 外の return。r52 指摘 1 (`24ac731`) で 7 件目。48 巡と同じ形を 4 巡後に再演。**53 巡では出ていない** |
| 登録解決 / unfinished | 4 | 36,47,50,52 | gate を通らない早期 return (36/47) と descriptor の解放順序 (50)。r52 指摘 2 は `6dcb92e` で閉じ、**53 巡で test も付いた** (レビューアが 3 周 fixture の作り方を示した) |
| log 走査 / contradictory | 3 | 20,51,52 | 読取失敗を「変化」に化けさせる形。51 巡の緩和 (`3d8ea00`) が r52 指摘 4 を生み、`e243e45` で閉じた |

### recurring (18 クラス) — 3 巡以上または断続再発

| クラス | 件数 | 出現巡 | 特徴 |
|---|---:|---|---|
| record 読取 / forgot | 13 | 17,18,19,20,21,23,25,26,31,34 | 型検査・id・stamp 厳格化・読取上限・例外境界・NotADirectoryError。34 巡以降は imagined / other へ移行 |
| 表示 / forgot | 11 | 25,26,27,28,29,30,40,42 | shlex.quote・printable()・moved 補正・cancel 行。毎巡 1〜3 site 残す |
| 登録解決 / imagined | 8 | 20,31,32,34,43,44,45,50 | 「1 回の listdir が走査窓を代表する」「名前一覧で identity を比べられる」「inode 番号で identity を保持できる」「fallback は選ばれない」 |
| 成果物 / forgot | 10 | 17,18,19,22,30,39,46,53,53 | 3 値化・bounded read・strict decode・descriptor 指紋・hold・裸 CR・祖先 dangling。**log / record へ先に配った対策が成果物にだけ届かない**という同一の形が 7 巡にわたる |
| ツリー / forgot | 8 | 18,19,23,24,27,29,49,50 | directory 自身・symlink・base・走査中の消失・未完走。49–50 は tree_age 2 値化の波及 |
| log 走査 / forgot | 8 | 18,31,32,38,45,48,49 | stamp full-match・pending 上限・秒の範囲・総量上限・descriptor 指紋・inode 押さえ |
| 成果物 / contradictory | 7 | 18,20,29,38,45,47 | strict decode 裁定・comment と code の逆転・変化検知済みの現存断定・「無い」への畳み込み |
| 判定 / contradictory | 7 | 19,21,30,32,34,36 | 破棄 poll の再利用、docstring 契約との乖離 (r30 は code でなく docstring を直した)、先行確定の免除範囲 |
| 表示 / contradictory | 7 | 27,38,39,41,42,50 | 「判定と表示は同じ値を使う」裁定に反する断定表示。41–42 は畳み方を変えるたび別の断定が生まれた連鎖 |
| 履歴 / forgot | 7 | 19,22,33,35,36 | 一貫性検査・走査上限・counted_all の 2 値伝播。35 巡は 1 巡で 3 件が同クラス |
| record 読取 / imagined | 6 | 25,32,33,34,37 | check-then-use / 別々の壊れ方を不変と読む / 秒粒度 mtime / A→B→A 透過 |
| test-fixture / imagined | 6 | 26,27,28,36,37,38 | 実装が呼ばない関数を patch。37 巡で patch 対象 27 種を全数突合するまで毎巡 1 件ずつ出た |
| 期限 / forgot | 5 | 23,24,25,34,35 | 期限確認を 2 sleep の片方・loop 入口・一部 read 経路にしか置かない。23–25 で 3 巡連続 |
| log 走査 / other | 4 | 19,23,24,33 | 「読めなかった」を値に残さない畳み込み / 動く EOF 追従 / byte 予算の単位 / stamp 小数切り捨て |
| 履歴 / imagined | 3 | 34,35,37 | 「log だけで peer の落ち着きを測れる」「上限は選り分けの後で数えてよい」「使わない材料の完全性で判定を止める」 |
| 登録解決 / contradictory | 3 | 20,36,49 | exit 9 契約との矛盾 / carried を raw list へ戻す / 「pin は掴んだ fd でも別 fd でもよい」という等価申告の誤り |
| 登録解決 / other | 3 | 18,19,44 | 走査不能・一意性・「動いた候補」を戻り値に残さず畳む。裁定化のたび別の畳み込みが現れる |
| CLI引数 / forgot | 4 | 19,30,38,53 | option 組合せ / 巨大値の OverflowError / job id の path component 未検証 / 明示された空文字を未指定に畳む。r53 の 1 件は **19 巡で書いた行が 34 巡ぶん残っていた** |

### closed (14 クラス)

| クラス | 件数 | 出現巡 | 閉じた理由 |
|---|---:|---|---|
| record 読取 / other | 2 | 46 | 裁定 38 の明文化 (同じ畳み込みは翌巡 登録解決/unfinished として現れた) |
| record 読取 / contradictory | 1 | 22 | RECORD_TS の `$` を fullmatch 化 |
| ツリー / contradictory | 2 | 17,19 | 裁定 7・8 の確立 |
| ツリー / imagined | 2 | 18,33 | dangling 対応と scandir 逐次化 |
| 期限 / other | 1 | 17 | monotonic 化 |
| 期限 / contradictory | 2 | 22,48 | それぞれ単発 |
| log 走査 / imagined | 2 | 46 | hold 化 |
| 判定 / forgot | 2 | 19,33 | — |
| 履歴 / contradictory | 1 | 18 | — |
| 履歴 / unfinished | 1 | 34 | — |
| 表示 / other | 2 | 42,43 | 裁定 36「補正は観測ごとに閉じる」 |
| 表示 / imagined | 1 | 18 | — |
| test-fixture / contradictory | 1 | 35 | r36 発注書に「test の oracle が spec 由来か」を観点追加 |
| snapshot比較 / imagined | 1 | 30 | dev/ino 追加 (以後は各 reader の descriptor 指紋の問題として現れる) |

## 5. 修正の効果 — 直したことで次巡に何件生んだか

判定できるのは r17〜r52 の 36 巡 (r53 の効果は 54 巡の結果が出るまで未判定) で、
**worsened 34 / mixed 2 (r30, r43) / improved 0**。
mixed の 2 巡は「次巡の指摘に由来の記載が無く帰属できない」巡であり、改善が確認できた巡ではない。

修正が次巡に生んだ件数の合計は **93 件** (179 件の 52%)。

| 巡群 | 次巡に生んだ件数 (巡ごと) | 群計 |
|---|---|---:|
| 17–20 | 4 / 6 / 4 / 3 | 17 |
| 21–25 | 3 / 1 / 4 / 3 / 1 | 12 |
| 26–30 | 2 / 3 / 5 / 1 / 0 | 11 |
| 31–35 | 2 / 4 / 5 / 5 / 3 | 19 |
| 36–40 | 2 / 1 / 1 / 3 / 2 | 9 |
| 41–45 | 1 / 2 / 0 / 3 / 3 | 9 |
| 46–52 | 1 / 1 / 3 / 4 / 1 / 3 / **3** | 16 |
| 53 | (54 巡待ち) | — |
| **計** | | **93** |

r51 の欄を 2 から 3 に訂正した。51 巡時点では r52 発注書の要約しか無かったが、r52 の報告書原文が現存し、
指摘 1・3・4 の該当行がそれぞれ `8b43dea` / `968714f` / `3d8ea00` — **いずれも r51 の commit** と特定できた。
指摘 2 も pin 系 (r44〜51) の続きだが、導入巡を 1 つに絞れないので数えていない。

収支が最も悪い巡:

| 巡 | 閉じた件数 | 次巡に生んだ件数 | 根拠 |
|---|---:|---:|---|
| 28 | 4 | **5** | commit fd9d82d が「5 件すべて round 28 の残骸」と明記。この巡だけ生んだ数が閉じた数を上回る |
| 18 | 10 | 6 | r20 発注書「12 件、うち 6 件は 18 巡目の修正が作り込んだ欠陥」 |
| 33 | 9 | 5 | r35 発注書「7 件中 5 件が 33 巡由来」 |
| 34 | 7 | 5 | r35 の 6 件中 5 件が 34 巡で入れた機構の欠陥 |
| 49 | 4 | 4 | r51 発注書「50 巡の 4 件をいずれも 49 巡目の変更が原因」。3 巡回避していた descriptor 持ち帰りを実装した巡 |
| 23 | 4 | 4 | r25 発注書「4 件で全件が 23 巡目の修正の残骸」。commit f1b38b0 が「the same mistake inside the fix for that mistake」と自認 |

「全件が前巡の作り込み」だった巡: **r22 (4/4), r24 (4/4), r25 (3/3 が 23 巡の残骸と発注書に記載), r29 (5/5), r43 (2/2), r50 (4/4)**。

修正が 2 巡以上先まで尾を引いた例 (資料に明示):

- r20 の streaming decode → r21 と **r22** (末尾 1 MiB だけで空白判定) の両方を生んだ
- r40 の record_unstable / 裁定 32 → r41 と **r42** の 2 巡続いた
- r44–46 の pin 機構 → r47・r48 まで 3 巡にわたり残骸を出し、r52 指摘 2 まで 8 巡にわたり尾を引いた
  (`6dcb92e` で閉じたが test で守れていない)
- r51 の 4 commit → r52 の 6 件中 **3 件** を生んだ。閉じた 3 件と同数である
- r52 の 4 commit → r53 の 5 件中 **3 件** を生んだ。閉じた 6 件に対して 3 件である

## 6. test 側の失敗

### 空振り fixture (状況を作れていない / 実装が呼ばない関数を patch)

| 巡 | 内容 | 原因 |
|---|---|---|
| 19 | 12 変異中 3 件が生存 (peer moved / incomplete accepted / truncation ignored) | 修正したのに test を書いていない / test が下流の別 check で通る / test が helper 止まりで watch loop に届かない |
| 23 | 5 変異中 2 件が通過 | 2 回目の poll に verdict を出させていない / 読み始める前に file を伸ばしていた |
| 24 | budget の変異が 2 度外れた | fixture に生の不正 byte が無い + 当てた変異が実際のバグ式でない (2 重の原因) |
| 26 | bounded-read test が「動かなくなったのに緑」 (**レビューアの指摘**) | os.open 移行で壊れて落ちた 5 本は直したが、黙って通り続けた 1 本を探さなかった |
| 27 | 6 変異中 2 件が一度で捕捉できず | symlink は format 後に anchor 貼り直しが必要 / delete+recreate で kernel が同じ inode 番号を返し実際には何も入れ替わっていなかった |
| 28 | 5 変異中 headline の 1 件が生存 | 制御文字 test が evidence() しか見ておらず watch レベルを検査していない |
| 29 | 登録待ち escape の変異が 1 度外れた | test が制御文字をその分岐に通していなかった |
| 33 | 10 変異中 2 件が「状況を作れていない」緑 | fixture が poll の開始**前**に record を書き換えていた (commit 本文に未記載、transcript のみ) |
| 35 | 6 変異中 2 件が空振り | fixture が状況を作れていない |
| 36 | 34 巡で書いた fixture が実装の呼ばない `job_record` を patch (**レビューアの指摘**) | 主張する状況を一度も作らないまま緑 |
| 37 | 同型がもう 1 件残存 (**レビューアの指摘**) | 36 巡で 1 件直しながら grep で兄弟を探さなかった。今回 patch 対象 27 種を全数突合し、無効は job_record のみと確認 |
| 38 | 5 変異中 1 件が空振り。指摘そのものも空振り fixture | 変異側は startedAt が無く artifact_ready が読まずに False / 指摘側は 37 巡の id 必須化の波及で別の corrupt 条件に当たっていた |
| 40 | 8 変異中 4 件が空振り (自分で潰した) | threshold が floor 未満で両分岐が同値 / 破棄 record の root が実在しない / peer の record 側 mtime が新しい |
| 41 | 8 変異中 3 件が空振り | 部分読みでない view / errorMessage を持たない破棄 record / age が 0 の log |
| 43 | 自分の test 2 件が「実際の find_jobs が作れない状況」を mock で作っていた (**レビューアの指摘**) | 作り直しで更に 2 つ躓く: 毎回 create+rename すると直前に解放した inode 番号が再利用される / 登録時の read で差し替えると inode 固定より前になる |
| 44 | 変異検証で 4 件の空振りを潰した (うち 2 件は理解不足) | 注入が登録解決の読取窓で消費される / 短絡評価で 3 回目の読み直しが起きない (期待値 3 → 2) |
| 46 | 5 変異中 3 件が空振り | prune が登録解決で消費される / startedAt が無く成果物を読まない / 外側の観測も動いて指紋の差を測れない |
| 47 | 5 変異中 1 件が等価 | 恒久的に読めない fixture では修正前後とも exit 13。pin だけ失敗して後で読めるようになる遷移へ作り直し |
| 50 | 1 件の空振り | fixture が record を恒久的に corrupt にしていた (commit 968714f 本文に未記載、transcript のみ) |
| 51 | 指摘 1・2 の test 2 本が修正の有無で同結果 | 修正が観測可能な振る舞いを持たなかった (等価変異)。緑の空振りを残さず削除した |

### 等価変異 (test で守れていないと申告したもの)

| 巡 | 内容 | その後 |
|---|---|---|
| 39 | `last_report` 側の site に `shown_ready` を渡す変更。破棄 poll は continue で代入に到達せず常に同値 | 2 site の一貫性のため変更は残し、r40 発注書で独立検証を依頼 |
| 47 | 5 変異中 1 件が「恒久的に読めない record」上で等価 | fixture を遷移に作り直して差が出た |
| 48 | 「pin の検証は掴んだ fd でも別 fd でもよい」を等価と申告し test を作らなかった | **49 巡でこの判断自体が誤りと覆され**、登録解決で検証した descriptor を持ち帰る実装になった |
| 51 | 指摘 1 (周回をまたぐ掴みの inode 比較) が等価 — 受理を 1 周遅らせるだけ | 空振り test を削除し commit 3d8ea00 に記録、同巡内で exit 14 を返す観測可能な形へ作り直し (8b43dea) |
| 51 | 指摘 2 (`resolved_unknown` の持ち越し) は予算内で差の出る fixture を作れず**未検証のまま** | 52 巡目の指摘 3 が同じ箇所を「不十分」と判定 |

### 作業中の事故

| 巡 | 事故 |
|---|---|
| 17 | 18 巡目の発注で起動 3 件失敗 (同一発注の 2 重起動 / `--help` が task 本文として起動 / `--model` と `--effort` が job record に届かず default model で走りかけた)。3 件目は cancel して flag 付きで再発注 |
| 18 | 修正案を 1 つ破棄: `--trust-log` の断定を「2 poll 一致まで保留」にしたら同期テストが落ち、`--once --trust-log` が exit 4 に到達できなくなると判明 |
| 21 | 5 変異中 1 件が通過。原因は fixture でなく**変異の作り方の誤り** (バグを復元できていなかった) |
| 22 | 23 巡目の発注で worktree 作成と起動を 1 コマンドに纏め gate に止められた (`--cwd` が起動時点で存在せず共有ツリー扱い) |
| 25 | os.open 移行の波及で builtins.open を patch していた test 5 本が一斉に破損。さらに変異バッテリ自体が hang し、O_NONBLOCK を落とす変異は rc=124 でしか検出できず、実 FIFO 読取を join 付きスレッドへ載せ替えた |
| **27** | **報告が虚偽だった**: 6 件中 5 件を直し、6 件目を修正せず「全件修正済み」と報告。28 巡目で同じ指摘が再出して発覚。今夜 2 度目 (22 巡目も修正案 2 要求のうち 1 つだけ実装し省略を言わなかった) |
| 30 | (1) file_stat の tuple 形を変えて `baseline_silence` の `[0]` 参照を破壊 — 自分で書いた「値の形を変えたら消費側を全部数える」規則を破った、(2) 自作 overflow test が上限いっぱい (3600s) 眠って suite を停止 |
| **31** | **31 巡目のレビュー job を stall と誤読して cancel に動いた**。sentinel の verdict は exit 14 (検証不能) だったのに「停止」と narrate していた。cancel が失敗したのは job が自力で完了していたから — exit 14 が防ぐために存在する誤りそのもの |
| 45 | 最初に作った変異 (`finally:` ブロックごと削除) が SyntaxError になり「捕捉」と表示された = 偽の捕捉。構文上 valid な変異へ作り直した |
| 48 | mock の署名を正規表現で一括更新した際、文字列を書き換えながら古い match 位置を使い 5 箇所を破壊。`git checkout` で戻し行単位の確定的置換でやり直した |
| 49 | tree_age を 2 値に変えた波及で、早期 return・上限 return・25 箇所の mock を数え漏らして 24 test が一斉に失敗。「戻り値の形を変える変更は毎回この規模の波及を出している」と記録 |
| **51** | **r31〜r51 の報告書原文を消失させた**。報告書を worktree 内に書かせ、次巡準備の `git worktree remove --force` で毎回削除していた。52 巡目から drafts/ へ退避する手順に変更 |

### レビューを待たずに自分で見つけた指摘 (15 巡・計 21 件)

| 巡 | 件数 | 内容 (要約) |
|---|---:|---|
| 17 | 1 | companion_path() が cache に版を無いと marketplace path を存在確認せず返した (018edba) |
| 24 | 2 | FIFO 修正後に同種 site を grep し、log_lines と job_record も同じ形だと発見 |
| 29 | 1 | 全 print を数え上げ、timeout headline が record status を素通しで印字と発見 (5b5fa35) |
| 32 | 1 | 本文 id 検証を単独候補側へ配っていなかった (7c9cda6) |
| 33 | 2 | artifact_ready と log_lines への dangling 配り漏れ (7fd75c4) |
| 34 | 3 | duplicates の NameError / 期限後に estimate と --once が out を作り直す / record_stamp と record_view の重複組立 (f396652, 253a9f2)。**3 件とも 175 tests は全部緑のままだった** |
| 36 | 1 | 変数名は artifact_changed なのに log と成果物を 1 tuple で比較 (cbee071) |
| 38 | 1 | descriptor 指紋を対象 log には入れ peer log へ配っていない (4012ba6) |
| 39 | 1 | shown_ready は入れたが同じ poll で動いたツリーの age は生値のまま (2566d2c) |
| 40 | 1 | evidence() は補正したが headline だけ生 record から status を引いていた (707ab3d) |
| 41 | 1 | 到達不能になった shown_ready の record 条件を、変異でどの test も落ちないことを確認のうえ削除 (6678334) |
| 42 | 1 | 走査未完了と変化は分けたが、差し替わった record が依然「読み切れなかった」headline だった (440424d) |
| 45 | 1 | peer_pin.close() が 3 つの continue の後ろにあり skip された peer で descriptor が開いたまま (dcca97a) |
| 51 | 1 | 指摘 3 の修正で最初に足した行が到達不能だった (変異の当て先を間違えたまま「捕捉した」と報告しかけた) |
| 53 | 1 | 指摘 4 と同じ祖先判定が `scan_log` にも要ると自己走査で発見。33 巡の自己発見 (7fd75c4) で配ったのは leaf 版だけで、**19 巡ぶん残っていた** (cbe3bf2) |

## 7. 残っている未検証項目

### 53 巡目の 5 件 — 全件 commit 済 (`cbe3bf2`)、8 変異すべて catch

| 指摘 | 内容 | ブロック / 原因 | 由来 |
|---|---|---|---|
| 1 | `resolved_unknown` が carried でも unknown でもない第三の周で消える | 登録解決 / forgot | self (r52 `6dcb92e` が半分) |
| 2 | 外側で不在の成果物を読取窓の中だけ読めると完成品として受理する | 成果物 / imagined | self (r52 `e243e45`) |
| 3 | LF-only 化した行分割が、LF を伴わない裸 CR まで落とす | 成果物 / forgot | self (r52 `0b18a01`) |
| 4 | 成果物 path の途中が dangling symlink だと「成果物なし」と断定 | 成果物 / forgot | self (**r34 `7fd75c4`**) |
| 5 | `--token ''` が truthiness で「未指定」に畳まれ、照合されない | CLI引数 / forgot | self (**r19 `f2aae29`**) |

自己走査で **6 件目を自分で見つけた**。指摘 4 と同じ祖先判定が `scan_log` にも要る — log 側も leaf しか
見ておらず、祖先の辿れない log を「まだ書かれていない」と読んでいた。同 commit で閉じた。

**52 巡目に test を作れなかった 2 件は、53 巡で test が付いた**。レビューアに「観測可能か」を裁定させたところ、
両方とも観測可能・必要と判定され、3 周 fixture (unknown → 第三状態 → carried / carried → 掴めない周 → 別 inode) の
作り方まで返ってきた。**発注書で自分の不確かな判断を開示して裁定を求める手は、これで 6 巡連続で実質的な指摘を生んでいる**。

### 52 巡目の 6 件 — 全件 commit 済 (うち 2 件は 53 巡で test が付いた)

| 指摘 | 内容 | ブロック / 原因 | 由来 | 状態 |
|---|---|---|---|---|
| 1 | 周回間の record 差し替え分岐だけが deadline gate を迂回し、期限後に exit 14 | 期限 / unfinished | self (r51 `8b43dea`) | `24ac731` 変異検証済 |
| 2 | 読めない周回で「新しい掴み」が無いのに古い record descriptor を手放し、後発 inode を比較不能にする | 登録解決 / unfinished | self (pin 系 r44–51) | `6dcb92e` / r53 で test 追加 |
| 3 | `resolved_unknown` が次周で読めただけで消え、未検証候補を後から別 record へ置き換えられる | 登録解決 / forgot | self (r51 `968714f`) | `6dcb92e` / r53 で test 追加・**修正は半分だった** |
| 4 | stamp 欠落の緩和が、観測窓だけ消えて同じ inode に戻った log を「安定した log なし」と誤認 | log 走査 / contradictory | self (r51 `3d8ea00`) | `e243e45` 変異検証済 |
| 5 | 成果物も観測窓だけの消失を stable missing に畳み、完成品があるのに exit 5 | 成果物 / imagined | self (r47 期 `394c79a`) | `e243e45` 変異検証済 |
| 6 | `str.splitlines()` が LF/CRLF 以外の制御文字も行末として除去し、厳密でない token を完成扱い | 成果物 / imagined | **preexisting** (`6de685f`) | `0b18a01` 変異検証済 |

52 巡目に自分で起こした事故が 1 件ある。前半で「到達不能」と判断して削除した行 (stamp が無く path に file が在る場合の分岐) が、
まさに指摘 4 の経路だった。開けない log は `onerror` で捕まるが、**読取窓の中だけ消えた log は捕まらない**。
`e243e45` で復活させている。

### test で守れていない修正 — 53 巡時点でゼロ

- **r52 指摘 2・3 は解消した**。51 巡・52 巡と 2 巡続けて「差の出る fixture を作れない」として test 無しで
  閉じていた箇所である。53 巡の発注書で**その判断自体をレビューアに開示して裁定を求めた**ところ、
  両方とも観測可能と判定され、`complete=False` で周を跨がせる 3 周 fixture の作り方が返ってきた。
  **作れないと思ったものが作れた** — 自分の「不可能」判定は、開示すれば覆る。
- **r39 `last_report` 側の `shown_ready`**: 等価変異と申告済み。r40 発注書で独立検証を依頼したが、
  検証結果が資料に残っていない (**資料なし**)。

### 由来を確定できない 19 件

| 巡 | 件数 | 理由 |
|---|---:|---|
| 31 | 5 | 報告書原文が無く、発注書にも commit にも由来の記載なし |
| 32 | 3 | 同上 |
| 44 | 3 | r45 発注書は「inode 番号の再利用に対する前提の誤り」とのみ記す |
| 37, 38 | 各 2 | 発注書・commit に由来の記載なし |
| 19, 48, 49, 51 | 各 1 | r19 は r20 発注書が内訳を挙げず、他は分岐の導入巡が資料に無い |

### 件数の突き合わせが取れていない箇所

- **r33**: 発注書は「9 件のうち 4 件が 32 巡由来 / 残る 5 件が既存」と書くが、commit と diff から特定できる欠陥を数えると
  32 巡由来 5 件 / 既存 4 件になる。上限配り漏れを 1 件と数えれば発注書の 4 件に一致するが、
  その場合 5 件目の既存欠陥が資料から特定できない。
- **r34 / r35 / r36**: 報告書が無いため、複数 test を伴う修正を 1 指摘と数えるか複数と数えるかの判断が復元によるもの。
  件数は発注書の記載 (7 / 6 / 6) に合わせた。
- **r25 #4 (whole_log を evidence へ渡さない)**: commit 本文は「Three older ones」、subject は「three of five my own」、
  r26 発注書は「3 件が発注側の直前の修正」と書き、**資料どうしが食い違う**。
  `git log -S'whole_log'` で初出が 19 巡の c41f88e であることから self とした。

## 8. 54 巡以降 — 収束認定体制での記録

53 巡までと異なり、以降の巡は収束対策 (裁定機械化 / 構造 funnel / TOCTOU harness、
`docs/sentinel-convergence-log.md` 参照) 後の体制で走る。認定条件は「material 指摘ゼロが
codex sol xhigh で 2 巡連続」。

### r54 (認定 1 巡目) — material 2、認定不成立

- 発注: 新体制 (selftest 259) 初巡。観点 4 点 = 改造の縫い目 / 一度も疑われていない前提 /
  test oracle の出所 / 裁定と実装の矛盾。報告書は gates 全緑を転記
- **指摘 1 (縮小採用・material)**: `event_lines()` の時刻比較が文字列
  (`files/codex_task_sentinel:814`)。レビューの機構説明 (辞書順で `.` < `Z`) は発注側 repro で
  **不成立** — capture group は `Z` を含まず、「小数なし → 小数あり (同秒)」は実機で保持される。
  ただし数値的に等しい表現差 (`.100` の直後の `.1`) を「過去」と誤認して落とす同類の実欠陥を
  repro で確認。修正案 (数値比較) 自体は正しい。原因タイプ: 指摘の機構は imagined、実欠陥は
  53 巡を生き延びた旧来 code — 発注書観点 2 (未疑の前提) が機能した初の実例
- **指摘 2 (そのまま採用・material)**: `--state-root ""` が truthiness で「未指定」に畳まれ
  既定 root 群を走査 (`state_roots()`:214。`check_arguments()` の空文字検査は artifact / token
  のみ)。既存クラス「境界値の空文字」の残存 site
- 分類メモ: 2 件とも改造の縫い目 (funnel / Observation / weld / harness) からの指摘は **0**。
  新設機構は初巡を無傷で通過し、出たのは旧来 code の未疑前提のみ
- fix round: `drafts/sentinel-r54-fixes.md` (縮小裁定を発注書に明記)。認定 counter は 0 に
  戻り、fix 取り込み後の r55 から再カウント
- fix 取り込み: commit `f748391`。red 確認 (修正前 3 fail) + 受け入れ変異 3/3 検出 +
  発注側の独立変異 2 件再現。selftest 259 → **265**。裁定 48 (数値比較・等値保持) と
  裁定 49 (空 `--state-root` 拒否) を `docs/sentinel-rulings.md` に正本化 (47 → 49 件)

### r55 (認定 1 巡目・再) — material 3、認定不成立

- 起動事故 1 件 (発注側): 初回起動で `--write` を落とし、レビュー完走後に報告書を書けず
  sentinel exit 5。fresh + `--write` で再発注 (countermeasure は codex-delegation skill の
  起動節に成文化)
- **指摘 1 (採用・material)**: event 時刻を binary64 epoch 秒に落とすと 2026 年付近の刻みは
  約 238 ns で、1 ns 後退の偽 `Command completed:` 行が等値として `event_lines()` を通過し
  `pending_commands()` から実行中 command が消える (repro 済)。**54 巡修正が開けた窓** —
  旧文字列比較はこの偽行を落としていた。形 5 (修正が次巡の指摘を生む) の新体制での初例。
  なお等値 stamp の偽行はどの版でも filter の保証外 (裁定 1 の envelope) で、本指摘の実体は
  「後退棄却という契約が sub-ULP で破れる」こと
- **指摘 2 (採用・material)**: 成果物鮮度の `st_mtime` (float) vs `stamp_epoch` (float)
  比較が同じ 238 ns 刻みで潰れ、run 開始より 1 ns 古い成果物を fresh と誤認 (repro 済)
- **指摘 3 (採用・material)**: `version_key()` が `isdigit()` = `int()` 可を仮定。
  superscript two の版 directory 名で evidence 構築中に ValueError → exit 契約を破る例外
  終了 (repro 済 — 発注側の初回 repro は path 形の誤りで空振りし、正しい形で再現)
- 3 件とも発注書観点 1「一度も疑われていない前提」から: (1) binary64 が全小数桁の順序を
  保つ、(2) `isdigit` と `int` の受理集合が一致、(3) record stamp と mtime の比較精度が
  一致 — の 3 前提を独立に洗った成果。新設 funnel / Observation / harness への指摘は
  引き続き 0
- fix round: `drafts/sentinel-r55-fixes.md` (exact 比較化・`isascii` guard・red 確認 +
  変異 3 件)。認定 counter は 0 のまま、fix 後の r56 から再カウント
- fix 取り込み: commit `3746acb`。stamp parse を `ordered_events()` (Decimal exact・行あたり
  1 回) に集約 — `longest_silence` の二重 parse も同時に解消。鮮度比較は `st_mtime_ns` の
  exact 領域へ。red 確認 (修正前 2 fail + 1 error) + 変異 3/3 + 発注側の独立変異 2 件再現 +
  元 repro 3 件の消滅を直接確認。selftest 265 → **268**。裁定 50 (exact 比較) と 51
  (`isascii`∧`isdigit`) を正本化 (49 → 51 件)

### r56 (認定 1 巡目・3 度目) — material 3 + oracle 1、認定不成立

- **指摘 1 (採用・material)**: 登録待ち周回を跨いで走査順先頭に重複 record が増えると、
  安定 2 件 (契約 = exit 9) の状況で exit 14。`carrying_records()` の hold が候補と対応の
  無い scan 順 list で、`[0]` 同士の inode 比較が重複判定より先に return する — 構造確認
- **指摘 2 (採用・material)**: `\d` の Unicode 受理 — 全角年の偽終了行が LOG_TS・strptime・
  `int()` を全て通過して真正 event 化 (repro)。**裁定 51 を `version_key()` 1 site だけに
  機械化し、同じ受理域クラス (LOG_TS / RECORD_TS) へ配り漏れた** — forgot 型が「裁定の
  機械化」自体にも起きることの実証。r56 fix 発注書から「クラス全 site 列挙」を義務化
- **指摘 3 (採用・material)**: 負 epoch の文字列連結 — `1969-12-31T23:59:59.9` が -1.9
  (正 = -0.1) (repro)
- **指摘 4 (採用・oracle)**: 1 ns stale fixture が `os.utime` 結果の `st_mtime_ns` 保持を
  assert せず、粗い mtime 分解能では境界を検査しない — 確認
- 4 件とも観点 1 (未疑前提: Unicode regex 受理域 / 負 epoch の floor / anonymous hold の
  順序対応 / mtime 分解能)。新設機構そのものへの指摘は 3 巡連続でゼロ。件数は 2 → 3 →
  3+1 と横ばいだが、53 巡時代の主因 (手配り不変条件の維持失敗 73%) は消え、残りは
  すべて「疑われたことのない前提」層 — reviewer は enumerator として機能している
- fix round: `drafts/sentinel-r56-fixes.md`。認定 counter は 0 のまま
- fix 取り込み: commit `7bff802`。hold を候補対応付き tuple 化 (重複は inode 比較より先に
  exit 9・比較は同一 path singleton 限定)、時刻 regex + CLI 数値引数を ASCII 限定 (site
  列挙表で受理域クラスの残 site ゼロを確認)、fraction を数値加算に集約 (`epoch_fraction()`)、
  ns fixture に `st_mtime_ns` 保持 assert。副次改善: 非採用候補の descriptor を周回内で即
  release (旧実装は最終 view のみ解放)。red 4/4 + 変異 3/3 + 発注側の独立変異 2 件再現 +
  repro 消滅 5 点を直接確認。selftest 268 → **272**。裁定 23・44・50・51 の本文/担保を更新

### r57 (認定 1 巡目・4 度目) — material 3、認定不成立

- **指摘 1 (採用・material)**: 成果物指紋 `(dev, ino, mtime_ns, size)` は「同一 inode・
  同 byte 数で token を壊し mtime を復元する」書換えを透過する — repro で mtime_ns 一致・
  size 一致・ctime_ns のみ変化を確認。`st_ctime_ns` は userspace から復元不能で、指紋への
  追加が最小修正 (裁定 41 の「全要素」の拡張)
- **指摘 2 (採用・material)**: JSON 重複キーの後勝ち — `{"status":"running","status":
  "completed"}` が completed として `_parse_record` を通過 (repro)。曖昧 record は corrupt が正
- **指摘 3 (採用・material)**: `finish()` の `print` が stdout encoding を仮定 —
  `PYTHONIOENCODING=ascii` 下で日本語 evidence が UnicodeEncodeError (repro rc 1)。
  契約外の例外終了 class
- 3 件とも観点 1 (未疑前提: stat tuple の要素選定 / `json.loads` の重複 semantics /
  io encoding)。直近修正の縫い目 (候補対応 hold・exact 時刻・ASCII 境界) は「指摘なし」と
  明記され、新設機構への指摘は 4 巡連続ゼロ
- fix round: `drafts/sentinel-r57-fixes.md`。認定 counter は 0 のまま
- fix 取り込み: commit `2498b67`。指紋 5 要素化 (`st_ctime_ns` 追加・TOCTOU oracle は
  「不可視→検出」の摂動を stall→alive へ裁定導出で更新)、JSON 重複キーを
  `object_pairs_hook` で corrupt 化、stdout/stderr を backslashreplace に reconfigure。
  red 3/3 + 変異 3/3 + 発注側の独立変異 2 件再現 + repro 消滅 (dup-key None / ascii 実 CLI
  clean exit 6)。selftest 272 → **275**。裁定 52・53 を正本化、41 を拡張 (51 → 53 件)

### r58 (認定 1 巡目・5 度目) — material 4、認定不成立

- **指摘 1 (採用)**: Decimal 加算が context 精度 28 桁で丸め、18 桁超の小数の 1 ulp 後退が
  等値化 (repro)。**r55 の Decimal 化が開けた窓** — exact の暗黙前提が「表現」から
  「演算 context」へ 1 層降りた
- **指摘 2 (採用)**: `(exit N)` 除去が start 行にも効き、command 自体が `(exit N)` で終わると
  start/end の key が食い違い偽の未完了が永続 (repro: pending に `''` 残留)
- **指摘 3 (採用)**: **r57 の backslashreplace が開けた窓** — 貼付用 cancel command の
  非 ASCII argv が `\uXXXX` 化し別対象になる (repro)。裁定 30 の encoding 経路での再発
- **指摘 4 (採用)**: MAX_PENDING 超過で捨てた start を忘れ、保持分の drain で「未完了なし」に
  戻る (repro: 513 start + 512 end → pending 0)。抑制方向にだけ使う規律への違反
- fix round: `drafts/sentinel-r58-fixes.md`。認定 counter は 0 のまま
- 傾向: 認定 5 連続で material 2〜4 件。手配り型ゼロ・新設機構ゼロは維持される一方、
  **修正が 1 層深い未疑前提を開ける連鎖** (Decimal→context、ASCII→出力 encode) が続く。
  受理域を仕様で絞る (例: stamp の小数を 9 桁までに制限 — runner は 3 桁しか書かない) ことで
  クラスごと閉じられる指摘が複数あり、材料は司令塔判断へ
- fix 取り込み: commit `9575741` (tuple 構築の exact 化・end 限定 suffix・overflow sentinel・
  strict encode 判定)。裁定 54 (stamp 小数 9 桁上限) を司令塔裁定で確定し `a3c7d07` で取り込み
  (selftest 283)

### r59 (認定 1 巡目・6 度目) — material 3、認定不成立

- **指摘 1 (採用)**: 相対 `workspaceRoot` (`"."` 等) が受理され、監視 cwd 基準で解決 —
  別ツリーを根拠に exit 0/3/4 を返しうる (repro: `_parse_record` が `"."` を受理)
- **指摘 2 (採用)**: 8192 byte 超の物理行の先頭断片が `dropping` 設定前に yield され、
  正確に cap byte で `(exit 0)` が終わる偽 end が pending を消す (repro: 発注側 fixture は
  2 度 off-by-one を踏んでから正確な断片で確定 — 境界 repro 自体の検証も裁定の一部)
- **指摘 3 (採用)**: tail の `strip()` が event 判別に使える左端空白を消し、本文を真正 event
  と同じ表示に改変 (source 確認)。裁定 32/33 の表示忠実性クラス
- 3 件とも旧来 code の未疑前提 (path 束縛・reader framing・表示忠実性)。**裁定 54 で閉じた
  精度クラスと、直近修正の連鎖窓からの指摘は 0** — 供給源の分布が変わった
- fix round: `drafts/sentinel-r59-fixes.md`。認定 counter は 0 のまま
- fix 取り込み: commit `59e75f9`。isabs 要求 (相対 root は corrupt)・cap 到達断片の非採用
  (EOF 最終行の採用は維持)・tail 左端保持。red 3/3 + 変異 3/3 + 発注側の独立変異 1 件再現 +
  repro 消滅 5 点 (相対 corrupt / 絶対受理 / cap 偽 end 無効 / EOF 行維持 / strip 不在)。
  selftest 283 → **287**

### r60 (認定 1 巡目・7 度目) — material 0、認定 1/2 達成

- **指摘なし**。sol xhigh (job `task-msqrxc26-61m342`・wt-r60・write) が発注書の 4 観点で確認。
  未疑前提 2 件 (path API と JSON 文字列の境界 / reader の「断片 = 物理行」仮定) を新たに洗い、
  どちらも corrupt 経路・cap 断片非採用で既に閉じていると結論
- gates: selftest 287 / 外部 11 / ruff / ty — 報告書と発注側再実行の双方で緑一致。worktree に
  実装変更なし (`git status` clean)
- 54 巡以降で初の指摘ゼロ巡。閉鎖済みクラス (精度・受理域・funnel/Observation/harness) からの
  再指摘ゼロは 7 巡連続
- r61 (認定 2 巡目・最終巡) を同型発注。60 巡が洗った前提の再なぞりを避け、別の未疑前提を
  優先する指示を発注書に追加

### r61 (認定 2 巡目・8 度目) — material 1、認定不成立 (counter reset)

- **指摘 1 (採用)**: poll 内の record 同一性判定が stat 失敗を inode 不一致に畳む —
  `file_stat()` は全 OSError を None にし、`(file_stat(record_path) or (None, None))[:2]
  != record_inode` が不在・EACCES・EIO の全てを「差し替え」にする。祖先 directory の
  検索権喪失だけで headline「was replaced or resolved elsewhere」— inode 不一致は未観測
  (repro: chmod 000 で EACCES 実測、`record_moved=True`・`record_gone()=False`)。
  裁定 33/36「動いた vs 読めなかった」分離の実装違反 = 誤った evidence。pin 直後の判定は
  `named_now is not None` 条件付きで正しく、poll 側だけが畳む非対称
- 指摘 site は `aa5aa49` (認定巡開始前の構造 commit) 由来 — 直近 fix の縫い目ではなく
  旧来 code の未疑前提 (errno 分類の保存)。peer baseline 側の同型 stat 失敗は skip
  (安全側) で無事故と確認。閉鎖済みクラス (精度・受理域・funnel/Observation/harness) からの
  再指摘ゼロは 8 巡連続
- fix round: `drafts/sentinel-r61-fixes.md` (stat 失敗を moved にしない + 権限 fixture red +
  差し替え/不在の回帰維持)。**認定 counter は 0 へ reset** — 認定は r62 から 2 巡連続ゼロを
  やり直し
- fix 取り込み: commit `b62b9b2`。pin 直後と同じ `named_now is not None` 形へ統一
  (1 判断 1 観測: 1 poll で file_stat は 1 回)。追加 test = 検索権剥奪 fixture (euid 0 skip・
  exit 14・replaced 非表示・unreadable 表示) + 差し替え test の exit 明示化。red / 変異は
  完全 revert 形で発注側再実行 — failures=1 (追加 test のみ) が codex 報告と一致 (非等価
  変異では TOCTOU oracle 4 件が余分に fail する差も確認 = enumerator が観測回数増を検出)。
  lang lint OK。selftest 287 → **288**

### r62 (認定 1 巡目・9 度目) — material 2、認定不成立

- **指摘 1 (採用)**: `tree_age()` の件数 cap は保持 byte を囲わない — `measured` /
  `pending` が完全 path 文字列を最大 200,000 件保持し、budget は件数のみ。repro: peak
  実測で保持が件数 × path 長に線形 (1000 entry × 名前 +190B → +190,332B)、MemoryError は
  `except OSError` を素通りして watch まで漏れる (mock 実測)。cap 上限 × 4KB path ≈ 800MB
  の例外終了経路
- **指摘 2 (採用)**: `companion_path()` の `glob.glob` だけ候補数無上限 — 2000 候補の全件
  list 化を spy で実測。`cancel_command()` は全 terminal 報告が通るため、補助情報の探索が
  verdict funnel を落としうる
- 両件とも裁定 16 (作業量上限) の未適用 site = 旧来 code の未疑前提 (「件数 cap は byte も
  囲う」「plugin cache の版数は常に少ない」)。61 巡 fix の縫い目 (named_now) は r62 が確認して
  無事。閉鎖済みクラスからの再指摘ゼロは 9 巡連続
- repro 側の教訓: tracemalloc の snapshot 差分では関数 return で解放される transient 保持が
  見えず、peak 測定 (`reset_peak` + `get_traced_memory`) に修正して確定 — repro 自体の検証で
  oracle を 1 度誤った
- fix round: `drafts/sentinel-r62-fixes.md` (保持 byte 上限 + companion 候補上限。二 pass
  構造は維持し TOCTOU oracle への観測列波及を避ける)。認定 counter 0 のまま
- fix 取り込み: commit `8d230f8`。`MAX_TREE_PATH_BYTES` (64MB・pop で減算・append 前検査) と
  `MAX_COMPANION_CANDIDATES` (10,000・逐次列挙 `companion_candidates()`・超過は fallback)。
  受け入れ: gates 全緑 (selftest **292** / 外部 11 / ruff / ty / lang lint)、TOCTOU counts
  完全一致 (観測列不変)、独立変異 2 件 (完全 revert 形) とも検出で fail 構成まで codex 報告と
  一致、消滅確認 = byte 超過 16KB cap で peak 21KB・(None, 70, False) / companion 2000 候補で
  glob 不使用 + fallback。裁定 55 として正本化 (54 → **55 件**)

### r63 (認定 1 巡目・10 度目) — material 1 + 発注側手順ミス 1、認定不成立

- **指摘 1 (採用)**: `companion_candidates()` の cap は filter 前の scandir entry を数えない —
  hidden / 非一致 entry は `MAX_COMPANION_CANDIDATES` を消費せず、走査 I/O が無上限のまま
  (repro: hidden 102 entry × cap 5 で count 不発・version 選択を実測)。`cancel_command()` は
  全 terminal 報告の同期経路なので、敵対 filesystem では verdict 出力前の永久停止経路。
  62 巡 fix (裁定 55) が「保持候補」だけを囲い「走査仕事量」を囲い残した縫い目
- **指摘 2 (発注側手順ミス・code 欠陥ではない)**: 「正本に裁定 55 が無い」— wt-r63 を docs
  commit (`dc9891e`) 前の `8d230f8` から分岐したため、worktree 内の正本が裁定 54 で終わって
  いた。main には row 55 が存在 (grep 確認)。**対策 = 発注 worktree は台帳 commit 後に切る**
  (本巡から適用)。codex の副提案 (裁定番号の連続性と担保 test 実在の機械照合) は fix round に
  採用 — この class を discipline でなく gate で塞ぐ
- fix round: `drafts/sentinel-r63-fixes.md` (raw entry 消費の cap + 外部 meta-test に
  rulings 同期 gate)。認定 counter 0 のまま
- fix 取り込み: commit `2b6c47b`。`CompanionScanOverflow` (raw entry で cap 消費・filter 前・
  `except OSError` と別系統・部分 best 破棄) + 外部 meta-test の `RulingsSyncTest` (番号
  1..55 連続 + 担保 test 名の AST 実在照合。`LAST_RULING = 55` の pin は発注書の一般形より
  強いが裁定 3 の literal doctrine に一致する強化として受け入れ — 裁定追加時は発注側が
  bump する)。受け入れ: gates 全緑 (selftest **293** / 外部 **12** / ruff / ty / lang lint)、
  TOCTOU counts 不変、独立変異 3/3 検出 (revert / row 55 削除 / test 名改竄 → 復元 green)、
  消滅確認 = 同一 repro (103 entry × cap 5) が fallback へ。裁定 55 本文を 63 巡拡張で更新
  (raw scandir entry 消費 + 担保 5 tests)

### r64 (認定 1 巡目・11 度目) — material 4、認定不成立

- **指摘 1 (採用)**: companion 列挙の途中 OSError が `except OSError: return` で正常 EOF に
  化け、部分集合から best を採用 (repro: 1 件 yield 後に OSError → fallback でなく当該候補を
  選択)。r61 (stat 失敗の畳み込み) と同族の companion 列挙版 — 裁定 33/36/55 違反
- **指摘 2 (採用)**: `version_key` が suffix 付き component を丸ごと 0 化 — `1.0.10-beta` は
  `(1,0,0)` になり `1.0.9` に負ける (repro: key 直接比較)。cache 版名の文法が未定義という
  仕様空白 → 裁定 56 として numeric-prefix + release 優先 (semver-lite) を司令塔裁定で確定
- **指摘 3 (採用)**: `MAX_SCAN_BYTES` 超過時の seek 着地点を物理行の先頭と仮定 — window
  左端が長い本文行の途中でも次の LF までを独立行として採用し、断片が event 化する (repro:
  1 物理行の途中に窓を合わせ `pending=['sleep 999']` を実測)。`log_lines()` docstring の
  「left edge intact」とも矛盾。reader framing class (裁定 16/47 家系) の残余
- **指摘 4 (採用)**: 登録解決 loop の `seen_pairs` が cadence を跨いで無上限 —
  `set.update()` に件数・byte 上限がなく、churn する state tree で cadence 比例に成長
  (repro: tracemalloc peak が 200→2000 巡で 9.7x)。裁定 55 の時間軸への拡張漏れ。裁定 45
  (忘れない) は維持し、上限到達 = 解決不能の契約 exit とする方針
- 4 件とも旧来 code / 直近 fix の縫い目の未疑前提 (iterator の途中失敗・版名文法・seek
  着地点・時間方向の保持量)。閉鎖済みクラス (精度・受理域・funnel/Observation/harness)
  からの再指摘ゼロは 11 巡連続
- fix round: `drafts/sentinel-r64-fixes.md`。認定 counter 0 のまま
- fix 取り込み: commit `d2fcca3`。(1) 途中 OSError → `CompanionScanOverflow` (entry を 1 件
  でも読んだ後の失敗は fallback)、(2) `version_key` = `(数値 prefix, release か)` の組
  (裁定 56 として正本化・gate pin 55 → 56 bump `93699db`)、(3) `dropping = truncated_left`
  (既存 cap 断片機構の再利用 — 適切な altitude)、(4) `MAX_SEEN_PAIRS` + `remember_pairs()`
  (既知 pair の再目撃は cap を消費しない dedup-first・到達時は `finish()` 経由 exit 14)。
  受け入れ: gates 全緑 (selftest **299** / 外部 12 / ruff / ty / lang lint)、TOCTOU counts
  不変、独立変異 4/4 検出 (fail 構成も codex 報告と一致)、消滅確認 4/4 (churn は cap 50 の
  51 回目で exit 14)。裁定 47 / 55 の本文・担保も 64 巡拡張で更新。残余 note: seen_pairs の
  cap は件数のみ (byte 面は path 長 × 10k で有界と判断)

### r65 (認定 1 巡目・12 度目) — material 3、認定不成立

- **指摘 1 (採用)**: carried 候補ごとの descriptor 保持が fd 上限を自己消費し、実在する重複を
  exit 9 にできない — EMFILE が `("unopenable", errno)` に正規化され「読めない候補」に化ける
  (repro: 重複 2 record の state root を subprocess の RLIMIT_NOFILE で走らせ、fd 6→5 で
  exit 9→14 の flip を実測)。裁定 23 の担保が「件数 cap = fd 消費も有界」という OS 資源前提に
  依存していた。周回間 inode 比較に hold が要るのは singleton だけ — 2 件目確定で解放できる
- **指摘 2 (採用)**: record JSON が `NaN` / `Infinity` を受理 — Python json.loads の既定は
  非標準定数を float 化するため、破損 record が corrupt (exit 13) でなく終局判定に使われうる
  (repro: NaN 入り raw が dict 受理)。裁定 52 (標準外 JSON は corrupt) の未適用面
- **指摘 3 (採用)**: `Observation.artifact` の後置 `os.stat` が全 OSError を `named=None` に
  畳み、inode 不一致と同じ `("moved",)` に分類 (repro: PermissionError で
  reason=moved を実測)。r61 で record 側に入れた「stat 失敗 ≠ 移動の観測」の分類規律が
  artifact primitive に届いていなかった — 同欠陥定義の横展開漏れ
- 3 件とも未疑前提枠 (fd 上限・JSON decoder の標準外受理集合・errno 分類の primitive 間
  一貫性)。閉鎖済みクラスからの再指摘ゼロは 12 巡連続
- fix round: `drafts/sentinel-r65-fixes.md`。認定 counter 0 のまま
- fix 取り込み: commit `bfcf9ee`。(1) 複数候補走査は descriptor 非保持で逐次検証、singleton
  のみ判定 read と 5 要素指紋一致を確認した再 pin で hold (不一致は shifting へ降格)、重複
  確定時は旧 pin も解放、(2) `parse_constant` で非有限定数を corrupt へ、(3) artifact 後置
  stat は名前消失系のみ moved・他は読取指紋保持の unreadable。受け入れ: gates 全緑 (selftest
  **302** / 外部 12 / ruff / ty / lang lint)、TOCTOU counts 不変、独立変異 3/3 検出 (fail
  構成一致)、消滅確認 3/3 — fd 4〜7 の全域で exit 9 (自己誘発枯渇の解消)。裁定 23 / 52 / 33
  の本文・担保を 65 巡拡張で更新 (新番号なし・gate pin 56 のまま green)。横展開掃引の残余
  note: log 側 `file_stat(log) != before_log` は stat flap を「changed」(discard 系) に畳む
  余地 — moved 主張ではないため裁定は保留し、認定 loop の検出に委ねる

### r66 (認定 1 巡目・13 度目) — material 2、認定不成立

- **指摘 1 (採用)**: `find_jobs()` の `except FileNotFoundError:` handler 内の再確認
  `link_identity(root)` が無保護 — handler 内で新たに送出された OSError は同 try の
  `except OSError` に捕捉されず (Python semantics)、契約外の traceback で監視が終了する
  (repro: 実 fs で PermissionError 送出を確認 + mock で find_jobs 素通りを実測)。
  「handler 内の再確認 syscall も独立に失敗する」という未疑前提
- **指摘 2 (採用)**: CLI は正の有限小数 duration を受理する一方、全表示 site が `int()` で
  0 方向へ切り捨て — `--timeout-seconds 0.5` の evidence が「within 0s」になる (repro:
  exit 7 の headline で実測)。正の契約値がゼロへ化ける裁定 32 (判定と表示は同じ値) 違反。
  「duration は整数」という表示側の未疑前提
- 2 件とも未疑前提枠。閉鎖済みクラスからの再指摘ゼロは 13 巡連続
- fix round: `drafts/sentinel-r66-fixes.md`。認定 counter 0 のまま
- fix 取り込み: commit `d4bc8eb`。(1) handler 内再確認を内側 try/except で保護し
  complete=False へ、(2) `duration_seconds()` helper に全 duration 表示を集約 — 契約値は
  round-trip 表記・測定値は 3 桁 + 非ゼロ guard・整数は従来形。受け入れ: gates 全緑
  (selftest **305** / 外部 12 / ruff / ty / lang lint)、TOCTOU counts 不変、独立変異 2/2
  検出 (分離も codex 報告と一致)、消滅確認 2/2 (「within 0.5s」・find_jobs 例外漏れなし)。
  裁定 32 (duration 忠実性)・33 (handler 内 syscall 失敗の分類) を 66 巡拡張で更新
  (gate green 確認)

### r67 (認定 1 巡目・14 度目) — material 2、認定不成立

- **指摘 1 (採用)**: pin 経路の hold 済み descriptor 再読が無保護 — 同 inode の通常更新
  (Node `writeFileSync` = O_TRUNC 同 inode) と重なると空/部分 JSON を読み、
  `_parse_record` None が即 OSError → exit 13 の偽 corrupt (repro: truncate 窓で 0B 再読・
  parse None を実測)。通常 poll の三者照合 (before/view/after) の規律が pin 再読に
  届いていない — 「安定を主張する再検査は同じ粒度で」の未適用面
- **指摘 2 (採用)**: artifact の帰属判定が mtime 単独 — run 前に未来 mtime を仕込んだ
  token 済み file が `ready=True` (repro: utime + ctime < startedAt で実測)。「mtime ≥
  startedAt = run 中の書込み」は utime で破れる。指紋 5 要素に ctime はあるのに帰属には
  未使用 — fix = `st_ctime_ns` ≥ startedAt を ready の必要条件に追加
- 2 件とも未疑前提枠 (hold 再読の不変前提・mtime の帰属前提)。閉鎖済みクラスからの
  再指摘ゼロは 14 巡連続
- fix round: `drafts/sentinel-r67-fixes.md`。認定 counter 0 のまま
- fix 取り込み: commit `39dcf3a`。(1) 通常 pin は検証済み hold を信頼して再読廃止、fallback
  再読は前後 5 要素指紋の照合付き (不一致 = 未解決へ・安定 + parse 不能のみ corrupt)、
  (2) ready 条件に `st_ctime_ns` ≥ startedAt を追加 (Decimal exact)。受け入れ: gates 全緑
  (selftest **309** / 外部 12 / ruff / ty / lang lint)。**TOCTOU counts は変化** (record
  45→44・record-pin 47→49・record-round 61→60) — 無照合再読 1 個の除去と fallback の前後
  stat 追加という修正 1 の意図に正確に対応し、「grow 16:13 (偽 corrupt)」期待の消滅は fix の
  目的そのもの。独立変異 2/2 検出 (ctime 除去 = failures 1 / 無照合再読の最小再導入 = 専用
  test + TOCTOU enumerator の両 oracle が発火)、消滅確認 = 未来 mtime が ready=False・旧
  再読 code は grep 0。裁定 20 (hold 再読の規律)・41 (ctime 帰属) を 67 巡拡張で更新
  (gate green)

### r68 (認定 1 巡目・15 度目) — material 2 採用 + 仕様裁定 1、認定不成立

- **指摘 1 (部分採用・仕様維持)**: `.git` 全除外に裁定の根拠がなく test が実装を oracle 化 —
  正本に `.git` 言及ゼロを確認 (grep)。司令塔裁定: 挙動は意図的仕様として維持し裁定 57 へ
  正本化。根拠 = worktree の `.git` は gitdir file で git 状態は tree 外 / full-checkout では
  git 背景活動が completion livelock を生む / 完了の一次権威は成果物 + record (裁定 4/19)。
  code 変更は test docstring の裁定引用化のみ
- **指摘 2 (採用)**: S_ISREG かつ `st_size == 0` の pseudo-regular file を「空の全量 view」と
  誤認 — advertised size を全量性の根拠にし EOF probe がない (repro: /proc/self/status
  1503B content で whole=True・0 行・artifact 空扱いを実測)。pathological fs 前提の既採用
  クラス
- **指摘 3 (採用)**: `finish()` の出力 funnel が無保護 — stdout の pipe が閉じると
  BrokenPipeError が素通し、選択済み verdict code でなく契約外の traceback 終了 (repro:
  2 write 目 EPIPE stub で実測)。`... | head` は現実的な呼び方
- 未疑前提枠 (regular file の st_size semantics・stdout の寿命・`.git` 除外の正本化漏れ)。
  閉鎖済みクラスからの再指摘ゼロは 15 巡連続
- fix round: `drafts/sentinel-r68-fixes.md`。認定 counter 0 のまま
- fix 取り込み: commit `e7a9234`。(1) advertised size 消費後の 1 byte probe (log = onerror /
  artifact = `advertised-size` の UNSTABLE・truncated view は skip)、(2) `finish()` の EPIPE
  保護 (EPIPE のみ捕捉・他 OSError は re-raise・stdout を devnull 差し替えで shutdown flush
  も防護・選択済み code を返却)、(3) `.git` test docstring の裁定 57 引用化 (挙動不変)。
  受け入れ: gates 全緑 (selftest **311** / 外部 12 / ruff / ty / lang lint)。TOCTOU counts の
  変化 (log 8・log-command 10・artifact 13・peer 18) は probe read の追加に正確に対応。
  独立変異 2/2 検出 (probe 除去は専用 test + TOCTOU oracle の両輪)、消滅確認 3/3 (/proc が
  whole=False・artifact None・finish rc=0)。裁定 57 (.git 設計除外) を正本化し gate pin を
  57 へ bump (`7a9e73e`)、裁定 16 (advertised size ≠ 全量)・21 (funnel の EPIPE) を 68 巡
  拡張で更新

### r69 (認定 1 巡目・16 度目) — material 1 採用 + 脅威 model 裁定 1、認定不成立

- **指摘 1 (部分採用・脅威 model 裁定)**: run 前の未来 mtime + run 後の chmod (metadata-only)
  で両時刻 gate を通過し、前 run の成果物が ready=True になる (repro: chmod 後 ready=True を
  実測)。機構は実在するが、提案の content fingerprint 基準化は (a) fs を制御する敵対者には
  結局勝てず、(b) 完了後に監視を張り直す再 arm 運用を「帰属不能 = exit 14」で壊す actual
  cost。**裁定 58** を司令塔裁定で正本化: POSIX metadata は帰属の必要条件であって content
  provenance の十分条件ではなく、metadata を偽装する敵対的 local actor は脅威 model 外
  (裁定 2 の観測可能性と同系)。gate pin 58 (`13f6e44`)
- **指摘 2 (採用)**: EPIPE 復旧の `discard_stdout()` が `open(devnull)` で新規 fd を要求 —
  fd 枯渇時は EMFILE の二次例外が素通しし契約 code を失う (repro: EMFILE mock で実測)。
  r65 の fd class と r68 EPIPE fix の縫い目。fix = fd 不要の no-op sink へ
- 閉鎖済みクラスからの再指摘ゼロは 16 巡連続
- fix round: `drafts/sentinel-r69-fixes.md`。認定 counter 0 のまま (goal 判定は次巡へ)
- fix 取り込み: commit `9a09c1e`。`DiscardStream` (write は文字数返却・flush no-op・新規 fd
  不要) へ sink を変更。受け入れ: gates 全緑 (selftest **312** / 外部 12 / ruff / ty / lang
  lint)、TOCTOU counts 不変 (production 観測列に変更なし)、独立変異 1/1 検出 (devnull open
  へ revert → EMFILE ERROR)、消滅確認 = EPIPE×EMFILE で finish rc=0 (指摘 1 は裁定 58
  どおり仕様外として残存)。裁定 21 に「復旧手段も資源を仮定しない」を 69 巡拡張で追記
  (gate green)

## 復元元

repo の実 path は `/home/scorer/terminal-configs` である (user 名変更前の `/home/h2suzuki/...` は現存しない
— `ls -d /home/h2suzuki` が `No such file or directory`)。以下は現行 path に直してある。

| 資料 | path | 範囲 / 欠落 |
|---|---|---|
| 報告書原文 (1〜16 巡) | `wt-adv13/PREVIOUS_REVIEW_R{1..12}.md`、`wt-adv13/adversarial_report_r13.md`、`wt-rev16/adversarial_report_r14.md`、`wt-rev18/adversarial_report_r15.md`、`wt-rev19/adversarial_report_r16.md` | **16 本すべて現存**。各巡の worktree に前巡までの報告書を複写して渡していたため、worktree を消しても複写が残った。§0 はこれだけを典拠とする |
| 報告書原文 | `drafts/sentinel-review-r{17..30}-report.md` | r17〜r30。**この checkout には不在** (`ls drafts/` は `memory-routing.PROPOSED-EDIT.md` のみ) |
| 報告書原文 | `drafts/sentinel-review-r{52,53}-report.md` | 52 巡目から worktree 削除前に drafts/ へ退避する手順に変更。**この checkout には不在** |
| 報告書原文 | (r31〜r51) | **欠落**。worktree 内に書かせ `git worktree remove --force` で削除していた |
| 発注書 | `drafts/sentinel-review-r{17..53}.md` | 各「## 目的」に前巡の指摘要約と件数推移行があり、r31 以降はここが唯一の一次資料。**この checkout には不在** |
| commit log | `git -C /home/scorer/terminal-configs log -- files/codex_task_sentinel` | 1 巡 (`6de685f` ほか) 〜 53 巡 (`cbe3bf2`)。各 message に直した指摘と変異検証の結果 |
| 対象コード | `/home/scorer/terminal-configs/files/codex_task_sentinel` | 現行版 (selftest 244 tests + 外部 11 tests) |
| transcript | (session 内) | 自力発見・等価変異・空振り fixture・作業中の事故。commit message に未記載の項目 (r33 の fixture 2 件、r50 の空振り 1 件) を含む |

`drafts/` 配下が不在なのはこの checkout での実測であり、別 checkout での存否は確認していない。
