# 敵対的レビュー loop のメタ評価 — マッチポンプの構造と出口

2026-08-25 の session (`a7526d44`) の transcript 3,774 行・git 履歴・docs 3,500 行・memory
entry 118 件・第三者意見書 2 通・文献 30 件を突き合わせ、「指摘を直すたびに欠陥を作り込み、
総合品質が上がらない」状態がなぜ続くのかと、どこで抜けるかを書く。数字はすべて実測で、
出典は各行に添える。第三者意見書 2 通は 08-21 の `drafts/quality-estimation-opinion-report.md` と
08-26 の `drafts/loop-exit-opinion-order-report.md`。

## 0. 結論

- **loop は収束しない設計になっている。** 停止条件「reviewer の指摘ゼロ」は、その時点で有効な
  規則で数えると 36 巡で 0 回しか満たされていない。reviewer は指摘を供給し続ける装置であり、
  指摘ゼロは artifact の状態ではない
- **失敗への反応が「規則を足す」に固定されている。** 方法論 198 → 509 行、checklist 14 → 26、
  裁定 47 → 63 の間、再発を止めたのは削除・機構化・context 遮断レビュー (= 道具本体だけを
  渡し、発注書・過去の指摘・裁定を見せないレビュー)・発注側自身の測定だけで、文言の追加は
  1 件も止めていない
- **出口は巡数でも規則でもなく、停止条件と artifact の大きさを変えること。** 受け入れ test と
  変異器 (= 実装に固定の欠陥を仕込み、test が検出するかを測る道具) を発注側が先に持ち、独立
  レビュー 1 巡で用途内 P0 (= 想定用途の入力で起きる最重要欠陥) が無ければ出荷、残りは記録しない。
  sentinel (`codex_task_sentinel`) は要件から小さく書き直し、ab_probe (`claude_ab_probe`) は
  廃棄、方法論 (`docs/adversarial-review-methodology.md`) は 1 ページへ (いずれも 2026-08-26 決裁)

## 1. 2026-08-25 の session で何が起きていたか

表中の「第 N 部」は transcript を 4 つに区切った区間の番号。

| 観点 | 実測 |
|---|---|
| 所要 | 16 時間。main context 処理 **4.18 億 token** (cache read 4.15 億 / output 86 万)。subagent 15 (codex 7 / opus review 8)・workflow 2 は別枠 |
| ユーザー待ち | 第 1 部 243 分中 assistant 無発話 **190 分**。第 3 部 132 分中 主 session 無操作 83 分 |
| product vs meta | 第 1 部: 稼働 53 分中 code 3 分。第 3 部: docs commit 13 / code commit **0**。第 4 部: docs commit 7 / code commit 0。08-08 以降の 575 commit = product 202 / docs 157 / todos 204 / tests 2 |
| artifact の成長 | sentinel 252 → **8,588 行** (production 2,197 / selftest 6,391 = 74%)、112 commit、76 巡。111 回の差分のうち増加 106・減少 5、有意な純減 3 件は**すべて人間裁定か発注側の削除**でレビュー由来 0。ab_probe 494 → **810 行** / 7 巡、純減は巡 6 の 1 回 |
| 発注書 | ab_probe 7 通 = **1,307 行** (170〜214 行/巡)。道具本体より長い仕様を毎巡書き直した |
| docs | sentinel 関連 6 本 3,434 行 = production の 1.56 倍。08-13 は docs 111 commit vs sentinel 27 commit |
| 反応速度 | ユーザー指摘 → 方法論 +83 行 → commit: **58 秒 / 10 秒**。レビュー結果 → 次巡発注: **89 秒**。「自走」許可 → 巡 5 発注: 2 分 (後に丸ごと破棄) |
| 本来のテーマ | todo の Goal「注入発生率そのものを下げる (書かせない)」の成果物は **51 秒**で書かれ、レビュー 2 系統が走行中のまま criterion を `[x]` に flip |
| hook 摩擦 | 1 commit に deny 7 回。委譲起動が検問で毎回 bounce (08-25 session 2/2、08-26 session 3/3)。発注書を書く heredoc が「codex」で始まる行で 3 回 deny。Stop hook で長文を丸ごと再出力 ×4。教訓照合を含む発話 19/66 (29%) |

## 2. なぜ収束しないか — 3 層のマッチポンプ

### 2.1 code 層 — 到達しない停止条件と、増え続ける artifact

- 停止規則は v1「codex sol xhigh 2 巡連続 material 0」→ v2「連続でなく計 2 回」→ v3「U0 (=
  ユースケース正本 `docs/sentinel-use-cases.md` の用途内で起きる指摘) のみ計 2 回」→ v4「5 巡で
  必ず意思決定」と 4 回改定された。**その時点の規則が満たされた巡は 36 巡 (sentinel の巡
  r54–r82 + 実証ケース 1 = `docs/methodology-case-ledger.md`、ab_probe を新規に作った 7 巡) で
  0 回**。唯一の「2/2 成立」は r60 と r82 — 9 日・22 巡・別規則・
  別 code・test −10 を挟んだ 2 点を対にして数えた
- reviewer は adaptive generator (= 直した先に合わせて次の指摘を生み出す装置) である。08-21 の
  第三者意見書がそう診断し、方法論
  §7.1 も転記したが、その後も r60 以降の指摘 **28 件は全採用** (28/28) — 「品質推定の sample」と
  呼びながら全件を fix queue に入れ、generator に報酬を払い続けた
- r54–r76 の指摘 54 件の性質: 通常運用で効く high **7 (13%)** / medium 13 / exotic 入力
  (= 想定用途では起きない入力) **25 (46%)** / 表層 5 / 過剰実装 4。sub-ns 精度・全角数字・
  RLIMIT_NOFILE=6・/proc の st_size=0 は codex job 監視の運用で起きない。後に過剰実装として
  撤去された late-round fix が 3 件以上ある
- 各巡が fix を要求し、fix は行数を増やす。ケース 1 の中 severity は巡 2〜6 で 1,1,1,1 と減衰ゼロ、
  減っていたのは低 severity の尾。「在庫 (= 過去巡から残る未検出欠陥) 0・指摘の 100% が直前 fix 由来」
  は、発注書だけを渡す diff round なら必ずそう出る恒等式で、4 巡にわたり道具の正しさの証拠に
  使われた。道具本体だけを渡す全体 round 1 巡で在庫 5 件、次で 8 件

### 2.2 process 層 — 失敗 → 規則追加の反射

- 4 部すべてで同じ型: 非ゼロ結果 → 自己帰責の表 → 規則 / 節 / 台帳 / memory を追加 → commit →
  次巡発注。「私は 6 巡ずっと『守る仕掛け』を足していた」と診断した 58 秒後に方法論へ 83 行を
  追加した。**診断した失敗形をメタ層で反復している**
- 規則は次巡の穴を塞がない。巡 3「literal の意味を確認せよ」→ 巡 4 で literal と件数の不一致。
  巡 3「修正行を戻すと落ちる test」→ 巡 4・6 で同 class 再発。方法論 §7.5 の常設節 4 → 巡 7 で 5 つ目の
  欠落 (read-only)。Opus 自身が「5 つ目の別の形が出る確率は高い」と予言していたとおりになった
- tripwire L3「同クラス 3 回目 → 機構化」は 30 巡で **発火 0 回** (alias family 5 巡、errno family
  5 巡を毎巡 1 層 patch)。L4「報告書を版管理へ複写」の直後に r77–r82 の一次資料を worktree
  ごと消失。方法論 §7.2 の 2 方向分析・構造判定列は実証ケース 1 の台帳に存在しない
- 再発を止めた実績は方法論自身が記録している — 機構化 (monotonic 化で 51 巡再発ゼロ)・全数
  突合・funnel (不変条件の検査を 1 箇所に集める)・enumerator (状態 × 遷移を機械列挙する
  meta-test)・受理域の縮小・削除。「注意で閉じた class はゼロ、memory に記録した
  癖は 4 巡後に同型再演」。**方法論の成長の大半 (verdict 6 項目・2 方向分析・上流照合・常設 4 節・
  checklist) は「毎巡書くべき文言」の追加であり、この実績側に一つも入っていない**
- under-specification は消えず発注書へ移動した。方法論の発散機構 M1 (スペックがレビューの中で
  発見されていく) は「スペックをレビューで書かせるのは最も高価な書き方」と診断したが、
  実証ケース 1 は「発注書の欠落を 1 巡 1 件レビューで発見し、次巡の発注書に 1 条ずつ足す」
  過程そのものだった。巡 7 の「契約をコード化」は発注書を code にする試みで、結果は同 class
  再発 — 移動先でも同じ機構が働く
- 依頼と作業のズレ: 提示された 3 案 (名前照合 / A/B 差分 / 変異) はすべて検出強化で、Opus も
  「網を細かくする」と自己申告。ab_probe はその検出器を作る実証ケースとして発注され、それ自体が
  7 巡の loop になった。「この部品は要るか」型の問いは transcript に 0 件

### 2.3 harness 層 — 同じマッチポンプが assistant の行動に

- memory 118 entry のうち、この失敗を予告していた entry は少なくとも 4 件ある — `architecture_
  before_review` (2026-08-21「指摘が乾かない・同 class 反復・fix が機構を足し続けるなら
  レビューを続けるな」)、`self_build_impulse` (「自作圏の品質保証だけで 76 巡」)、
  `threat_model_in_review_order` (「収束しないのは問いが無限だから」)、`control_before_
  mechanism_claim` (「網羅性の語は証跡に拘束する」)。**前 3 件は session 中一度も surface されず
  (tag は一致、retrieval 不一致)、surface された 18 entry も本文を Read した回数は 0**
- 従えた教訓はすべて hook / skill / lint に機構化されていたもの (再現義務・経路強制・見積もり
  宣言)。文章だけの教訓は違反した。教訓の接続力は「memory に書いてある」ことではなく「発話や
  tool 呼び出しの経路上に検問があるか」で決まっている
- 行動が実際に変わった唯一の局面は、ユーザーの中断 + effort max の cross-model 診断 (= 別 model
  による診断。在庫 0 は恒等式 / 中 severity 減衰ゼロ / 根拠なき裁定がバグを凍結) で、memory
  からではない
- gate 群は「検出層を足す」と同じ設計思想で、同じ結果を出している: 摩擦は増え、行動は変わらない。
  Anthropic 自身の Stop hook は 8 回連続 block で強制解除される (公式 doc)。本 repo の gate は
  mention と execution を区別できないまま、発注書を書く行為を 3 回止めた

## 3. 既に手元にあった答え

08-21 の第三者意見書 (`drafts/quality-estimation-opinion-report.md`) の助言と、その後の運用
(sentinel r77–r82・実証ケース 1) での採否:

| 助言 | 採否 |
|---|---|
| finding round は read-only、直さず品質推定表へ | 文言のみ。ケース 1 は 7 巡とも per-finding fix、推定表は存在しない |
| bounded-risk 受入 (既知 U0 ゼロ + 残余台帳 + 凍結) | 文言のみ。選ばれた例なし。r76 後は 6 巡 + 3 round 続行 |
| 停止規則を charter (= reviewer に何を疑わせるかの委任範囲) × severity × 時間箱へ | charter のみ (意見書より前)。時間箱の実値は doc のどこにも無い |
| self P0 が出たら rollback・縮小 | 文言のみ。rollback 0 回 |
| Round 3 は別 reviewer + charter から機械抽出した scenario | 文言のみ。ケース 1 は全巡同じ opus subagent |
| 入場条件 (severity 定義・予算) を確定してから round 1 | 文言のみ。ケース 1 は severity 定義と token 予算が未合意のまま開始 |
| Round 1 に過去 finding を渡さない | **逆方向に採用** — 裁定 catalog を先渡し、ケース 1 は発注書だけを渡して恒等式を作った |
| fix 型の優先順 (仕様縮小 > 削除 > 集約 > 新機構) | 運用でも採用 (唯一定着) |
| strangler 型、全面 rewrite は不要 | 採用 (意見書以前から同方針) |

つまり答えは 08-21 に文書化され、方法論に転記され、運用は変わらなかった。08-26 の
第三者意見書 (`drafts/loop-exit-opinion-order-report.md`) も同じ診断で、違いは「凍結でなく
小さく書き直せ」の 1 点 (§5.2)。

## 4. 文献との照合

**LLM の自己修正 loop は巡を重ねると劣化する。**
Olausson 2023 (arXiv:2306.09896): 修復の深さより初期標本の幅、10 repairs/sample は無修復の
0.97x。Huang 2023 (arXiv:2310.01798): oracle なし自己修正は巡ごとに劣化 (GPT-4 GSM8K
95.5 → 91.5 → 89.0)。Stechly 2023 (arXiv:2310.12397): verifier は正解 40 件中 39 件に欠陥を
幻視、原因は「正確な停止条件の欠如」。Song 2026 (arXiv:2603.12123): 同 context の 2 回目
レビューは 1 回目と差なし (p=0.11)。Arimbur 2026 (arXiv:2604.10508): 2 巡で改善の 76–95%。

**人間の code review は「指摘ゼロ」で止めない。**
Google eng-practices (google.github.io/eng-practices): 完璧でなく「code health の純改善」で
approve、Nit は無視可、100 行が妥当・1000 行は大きすぎる。Sadowski 2018 (ICSE-SEIP): 変更の
80% 超が反復 1 回以下、中央値 24 行。Bacchelli & Bird 2013 / Czerwonka 2015 (Microsoft):
指摘のうち欠陥は 14–15%。Cohen/Cisco: 200–400 行・60–90 分が有効域、400 行/時超では 87% が
平均以下。Yin 2011 (FSE): fix の 14.8–24.4% が誤り。Mockus 2000: 失敗確率の FIX 係数 0.60。

**検証は指摘数でなく仕様接地と変異で測る。**
Google mutation testing (2018 ICSE-SEIP / arXiv:2102.11378): raw 変異指摘の 85% は
unproductive、mutation score を目標にしない、diff 単位・changelist あたり中央値 7 件。
Anthropic Claude Code best practices (code.claude.com/docs/en/best-practices): 「gap を探せと
言われた reviewer は健全でも指摘を出す。全部追うと over-engineering。correctness に効く
指摘だけ採用」「pass/fail を返す check を停止条件に」「同じ件で 2 回超なら /clear」。
He 2025 (arXiv:2506.18315): 実装と test の cycle of self-deception。Haeri 2026
(arXiv:2607.06636): 仕様を渡した tester は 27/30、なしでは 2/30 — test 予算倍増でも届かない。
Spolsky 2000 / Fowler strangler fig: 全面 rewrite への歯止め、seam を切って小さく置換。

本件はこれらの否定形を全部踏んでいる — 8,588 行を一括で回し、同系 reviewer を 7 巡回し、
指摘 (欠陥 13%) を全採用し、fix (誤り 15–24%) を毎巡重ね、停止条件を reviewer の沈黙に置いた。

## 5. 出口 — 何を変えるか

### 5.1 停止条件を置き換える

出荷条件は次の 3 つだけ。「指摘ゼロ」は条件から外す。

1. **発注側が実装前に書いた受け入れ test が全通過。** 実装者は test を足せるが、採否用の
   oracle を変更・削除できない
2. **発注側が実装前に固定した変異 4 種の生存 0/4。** 不正 byte の置換 / timeout 境界の反転 /
   marker・counter の増減 / path 正規化の除去 — 実装 file の機械列挙ではなく、契約に対応する
   固定変換を発注側の copy に当てる。実装者が変異集合を選ぶと方法論の発散機構 M4 (実装者が自分の検証を
   設計する) が再演する (巡 7「71/71 kill」
   の自己申告が誤りだった)
3. **context 遮断の独立レビュー 1 巡 (全体 round・道具本体のみ) で、用途内 P0 が無い。**
   reviewer には「correctness と要件に効くものだけ」を求め、それ以外は直さず、転記もしない。
   reviewer の報告書 file がそのまま記録であり、行動を伴わない転記は積み上がるだけで読まれない

巡は最大 3: 基準品質 (read-only) → class 単位の fix 1 回 → 独立再確認 1 回。再確認で P0 が出たら
4 巡目は回さず、縮小 / rewrite / bounded-risk 受入のいずれかを人間が選ぶ。

### 5.2 artifact の処遇

| artifact | 処遇 | 根拠 |
|---|---|---|
| `codex_task_sentinel` 8,588 行 | **要件から小さく書き直す** (2026-08-26 決裁)。旧版は書き直し版が配備されるまで凍結 — r77 以降を回さない、patch しない | 要件は数行。認定 23 巡で通常運用の high は 7 件、以後は exotic と過剰実装。第三者意見書の見積もりは 3 部品 (reader / poll と終端分類 / CLI adapter)・production 120–220 行・test 80–150 行。14 exit code と TOCTOU 防御を持ち込むならこの見積もりは成立しないので、契約 (10〜30 行) に無いものは入れない。§5.1 の protocol で最大 3 巡 |
| `claude_ab_probe` 810 行 | **廃棄** (worktree ごと、2026-08-26 決裁) | false negative を抱え未 merge、配備先で selftest 必失敗。要件 (2 版の出力 diff) は数十行で足りる。両意見書一致 |
| 方法論 509 行 | **本当に有効な最小限へ書き直す** — §5.3 の 6 項目 (2026-08-26 決裁) | 現行 509 行版は git 履歴に残る |
| 台帳・分析 3,434 行 | **凍結** (追記禁止)。再発防止は LLM が台帳を書く工程そのものを方法論から消すこと | 台帳は `docs/` の分析文書 3 本 (todos.md ではない)。LLM が台帳を書く時間が product を上回った。巡ごとの件数は reviewer の報告書 file から script が数え、LLM は台帳 prose を書かない。todos.md も同じ病 (983 行、経緯 prose が大半) だったので 2026-08-26 に起票 / Goal / Exit Criteria だけの形へ戻した |

### 5.3 最小の方法論 (残す 6 項目)

1. 実装前に発注側が 10〜30 行の契約 (目的・用途内外・入出力 / exit・不変条件・所有点) と
   受け入れ test と変異 4 種を書く。書けなければ発注しない。既存正本を先に読む
2. 不変量が複数 site に配られる、または状態 × 遷移を列挙できないなら、funnel / enumerator を
   先に作るか用途を縮小する。局所 patch は発注しない
3. 初回レビューは read-only の品質推定。finding は class 化し、処置は 仕様縮小 → 削除 → 既存
   primitive への集約。新機構は fix ではなく別発注
4. fix は 1 回。同 round に発注側の failing repro・変異器・独立 reviewer を入れる。自己申告と
   test 本数は証拠にしない
5. 採否は用途内 P0 と変異の生存数で決める。緑と指摘総数は補助記録
6. 最大 3 巡で止める。非ゼロなら patch を継ぎ足さず、縮小 / rewrite / bounded-risk 受入を選ぶ。
   この文書と方法論への追記は禁止し、削除のみ許す

### 5.4 prevention の実体 — 触る量を減らす

5 巡連続で近因が発注書だったのは、発注書が毎巡 180 行の新しい仕様を書いていたからである。
書く量を減らせば書き落としも減る。数字は文献の実測に合わせる:

- 発注書 ≤ 60 行 (契約 + scope + 禁止事項。再現手順の無い裁定は書かない)
- レビュー単位 ≤ 400 行 (Cisco の有効域)、fix diff ≤ 100 行 (Google の妥当域)。超えたら
  実装ミスでなく設計ミスとして戻す
- fix は削除・縮小のみ。注入ゼロだった fix 巡 (`docs/injection-corpus-baseline.md` の review-gates
  fix 12・sentinel fix 8・実証ケース 1 の巡 6) はすべてこの型だった
- `docs/injection-prevention-proposal.md` の候補 7 件の採否: 契約コード化 (入口に限定して採る) /
  削除第一 (採る) / 変異生存数 (発注側所有で採る) / 既存集約回避・一般形の報告・表面積の報告・
  裁定への再現手順義務 (捨てる — 相関のみ、または実績なし)

### 5.5 meta 作業の予算

- docs / todos の commit 数 ≤ product の commit 数 (同 session)
- 台帳は LLM が書かない。巡ごとの件数は script が報告書 file から数える。方法論・台帳への追記は
  禁止、削除のみ。直さない指摘は転記しない
- 失敗に対する反応で「規則・節・entry を足す」を選ぶ前に、先に何を消すかを 1 行書く

### 5.6 判定指標

- 納品ごと: 発注側の固定 4 変異の生存 **0/4**。1 件でも生き残ればその納品は受け入れない
- approach 全体: 次の新規 tool 1 件が **3 巡以内に出荷** (§5.1 の 3 条件) し、**出荷後 2 週間の
  実運用で用途内 P0 が 0**。達成できなければ敵対的レビュー loop という approach 自体を捨て、
  受け入れ test + 独立レビュー 1 回のみに戻す。巡数と規則を足して延命する選択肢は事前に除外する

## 6. 次 session の最初の 3 行動

1. `wt-abprobe` を削除し、sentinel の書き直しに向けて発注側が契約 (10〜30 行)・受け入れ test・
   固定 4 変異を先に書く。旧 sentinel には触らない
2. 方法論 doc を §5.3 の 1 ページ版に置換し、台帳 3 本に「凍結・追記禁止」を注記する
3. 次の小さな実案件 1 件を §5.1 で回し、§5.6 の指標で判定する

この文書自身への注意: 規則を足す文書ではなく減らす文書である。次に足すべきものが出たら、
先に何を消すかを書く。
