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

- [x] deploy 後の実 session で、`opus-5` tag 付き entry が `claude-opus-5[1m]` の session に surface することを観測する — **2026-08-11 に成立。当初 2026-08-09 の観測として書いた根拠は誤りだったので差し替えた** (`kind=emit` かつ `model LIKE 'opus-5%'` の行は DB 全期間で 2 行しかなく、両方とも 2026-08-11 23:20 / 23:49 に本 session が生成したもの。2026-08-09 時点では 1 行も存在しない)。正しい根拠: `models: opus-5` の `feedback_grep_before_reading_search_space.md` が、`claude-opus-5[1m]` で走る本 session に `kind=emit model=opus-5` で surface した
- [x] deploy 後の実 session で muted-memory-at-wall が live 発火することを観測する — **2026-08-12 に初の live 発火を観測**。私が「読み違えた」と書いたターンの Stop で `<muted-memory>` が additionalContext に入り、`models=opus-4.8` ゆえ mute されていた `feedback_cjk_tool_arg_glyph_contamination.md` を名指しした。replay ではなく実 turn である証拠: 直前まで HOME 配下 0 件だった `.muted` latch が `96c7898d-...turns.muted` として初めて生成された
  - 提示を受けて実際に走査した (本 family の目的どおりの帰結): 当該 entry は Fable 5 固有の Cyrillic 混入で、todos.md・memory entry・commit message 14603 字・両 hook source を Greek/Cyrillic/Hangul 等で走査して混入 0 件。よって tag は追記していない (「効きそうだから」で盛らない)
  - 経緯の記録: 過去の `[x]` は「latch を temp path に隔離した replay」を根拠にした虚偽 closure だったので一度 `[ ]` に戻し、今回 live 発火で改めて閉じた
  - 私は「機会が 2 回しかないので 0 発火は当然」と一度書いたが、これは text 付き assistant message 126 件という弱い標本によるもので撤回する。より硬い測定では production Stop 3226 件を census して 106 件が壁 regex に一致し、deploy 済 module + 実 DB の replay で 83 件が emit 相当 (2.6% ≒ 39 turn に 1 回)。「機会が稀」は否定されている
  - 未説明の 1 件が核心: deploy 確定後の window (18 Stop) に入った唯一の壁一致 Stop (2026-08-11T12:57:57Z) は、replay では model 解決 3 通りすべてで emit するのに、production では additionalContext が空で hook 実行 183 ms だった (同夜 emit した Stop は 435 ms)。log が無いため「live text が regex に当たらなかった」のか「壊れている」のか判別できない

- [x] `_normalize_model` が `[1m]` 等の context-window 変種を落とすよう修正 + unit test — 修正自体は有効 (pre-fix の `_normalize_model` は `opus-5[1m]` を返し、`_model_pred` は完全一致で判定するため `models: opus-5` の entry は原理的に mute された)。ただし当初書いた「33 行中 21 行が解消」は再現不能: `MODELS_DEFAULT = 'opus-4.8'` ゆえ untagged entry の mute は本バグと無関係に起きており、87 行中 76 行がこれに当たる。mute 時点で既に tag が付いていた確定被害は **6 行** (2 file / 2 session / 101 分間)、今日の tag での counterfactual でも 11 行。最古の `models:` tag は 2026-08-09 08:18:57 で、累計が 33 行に達した時点では tag が 1 件も存在しない
- [x] memory-routing skill に「壁と結論する前 / 2 回失敗した時に引く」 trigger を追加 (既存 Tag propagation 節の入口を拡張、コマンド重複なし)
- [x] 壁宣言 probe を stop_checks の muted-memory-at-wall family として畳み込み — 別 session 提案の中身 (WALL_RE corpus / 否定周辺 ±120 字を query 化 / mute された entry の報告) を採用し、単独 hook 化で懸念した再 block loop と turn counter 二重 bump は exit 0 + additionalContext + `.muted` latch で解消。floor は実測分離点 0.35。`search_unfiltered()` を memory_surface に切り出して CLI と共用。stop_checks 107 tests (新規 7) / memory_surface 31 tests (新規 3)
- [x] deploy (ユーザー手動): `files/claude_user-hooks/memory_surface.py` → `~/.claude/hooks/`、`files/claude_managed-hooks/stop_checks.py` → `/etc/claude-code/hooks/`、`files/claude_managed-skills/` 配下の memory-routing・codex-delegation の SKILL.md → `/etc/claude-code/skills/<name>/` (`~/.claude/skills/` 側と同一 inode)、`files/codex_task_sentinel` → `/usr/local/bin/` (0755) — 2026-08-11 に 5 対象すべて `diff -q` 一致を確認

codex (gpt-5.6-sol / xhigh) レビュー指摘の是正。deploy 前に少なくとも最初の 2 つを直す:

- [x] **発火 0 回の経路**: enforcement block が出た turn は `main()` が muted lookup 前に return し、retry は `stop_hook_active` gate で止まる。壁宣言と謝罪等が同居する典型応答ほど一度も出ない → `_run` の block stderr 出力直後で lookup し併記 (降格 retry は exit 0 で main 経路に戻すため二重に出さない)。test 2 件
- [x] **latch が初回 turn で無効**: `_stop_latch_key()` が `.turns` file の存在に依存し、muted warning を返した Stop は marker/bump に到達しないため fresh session では latch が no-op → `.turns` 不在を turn key `"0"` とし、`_stop_latched`/`_stop_latch_set` を flock 済み 1 回 RMW の `_stop_latch_claim()` に統合 (.wt / codex / surf / muted の 4 latch 共通)。test 4 件
- [x] **壁 regex の corpus 総取り替え**: 実測で誤検知 8/8・取りこぼし 8/8 → 動詞列挙をやめ「可能形の否定 + 断定の尾」を核にし、疑問「〜か」・条件「〜場合 / とき」・二重否定「〜わけではない」・推量「〜かもしれ」を尾で落とす。誤読系は自認に限るため過去形のみ (te 形はプログラムの誤読の叙述に出る)。table-driven test は断定 14 / 非断定 16。実 transcript 263 block で発火 7 件・全件が真の断定 (旧 regex は 3 件中 1 件が誤検知で、家族の動機になった壁宣言自体を落としていた)
- [x] **floor を backend 別に較正** → **問題の本体は「劣化が無言だったこと」だったので、そちらを塞いだ** (ユーザー判断: DB を失えば普通エラーを出すはず、出さないならエラー処理を掛けろ)。`_model_open()` は DB 不在でも破損でも無言の `None` を返していた (docstring も "None when absent/invalid") → `_warn_degraded()` を追加し、不在と破損を区別して stderr に報告し復旧コマンドまで示す。hot path なので marker file の mtime で 1 時間に 1 回に絞る。test 4 件 (不在 / 破損 / 窓内は 1 回 / 健全時は無言)、memory_surface 41 tests、deploy 済 (`diff -q` 一致・0755・裸実行 rc=0)
  - 定数を hybrid / BM25 で分ける作業自体は**していない**。実測では `entries_fts` 68 = `entries_vec` 68 で join でも欠落 0 件、embed DB (359 MB) も健在ゆえ BM25 単独分岐に traffic が無い。失えば警告が出るので、黙って劣化する経路は残っていない
- [x] **mismatch 行が emit の throttle を食う**: `_throttle_check()` の SQL に `kind` 条件が無く、mute 記録が 15 分の抑止に効いていた (実測: 60 秒後も空、901 秒後に初めて surface) → `kind` 引数を足して kind 別に見る (emit は emit、mismatch は mismatch)。mute 記録の直後でも emit が出ることを test で pin
- **model source の一本化 — 却下済み (2026-08-12・ユーザー判断)。再提案しないこと**。`_current_turn()` は使えない: memory_surface は UserPromptSubmit hook で、その時点では当該ターンの assistant 応答がまだ存在せず turn が成立しない。ゆえに `_resolve_model()` が statusline cache を先に見る現行構造が正しい。この結論は過去に一度出ており、本 session で私が蒸し返した
  - 私が「両者が食い違った実例は 1 件もない」と書いたのは監査の受け売りで誤り。実測すると本 session で `statusline=claude-opus-5[1m]` / `transcript=claude-opus-5` と食い違っている。ただし `_normalize_model` が `[1m]` を畳むので解決結果は同一 (`CONTEXT_WINDOW_SUFFIX = \[\d+[kmg]\]` は数字+k/m/g のみ畳み、`[safety-eval]` 等は畳まない)
- [x] **検索に時間上限が無い**: 元 probe の subprocess 20 秒 watchdog を失い、例外 catch では hang に効かず Stop 全体が止まりうる状態だった → `_bounded()` (daemon thread + `join(20s)`) 経由で呼ぶ。返らなくても None で fail-open し、居残った thread は Stop の終了を待たせない
- [ ] **失敗したら毎回、過去の教訓を横断検索する**: skill には書いたが hook は tool failure を観測しない。**要件変更 (2026-08-12・ユーザー判断): 「2 回目で起動」をやめ、失敗のたびに毎回起動する** — 2 回待つ理由が無い。current turn の tool_result 失敗を検知したら `search_unfiltered()` を回し、mute された候補も含めて提示する

### codex_task_sentinel: 敵対レビューの収束と上流依存 1 件

Goal: 監視判定が plugin の実挙動と skill の 4 分岐に一致する状態にする。

Exit Criteria:

- [ ] レビューの新規 material 指摘がゼロで安定する — 4〜7 巡目は連続ゼロ。exit 14 導入の検証を
  論点にした 12 巡目で 2 件、13 巡目でさらに 2 件。いずれも直前の巡の修正が生んだ欠陥で、全て修正済み。
  14 巡目は 4 回発注して 3 回失敗 (provider の content filter 2 回・plugin state dir 再利用 1 回)。
  中断した 2 回の最終出力が示した欠陥 (baseline の list 化 / timeout headline) は自力で確認し修正した。
  4 回目が完走して 4 件 (completed + 活動中ツリーで exit 5 を早出し / 判定と evidence が別 snapshot /
  同期 test が runtime 定数と繋がっていない / 本文の不正 stamp で監視が例外終了) — すべて修正済み。
  15 巡目は 3 件 (mktime が Z stamp を local 時刻として読む / silence age を log 再読より前に取る /
  exit table を数値集合で比較するため定数入替が通る)、16 巡目は 4 件 (contract が検査対象の定数を
  自分の出典にする / completed 直後の record と log で snapshot race 2 件 / 読めない tree に
  「書き込みなし」と表示) — いずれも修正済み (a0a6ace / b1d8ed7)。17 巡目で再判定する
- [x] log 由来の曖昧さが正常 job の cancel を招かない — 既定で cancel 導線 (exit 4/3) を出さず、
  exit 14 で evidence を示して判断を呼び手に渡す (206ce7a)。断定したい呼び手は `--trust-log`。
  12 巡目が 504 case の直積で「既定の exit 3/4 は 0 件」「`--trust-log` は旧判定と mismatch 0」を実測

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


## Medium

### Handoff 強化 + 言語 lint 機構の deploy と実運用確認

Goal: wind-down open-task 機構 (inject + block)・handoff cross-check step・session_resume_context pointer 化・claude_lang_lint を deploy し、実運用での駆動を確認する。

Exit Criteria:
- [x] 追補 deploy (hooks 3 本 0755 / handoff・codex-delegation skill / crosscheck-prompt.md / /usr/local/bin/claude_lang_lint) を canonical と `diff -q` 一致で検証 — 2026-08-06 ユーザー実行、7/7 identical・exec bit 確認・deployed claude_lang_lint --selftest OK (PATH 解決込み)
- [x] 実 session で open Task を残した wind-down に inject + block が発火し、todos.md 転記 + close で通過することを確認 — **2026-08-08 04:26 に full loop を live 観測**: ユーザー発言「セッションを閉じます」に対し UserPromptSubmit で inject (open Task #7 を列挙) → ターン終了時に stop_checks が exit 2 で block (#7 を名指し) → todos.md へ転記済みのうえ Task を close して通過。以下は経緯: 2026-08-07 **inject は実 session で live 発火を観測** (ユーザーの「セッションは終わります」prompt に対し UserPromptSubmit で open Task 1 件を列挙、clean tree ゆえ未コミット節は出ず = 偽陽性修正も live 確認)。block 側は下記 shadow 欠陥を修正済 (40f89e8)。deploy 完了・canonical と diff 一致を確認済 (2026-08-07 ユーザー実行) で、deployed 版が実 transcript から人間 prompt を復元し harness entry 14 件を skip することも確認。残るは **live block の観測のみ** (実装は 3a6a2c5 で完了・deploy 済)。ユーザー指摘により設計から作り直した: Stop payload には prompt が無いため transcript を遡っていたが、これをやめ **prompt を受け取る UserPromptSubmit hook 側で判定し session 単位の控えに記録**、Stop 側はそれを読むだけにした。未処理項目は従来どおり Task store + mytask の両対応。transcript を読まなくなったので下記 2 段の不発原因は原因ごと消滅し、widen-once (75de34b) も削除。通し試験で「合図なし→素通り / 合図あり→block / 通常発言で上書き→素通り」を確認、deploy 後は本番 hook が実際に控えを書くことも確認済 (04:11)。
  - 旧原因の記録 (再発時の手がかり): (1) harness 生成 entry が人間 prompt を shadow、(2) `_load_tail` が末尾 128KB しか読まず長 session で人間 prompt に届かない、(3) `<system-reminder>` も harness 生成だが roster 未収載だった

- [ ] **発注書を発注先に敵対レビューさせてから発注する** — **方針変更 (2026-08-12・ユーザー判断)**。当初は「codex-delegation skill が active でない限り codex-companion の Bash を止める」という hook 案だったが、gate の state が agent 単位で subagent から見えないという罠があり詰んでいた。代わりに **発注書そのものを発注先 (codex) に敵対レビューさせ、規約に従っていなければ突き返す**。発注前に規約違反が発注先から返ってくるので、こちらの skill invoke 状態に依存しない
  - 経緯: 2026-08-08 に発注〜監視ターンで codex-delegation skill を invoke せず、既存規約 (running[]-empty monitor 禁止) を再違反した
- [x] 環境依存で緑になる test 2 件を、環境に依らず正しい結果を出すようにする — 2026-08-11 に両方修正
  - `test_non_repo_fails_open_with_diagnostic`: stderr の行数を数える assert をやめ、診断の件数を数えるようにした (本来の主張)。git stderr を 2 行に強制する test を追加して、件数が行数に追従しないことを pin
  - `test_corpus_against_current_adapter`: corpus は実 session 履歴から採取するもので repo に入れるべきでないと判断し、tracked 化ではなく不在時 `skipTest` を選択。dir を退避して skip、戻して pass を実測
- [x] index sync の失敗が不可視な設計を塞ぐ — `_main_rebuild()` が「disk にあるがどちらの名簿にも無い entry」を drop 時に full path で名指しする (`_unlisted_entries()`、test 4 件)。retired は報告しないので実 memory dir では 1 件だけ出る。当初の `memory_routing_gate.py` の DEVNULL + `check=False` は、upsert 経路が健全と判明したため原因ではなかった
  - **私が一度「corpus の 46% が index から欠落」と書いたのは誤り。撤回する**。disk 125 件に対し `entries_fts` 67 件なのは事実だが、名簿と突き合わせると欠落 58 件の内訳は roster file 自体が 7 件 (MEMORY.md ×5 / OLD-MEMORY.md ×2)、**OLD-MEMORY.md 収載 = retired が 42 件** (載らないのが正しい)、どちらの名簿にも無い orphan が 8 件。「欠損」と呼べるのは最後の 8 件だけ
  - **orphan は 8 件ではなく 1 件。これも私の誤りで訂正する**: 8 件と数えたとき、project scope の file を user scope の MEMORY.md / OLD-MEMORY.md と突き合わせていた。scope ごとに正しい名簿で測ると unlisted は user scope 1 件・project scope 全 4 dir とも 0 件。`user_profile.md` は feedback entry ではなく、terminal-configs の 6 件は同 project の OLD-MEMORY.md に収載済 = 正しく retired
  - 真の欠損は **`feedback_turn_end_continuation_claim.md` (2026-08-06 / `models: fable-5`) の 1 件のみ**
  - upsert 経路自体は健全: orphan 1 件に `--upsert` を実行すると rc=0 で index に載る (検証後 `--delete` で baseline 67 に戻した)。原因は権限でも parse でもない
  - **機序を code で確定**: `_list_active_entries()` (`memory_surface.py:466-486`) は **MEMORY.md の `- [title](path.md)` link だけ**を active とみなし、`_main_rebuild()` は当該 scope を `DELETE` で全消ししてから listed path のみ再投入する (`:1164-1180`)。つまり **MEMORY.md に link されていない entry は、次の `--rebuild` で無言で index から消える**
  - 実害の実例: `feedback_turn_end_continuation_claim.md` は 2026-08-06 19:14〜08-07 17:17 に **32 回 emit** し 08-08 01:05 まで mismatch を記録していた = 当時は index にいた。その後 rebuild で消え、以降 0 件。同名 skill も無いので retire ではない
- [x] deploy (ユーザー手動): `files/claude_user-hooks/memory_surface.py` → `~/.claude/hooks/memory_surface.py` — 2026-08-12 00:33 に deploy、`diff` 0 hunk 一致。私が渡した `install -m 0644` が原因で一度 0644 になり裸実行が rc=126 で死んだが、`chmod 0755` で復旧 (裸実行 rc=0 を確認)
- [x] `feedback_turn_end_continuation_claim.md` を MEMORY.md に載せ直すか retire するかを決める (内容判断・要ユーザー) — 2026-08-12 に復帰。MEMORY.md へ追記 (40 行) + `--upsert` で `entries_fts` 68 件。deploy 済 hook で `--rebuild` すると `rebuilt 33/33` かつ `dropped` 行が消え、roster 経由で落ちなくなったことを確認。tag は観測どおり `fable-5` のまま
  - 判断材料 (除外ゼロ走査): `継続します` / `自走` / `再開の種` / `continuation-claim` は user skill 33 本・managed skill 30 本・3 つの CLAUDE.md・repo の `files/` 全体で **0 hit**。`遂行宣言` は `stop_checks.py` の intent-without-task family にのみ存在するが、その是正は「Task を登録せよ」であって「未来形の主張をするな」ではない
  - よって本 entry の教訓を代替する skill / hook は存在せず、retire ではなく欠損として扱うのが妥当。なお本 session で intent-without-task から疑問形を除外して発火を弱めているため、この discipline の被覆は以前より薄い

Work file: `last-session-handoff.md` の同名 section
