# スキル・フックによるガードレイルの仕組み

## 背景と本ドキュメントの意図

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

## 実装 contract（技術者向け）

フックを使って表 A〜D を実現する実装規約を説明します。新しいフック / skill を作るときの一貫性のため、各項は具体例として実フック名を挙げます。deploy の決まりは contract とは別物ですので、末尾の「除外」を参照してください。

### 0. 二つの contract family

| family | event | 動き |
|---|---|---|
| **Gate**（`skill_reminder_gate` / `declare_and_proceed_gate`） | PreToolUse | capability を確認し、無ければ行動を **deny で止めます** |
| **Detection**（`stop_checks` / `memory_surface` の `_concern_inject`） | Stop / UserPromptSubmit | pattern を検出します。 `stop_checks` は family で分岐します — meta-announce-silence / hollow-claims / recognize-own-work / evaluative-terms は turn 初回 Stop で **exit 2 (decision:block) により block** します（advise-once で retry のみ降格）、 deferral / claim-without-evidence / provide-user-instructions / verify-positive と turn-marker は **warn / 通知のみ** です。 `_concern_inject` は **inject のみ** で止めません |

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
