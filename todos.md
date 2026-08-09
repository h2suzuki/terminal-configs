# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)


## Critical

## High

### memory surface の model tag mute を塞ぐ

Goal: 実行中モデルの tag 判定と「壁と結論する前に引く」導線を直し、過去の教訓が mute されたまま同じ失敗を繰り返す経路を閉じる。

Exit Criteria:

- [ ] deploy 後の実 session で、`opus-5` tag 付き entry が `claude-opus-5[1m]` の session に surface することを観測する
- [ ] deploy 後の実 session で muted-memory-at-wall が live 発火することを観測する
- [ ] deploy 後に新規蓄積された `kind='mismatch'` が untagged entry 由来のみになっていることを SQL で確認する

- [x] `_normalize_model` が `[1m]` 等の context-window 変種を落とすよう修正 + unit test — 実データで `opus-5[1m]` の mismatch 33 行中 21 行が解消することを確認
- [x] memory-routing skill に「壁と結論する前 / 2 回失敗した時に引く」 trigger を追加 (既存 Tag propagation 節の入口を拡張、コマンド重複なし)
- [x] 壁宣言 probe を stop_checks の muted-memory-at-wall family として畳み込み — 別 session 提案の中身 (WALL_RE corpus / 否定周辺 ±120 字を query 化 / mute された entry の報告) を採用し、単独 hook 化で懸念した再 block loop と turn counter 二重 bump は exit 0 + additionalContext + `.muted` latch で解消。floor は実測分離点 0.35。`search_unfiltered()` を memory_surface に切り出して CLI と共用。stop_checks 107 tests (新規 7) / memory_surface 31 tests (新規 3)
- [ ] deploy (ユーザー手動): `files/claude_user-hooks/memory_surface.py` → `~/.claude/hooks/`、`files/claude_managed-hooks/stop_checks.py` → `/etc/claude-code/hooks/`、`files/claude_managed-skills/` 配下の memory-routing・codex-delegation の SKILL.md → `/etc/claude-code/skills/<name>/` (`~/.claude/skills/` 側と同一 inode)、`files/codex_task_sentinel` → `/usr/local/bin/` (0755)

codex (gpt-5.6-sol / xhigh) レビュー指摘の是正。deploy 前に少なくとも最初の 2 つを直す:

- [x] **発火 0 回の経路**: enforcement block が出た turn は `main()` が muted lookup 前に return し、retry は `stop_hook_active` gate で止まる。壁宣言と謝罪等が同居する典型応答ほど一度も出ない → `_run` の block stderr 出力直後で lookup し併記 (降格 retry は exit 0 で main 経路に戻すため二重に出さない)。test 2 件
- [x] **latch が初回 turn で無効**: `_stop_latch_key()` が `.turns` file の存在に依存し、muted warning を返した Stop は marker/bump に到達しないため fresh session では latch が no-op → `.turns` 不在を turn key `"0"` とし、`_stop_latched`/`_stop_latch_set` を flock 済み 1 回 RMW の `_stop_latch_claim()` に統合 (.wt / codex / surf / muted の 4 latch 共通)。test 4 件
- [x] **壁 regex の corpus 総取り替え**: 実測で誤検知 8/8・取りこぼし 8/8 → 動詞列挙をやめ「可能形の否定 + 断定の尾」を核にし、疑問「〜か」・条件「〜場合 / とき」・二重否定「〜わけではない」・推量「〜かもしれ」を尾で落とす。誤読系は自認に限るため過去形のみ (te 形はプログラムの誤読の叙述に出る)。table-driven test は断定 14 / 非断定 16。実 transcript 263 block で発火 7 件・全件が真の断定 (旧 regex は 3 件中 1 件が誤検知で、家族の動機になった壁宣言自体を落としていた)
- [ ] **floor を backend 別に較正**: `MUTED_FLOOR=0.35` は hybrid 2 点のみが根拠。embed DB 不在時は `_fuse(s, 0.0)` 経由で BM25 <= -7 相当となり、通常 surface の BM25 <= -2 と桁が違う。hybrid / BM25 で定数を分け、labeled corpus で PR を測る
- [ ] **観測できない**: fail-open が全て無言の `None` で、`search_unfiltered()` は記録もしないため「0 件」が無事故か feature 死かを区別できない。rate-limit した error log と wall 専用 event を残す
- [ ] **mismatch 行が emit の throttle を食う**: `_throttle_check()` の SQL に `kind` 条件が無く、mute 記録が 15 分の抑止に効く。tag 追記直後の動作確認が空振りする (実測: 60 秒後も空、901 秒後に初めて surface)。`kind='emit'` のみ見るようにする
- [ ] **model source の一本化**: `_current_turn()` が持つ当該 turn の model を捨て、`_resolve_model()` が statusline cache を transcript より優先して再解決している。壁文と同じ turn の model を muted lookup へ渡す
- [ ] **検索に時間上限が無い**: 元 probe の subprocess 20 秒 watchdog を失い、同一 process 呼び出しになった。例外 catch は hang に効かないので Stop 全体が止まりうる
- [ ] **提示が top-1 のみ**: 弱い誤 hit が真の教訓を shadow する。上位 2-3 件を score つきで返すか、margin が小さい時だけ複数出す
- [ ] **強制力の設計**: warning 化で「読んでから結論を出し直す」は保証でなくなった。同じ壁を繰り返し、かつ提示 path を Read していない 2 回目だけ既存 advise-once に統合して block する案を検討する
- [ ] **`models:` の役割分離 (設計)**: provenance (どの model で観測したか) と delivery allowlist (どの model に見せるか) を同じ field が兼ねるため、model 更新の度に corpus が cold-start する。`observed_models:` と `applies_to:` に分ける
- [ ] **「2 回失敗」の機械 trigger**: skill には書いたが hook は tool failure を観測しない。current turn の tool_result 失敗 signature を数え、2 回目で横断検索を起動する

### codex_task_sentinel: 敵対レビューの収束と上流依存 1 件

Goal: 監視判定が plugin の実挙動と skill の 4 分岐に一致する状態にする。

Exit Criteria:

- [ ] レビューの新規 material 指摘がゼロで安定する — 4〜7 巡目は連続ゼロ。exit 14 導入の検証を
  論点にした 12 巡目で 2 件、13 巡目でさらに 2 件。いずれも直前の巡の修正が生んだ欠陥で、全て修正済み。
  14 巡目は 4 回発注して 3 回失敗 (provider の content filter 2 回・plugin state dir 再利用 1 回)。
  中断した 2 回の最終出力が示した欠陥 (baseline の list 化 / timeout headline) は自力で確認し修正した
- [x] log 由来の曖昧さが正常 job の cancel を招かない — 既定で cancel 導線 (exit 4/3) を出さず、
  exit 14 で evidence を示して判断を呼び手に渡す (206ce7a)。断定したい呼び手は `--trust-log`。
  12 巡目が 504 case の直積で「既定の exit 3/4 は 0 件」「`--trust-log` は旧判定と mismatch 0」を実測
- [ ] 上流 (plugin) が per-command lifecycle を record に持ち、stall 判定の原理的曖昧さ自体が消える

13 巡のレビュー (gpt-5.6-sol / xhigh) の指摘はすべて修正済み
(a746ef5 / b9f32d0 / fabe928 / bb56980 / 7c4d532 / 2607f1d / 890349a / 1f37e46 / 206ce7a /
13832d2 / d8b1781 / 87cc3e0 / 6ccb4b4)。内容は commit message に要約してある。

- [ ] **worktree を作り直したときの plugin state dir 掃除を機構化する**: 同じ path で
  `git worktree add` し直すと `plugin data/state/<worktree>-<hash>/` が再利用され、job が
  `failed to load configuration: No such file or directory` で即死する。codex-delegation skill に
  rule はあるが、worktree 再作成の時点では skill を invoke していないので発火しなかった
  (2026-08-09 に実際に踏んだ)。`codex_worktree_gate.py` は既に codex の Bash を検査しているので、
  起動時に「workspaceRoot の state dir があるのに worktree の作成時刻の方が新しい」を検出して
  警告するのが素直。sentinel 側は `errorMessage` を evidence に出すようにして (87cc3e0)
  「手で record を開き直す」までは消えている

- [ ] **command lifecycle が log 層でしか観測できない (上流依存)**: plugin の `appendLogBlock` は
  message 本文を無加工で append するため、本文が log 行を引用すると event と区別できない。
  11 巡の敵対レビューで「真 event を一切落とさず正しい stall 判定も保つ reader は作れない」と
  結論が出ている (stamp 単調性 + コマンド名の対応付けで実 corpus の誤検知は 0 だが、
  本文が未来 stamp を持てば通る)。害の側は 206ce7a で消した。
  原理的に閉じるには job record に per-command lifecycle (item id) の永続化が要り、
  書けるのは plugin 側だけ (`phase` は investigating / editing / running 等の粗い活動状態で
  command 単位ではない)。plugin 更新時に再評価する

### worktree-cleanup が稼働中の codex worktree を削除候補にする

Goal: 実行中の作業を壊す削除提案を出さないようにする。

Exit Criteria:

- [ ] codex job が走っている worktree に対し、削除候補として提案されないことを実機で確認する

- [ ] `stop_checks.py` の `_worktree_cleanup_warnings()` が「clean かつ本線の祖先」だけを見ており、その worktree を `workspaceRoot` とする codex job が running かどうかを見ていない。2026-08-08 の 2 回とも、codex がレビュー用 worktree で走っている最中に削除コマンドを提示した (成果物を書く前なので clean に見える)。提案どおり実行すると走行中の job の作業 root が消える。`~/.claude/plugins/data/codex-openai-codex/state/*/jobs/*.json` の `status=running` かつ `workspaceRoot` 一致を候補から除外する

## Medium

### Handoff 強化 + 言語 lint 機構の deploy と実運用確認

Goal: wind-down open-task 機構 (inject + block)・handoff cross-check step・session_resume_context pointer 化・claude_lang_lint を deploy し、実運用での駆動を確認する。

Exit Criteria:
- [x] 追補 deploy (hooks 3 本 0755 / handoff・codex-delegation skill / crosscheck-prompt.md / /usr/local/bin/claude_lang_lint) を canonical と `diff -q` 一致で検証 — 2026-08-06 ユーザー実行、7/7 identical・exec bit 確認・deployed claude_lang_lint --selftest OK (PATH 解決込み)
- [x] 実 session で open Task を残した wind-down に inject + block が発火し、todos.md 転記 + close で通過することを確認 — **2026-08-08 04:26 に full loop を live 観測**: ユーザー発言「セッションを閉じます」に対し UserPromptSubmit で inject (open Task #7 を列挙) → ターン終了時に stop_checks が exit 2 で block (#7 を名指し) → todos.md へ転記済みのうえ Task を close して通過。以下は経緯: 2026-08-07 **inject は実 session で live 発火を観測** (ユーザーの「セッションは終わります」prompt に対し UserPromptSubmit で open Task 1 件を列挙、clean tree ゆえ未コミット節は出ず = 偽陽性修正も live 確認)。block 側は下記 shadow 欠陥を修正済 (40f89e8)。deploy 完了・canonical と diff 一致を確認済 (2026-08-07 ユーザー実行) で、deployed 版が実 transcript から人間 prompt を復元し harness entry 14 件を skip することも確認。残るは **live block の観測のみ** (実装は 3a6a2c5 で完了・deploy 済)。ユーザー指摘により設計から作り直した: Stop payload には prompt が無いため transcript を遡っていたが、これをやめ **prompt を受け取る UserPromptSubmit hook 側で判定し session 単位の控えに記録**、Stop 側はそれを読むだけにした。未処理項目は従来どおり Task store + mytask の両対応。transcript を読まなくなったので下記 2 段の不発原因は原因ごと消滅し、widen-once (75de34b) も削除。通し試験で「合図なし→素通り / 合図あり→block / 通常発言で上書き→素通り」を確認、deploy 後は本番 hook が実際に控えを書くことも確認済 (04:11)。
  - 旧原因の記録 (再発時の手がかり): (1) harness 生成 entry が人間 prompt を shadow、(2) `_load_tail` が末尾 128KB しか読まず長 session で人間 prompt に届かない、(3) `<system-reminder>` も harness 生成だが roster 未収載だった

- [ ] codex-companion を叩く Bash を codex-delegation skill が active でない限り止める — 2026-08-08 に発注〜監視ターンで同 skill を invoke せず、既存規約 (running[]-empty monitor 禁止) を再違反した。CLAUDE.md「ルール違反 = 即 countermeasure」に基づく機構化
  - **着手前に解く設計上の罠** (cross-check readback で判明): 発注は Bash しか持たない codex-rescue subagent 内で起きるが、`skill_reminder_gate` の skill-active state は agent 単位 (`agent_id or "main"`)。素直に相乗りすると skill を invoke できない subagent が恒久 deny になり発注不能。判定を親 session の state で行うか subagent を対象外にするかを先に決める
  - 相乗り先候補は 2 つ: `skill_reminder_gate.py` (編集前 gate) と `codex_worktree_gate.py` (既に codex Bash を検査済・検出面を持つ)。後者が有力
  - 射程を明示する: 今回の違反は監視側で発生。既存 codex hook は `status` / `cancel` / `result` を素通ししているので、監視系を含めるか決めてから実装する
- 既存の失敗テスト 2 件 (今 session 以前から・新規 regression ではない): `stop_checks.WorktreeCleanupTest.test_non_repo_fails_open_with_diagnostic` (temp dir が repo と別 filesystem だと git stderr が 2 行になり 1 行前提の assert が落ちる) / `test_git_corpus.GitCorpusTest.test_corpus_against_current_adapter` (参照する `drafts/git-corpus/*.tsv` が repo に不在で error、原因未調査)
- 環境 finding (2026-08-08 実測・要 root): memory index DB (`/var/lib/claude-rag-memory/memory_index.sqlite3`) が `nobody:nogroup 664` で uid scorer から書けず (`os.access(W_OK)` False)、この user の memory entry は **index に永久に載らない**。`memory_routing_gate.py` の sync は `--upsert` を stdout/stderr とも DEVNULL・`check=False` で呼び、`_upsert_entry` も sqlite エラーを握り潰すため**失敗が完全に不可視**。dir が 0777 ゆえ `-wal`/`-shm` は作れて健全に見える。結果 `--search` は root 由来の 13 件しか返さず、その中に skill と矛盾する reminder (「running[] が空になったら」) が現役で残る

Work file: `last-session-handoff.md` の同名 section

### court バグ guard (command + stop_checks/skill 配線)

Goal: stray token (court/count/câu… と揺れる) + 行頭 invoke-leak を厳密パターンで捕捉し、court バグ汚染 (#76912 / #64108) を早期検知する。

Exit Criteria:
- [x] 検出方式を実データで確定 — 888 transcript 走査で 2 signature を FP ゼロ検証: stray-token 単独行 `(?m)^[ \t]*(court|count)[ \t]*$` / 行頭 invoke-leak `(?m)^[ \t]*<invoke name="`。token 固定でなく leaked XML を token 非依存で捕捉するのが要 (実バグ例 "câu")
- [x] 実装 + test + commit — 02e3054 (command `files/claude_court_guard` 7 tests / stop_checks warning-only 55 tests / /my-tasks 自己チェック / 両 .sh に copy 行、独立再実行 OK)
- [x] deploy 完了・配置検証 — 2026-07-13 ユーザー実行、`/usr/local/bin/claude_court_guard` PATH 動作・hooks/ 一致を確認
- [ ] 実運用で court 汚染の live 検出を確認 (opportunistic)
- 既知 finding (低 pri): stop_checks の court チェックは生 `text` 対象で、fence 内に court パターンを書く session は理論上 FP。`stripped` 化は要検討 (実 corpus では 0 FP)

### SKILL-HOOK-CONTRACT.md パターン集

Goal: repo 直下 `SKILL-HOOK-CONTRACT.md` を 4 部構成で完成 — (A) event 別 hook 利用カタログ (ユーザーの番号フロー形式) / (B) Skills フォーマット規約 / (C) 応用編 = CLAUDE.md→skill/hook 化の概要 (Big Picture) / (D) 実装 contract (技術者向け再利用規約)。 一貫性担保が目的 (2026-05-30 起案・A/B 記入は 2026-06-07 前 session で ユーザーが依頼したが court バグでセッション腐敗→リセット、 本 session で再開。 「今 session の新指示」ではない)。

Exit Criteria:
- [x] (D) 実装 contract §0-5 記載 (capability-grant / permission semantics / session-keyed state / transcript current-turn scan / fail-open / deny-wording / extensible dispatch table / use-case 駆動 TTL / PostToolUse sync) — prior session commit 27b498c
- [x] **除外を厳守**: deploy の決まり (`copy_dir`・exec-bit 0755・settings `copy`) は deploy ルールとして除外し contract に混ぜず (doc 末尾「除外」節)
- [x] (C) overview/応用編 (動機/仕組み/狙う効果 3軸表 + 具体例、 commit 91cf0e0)。 固有名は「相手」に汎用化
- [x] event→hook 完全対応表を 3 json から確定 (2026-06-07 本 session、 下記「確定済みファクト」)
- [x] **(A) event 別 hook 利用カタログ** を全 event 分記入 (commit e5e8b19)。 抽出 workflow wdjbl0ux3 + 敵対検証 w8kl0gkmu (1 error + 6 minor 修正反映)
- [x] draft 要修正: SessionEnd N/A 訂正 + `### ConfigChange`→`####` + WorktreeCreate 新設 + 真の N/A 明記。 CwdChanged は本 session で voicevox 配線したため実 use-case 記載
- [x] **(B) Skills フォーマット規約** を「## Skills」に記入 (frontmatter/本文構造/言語規約。 deploy 位置は doc「除外」原則ゆえ割愛)
- [x] draft SessionStart の `xxxx Skill` placeholder を「複数のスキル (verify-before-claim 等)」で充足
- [x] **`deny_unsafe_git_reset` を PreToolUse:Bash catalog に追記** (2026-06-08 完了): PreToolUse 節に新 use-case「破壊的 reset / restore の advise-once 防止」を番号フロー + Related で追加 (L334-340)。 全 24 hook 再 gap 監査で MISSING 0 達成。 entry 自体の構成は ユーザーの doc 全体 review 対象
- [ ] ユーザーレビュー承認 → Exit flip + block 削除。 register は ですます に統一済 (commit 9fe0933、 prose 8 行を である→ですます・番号フロー step は体言止め維持)、 SessionStart step2 の述部欠落も修正済 (commit d56b27c)。 残るは ユーザーの最終 review (構成/粒度) のみ。 2026-06-08 本 session で skill 一覧 (全 22 entry に category＋≤2文概要)・全 hook の Related 記入・UserPromptExpansion 節 (probe 結果)・Stop の check_push_prompting 欠落補完・応用節 bridge 文を追記し、 hook 記述を 20-agent workflow で実 source 検証して修正 (stop_checks 重複統合・§0 表 block family 4→6) — これらも ユーザー review 対象 (commit 20a4858 / 0cf974c)。 **追従済** (commit ae2a3de): 2ca11ff の broad/pathless add deny (`-A`/`.`/`-u`/pathless) を PreToolUse:Bash catalog へ反映 — 新 use-case「広域 git add の cross-session 巻き込み防止」block 追加 + 「commit 規律」step1 に forward pointer。 3-lens 敵対 workflow (wpivtp9py) で hook source を逐語検証 (medium 1 = compound-only 誤読の forward pointer 反映)。 ユーザー review 対象に含む

確定済みファクト (2026-06-07 本 session・再導出不要):
- **task 定義** (ユーザーの前 session 原文趣旨): 「SessionStart の見出しを少し書いた。 こんな感じで repo のフックを記入していってほしい。 Skill はフォーマットを規約として書ける。 CLAUDE.md のスキル&フック化は後半の応用編で概要 (ここのフックでなく Big Picture)」。
- **記入形式** = `#### <event>` 配下に `**use-case 名**` + 番号フロー (2-4 step・体言止め/である・です ます禁止・一人称禁止・実フック名 jargon 可)。 use-case は機能単位グルーピング (例: コンテキスト引き継ぎ = handoff skill + session_resume_context、 event 跨ぎ可)。
- **canonical source** = hook 配線は 3 json: `files/claude_managed-extensions.json`(managed) / `files/claude_user-extensions.json`(user) / `files/claude_managed-voicevox.json`(voicevox)。 hook 実体は managed=`files/claude_managed-hooks/`・user=`files/claude_user-hooks/`・voicevox=`files/voicevox_claude_alerts`。 再導出は 3 json Read で 1 分。
- **完全 event→hook 対応表**:
  - SessionStart: claude-md-lint.sh / feature_findings_build.py / session_resume_context.py
  - SessionEnd: session_cleanup.py (**draft の N/A は誤り**)
  - UserPromptSubmit: check_uncommitted_at_handoff.py(managed) / memory_surface.py(user・過去事例 surfacer ＋ concern/correction inject) / subagent_gate_suggest.py(user)
  - Stop: stop_checks.py(managed) / check_push_prompting.py(user) / voicevox Stop
  - PreToolUse: read_before_edit.py(check,Read|Edit|MultiEdit) | check_dangling_refs.py+memory_routing_gate.py(guard)+skill_reminder_gate.py(gate)+comment_rationale_gate.py(Edit|Write|MultiEdit) | avoid_cd.py+deny_compound_git_add.py+deny_compound_git_commit.py+check_commit_format.py+deny_unsafe_git_reset.py(Bash) | subagent_gate_warn.py(Task|Agent) | declare_and_proceed_gate.py(AskUserQuestion) | check_push_prompting.py(user,AskUserQuestion) | check_commit_author.py(user,Bash)
  - PostToolUse: read_before_edit.py(record,Read|Write|Edit|MultiEdit) / memory_routing_gate.py(sync,Write) / check_todo_completion.py(Bash)
  - PostToolUseFailure: detect_cwd_pollution.py(Bash)
  - voicevox (`voicevox_claude_alerts <Event>`): Stop / Notification / SubagentStart / SubagentStop / ConfigChange / PreCompact / WorktreeCreate / CwdChanged (本 session 追加)
  - **真の N/A (hook 無し)**: StopFailure / UserPromptExpansion / PermissionRequest / PermissionDenied / PostCompact (CwdChanged は本 session で voicevox 配線済ゆえ N/A から除外)
- **draft 要修正 3 点**: (1) SessionEnd=N/A は誤り、 (2) `### ConfigChange` は h3 で兄弟 (`####`) と不揃い、 (3) **WorktreeCreate セクションが丸ごと欠落** (voicevox 配線あり)。
- **voicevox ConfigChange 裏取り (workflow VERIFIED)**: 現状 ConfigChange branch は payload の種別判定を一切していない (source field 等を読まず無条件で固定句「設定をリロードしたよ。」)。 ∴ 別 todo「source field で発話分岐」は実装余地が実在。
- **編集規律**: doc は ユーザーレビュー中 draft だが前 session 指示「記入してほしい」= 私が埋めて可。 document-editor は inline で discipline verbalize して適用 (doc 既読・modest size ゆえ fork でない)。 bare-invoke は dirty file 暴発の前科ありゆえ対象明示必須。 register 等の編集ルール詳細は handoff doc に置いていたが、 当該 section は消失 (2026-08-07 確認) — 再開時は doc 本文と git log から再導出する。

Note: doc 本体 (L1〜L4 概観 head + 実装 contract 0〜5 + 除外) 記載・commit 27b498c・SendUserFile 送付済。 目次 = 二つの family → capability-grant → 判定/検出/状態/安全 → 除外、 各項に実フック名の具体例。 **ユーザーレビュー待ち** (外出先・後日)。 承認後に Exit flip + block 削除 (body 構成/粒度の直しがあれば反映してから)。 2026-05-31: コード照合 audit (workflow wvsbvz52x、 34 claim 中 30 accurate、 adversarial 確認・誤 flag 1 件棄却) 実施し確定 3 finding を commit eedd808 で反映 — (A) 中核 dichotomy 訂正 (L3 stop_checks の 4 family は exit2 で block、 overview L3 行+段階補足+§0 表)、 (B) §3 synthetic-skip を path 別に (BM25 surfacer `_memory_surface` は非 skip・本 turn live 確認)、 (C) §1/§2 に advisory-allow + content-embedded opt-out token 追記。 **事実精度は audit 済**、 残は ユーザーの構成/粒度レビュー。 任意候補: 補足「L3とL4どう違うか」の「指摘する」(現 line 24) も同根で、 ユーザーが望めば「介入する」系へ。 follow-up (doc外・コード): `_memory_surface` が synthetic prompt を surface する挙動の許容可否。 2026-06-01〜02: ユーザー live レビューで overview を全面改稿 (歴史先行 CLAUDE.md→skill→hook / L1-L4 jargon 撤去 / 一人称除去 / です・ます / 表 A-D 化+俳句 / capability-grant をフロー番号リスト化 / 事実確認) + ファイル名 `_`→`-` リネーム (commit 025a3c6・14cf6d0)。 **レビュー継続中** — 次 session も ユーザーの追加指摘を反映。

Work file: なし (handoff / plan file とも消失を 2026-08-07 確認。 再開に要る事実は上の「確定済みファクト」と Note に inline 済)
