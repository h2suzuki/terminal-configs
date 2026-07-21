# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108


## Critical

## High

### memory surface 改善実装

Goal: 分析レポート (`drafts/memory-surface-analysis.md`) の合意済み方針を実装する — project entry の index 登録、noise 上位 entry の keyword 修正 + バックテストによる効果測定、fable 作成の改善計画、再測定コマンドの実装・インストール。

Exit Criteria:
- [x] 未 index の project entry を --rebuild 登録 — 2026-07-10 実行、index 23→50 (terminal-configs 6 + genai 20、事前推定 3+15 は MEMORY.md 参照の undercount)。fts/vec 両テーブルで件数一致を確認
- [x] noise 上位 entry の keyword 修正 + バックテスト — 2026-07-11 ユーザー承認の部分反映: 4 entry (doc_editor/run_exec/emergency/rebase) を live 反映 (backtest: killed_r0 7/20、killed_r2 は許容例外のみ、run artifacts = analyzer/20260710T-step2-tune1)。rebut_user は net negative 疑いで保留
- [x] rebut_user の reminder 文言書き直し + 保留解除の再 backtest — 2026-07-11 live 反映済 (run = analyzer/20260711T-rebut-v4)。entry 所有 event の実測分母で gate PASS: killed_r0 1/1、killed_r2 1/3 (id291、許容上限内。id282/id67 保全 + id30 新規 r2 獲得)。旧 44% 未達の主因は keyword でなく「event 所有権を無視した集計」と「body BM25 飽和」だったと判明 (echo loop は throttle 900s が既に部分抑制、文言非依存で keyword 対処対象外と結論)
- [x] 計画 Step 3 実装 — C-1 declared_intent 退役済 (OLD-MEMORY 移動 + --delete、index 49)。C-2/C-3 stop_checks warn family (codex 実装・opus APPLY-AS-IS・44/44)、C-5 pixel L4 channel + C-6 sandbox_server_gate (sonnet 実装・codex レビュー 1 blocker+regex 修正済・20/20+4/4) を commit 41aa5eb
- [ ] Step 3 の二段階退役: 各 hook の deploy 後、実運用で正発火を 1 回ずつ確認してから run_executable / ui_screenshot / pixel / sandbox_server の 4 entry を退役 (--delete + OLD-MEMORY 移動)
- [x] deploy 反映 — 2026-07-11 ユーザー実行、全 8 target を cmp で canonical 一致確認 (analyzer/skill×2/stop_checks/sandbox_gate/extensions.json/memory_surface×2)
- [x] 改善計画 (fable subagent, effort xhigh) を作成しレビュー — `drafts/memory-surface-improvement-plan.md` (A keyword diff 5 件 / B backtest 設計 / C hook 移管 6 判定 / D analyzer / E 実装順)。Claude レビュー済・実装続行を宣言 (Step 0 rebuild は完了済み、検証値 41→50 に読み替え)
- [x] analyzer の実装形態を合意 — 2026-07-10 hybrid (deterministic 核 = /usr/local/bin command、LLM 判定・解釈 = 薄い skill) をユーザー選択
- [x] `claude_memory_surface_analyzer` (hybrid) 完成 — CLI は codex 2 巡 + 司令塔仕分けで hardening (commit c20280a, 89b6c72, fb15aee)、skill は codex 起草 + opus レビュー反映 (89b6c72)。2026-07-11 deploy 済: /usr/local/bin で --help 実行確認、skill は session に自動 discover 済
- [x] ubuntu2404-wsl.sh / debian12.sh に install 手順を組み込み — 相談・承認済み、copy 行追加 commit 4ee80ae (skill は既存 copy_dir が自動で拾うため追加行不要)
- [x] 閾値現状維持の結論を記録として commit — `docs/memory-surface-analysis-2026-07-10.md` (commit 128a41c) の §1 score 分離なし根拠 + §4 案5 非推奨判断で充足

Work file: `last-session-handoff.md` の「memory surface 改善実装」 section

## Medium

### codex write 委譲の worktree 隔離 gate

Goal: `codex-companion.mjs task --write` を主 checkout で起動したら deny する PreToolUse hook を入れ、共有ツリーへの委譲で並行セッションの変更が混在する事故を防ぐ。

Exit Criteria:
- [x] 判定方法を実測で確定 — `git rev-parse --absolute-git-dir` と `--git-common-dir` を abspath 正規化して比較し、異なれば linked worktree。当初は「`--absolute-git-dir` の親ディレクトリ名が `worktrees`」で確定したが、top directory 名が literal `worktrees` の主 checkout を誤判定するためレビューを経て比較方式へ変更 (2026-07-22)
- [x] 発注書作成 — `drafts/codex-worktree-gate-order.md`
- [x] hook 実装 + 登録 + test — commit f03c3b6 (`files/claude_managed-hooks/codex_worktree_gate.py` 796 行 + `claude_managed-extensions.json` 登録 1 行、index mode 100755)。codex 3 round + sonnet 手直し 1 round + opus 3 回のレビュー。**受け入れ時に司令塔が 14 payload を自ら実行し全件期待通り**を確認 (主 checkout の `task --write` deny / linked worktree allow / 多段 segment / `cd` 追跡 / subshell 継承 / 相対 `--cwd` / 改行と CRLF の segment 境界 / escape hatch の segment スコープ / read-only allow)。in-file unittest 39 件 green、ruff・ty exit 0。mutation は 15 種中 13 kill で、生存 2 件は git 失敗時の診断文言のみ (どちらの変異でも決定は fail-open のまま不変)
- [ ] `cd -- <path>` を解する — 残る唯一の実挙動の穴。`cd -- <primary> && node ... task --write` が存在しない path を組み立てて `FileNotFoundError` → fail-open で allow する (2026-07-22 実測)。`segment[1] == "--"` なら `segment[2]` を採るだけで塞がる。相対 `cd` の連鎖 (`cd .. && cd ..`) と絶対 `cd` の連鎖は既に deny 済み。**`avoid_cd.py` は allow + advisory で block しないことを実測**したので到達可能
- [x] 委譲用 worktree `<repo>/.claude/worktrees/codex-gate` を削除 — 2026-07-22 に `git worktree remove --force` + `prune` 実行、`worktree list` が主 checkout のみ・`.claude/worktrees/` が空であることを確認
- [x] 委譲時の worktree の作り方を確定 — `Agent` の `isolation: "worktree"` は**使わない**。harness が agent 終了時に unchanged な worktree を自動削除するため、agent より長生きする codex の作業ツリーが走行中に消える (2026-07-21 実測: codex が「requested worktree does not exist / filesystem is read-only」で何も書けずに完了)。発注側が `git worktree add --detach` で作り、codex の `--cwd` に渡す。`--background` を付けなければ同期実行なので Bash job の終了が真の完了シグナルになる
- [x] deploy 反映 — 2026-07-22 H.S. 実行。deploy 先 3 file が canonical と `diff` 一致、hook は mode 755、`extensions.json:28` に登録を確認。**PreToolUse チェーン経由の live 発火も確認**: 共有 checkout から `node .../codex-companion.mjs task --write` を実行して deny を取得 (セッション再起動を待たず反映)。`/etc/claude-code/` は root 所有かつ `no_new_privs` で sudo 不可のため deploy は H.S. 実行が必要。`copy_dir claude_managed-hooks/` が dir 丸ごと配るので per-file の copy 行は不要

Work file: `drafts/codex-worktree-gate-order.md`

### commit gate の射程: 非敵対的な commit 生成経路のカバー

Goal: `git commit` 文字列を含まないが実際に commit を作る経路のうち、迂回意図なく普通に踏むものを gate 対象に加える。敵対的回避経路は対象外とする。

脅威モデル (2026-07-21 調査で確定・再導出不要): 4 hook (`deny_compound_git_commit.py` / `check_commit_format.py` / `check_commit_author.py` / `deny_compound_git_add.py`) は「文字列に `git` と `commit` がこの順で現れる」regex 検出で、shell 文法パーサではない。射程限定は `skill_reminder_gate.py:17-26` docstring と `git_corpus_cases.py` の既知ケース群で明示済みの設計判断。gate の目的は自分の commit の品質担保であり、迂回主体は agent 自身ゆえ**敵対的 bypass は脅威に数えない**。

- covered: `git commit` 単独形 / `-a`・`-i`・pathless (deny) / compound (deny) / `git -C`・`git -c`・先頭 env 代入 / `-F`・stdin
- **対象とする穴** (非敵対・実害あり): `merge` / `cherry-pick` / `revert` / `rebase --continue` / `am` / `stash push` / `gh pr merge` / `gh api .*/git/commits`
- **対象としない穴** (敵対的回避のみ): `bash -c` / heredoc / `eval` / Python・Node subprocess / shell alias。再帰的 quote パーサという機構を足す費用に見合わない

Exit Criteria:
- [ ] `commit-tree` の記述と挙動の食い違いを訂正 — docstring は「射程外」と書くが `\bcommit\b` が `commit-tree` 内に一致して実際は deny される。`-- <token>` 1 つで外れる偶然の防御であり、docstring か実装のどちらを正とするか決めて揃える
- [ ] 非敵対経路のうち author / format チェックを適用すべきものを確定し実装
- [ ] test 追加 (`git_corpus_cases.py` の既知ケースから昇格) + deploy

### skill_reminder_gate の恒久策: PostToolUse Skill 記録方式 (要相談)

Goal: transcript 依存を排し、PostToolUse `^Skill$` で invoke を session/agent-key state に記録して gate が参照する方式へ移行する。subagent hotfix (agent_id skip = subagent で enforcement 喪失) と resume 系 flush lag <120s の両残穴を同時に塞ぐ。

確定済み実態 (2026-07-22 実測・再導出不要):
- **gate mode は false-allow**: `cmd_gate` が `agent_id` で早期 return する (`skill_reminder_gate.py:842-843`)。subagent の Edit/Write は skill 未 invoke でも素通りし enforcement を喪失。実例 = 本 repo の hook file を sonnet subagent に編集させ、Skill invoke 0 件で Edit 5 件成功
- **commit-gate mode は false-deny**: `cmd_commit_gate` は `agent_id` で分岐せず staleness fail-open も適用しない (`:953-958` の意図的設計)。subagent が規約 skill を正しく invoke しても痕跡は親 transcript に無いため必ず deny。同一 payload で transcript だけ差し替えると allow/deny が反転することを実測
- **共通の原因は上流**: PreToolUse payload の `transcript_path` が main session 由来に固定される。2.1.216 の binary で確認 — PreToolUse は `sm(o, void 0, n)` を呼ぶため `n` が main session id に解決される。`agentId` は hook 選択と `agent_id` field にのみ使われ path 導出に関与しない。`agent_transcript_path` は SubagentStop 専用
- **hotfix の履歴**: `ff1129e` (2026-07-10) で `agent_id` early return を追加、`59c3925` (2026-07-21) はコメント文言のみ
- **案 3 (child transcript path 導出) は不採用**: transcript 配置レイアウト依存 + flush race が残る。案 2 が両穴を同時に塞ぐ
- **gate 起動には argv が必須**: `main()` は `len(sys.argv) < 2` で stdin を読まず exit 0 (`:1009-1010`)。配線は `managed-settings.d/extensions.json:13` (`gate`) と `:25` (`commit-gate`)。payload だけ流して「allow」と読むと hook が動いていない誤診になる

別セッションからのバグ報告 (`drafts/terminal-config-request-skill-gate.md`) は hotfix 前の状態を記述しており、回答を `drafts/terminal-config-request-skill-gate-response.md` に作成済み。

Exit Criteria:
- [ ] 方針合意 (実装規模 1.5-3 日 + managed-settings.d/extensions.json への hook 配線追加。診断 = `drafts/subagent-gate-diagnosis.md` 案 2/5 参照)
- [ ] PostToolUse:Skill が subagent 含む全成功経路で発火することの live probe
- [ ] 実装・deploy・commit し、subagent skip を撤去して enforcement 回復

### Task 管理ツール (TaskCreate 系 / TodoWrite) が model gate で使用不可

Goal: 最新 3 モデル (Opus 4.8 / Sonnet 5 / Fable 5) で TaskCreate/TaskGet/TaskList/TaskUpdate と旧 TodoWrite がサーバー側 feature-flag gate で無効化される問題を、原因確定の上で対処方針を H.S. と合意する。これが本質であり、hook 誤発火等は下流被害。

Exit Criteria:
- [x] 原因の確定 — 2026-07-13 に model gate `tengu_vellum_ash` と特定 (下記「確定済み背景」、実機裏取り済)
- [x] 対処方針を確定・実装 — hook gate エミュレーション + /my-tasks 代替 skill + court-guard + DISABLE_GROWTHBOOK ad-hoc、全 deploy 済 (9eac0bc/02e3054)。env-check (DISABLE_GROWTHBOOK 迂回) は H.S. が 2 度不採用・再提起しない (2026-07-13)
- [ ] 上流 gate (tengu_vellum_ash) の解除を watch (opportunistic)

確定済み背景 (2026-07-13・再導出不要):
- **問題定義**: Opus 4.8 セッションで TaskCreate/TaskGet/TaskList/TaskUpdate と旧 TodoWrite が完全に不在 (tool 一覧にも ToolSearch deferred にも出ない)。background-agent 系の TaskStop/TaskOutput のみ残る。
- **メカニズム**: 各 Task 系 tool の isEnabled() が `JI() && !VY()` (TodoWrite は `!JI() && !VY()`) を評価。JI() (CLAUDE_CODE_ENABLE_TASKS gate) は満たされ、ブロック元は VY()。VY() は GrowthBook feature flag `tengu_vellum_ash` を走行 model id で substring 照合する。実機 ~/.claude.json の cachedGrowthBookFeatures.tengu_vellum_ash = ["claude-opus-4-8","claude-sonnet-5","claude-fable-5"] で、現 model id が claude-opus-4-8 に部分一致し VY()=true → isEnabled()=false。env・settings・再起動と独立した server 側 model 別 kill-list。**2026-07-13 自機 binary 2.1.207 を grep し gate 関数を一次確認**: `DX(){ let e=Qe("tengu_vellum_ash",[]); if(!Array.isArray(e)||!e.length)return false; let t=Ti(); return e.some(r=>r.length>0&&t.includes(r)) }` (issue #76076 の VY() に相当)。ただしローカル cache は解決済み値のみで experiment metadata (source/hashAttribute/inExperiment) を持たない。裏付け = issue #76076 / #75577。
- **sandbox は無関係**: filesystem 権限と tool 提供有無は直交。~/.claude/tasks を sandbox write allowlist に追加する deploy (managed-settings の allowWrite、2026-07-13 実施) を行っても tool は復活しない。tasks dir が read-only だったことは gate の原因ではなく、無関係な別事象。
- **こうなっている理由 (推論・2026-07-13 workflow で更新)**: 公式 CHANGELOG (2.1.100-207)・自機 binary いずれにも rationale 文字列は無く理由は非公開 (tengu_ flag は意味を隠す randomized 2 単語命名の内部 kill-switch 群)。当初の「バグ由来の緊急 kill」より **意図的な per-account A/B 実験 / 段階ロールアウト (holdback)** 説が有力: third-party の 2.1.207 eval-response capture が source="experiment" / hashAttribute=accountUUID / 別アカウントは [] (=ツール有) を示す (issue #75577)。ただし**自機 cache に experiment metadata は無く、A/B は third-party 依存の推定**に留まる。動機仮説 (相関のみ) = 最新モデルの tool-calling 破綻 (malformed tool_use 等) 回避 (#63583 / #64129, Ronacher blog)。deprecation 説は否定 (Task* と TodoWrite 両方を false 化する swap でない挙動)。
- **回避策**: (1) kill-list 外の model (Opus 4.7 / Haiku 4.5) へ切替で即復活 (issue #76076 repro)。(2) **env `DISABLE_GROWTHBOOK=1` を export して起動 — 2026-07-13 自機検証で Opus 4.8 のまま Task 系ツール復活を確認** (TaskCreate/TaskUpdate/TaskList/TaskGet が deferred に出現、TaskCreate 実行成功)。cache に 3-model 値が残存していても有効 = 当初の「cache 値で無効化され効かない」仮説は誤りと判明。全 GrowthBook flag を無効化する副作用があり**恒久策にはしない**方針。維持で追跡のみ要るなら todos.md 代替。

関連 — GrowthBook flag が local 設定を上書きする同型事例 (2026-07-13 調査。tengu_vellum_ash とは別 flag だが同機構):
- Qiita「defaultMode が勝手に戻る」 https://qiita.com/yurukusa/items/98f044fe42f25c4459ba — flag `tengu_quill_harbor` / `tengu_permission_friction` が ~9 分ごとの server sync で settings.json を上書きし defaultMode を bypassPermissions→acceptEdits に戻す。**GrowthBook flag が periodic sync で local を上書きする機構を実証** = 上記回避策の懸念「cache 手編集は再 fetch で消える」の裏付け。
- 裏取り issue: #62205 (OPEN, root cause = 上記 2 flag が ~9 分 sync で override) / #61415・#61436 (症状クラスタ = Desktop が Accept Edits に戻る、#61436 は closed) / #63015 (別件・auto-compact 不発、参考)。
- cc-safe-setup (npm, 記事著者): flag drift 監視 hook 群 (growthbook-flag-monitor / compact-dispatch-watchdog / permission-mode-drift-guard) を導入する緩和ツール。npm ページは 403 で本文未取得、記述は記事準拠。

### court バグ guard (command + stop_checks/skill 配線)

Goal: stray token (court/count/câu… と揺れる) + 行頭 invoke-leak を厳密パターンで捕捉し、court バグ汚染 (#76912 / #64108) を早期検知する。

Exit Criteria:
- [x] 検出方式を実データで確定 — 888 transcript 走査で 2 signature を FP ゼロ検証: stray-token 単独行 `(?m)^[ \t]*(court|count)[ \t]*$` / 行頭 invoke-leak `(?m)^[ \t]*<invoke name="`。token 固定でなく leaked XML を token 非依存で捕捉するのが要 (実バグ例 "câu")
- [x] 実装 + test + commit — 02e3054 (command `files/claude_court_guard` 7 tests / stop_checks warning-only 55 tests / /my-tasks 自己チェック / 両 .sh に copy 行、独立再実行 OK)
- [x] deploy 完了・配置検証 — 2026-07-13 H.S. 実行、`/usr/local/bin/claude_court_guard` PATH 動作・hooks/ 一致を確認
- [ ] 実運用で court 汚染の live 検出を確認 (opportunistic)
- 既知 finding (低 pri): stop_checks の court チェックは生 `text` 対象で、fence 内に court パターンを書く session は理論上 FP。`stripped` 化は要検討 (実 corpus では 0 FP)

### memory surface の閾値をモデル別に変えられるか調査

Goal: Opus セッション向け調整の memory surface (UserPromptSubmit `memory_surface.py` / Stop `stop_checks.py` の RAG surface) が Fable 5 では過剰という H.S. の体感に対し、走行モデルを hook 側から検出してモデル別に閾値・頻度を変える実装の可否と方針を確定する。

Exit Criteria:
- [x] hook から走行モデルを検出する手段の有無を実測で確定 — 2026-07-21 workflow で 4 チャネル並列 probe。**transcript JSONL の `.message.model` (type=="assistant") のみ可**、他は不可。binary v2.1.216 の payload 構築 base object `sm()` = `{session_id, transcript_path, cwd, prompt_id, permission_mode, agent_id, agent_type, effort}` に model 無し、~30 の `hook_event_name` 構築箇所すべて同様で、`model` を持つのは `SessionStart` のみ。`~/.claude.json` の `lastModelUsage` は 3 model が recency 順序なく同居し現行 model を取れず、`~/.claude/sessions/<pid>.json` は model field 自体が無い。transcript は 12.8MB でも tail 抽出 0.009s、assistant message 単位 stamp ゆえ mid-session `/model` 切替に追随する
- [x] 対象 hook の surface 閾値・頻度パラメータの所在を特定 — 計 9 個 / 2 file。`memory_surface.py`: `THROTTLE_SECONDS` / `BM25_SURFACE_FLOOR` / `BM25_STRONG_FLOOR` / `HYBRID_FLOOR` / `HYBRID_STRONG_FLOOR` / `DENSE_RESCUE_FLOOR` / `BM25_CANDIDATES` / `max_emit`(UPS=2)、`stop_checks.py`: `max_emit`(Stop=1)。体感頻度に効く第一段は 4 個 (`max_emit`(UPS) / `THROTTLE_SECONDS` / `HYBRID_FLOOR` / `HYBRID_STRONG_FLOOR`)、残る BM25_* は embedding 不在時の legacy path 用。9 個中 7 個が module-level 定数で chain は model 引数を持たないため分類は**改造 (surgical)**
調査フェーズは 2026-07-21 で完了・打ち切り。H.S. 指示により方針決定は別途検討とし、当時の session scope 外とした。上記 2 項目は一次実測済みゆえ**再調査は不要**で、再開時は下記の推奨をそのまま合意の議題にすればよい。

- [ ] 可否の結論とモデル別チューニング方針 (やらない選択肢含む) を H.S. と合意 — 推奨は transcript tail 方式 + `main()` 入口で profile を解決し module global を rebind する `_apply_model_profile(model)` 1 関数 (chain 全段への plumbing 不要)。SessionStart の `model` は `/model` 切替後も恒久 stale ゆえ不採用。global 引き下げ案は Opus 側の recall を確実に落とすため却下。**未 probe**: env var チャネルは probe が placeholder を返し未検証 — ただし launch 時静的ゆえ SessionStart と同じ恒久 stale 欠陥を持ち、結論は変わらない

### SKILL-HOOK-CONTRACT.md パターン集

Goal: repo 直下 `SKILL-HOOK-CONTRACT.md` を 4 部構成で完成 — (A) event 別 hook 利用カタログ (H.S. の番号フロー形式) / (B) Skills フォーマット規約 / (C) 応用編 = CLAUDE.md→skill/hook 化の概要 (Big Picture) / (D) 実装 contract (技術者向け再利用規約)。 一貫性担保が目的 (2026-05-30 起案・A/B 記入は 2026-06-07 前 session で H.S. が依頼したが court バグでセッション腐敗→リセット、 本 session で再開。 「今 session の新指示」ではない)。

Exit Criteria:
- [x] (D) 実装 contract §0-5 記載 (capability-grant / permission semantics / session-keyed state / transcript current-turn scan / fail-open / deny-wording / extensible dispatch table / use-case 駆動 TTL / PostToolUse sync) — prior session commit 27b498c
- [x] **除外を厳守**: deploy の決まり (`copy_dir`・exec-bit 0755・settings `copy`) は deploy ルールとして除外し contract に混ぜず (doc 末尾「除外」節)
- [x] (C) overview/応用編 (動機/仕組み/狙う効果 3軸表 + 具体例、 commit 91cf0e0)。 固有名は「相手」に汎用化
- [x] event→hook 完全対応表を 3 json から確定 (2026-06-07 本 session、 下記「確定済みファクト」)
- [x] **(A) event 別 hook 利用カタログ** を全 event 分記入 (commit e5e8b19)。 抽出 workflow wdjbl0ux3 + 敵対検証 w8kl0gkmu (1 error + 6 minor 修正反映)
- [x] draft 要修正: SessionEnd N/A 訂正 + `### ConfigChange`→`####` + WorktreeCreate 新設 + 真の N/A 明記。 CwdChanged は本 session で voicevox 配線したため実 use-case 記載
- [x] **(B) Skills フォーマット規約** を「## Skills」に記入 (frontmatter/本文構造/言語規約。 deploy 位置は doc「除外」原則ゆえ割愛)
- [x] draft SessionStart の `xxxx Skill` placeholder を「複数のスキル (verify-before-claim 等)」で充足
- [x] **`deny_unsafe_git_reset` を PreToolUse:Bash catalog に追記** (2026-06-08 完了): PreToolUse 節に新 use-case「破壊的 reset / restore の advise-once 防止」を番号フロー + Related で追加 (L334-340)。 全 24 hook 再 gap 監査で MISSING 0 達成。 entry 自体の構成は H.S. の doc 全体 review 対象
- [ ] H.S. レビュー承認 → Exit flip + block 削除。 register は ですます に統一済 (commit 9fe0933、 prose 8 行を である→ですます・番号フロー step は体言止め維持)、 SessionStart step2 の述部欠落も修正済 (commit d56b27c)。 残るは H.S. の最終 review (構成/粒度) のみ。 2026-06-08 本 session で skill 一覧 (全 22 entry に category＋≤2文概要)・全 hook の Related 記入・UserPromptExpansion 節 (probe 結果)・Stop の check_push_prompting 欠落補完・応用節 bridge 文を追記し、 hook 記述を 20-agent workflow で実 source 検証して修正 (stop_checks 重複統合・§0 表 block family 4→6) — これらも H.S. review 対象 (commit 20a4858 / 0cf974c)。 **追従済** (commit ae2a3de): 2ca11ff の broad/pathless add deny (`-A`/`.`/`-u`/pathless) を PreToolUse:Bash catalog へ反映 — 新 use-case「広域 git add の cross-session 巻き込み防止」block 追加 + 「commit 規律」step1 に forward pointer。 3-lens 敵対 workflow (wpivtp9py) で hook source を逐語検証 (medium 1 = compound-only 誤読の forward pointer 反映)。 H.S. review 対象に含む

確定済みファクト (2026-06-07 本 session・再導出不要):
- **task 定義** (H.S. 前 session 原文趣旨): 「SessionStart の見出しを少し書いた。 こんな感じで repo のフックを記入していってほしい。 Skill はフォーマットを規約として書ける。 CLAUDE.md のスキル&フック化は後半の応用編で概要 (ここのフックでなく Big Picture)」。
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
- **編集規律**: doc は H.S. レビュー中 draft だが前 session 指示「記入してほしい」= 私が埋めて可。 document-editor は inline で discipline verbalize して適用 (doc 既読・modest size ゆえ fork でない)。 bare-invoke は dirty file 暴発の前科ありゆえ対象明示必須。 register 等の編集ルール詳細は handoff doc。

Note: doc 本体 (L1〜L4 概観 head + 実装 contract 0〜5 + 除外) 記載・commit 27b498c・SendUserFile 送付済。 目次 = 二つの family → capability-grant → 判定/検出/状態/安全 → 除外、 各項に実フック名の具体例。 **H.S. レビュー待ち** (外出先・後日)。 承認後に Exit flip + block 削除 (body 構成/粒度の直しがあれば反映してから)。 2026-05-31: コード照合 audit (workflow wvsbvz52x、 34 claim 中 30 accurate、 adversarial 確認・誤 flag 1 件棄却) 実施し確定 3 finding を commit eedd808 で反映 — (A) 中核 dichotomy 訂正 (L3 stop_checks の 4 family は exit2 で block、 overview L3 行+段階補足+§0 表)、 (B) §3 synthetic-skip を path 別に (BM25 surfacer `_memory_surface` は非 skip・本 turn live 確認)、 (C) §1/§2 に advisory-allow + content-embedded opt-out token 追記。 **事実精度は audit 済**、 残は H.S. の構成/粒度レビュー。 任意候補: 補足「L3とL4どう違うか」の「指摘する」(現 line 24) も同根で、 H.S. が望めば「介入する」系へ。 follow-up (doc外・コード): `_memory_surface` が synthetic prompt を surface する挙動の許容可否。 2026-06-01〜02: H.S. live レビューで overview を全面改稿 (歴史先行 CLAUDE.md→skill→hook / L1-L4 jargon 撤去 / 一人称除去 / です・ます / 表 A-D 化+俳句 / capability-grant をフロー番号リスト化 / 事実確認) + ファイル名 `_`→`-` リネーム (commit 025a3c6・14cf6d0)。 **レビュー継続中** — 次 session も H.S. の追加指摘を反映。 確立した編集ルールは handoff doc 参照。

Work file: handoff = `last-session-handoff.md` の「SKILL-HOOK-CONTRACT.md パターン集」 section ＋ plan `~/.claude/plans/breezy-bubbling-quiche.md` の「並行 deliverable」節
