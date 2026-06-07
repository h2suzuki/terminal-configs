# スキルとフックの実装パターン

この文章は、本レポジトリに含まれる Claude Code Skills と Hooks の実装パターンについて解説します。

--------

## Skills

Claude Code に守らせたいルールや手順を文章化します。Anthropic では９カテゴリーで利用を推奨しています。

Categories:

1. Library and API reference: explain how to correctly use a library, CLI, or SDKs
2. Product verification: describe how to test or verify that your code is working
3. Data fetching and analysis: connect to your data and monitoring stacks (IDs, field names, query patterns)
4. Business process and team automation: automate repetitive workflows (multiple tool calls) into one command
5. Code scaffolding and templates: generate framework boilerplates for your codebase
6. Code quality and review: enforce code quality and help review code according to your knowledge and methodology
7. CI/CD and deployment: help you fetch, push, and deploy code safely
8. Runbooks: take a symptom (error signatures), walk through a multi-tool investigation, and produce a structured report
9. Infrastructure ops: perform routine maintenance and operational procedures with safety guardrails

引用: https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills


### SKILL.md の書き方

本レポジトリのスキルは、次のスタイルを規定しています。

#### Frontmatter

英語で書きます。 日英の中途半端な mix は避けます。
Frontmatter はセッションのコンテキストに乗るので `description` / `when_to_use` は簡潔に書きます。

必須フィールドは 3 つ。

1. `name` — skill 識別子 (kebab-case)。 ディレクトリ名と一致させます
2. `description` — skill が何をするかの 1 文。 常時の skill 一覧に表示されます
3. `when_to_use` — 発火条件。 `TRIGGER when ...` と `SKIP when / for ...` を必ず両方書きます。 片方だけでは曖昧で、 誤発火・不発火を招きます。 trigger に埋め込むキーワードは、 引用符付きの日本語 (例 `"網羅した"`) を許容します。 この列挙では具体フレーズを引用します。 一般化しすぎると発火しません。

任意フィールドは、必要な skill だけが保有します。

- `argument-hint` / `arguments` — invocation 引数のヒントと引数名
- `context: fork` / `agent: general-purpose` — fork (subagent) 内で実行し、 main session の context を持たせない場合に付けます
- `paths` — 編集中ファイルでの auto-load 化。 ただし付けると skill 一覧・`/name`・Skill tool から description が外れて不可視になる副作用があるため、 真にパス限定が要る時だけ使います
- `disable-model-invocation: true` / `user-invocable: false` — それぞれ model から不可視・user から不可視。 意図しない限り付けません


#### 本文

見出しは英語で書きます。 本文は日本語で書けます。

次の構成とします。

- 冒頭は `# <Title Case のスキル名>` の H1 見出し
- 防ぎたい失敗の説明 1 段落
- ワークフローを定義する `##` の H2 見出し (以下の順番)
 1. `Process`
 2. `Rules`
 3. `Output`
 4. `Related`

`Related` では隣接 skill をシンボリックに引用し (例 `writing-code`)、 重複や直交する scope を明示して family 化します。

本文から、このレポジトリのデプロイ先がカバーしないファイル・skill ディレクトリ外のファイル・会話文脈の単語を入れてはいけません。デプロイ先マシンに開発マシンのファイルや会話は存在しないからです (宙吊り防止)。


### スキル一覧

本リポジトリのスキルは大半が LLM の行動規律（ガードレイル）です。上記 9 カテゴリーは開発タスク向けの分類なので綺麗には収まりません。各スキルには最も近い番号を当てています。

#### attribute-existing-issues (Category 6)

永続テキスト（commit message・memory・doc・SKILL.md 等）で誤ったパターンを説明するとき、「既存」「引き継いだだけ」等の表現で当セッションの関与をぼかすのを禁じます。自分が何をしたかを正直に書かせます。

#### auto-mode-denial-recovery (Category 8)

auto モードで tool 呼び出しが拒否されたとき、settings.json に権限を足しても classifier の gate は迂回できない、という誤解を正します。有効な復旧は手動実行・skip・ユーザーへの再依頼だけだと示します。

#### claude-md-lint (Category 6)

起動時に自動ロードされる CLAUDE.md チェーン（org / user / project と @-import）を lint します。System Prompt との重複・ファイル間の矛盾・曖昧なトリガーを検出し、CLAUDE.md を小さくタイトに保ちます。

#### commit-discipline (Category 7)

commit の粒度・タイミング・保留判断を LLM 自律で行い、毎回ユーザーに可否を聞かないようにします（cheap & reversible なため）。push・force・reset --hard 等の破壊的操作だけは許可を要求します。

#### debug-guardrail (Category 8)

「動かない」「失敗した」系の不可解な現象に対し、2-3 個の仮説をコード／ログで裏づけて artifact レベルの修正に着地させます。修正がバグと代数的に同一でないか検証してから確定します。

#### declare-and-proceed (Category 4)

素材があり妥当な既定があるなら、ルーティングや細かい選択を自分で決め、AskUserQuestion や散文の二択でユーザーに丸投げしないようにします。人手（HITL）の往復を減らします。

#### document-editor (Category 6)

README・公開 doc・spec・設計書などの永続成果物を fork（subagent）内で編集します。編集前に意図を verbalize し、本体は fork で書き戻して main には変更サマリだけ返すことで、context の肥大を防ぎます。

#### handoff (Category 4)

セッション境界で、固定スキーマの引き継ぎドキュメントを生成し、次の自分が 5 分で再開できるようにします。「handoff して」「終わります」等の終了合図で発動します。

#### illuminate-not-reassure (Category 4)

ユーザーの懸念に、安心の言葉や一見正しい説得で蓋をせず、(1) 核心を言い直し (2) 可能性を本気で深掘り (3) 実機構と状態を中立に晒す、の 3 段で応じます。解決は実態を照らすことから生まれます。

#### intent-preserving-rephrase (Category 6)

CLAUDE.md・spec・SKILL.md 等を言い換え／翻訳するとき、意味を厳密に保ちます。否定形→肯定形の変換は同義になる時だけ行い、指摘箇所だけでなく同種の変換を全て自己監査します。

#### lost-track-recovery (Category 8)

長い作業で現状を 1 文に言い直せない（lost track の signal）状態を検知し、タスクの現在地を立て直します。describe-back 不能をリカバリの起点にします。

#### make-plan-before-coding (Category 4)

実装に入る前に、設計空間の探索・合意・根拠の継承を揃えます。research 後に本格的な Edit を始める前や、既に文書化済みの選択を蒸し返す前に発動します。

#### memory-routing (Category 4)

memory entry の保存先（user か project-local か）・世代（MEMORY.md か OLD-MEMORY.md か）・保存タイミング・日付書式を判断します。skill / hook / CLAUDE.md で cover された entry は OLD へ退役させます。

#### provide-user-instructions (Category 4)

ユーザーが手で実行するコマンド（host 側の cp・git push・curl 等）を、地の文に混ぜず、完全パスでコピペ即実行できる独立コード枠で提示します。

#### rejection-via-actual-cost (Category 6)

設計案を却下する根拠を、採用時に増える実コスト（部品数・LoC・IO・既存経路との重複等）で論じます。「実機検証が要る」等のやれば済むコストを却下理由にしません。

#### report-by-evidence (Category 6)

判定・推奨・結論・規模／影響評価を述べる前に、公式情報・コード・文書・設定を必要範囲で読み、根拠を示します。読んでいなければ「未確認」と明言します。

#### scope-mismatch-detector (Category 6)

過去のルール／経験／skill を別状況に再利用する前に、trigger と scope の一致を検証します。過剰適用と過少適用の両方（LLM の calibration error）を補正します。

#### skill-and-hook-extraction-workflow (Category 4)

CLAUDE.md のルールを hook／skill へ抽出する反復作業の進め方を定めます。実装→smoke→ペア commit→背景レビューの spawn→次項目を並行→idle で triage→fixup、の流れです。

#### subagent-gate (Category 4)

subagent を spawn する前に、4 条件（並列化可能・大出力・3+ query 探索・専門領域）のいずれかが成立するか確認します。spawn overhead に見合わない小さな lookup では使いません。

#### verbalize-before-action (Category 6)

判定・推奨・影響評価を、行動の前に 1 文で言語化して自己反証してから動きます。暗黙の意図推測に頼らないための代替手段です。

#### verify-before-claim (Category 6)

肯定主張（「網羅した」等）・否定断定（「できない」等）・実行可能成果物の暗黙の done 報告の前に、一次情報・実コード・参照先を自分で直接 verify します。確認できなければ scope を明示します。

#### writing-code / tests / bash / python / skills / todos (Category 6)

コード・テスト・bash・python・skill・todos を書く際の規約集です。writing-code が全言語共通の土台で、言語別 add-on（bash / python）やテスト・skill・todos の規約がその上に積み重なります。


--------


## Hooks

フック利用の概観を列挙します。


### セッション

セッションに関わるフック利用について説明します。


#### SessionStart

**Claude Feature Research**

1. SessionStart で、`claude --version` と findings.md 先頭の version を比較し、古ければ／無ければ background で findings.md を再構築する（hook 自身は何も注入せず即リターン）
2. Claude Code の機能に言及すると、複数のスキル (verify-before-claim 等) が findings.md 参照を指示
3. LLM cut-over 後の最新仕様を把握して設計に生かす

Related: `feature_findings_build.py`

**コンテキスト引き継ぎ**

1. ユーザーの「セッションを終わります」「セッションリセットします」といった言葉で /handoff スキルが発動
2. /handoff がセッションの最終状況を transcript log に出力
3. 新規／clear 起動時の SessionStart で、同じプロジェクトの以前の transcript logs の最後を数ターン分読み、additional context に注入して再開をスムーズにする

Related: `session_resume_context.py`

**CLAUDE.md Linter**

1. SessionStart で、CLAUDE.md の３レイヤー（managed / user / project）と @-import を読み、lint 対象を集める
2. Recursive Entrance Guard: この後 claude background session を作るので、再入しないようにロックファイルを掴む（掴めなかったら再入扱いで即 exit）
3. claude --bg .... で、background session スタート → Hook script は直ちにリターン
4. Background session の Haiku が、CLAUDE.md に重複や矛盾がないかチェック、System Prompt とも比較
5. Background session は結果をファイルで返却
6. 次の UserPromptSubmit で結果ファイルを拾い Background session reap

Related: `claude-md-lint.sh`


#### SessionEnd

**セッション一時ファイルの掃除**

1. SessionEnd で、 他のスクリプトが生成する Session 作業ファイル／状態ファイルを削除: statusline cache, turn counter など
2. マシン電源断などで SessionEnd が呼ばれず消されなかった作業ファイル／状態ファイル（7日以上古いもの）を見つけ orphan reap

Related: `session_cleanup.py`


### ターン

ターンに関わるフック利用について説明します。

#### UserPromptSubmit

**過去事例の強制想起**

1. UserPromptSubmit で、プロンプトから過去事例を検索
2. マッチした事例のファイルパスと、事例に紐付く reminder ノートを additional context に挿入して案内
3. LLM は、その事例を繰り返さないように回避行動をとれる

Related: `memory_surface.py`

**ユーザーの懸念 → 事実の深掘りへ誘導**

1. UserPromptSubmit で、ユーザーの懸念フレーズ (心配 / 大丈夫? / 壊れない? 等) をキャッチ
2. 事実を深掘る illuminate-not-reassure スキル を additional context に挿入して案内
3. LLM は、ユーザーを説得して懸念を覆うのではなく、事実を深掘りして懸念の根源に手当てする

Related: `memory_surface.py`

**繰り返す訂正指摘の永続メモリ化**

1. UserPromptSubmit で、ユーザーの訂正フレーズ (そうじゃない / 何度も指摘 等) をキャッチ
2. memory-routing スキルを additional context に挿入して案内
3. LLM は、このやりとりを事例として永続メモリ化
4. 次回以降の UserPromptSubmit で、類似プロンプトからこの事例を検索 HIT → 事前に案内

Related: `memory_surface.py`

**未コミットの取りこぼし防止**

1. UserPromptSubmit で、ユーザーのセッション終了示唆（お疲れさま / 終わります 等) をキャッチ
2. `git status` を確認し、 未コミット変更があれば件数とパスを additional context で提示
3. 終了の合図で警告

Related: `handoff_uncommitted_check.py`

**サブエージェント委譲の助言**

1. UserPromptSubmit で、プロンプトに sweep / 並列 / 複数対象 等のパターンをキャッチ
2. Subagent に適する条件か検査し、適するなら additional context で示唆
3. LLM は、漫然と Tool を連発する前に、委譲を一度 verbalize する機会をえる

Related: `subagent_gate_suggest.py`

#### Stop

**自己解決できる質問の却下・不適切な発言の自動訂正**

1. Stop で、このターンの最後の発言（`last_message`）と transcript を抽出する
2. 確度の高い悪パターン — 根拠なき評価語・空虚な宣言・自分の成果を他人に帰属・A or B 等の自己解決できる質問など — は exit 2 / decision:block で却下し、書き直しを促す
3. 判断を要する型 — 先送り・証拠なき主張・地の文での手順裸書きなど — は警告にとどめる。advise-once で同ターンの再試行は通し、自己 block loop を防ぐ

Related: `stop_checks.py`

**push 催促の却下**

1. Stop で、 `push_prompting_check` がこのターンの assistant 発言を走査し、 push を提案／確認／予定告知するフレーズ（「push しますか?」等）を検出する
2. 命中したら exit 2 で却下し、 該当発話を取り消して再応答するよう stderr で促す
3. git push は user 指示を待つ規律 (commit-discipline / push silence) を機械的に担保する

Related: `push_prompting_check.py`

**応答待ちの音声催促**

1. Stop で、 voicevox_claude_alerts が最終発言の末尾文を取得し、 末尾が「？」または「?」(全角・半角の疑問符) の時だけ発話対象とする
2. 短い和文はそのまま、 長文や英単語入りは Haiku でカタカナ要約してから読み上げ
3. 画面を見ていない相手が応答待ちを取りこぼさないよう耳で知らせる (バックグラウンド session は沈黙)

Related: `voicevox_claude_alerts`


### ツール

ツール利用に関わるフック利用について説明します。

#### PreToolUse

**スキルを飛ばした行動の矯正 (capability-grant)**

1. skill 発動 (または `declare` CLI) が「この対象を編集/質問/メモリ書き込みしてよい」という capability を発行 (編集・質問は当 turn ∪ 直近 5 分の窓、 メモリ書込は対象 path の grant を 1 時間鮮度で判定 — turn 概念は持たない)
2. PreToolUse でフックが capability の有無を確認し、 無ければ却下 — `skill_reminder_gate` がコード編集を、 `memory_routing_gate` (guard) がメモリ書き込みを、 `declare_and_proceed_gate` が AskUserQuestion を gate
3. 正しい kind を declare しスキルを通れば編集が通る。 発火依存をやめ、 スキルのルールに沿わせる

Related: `skill_reminder_gate.py` `memory_routing_gate.py` `declare_and_proceed_gate.py`

**読まずに編集を防ぐ**

1. PreToolUse で、 `read_before_edit` (check) が編集対象の最新 mtime に一致する Read 記録を要求
2. 未読なら「未 Read」、 読後に内容が変わっていれば「内容が変化」を理由に却下 (Read 自体は止めない)
3. ディスク上の最新内容を見ずに書き換える盲目編集を塞ぐ

Related: `read_before_edit.py`

**宙吊り参照のブロック**

1. PreToolUse で、 `dangling_ref_check` が永続ファイルへの new content を走査
2. deploy 範囲外のパスや ephemeral タグ (Plan X / Phase α 等) を見つけたら却下し、 inline 化やタグ削除を指示
3. 再 deploy や時間経過で参照が宙吊りになる regression を防ぐ (意図的記載は `dangling-ref-check: allow` で opt-out)

Related: `dangling_ref_check.py`

**コメントへの経緯混入を防ぐ**

1. PreToolUse で、 `comment_rationale_gate` が new content のコメント行だけを抽出
2. 「以前は」「移行用」等の経緯マーカーに命中したら却下し、 経緯は commit message へ寄せるよう誘導
3. コードの進化と乖離して未来の読み手を誤誘導するコメントを残さない

Related: `comment_rationale_gate.py`

**commit 規律**

1. PreToolUse:Bash で、 `deny_compound_git_add` / `deny_compound_git_commit` が `git add` / `git commit` の compound 形 (`&&` 等) を却下し、 staged 状態を確定させてから後続 gate へ渡す
2. `check_commit_format` が subject を `<area>: <Capital>` 形式で検証し、 72 字超または形式不一致は却下、 50 字超 (51-72) は soft warn で通す (`-F`/`--file` は内容到達不能ゆえ却下)
3. `check_commit_author` が effective な user.email を期待値と照合し、 別人名義の commit を阻止

Related: `deny_compound_git_add.py` `deny_compound_git_commit.py` `check_commit_format.py` `check_commit_author.py`

**cwd 汚染の予防**

1. PreToolUse:Bash で、 `avoid_cd` が行頭の `cd` を検出
2. ブロックはせず、 絶対パス・`git -C`・`pushd`/`popd` への置換を additional context で提案
3. cwd drift で後続コマンドが突然失敗する事故を未然に減らす

Related: `avoid_cd.py`

**サブエージェント乱発の助言**

1. PreToolUse:Task|Agent で、 `subagent_gate_warn` が prompt・agent 種別・description を機械的に検査
2. 単一 Read / 単一 grep 相当の軽い spawn と判定したら、 subagent-gate の 4 条件のどれに該当するか verbalize せよと助言 (却下はしない)
3. spawn overhead が見合わない委譲を抑え、 直接実行の安い経路へ誘導

Related: `subagent_gate_warn.py`

#### PostToolUse

**読んだ事実の刻印 (読まずに編集を防ぐ、の後段)**

1. PostToolUse:Read|Write で、 `read_before_edit` (record) が読んだ範囲 (Read は offset/limit、 Write は file 全体) と現 mtime を state に追記
2. PreToolUse (check) がこの派生 state を参照して編集可否を判定
3. record と check が対になり、 刻印が次の編集 gate の根拠になる (7 日で prune)

Related: `read_before_edit.py`

**メモリ index の自己修復**

1. PostToolUse:Write で、 memory entry の書き込みを検知し、 `memory_routing_gate` (sync) が `memory_surface --upsert` を起動
2. FTS DB を再同期し、 スキル側の upsert 漏れを保険として self-heal
3. PostToolUse ゆえ却下はせず、 後の検索 (過去事例の想起) が新 entry を拾える状態を保つ

Related: `memory_routing_gate.py`

**完了済み todos block の削除催促**

1. PostToolUse:Bash で、 `todos_completion_check` が todos.md に触れた `git commit` を検知
2. working tree の todos.md を直読し、 全 checkbox が [x] の親 block が残っていれば検出
3. 次 commit での block 削除か、 保留作業の checkbox 化かを additional context で促す (完了記録の残置を防ぐ)

Related: `todos_completion_check.py`

#### PostToolUseFailure

**cwd 汚染の検出**

1. Bash 失敗時、 `detect_cwd_pollution` が出力を pathspec / no-such-file パターンと照合
2. cwd 由来のエラーと判定したら、 現在の cwd を添えた助言を additional context で注入
3. 原因に気付かず推測 retry を繰り返す前に、 絶対パス・`git -C` での書き直しへ導く (ブロックはしない)

Related: `detect_cwd_pollution.py`


### スキル

スキル利用に関わるフック利用について説明します。

#### UserPromptExpansion

ユーザーが入力したコマンド（`/foo` 等のスラッシュコマンドやスキル）がプロンプトへ展開される直前に発火するイベントです。`command_name` / `command_source` / `expansion_type` / `prompt` を受け取り、展開の却下や additional context の注入ができます。

本リポジトリでは未使用です。スキル利用を gate したい主目的は「**モデルが自分で**スキルを invoke したか」の検出ですが、UserPromptExpansion は **ユーザーが手で打ったコマンドの展開でのみ発火し、モデルの自己 invoke では発火しません**（実機 probe で確認）。モデルの自己 invoke は PreToolUse が `tool_name:"Skill"` で直接捕捉できるため、スキル gate は PreToolUse 側（`skill_reminder_gate`）で実装しています。


### サブエージェント

サブエージェントの活用状況に関わるフック利用について説明します。

#### SubagentStart

**サブエージェント起動の通知**

1. SubagentStart で、voicevox_claude_alerts が内部 subagent (agent 種別が空) を除外
2. 一定時間 throttle した上で「サブエージェントを起動しています。」を発話
3. 起動を聞き逃さず、 内部 subagent 連発での発話氾濫を抑える

Related: `voicevox_claude_alerts`

#### SubagentStop

**サブエージェント成果の要約読み上げ**

1. SubagentStop で、voicevox_claude_alerts が内部 subagent を除外
2. 最終報告を Haiku で 30 字程度の和文に要約して読み上げ (失敗時は固定句)
3. サブエージェントが何を完了したかを耳で受け取る

Related: `voicevox_claude_alerts`

### 通知

状態変化の通知に関わるフック利用について説明します。

#### Notification

**通知種別ごとの注意喚起**

1. Notification で、voicevox_claude_alerts が通知種別 (idle / permission) を判定
2. idle は一定時間の沈黙後に「作業が終わりました。」、 permission は message が needs your attention / needs your permission を含む時のみ「お伺いしたいことがあります。」を発話 (未知 message は誤発話回避で沈黙)
3. 許可待ちや放置を見落とさないよう耳で知らせる (バックグラウンド session は沈黙)

Related: `voicevox_claude_alerts`

#### PreCompact

**圧縮開始の前置き通知**

1. PreCompact で、voicevox_claude_alerts がフォア/バックグラウンドを判定
2. フォアは「コンテキストを圧縮します。」、 バックグラウンドは UUID 読み上げを避け session 特定はログ参照に促す句を発話
3. コンテキスト圧縮の開始を耳で知らせる

Related: `voicevox_claude_alerts`

#### PostCompact

N/A

#### CwdChanged

**作業ディレクトリ変更の読み上げ**

1. CwdChanged で、voicevox_claude_alerts が移動後の cwd を取得 (30s throttle・バックグラウンドは沈黙)
2. パスを Haiku でカタカナ読み (「/」→「スラッシュ」・各階層名カタカナ) に変換し「作業ディレクトリが変わりました。…」と発話
3. path→読みを cache し、 同じ dir 再訪では Haiku を省く

Related: `voicevox_claude_alerts`

#### ConfigChange

**設定リロードの確認発話**

1. ConfigChange で、voicevox_claude_alerts がフォアグラウンド session のみ「設定をリロードしたよ。」を発話
2. 設定の再読み込みが起きたことを耳で確認 (バックグラウンドは多重 ack 抑止で沈黙)
3. 現状は payload の種別を見ず固定句のみ。 source 別に文言を分ける拡張余地あり

Related: `voicevox_claude_alerts`

#### WorktreeCreate

**ワークツリー作成の通知**

1. WorktreeCreate で、voicevox_claude_alerts が「ワークツリーを作成します。」を発話
2. 作業ディレクトリの切り替わりを耳で知らせる最小ハンドラ (throttle なし)

Related: `voicevox_claude_alerts`


## 応用： スキル・フックによるガードレイルの仕組み

ここまではスキルとフックを個別に列挙してきました。 ここからは、 それらがなぜこの形に行き着いたのか——CLAUDE.md に始まり、 スキル化を経てフック化へ至った経緯——を説明します。

### CLAUDE.md

Claude に行動規範やプロセスルールを指示するとき、最初に書く場所が `CLAUDE.md` です。

このファイルに書いたことは常に効きますが、ルール数が増えると注意が分散し、コンプライアンスは低下します。2026 年 5 月時点のコミュニティの見解でも、遵守率は最高 80 % 程度で頭打ち、ルールが 10 個ほどで 75 % を切るとされています。しかも、この限られた枠を org CLAUDE.md (`/etc/claude-code/CLAUDE.md`)・user CLAUDE.md (`~/.claude/CLAUDE.md`)・proj CLAUDE.md (`repo-top/CLAUDE.md`) の 3 レイヤーと、自動メモリのインデックス (`~/.claude/projects/<proj-id>/memory/MEMORY.md`) で分け合うため、実際に効かせられるルールはごく少数です。加えて、ファイル間でルールが矛盾していたり、トリガーが曖昧だったり、否定形のルールで正しい行動が読み取りにくかったりすると、遵守率は看過できないほど下がります。そして、同じルールを表現を変えて何度も書くことは、強調ではなく弱化になります。

### スキル化と失敗

このリポジトリでは開発マシンの設定ファイルを一括管理しており、自動メモリ由来のルールも数多くありました。ただし、それらが守られることはなく、気まぐれに思い出されて話題に上る程度でした。

折を見て、これらを自動メモリから CLAUDE.md へルールとして昇格させました。一時的には守られるようになったものの、ルール数が増えるに従って遵守率は気まぐれの域を出ないレベルまで下がり、特にセッションが長くなると完全に忘れ去られる状況でした。

CLAUDE.md の肥大化に加え、org / proj / user の 3 ファイルと自動メモリのあいだで内容の重複・整合性の問題が生じたため、ルール群を分類してスキル化しました。公式ドキュメントも、CLAUDE.md を小さくタイトに保つために `.claude/skills/` や `.claude/rules/` の利用を推奨しています。これらは実際に必要となる状況でのみ文面をロードするので、注意の分散を防ぎコンプライアンスを高めます。ちょうど、机に積んだ取扱説明書を状況に応じて開いて読むイメージです。しかしロードの仕組み自体は、コンテキストの冒頭にインデックスを置いて LLM にロードを委ねる方式（CLAUDE.md と同じ）なので、スキルが 40 近くになると、ほとんど全てのルールが無視されるようになりました。机の上に取説が山と積まれ、見向きもされなくなった状態です。結局、スケールしませんでした。ただし、「あのスキル使った？」「どこかにルールが書かれていなかった？」という会話は成立するようになりました。

### そして、フック化

スキルが自動発火しない原因を Claude Code 自身に分析させると、様々な理由を説明してくれるのですが、状況は一向に改善しませんでした。そこで分析結果を Claude on Web に渡し、第三者の視点で意見を求めました。すると「当事者の LLM による分析は post-hoc rationalization に陥り、有効な結論を得られない。コミュニティの見解は Hooks 一択だ」との回答でした。こうしてスキルを全面的に Hooks へ移行したのが、現在の形です。

Claude によるスキルの自動ロード（自動発火）に頼らず、Hooks で Just-in-time に取説を目の前で開く（＝ コンテキストへ挿入する）ことで、100 % のコンプライアンスを目指しています。


## フック+スキルの仕組み

フックは「いつ動くか」で4つに分けられます。

| タイミング | 防ぎたい失敗 | 仕組み | 狙う効果 |
|---|---|---|---|
| A. ファイル編集の直前 | 関連スキルを忘れ、自己流でファイル編集 | 関連スキルを開いたか確かめ、未読なら編集を拒否 | スキルのルールに沿った編集 |
| B. ユーザーへの質問の直前 | 自分で決められる事まで質問で丸投げ | 「自分で決められないか」を点検するスキル未読なら質問を禁止 | 人手（HITL）の削減 |
| C. ユーザーへ回答した直後 | 「大改造」等の根拠なき評価語、安心させ先送りする虚言 | 文章を検閲し、悪パターンを書き直させる／指摘 | Token 浪費の抑止と対話の円滑化 |
| D. ユーザーによる発話の直後 | 過去の教訓を忘れ、同じ失敗を繰り返す | 適切な行動パターンをコンテキストに挿入（こっそり耳打ち） | 過去の事例から状況に合う応答を引き出す |

### 止める力には段階がある

編集・質問という行動そのもの（表 A・B）は、機械的に判別できるので確実に**止められます**。回答後の検閲（表 C）は文章の中身しだいです — 根拠を欠いた規模評価語や空虚な宣言など確度の高い型は**止めて書き直させ**、判断が要る型は指摘にとどめます。発話直後の耳打ち（表 D）は**止めず挿入のみ**です。受け答えの良し悪しは見た目だけでは確実に判定できないものも多く、そこを無理に止めれば正しい返事まで巻き込むため、確度の高い型に限って止めます。**確実に見分けられる場面ほど強く介入し、判断が要る場面ほど軽く促す** ——これは意図的な段階分けです。

### 具体例

- ルールを無視して `myprog.py` を新規作成しようとする → フックが編集を拒絶し、関連ルールを含むスキルを提示 → スキル経由でルールを守って `myprog.py` を作成。
- 「ログ出力は JSON と text どちらにしますか?」と相手に質問しようとする → フックが「自明な既定では?」と点検を促して質問を拒絶 → 自分で JSON と決めて進行。
- デプロイ手順で「お手元で sudo cp … を実行してください」とコマンドを地の文に裸書きして回答 → 直後にフックが「独立したコード枠に入れて」と指摘。
- 以前「deploy 先だけ直して `files/` を放置」し regression を起こした → 似たデプロイ作業を頼まれた瞬間、フックが「`files/` も直せ」と当時の教訓を耳打ち → 両方そろえて同じ轍を回避。

---

## 実装 contract

フックを使って表 A〜D を実現する実装規約を説明します。新しいフック / skill を作るときの一貫性のため、各項は具体例として実フック名を挙げます。deploy の決まりは contract とは別物ですので、末尾の「除外」を参照してください。

### 0. 二つの contract family

| family | event | 動き |
|---|---|---|
| **Gate**（`skill_reminder_gate` / `declare_and_proceed_gate`） | PreToolUse | capability を確認し、無ければ行動を **deny で止めます** |
| **Detection**（`stop_checks` / `memory_surface` の `_concern_inject`） | Stop / UserPromptSubmit | pattern を検出します。 `stop_checks` は family で分岐します — meta-announce-silence / hollow-claims / recognize-own-work / evaluative-terms / known-possible-denial / order-question-to-user は turn 初回 Stop で **exit 2 (decision:block) により block** します（advise-once で retry のみ降格）、 deferral / claim-without-evidence / provide-user-instructions / verify-positive と turn-marker は **warn / 通知のみ** です。 `_concern_inject` は **inject のみ** で止めません |

両 family は以下 1〜5 の共通機構を組み合わせて作ります。

### 1. capability-grant（skill ↔ hook 協調の中核）

中核は mint（権限の発行）と check（権限の確認）の分離で、フローは次の通りです。

1. skill 発動（または `declare` CLI）が「この turn・この対象を編集/質問してよい」という capability を **mint** する。
2. Claude が同じ turn で、その対象を編集（または質問）しようとする。
3. PreToolUse でフックが `required ⊆ active` を **check** する。
4. 満たせば通し、skill を飛ばした detour なら **deny** する（正しい kind を `declare` → skill 発動 → 再実行、で解消）。

- **真実源は sniff でなく宣言**: 拡張子なし file 等で kind を機械推定できないときは model の `declare` を真実源にします。deny が語彙を提示し model が選びます。
- **declare は追加のみ**（auto-detect を下回れない）: `.py` を `else` 宣言して gating を無効化する穴を塞ぎます。
- **content-embedded opt-out token**: gate は対象 content / header 中の `<gate-name>: allow` token で自身の enforcement を bypass できます（`memory_routing_gate` の `memory-guard: allow`）。 LLM が Bash 無しで 1 行で書ける escape hatch です（横展開は現状 1 hook）。 （注: `memory_surface.py:2` の `dangling-ref-check: allow` は別物です — そのファイルが外部 scanner の対象から自身を除外する宣言で、 本 hook が opt-out を実装しているのではありません。）
- 起源は `memory_routing_gate` です（memory への Write を skill 経由に強制）。これを編集（`skill_reminder_gate`）と質問（`declare_and_proceed_gate`）へ一般化しました。

### 2. 判定の返し方（permission / output semantics）

- **deny は JSON、exit 0**: `{"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":...}}` を stdout に出して exit 0 とします。exit 2 でなく JSON にするのは、フックの bug が誤って tool を block しないためです（fail-open と整合）。
- **output 省略 = そのまま通す**（passthrough）。`allow` を明示すると以降のフック / permission を skip します（意図せぬ auto-approve）ので、通すときは原則何も出しません。
- **advisory-allow（pass しつつ助言する）**: PreToolUse でも `permissionDecision:"allow"` に `additionalContext` を併せれば、 行動を通しながら model 可視の助言を inject できます（`read_before_edit` の重複 Read 警告 / Read scope 外 Edit 警告）。 前項「通すときは原則何も出さない」の意図的な例外で、 §0 の「Gate は deny で止めるだけ」という二分にも乗りません（PreToolUse hook が advisory な pass を出す形です）。 乱用は auto-approve 化を招くので、 deny に値しないが助言したい場面に限ります。
- **channel は event ごとに違う**: PreToolUse は `permissionDecision` です。UserPromptSubmit は `additionalContext`（model 可視）です — fullscreen TUI は UPS の `systemMessage` を塗らない未文書 gap があるので additionalContext が確実です。Stop は exit 2 / `decision:block` の 2 つだけです（additionalContext 非対応）。

### 3. trigger の検出（input contract）

- **transcript の current-turn scan**（`stop_checks` / `skill_reminder_gate`）: 直近の human-input user entry を境界に、それ以降（＋任意で直近 N 秒）の assistant entry を見ます。境界判定が load-bearing です — `isMeta`（skill 展開 injection）は除外、content が str または非 tool_result block を含む list は境界、全 tool_result は継続です。境界が取れない corrupted transcript は None → fail-open となります。
- **prompt 直取得 + synthetic re-entry skip**（`memory_surface`）: いずれの path も UserPromptSubmit を `payload["prompt"]`（str）で直取得します。 合成 re-entry prompt の skip は **path ごとに異なります** — `_concern_inject` は `<task-notification>`（dynamic workflow 完了）と `This session is being continued`（compaction 継続）の両 prefix を skip し、 `_turn_marker` は `<task-notification>` のみ skip します。 **BM25 surfacer `_memory_surface` は合成 prompt を skip せず** tokenize して query に当てます（compaction / task-notification 再入でも surface し得ます）。
- **memory-surface の match→inject**（`memory_surface`）: prompt を 3+字 CJK / 4+字 ASCII の語に分解し OR-join した FTS5 query を、全 entry の **keywords + body**（index 対象。`reminder`/`file_path` は非 index）に trigram で当て、**BM25 で top-1**（global + 現 project、throttle 通過分）を選びます。弱すぎる match は confidence floor (`BM25_SURFACE_FLOOR`) で抑止し、2 件目は strong bar (`BM25_STRONG_FLOOR`) を超えた時だけ追加 surface します (大抵 1 件)。inject は各 entry の `reminder` + `詳細: <path>` のみです — **body は inject しない**ので、 reminder は単体で行動を正せる self-sufficient な是正指示 1 文で書きます（≤150 字・事案名/jargon 排除。詳細は `memory-routing`）。
- **phrase pattern 規律**（`stop_checks` / `memory_surface`）: precision-over-recall（noisy なフックは net-negative）です。実 transcript で FP/FN を corpus 実測してから採否を決め、盲目の bare-substring を避けます。module-level で 1 回 compile します。
- **extensible dispatch table**: `KIND_SKILLS` / `CODE_EXTENSIONS` / `LANGUAGES` のように kind・言語 → skill を table 1 行で拡張します。未実在の言語は持ちません（要るとき 1 行足します）。

### 4. 状態の持ち方（cross-invocation state）

- **session-keyed state**: `$CLAUDE_CODE_SESSION_ID`(env) == payload `session_id`（実証済）です。これで `declare`(Bash) とフック(gate) が同 session を共有します。state は session_id でキーします。
- **path は絶対 path で keying**: gate は payload cwd、declare は shell cwd で解決するので、相対 path だと cwd drift で hash 不一致 → 永久 deny loop となります。絶対 path 必須です。
- **TTL は use-case 駆動で選ぶ（盲目流用禁止）**: skill-active = 現 turn ∪ 5 分（guidance は invoke した turn の context にあります）/ memory-surface = 900s（同 entry の 15 分掃除）/ `_concern_inject` = 900s × channel（debugging 往復での再 inject 抑止）。同じ理由で `memory_routing` の 1hr grant を skill-active に流用するのは誤りです。
- **throttle 機構の多目的再利用**: `_concern_inject` は memory-surface の inject_log throttle を sentinel key（`<L4-concern>` 等）で流用し、schema 変更ゼロで channel ごとの抑止を得ました。
- **PostToolUse で derived state を同期**: `read_before_edit` の `record` mode が PostToolUse(Read/Write) で「読んだ」事実を state に追記し、PreToolUse gate がそれを読みます。派生 index は `memory_surface --upsert` で同期します。
- 放置 state は self-prune します（`skill_reminder_gate` は 7 日で session dir を掃除）。

### 5. 安全側への倒し方（robustness）

- **fail-open**: 全例外を exit 0 で握り、enforce 不能（transcript 読めない / 境界 None / DB 不能）なら通します。enforcement の glitch で user 作業を止めません。止めるのは確証があるときだけです。noise-dominant なフックでは DB 不能時は inject せず drop します（unthrottled spam を避ける）。
- **deny-wording 規律**: (1) フックを変更主体に誤読させません（「hook 自身は file を変更しません」と明示）(2) deny 解除条件と次回回避の corrective 行動を reason に書き下します (3) そのため意図的に冗長です — inline コメントで「trim 禁止」と意図を残します。
- **advise-once**: 同 turn の `stop_hook_active` retry を pass に降格し、自己 block loop を断ちます。turn counter の once-per-turn 不変条件（cross-hook で load-bearing）を壊しません。

### 除外: deploy ルールは contract でない

`copy_dir` の自動展開・exec-bit 0755・settings の `copy` / `managed-settings.json` 配置は、本 contract ではなく **deploy ルール**です（`writing-bash` / `writing-python` の exec-bit rule と deploy script が所掌）。種類が違うので本書には混ぜません。
