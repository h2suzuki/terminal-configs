# スキルと自動チェックの仕組み

このリポジトリには、Claude（私）の受け答えの信頼性を高めるための2種類の仕掛けがある。1つは行動規則をまとめた「スキル」、もう1つはそれを下支えする「自動チェック」。本書は前半でその全体像を専門用語なしで説明し、後半に実装時に繰り返し使う型をまとめる。

## なぜ自動チェックが要るか

スキルは、私が「今この場面はこのスキルだ」と自分で気づいて呼び出すことに頼っている。だが人間と同じで、必要な場面で必ず思い出せるとは限らない。そして思い出せなければ、そのスキルは無いのと同じになる。実際、必要なスキルを呼び忘れる失敗が繰り返し起きた。

そこで方針を決めた。**機械が自動で見分けられる場面については、私の記憶に頼るのをやめ、仕組みの側で「気づかせる・止める・思い出させる」**。思い出せる確率を上げようと頑張るのではなく、頼らずに済む所は頼らずに済ませる。この考えで作った4つの仕掛けが L1〜L4 で、「いつ動くか」で性格が分かれる。

## 4つの仕掛け（L1〜L4）

各仕掛けを「動機（どんな失敗を防ぐか）／仕組み（いつ・何を見て動くか）／狙う効果」の3点で並べる。

| 仕掛け | 動機 | 仕組み | 狙う効果 |
|---|---|---|---|
| **L1**（編集の直前） | 編集前に開くべき手引きを呼び忘れ、自己流でファイルを書き換えてしまう | 私がファイルを書き換えようとした直前に動く。その種類のファイルに必要な手引きを今開いたか確かめ、開いていなければ編集を止める | 編集の前に、必ずその場に合った手引きを開かせる |
| **L2**（質問の直前） | 自分で決められることまで二択にして相手へ丸投げしてしまう | 私が確認・二択の質問を出そうとした直前に動く。「自分で決められないか」を点検する手引きを開いていなければ、質問を止める | 安易な判断の丸投げを防ぐ |
| **L3**（返事の直後） | 根拠なき言い切りや、未整形のコマンドを地の文に出してしまう | 私が返事を書き終えた直後に動く。私の文章を見て、根拠なき「網羅した」式の断定や、コピペ用に整えるべきコマンドの裸書きを指摘する | 出してしまった悪い書き方を、その場で気づいて直させる |
| **L4**（答える直前） | 相手の不安や訂正を、ただ安心させて流したり、記録し損ねたりする | 相手が発言した直後・私が答える前に動く。発言中の不安・訂正のサインを見て、「安心で覆わず実態を照らす」「訂正を記録すべきか考える」構えを耳打ちする | 答える前に、その場面に合った構えを取らせる |

### 補足：L3 と L4 はどう違うか

似て見えるが向きが逆である。**L3 は事後** — 私が**書いた後**の文章を見て指摘する。**L4 は事前** — 相手が**発言した直後・私が答える前**に構えを促す。動くきっかけ（私の文章か、相手の発言か）も、見る対象も違うので、片方でもう片方の仕事はできない。

### 補足：止める力には段階がある

L1・L2 は行動そのものを**止められる**。「編集」「質問」という、機械が確実に見分けられる行動だからだ。一方 L3・L4 は**止めず、指摘・耳打ちにとどまる**。受け答えの良し悪しは文章の見た目だけでは確実に判定できず、無理に止めると正しい返事まで巻き込んでしまう。**確実に見分けられる場面ほど強く介入し、判断が要る場面ほど軽く促すに留める** ——これは意図的な段階分けである。

### 具体例

- **L1**：フックの `.py` を直す前に、コードの手引きを開かずいきなり編集に入る → L1 が編集を止める → 手引きを開いてから編集が通る。
- **L2**：「ログ出力は JSON と text どちらにしますか?」と相手に聞こうとする → L2 が「自明な既定があるのでは?」と点検を促し、質問を止める → 自分で JSON と決めて進める。
- **L3**：デプロイ手順で「お手元で sudo cp … を実行してください」とコマンドを地の文に裸書き → 返事の直後に L3 が「独立したコード枠に入れて」と指摘する。
- **L4**：相手が「この設計、本当に大丈夫? 心配なんだけど」と言う → 私が答え始める前に L4 が「安心させて終わらせず、実態を照らして答えよ」と耳打ちする。

---

## 実装 contract（技術者向け）

L1〜L4 と兄弟フックが共有する**実装の再利用パターン**。新しいフック / skill を作るときの一貫性のため。各項は具体例として実フック名を挙げる。deploy の決まりは contract でなく別物ゆえ末尾の「除外」を参照。

### 0. 二つの contract family

| family | event | 動き |
|---|---|---|
| **Gate**（L1 `skill_reminder_gate` / L2 `declare_and_proceed_gate`） | PreToolUse | capability を確認し、無ければ行動を **deny で止める** |
| **Detection**（L3 `stop_checks` / L4 `memory_surface` の `_concern_inject`） | Stop / UserPromptSubmit | pattern を検出し **warn / inject で促すのみ**（止めない） |

両 family は以下 1〜5 の共通機構を組み合わせて作る。

### 1. capability-grant（skill ↔ hook 協調の中核）

- **mint と check を分離する**: skill 発動（または `declare` CLI）が「この turn この対象を編集/質問してよい」という capability を **mint** し、フックは `required ⊆ active` を **check** するだけ。正規ルート（skill → 同 turn で行動）は通り、skip = detour は deny。
- **真実源は sniff でなく宣言**: 拡張子なし file 等で kind を機械推定できないときは model の `declare` を真実源にする。deny が語彙を提示し model が選ぶ。
- **declare は追加のみ**（auto-detect を下回れない）: `.py` を `else` 宣言して gating を無効化する穴を塞ぐ。
- 起源は `memory_routing_gate`（memory への Write を skill 経由に強制）。L1 が編集、L2 が質問へ一般化した。

### 2. 判定の返し方（permission / output semantics）

- **deny は JSON、exit 0**: `{"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":...}}` を stdout に出して exit 0。exit 2 でなく JSON にするのは、フックの bug が誤って tool を block しないため（fail-open と整合）。
- **output 省略 = そのまま通す**（passthrough）。`allow` を明示すると以降のフック / permission を skip する（意図せぬ auto-approve）ので、通すときは原則何も出さない。
- **channel は event ごとに違う**: PreToolUse は `permissionDecision`。UserPromptSubmit は `additionalContext`（model 可視）— fullscreen TUI は UPS の `systemMessage` を塗らない未文書 gap があるので additionalContext が確実。Stop は exit 2 / `decision:block` の 2 つだけ（additionalContext 非対応）。

### 3. trigger の検出（input contract）

- **transcript の current-turn scan**（`stop_checks` / `skill_reminder_gate`）: 直近の human-input user entry を境界に、それ以降（＋任意で直近 N 秒）の assistant entry を見る。境界判定が load-bearing — `isMeta`（skill 展開 injection）は除外、content が str または非 tool_result block を含む list は境界、全 tool_result は継続。境界が取れない corrupted transcript は None → fail-open。
- **prompt 直取得 + synthetic re-entry skip**（`memory_surface`）: UserPromptSubmit は `payload["prompt"]`（str）。`<task-notification>`（dynamic workflow 完了）や `This session is being continued`（compaction 継続）で始まる合成 prompt は skip。
- **phrase pattern 規律**（L3 / L4）: precision-over-recall（noisy なフックは net-negative）。実 transcript で FP/FN を corpus 実測してから採否を決め、盲目の bare-substring を避ける。module-level で 1 回 compile する。
- **extensible dispatch table**: `KIND_SKILLS` / `CODE_EXTENSIONS` / `LANGUAGES` のように kind・言語 → skill を table 1 行で拡張する。未実在の言語は持たない（要るとき 1 行足す）。

### 4. 状態の持ち方（cross-invocation state）

- **session-keyed state**: `$CLAUDE_CODE_SESSION_ID`(env) == payload `session_id`（実証済）。これで `declare`(Bash) とフック(gate) が同 session を共有する。state は session_id でキーする。
- **path は絶対 path で keying**: gate は payload cwd、declare は shell cwd で解決するので、相対 path だと cwd drift で hash 不一致 → 永久 deny loop。絶対 path 必須。
- **TTL は use-case 駆動で選ぶ（盲目流用禁止）**: skill-active = 現 turn ∪ 5 分（guidance は invoke した turn の context にある）/ memory-surface = 900s（同 entry の 15 分掃除）/ L4 = 900s × channel（debugging 往復での再 inject 抑止）。同じ理由で `memory_routing` の 1hr grant を skill-active に流用するのは誤り。
- **throttle 機構の多目的再利用**: L4 は memory-surface の inject_log throttle を sentinel key（`<L4-concern>` 等）で流用し、schema 変更ゼロで channel ごとの抑止を得た。
- **PostToolUse で derived state を同期**: `read_before_edit` の `record` mode が PostToolUse(Read/Write) で「読んだ」事実を state に追記し、PreToolUse gate がそれを読む。派生 index は `memory_surface --upsert` で同期する。
- 放置 state は self-prune（`skill_reminder_gate` は 7 日で session dir を掃除）。

### 5. 安全側への倒し方（robustness）

- **fail-open**: 全例外を exit 0 で握り、enforce 不能（transcript 読めない / 境界 None / DB 不能）なら通す。enforcement の glitch で user 作業を止めない。止めるのは確証があるときだけ。noise-dominant なフックでは DB 不能時は inject せず drop（unthrottled spam を避ける）。
- **deny-wording 規律**: (1) フックを変更主体に誤読させない（「hook 自身は file を変更しません」と明示）(2) deny 解除条件と次回回避の corrective 行動を reason に書き下す (3) そのため意図的に冗長 — inline コメントで「trim 禁止」と意図を残す。
- **advise-once**: 同 turn の `stop_hook_active` retry を pass に降格し、自己 block loop を断つ。turn counter の once-per-turn 不変条件（cross-hook で load-bearing）を壊さない。

### 除外: deploy ルールは contract でない

`copy_dir` の自動展開・exec-bit 0755・settings の `copy` / `managed-settings.json` 配置は、本 contract ではなく **deploy ルール**である（`writing-bash` / `writing-python` の exec-bit rule と deploy script が所掌）。種類が違うので本書に混ぜない。
