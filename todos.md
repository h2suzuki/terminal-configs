# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108


## Critical

## High

### 部分 stage workflow と pathless commit 禁止の整合 (要相談)

Goal: 本 session で `deny_compound_git_commit.py` を強化し pathless `git commit` を deny した結果、 user memory `partial_stage_foreign_changes` の手順 (`git apply --cached` で自分の hunk だけ index に stage → commit) が壊れる衝突を解消する。 衝突理由: pathless commit は index を commit するが、 強化後に要求する `git commit -- <file>` は working tree を commit するため、 部分 stage した hunk でなく foreign hunk 込みの file 全体を commit してしまう。

Exit Criteria:
- [ ] H.S. が方針決定: (a) memory rule を更新し部分 stage 後の安全 commit 手段を明記 / (b) hook に意図的 escape を追加 / (c) 現状許容 (部分 hunk commit は諦める)
- [ ] 決定を memory rule か hook に反映し動作確認

## Medium

### ターミナルタブの状態別アイコン (実験中・repo 未 commit)

Goal: Claude Code のタブアイコン (待受=✳ / 実行=・ の hardcode) を状態別カスタムに置換。 hook の `terminalSequence` (OSC 0/1/2 許可・binary 2.1.183 で allowlist 確認) で発行し、 CC 純正 title は `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` (env・gate 実在確認) で停止。 H.S. 指示で「まず repo 非 commit の実験」→承認後 back-port。

実験構成 (gitignore 内・deploy-target 非汚染):
- hook 実体: `~/.claude/title-icon-hook.py` (live・非 repo)。 先頭 `ICON` dict 1 行で差替可。 現状 ⚡生成中 / 💤暇 / ❓質問 (シンプル路線・H.S. 確定待ち)。
- 配線: `.claude/settings.local.json` (gitignore) の hooks に UserPromptSubmit / Stop / Notification 登録 (既存 permissions は非破壊で merge 済)。
- DISABLE env: 起動時インライン `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1 claude --continue` で付与 (settings env が CC 自身に効くか不確実ゆえ inline が確実)。

Exit Criteria:
- [ ] H.S. が実機 relaunch で表示確認: 3 状態でアイコン切替わるか / DISABLE で純正 glyph 消えるか / ちらつき有無 / session 名併置の可否
- [ ] アイコン絵柄を H.S. が確定
- [ ] **承認後 back-port** (CLAUDE.md 必須): canonical 版を Codex 生成+敵対レビュー → script を `files/` へ + `ubuntu2404-wsl.sh`/`debian12.sh` に copy 行 / DISABLE を `files/claude_env.sh` / hooks 配線を該当 source json へ反映 → commit
- [ ] back-port 後に実験用暫定配線 (settings.local.json の hooks block・live script) を整理

未検証 (実機 relaunch で初確認): DISABLE が動的 glyph を完全停止するか / terminalSequence が UserPromptSubmit·Stop でも honor されるか / hook input に session_name·title が実在するか (無ければ cwd basename で表示)。 静的に確認済は terminalSequence allowlist・DISABLE env・process.title は静的 "claude"。

Work file: last-session-handoff.md

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

### codex review-nudge: deferred 配信 (実装済) + asyncRewake 両立 (調査中)

Goal: codex-rescue 完了時の「codex 出力を敵対的/受入レビューせよ」review-nudge を、 SubagentStop が session-keyed flag を arm し、 次に発火する surface 可能イベント (PreToolUse=同一ターン内 / UserPromptSubmit=次ユーザーターン、 先着が deliver+clear・二重配信なし) で main agent へ届ける。 SubagentStop 直接 emit は無効 (下記) ゆえ不採用。 DELEGATE_MSG (ExitPlanMode 時) は維持。

E2E 確定事実 (session b9a67872、再導出不要):
- deployed hook は SubagentStop[agent_type=codex:codex-rescue] で `[codex-review]` を正しく emit (synthetic + unittest 6 green)。 実 codex-rescue subagent も完了 (main jsonl record 75)。
- だが完了後の main agent ターンに SubagentStop 由来の `hook_additional_context` attachment が **0 件**。 実 surface するのは SessionStart / UserPromptSubmit / PreToolUse のみ (jsonl 全 attachment 走査で確認)。 subagent jsonl にも hook attachment 0 件。
- ∴ **SubagentStop の additionalContext は main agent に一切 surface しない** (前 session b61304b5 の結論と一致、 却下された feature request #5812 = subagent→parent context bridge とも整合)。 ∴ commit 33b78a4 (SubagentStop branch + delegation.json 登録) を revert。

設計決定 (2026-06-20 H.S. 承認): (b') PreToolUse-proxy + (c) UserPromptSubmit fallback を両採用 = deferred 配信。 state 規約は `deny_unsafe_git_reset.py` に倣う (`~/.claude/hooks/state/codex_review_pending/<sid>/pending`、 TTL 1800s で stale は emit せず削除、 fail-open、 self-prune)。 codex plugin の result-handling は出力提示のみで実装 review nudge を出さない (実ソース確認済) ゆえ別機構が必要。

Exit Criteria:
- [x] H.S. が代替経路を決定 (2026-06-20: (b')+(c) deferred 配信を採用)
- [x] `codex_delegation_surface.py` を deferred 配信へ改修 (SubagentStop=arm / PreToolUse 全 tool・UserPromptSubmit=fresh flag で deliver+clear / DELEGATE_MSG 維持)、 12 unittest green、 Codex 委譲→Claude 敵対的/受入レビュー済 (commit 8ec53f5)
- [x] `delegation.json` 更新 (PreToolUse matcher を全 tool 化 + UserPromptSubmit 登録、 commit 8ec53f5)
- [x] canonical source (`files/`) と `/etc/claude-code` deploy を同期 (diff SAME)
- [x] live E2E (b') PreToolUse: 実 codex-rescue 完了→本 session sid (`b9a67872`) で arm→次 PreToolUse:Bash で `[codex-review]` が system-reminder として surface し marker 消費を実観測。 **session_id 一致も実証** (registration は live-reload された)。 (c) は deployed hook に synthetic payload で arm→deliver→clear→二重配信なしを検証
- [x] (c) UserPromptSubmit 配信: deployed hook に synthetic payload で deliver+clear+二重配信なしを検証 (E2E [6] PASS)。 harness surface 機構は PreToolUse additionalContext と同一で (b') が live 実証済ゆえ transitive に成立

asyncRewake 両立 (2026-06-20 H.S. 承認 "両立。フラグを誰が消すか"):
- **clearing rule (確定)**: flag を消すのは deferred deliver 経路 (PreToolUse/UPS) のみ。 asyncRewake 経路は flag に触れない。 版でモード相互排他にし配信者/clearer を常に 1 つに保つ — asyncRewake 対応版: SubagentStop は REVIEW_MSG emit + exit 2 (flag arm せず・re-wake が配信)、 非対応版: 現行 deferred (flag arm + PreToolUse/UPS が deliver-and-clear)。
- **asyncRewake 知見 (binary 2.1.183)**: per-hook flag `asyncRewake:bool` = "hook runs in background and wakes the model on exit code 2"。 stdout は rewakeMessage prefix 後に system-reminder 注入、 rewakeSummary は端末用 1 行。 **未公開** (公式 Hooks/Settings/changelog に記載なし — claude-code-guide 確認) + rewakeMessage/rewakeSummary は @internal + pluginId 込みの内部 hook 形状。 2.1.179+。

asyncRewake 両立 Exit Criteria:
- [x] **settability 確定** (gating): asyncRewake は public command-hook zod schema 内 (binary 2.1.183、 `type/command/args/timeout/async/asyncRewake/rewakeMessage` の順で同一 object・offset 1149)。 = **delegation.json から設定可能**。 sibling に `async:bool` も存在。 両立は技術的に可能
- [x] SubagentStop で asyncRewake 発火・exit 2 で main agent re-wake を実機検証: 実 codex-rescue 完了→exit 2→`[codex-review]` が非同期 surface (subagent return 後の別 notification)・flag 不在を確認 (commit d3a2df7)
- [x] モード切替 = hook 実行時 version 検出 (env `CLAUDE_CODE_VERSION`/`EXECPATH`/`AI_AGENT`、 SubagentStop env には AI_AGENT のみ存在ゆえ 3 source 必須) を実装 + 両モード E2E 14/14 PASS + deploy SAME (commit d3a2df7、 AI_AGENT fix は Claude)
- [ ] **pre-2.1.179 残課題** (本 2.1.183 機では検証不可): 旧 Claude Code が未知 config field `asyncRewake` を strip(無視) するか reject(delegation.json 破損) するか。 hook 側は runtime version 検出で安全 (旧版→deferred branch・exit 2 出さず)、 残るは config field strictness のみ。 非 strict 証拠あり。 旧版機が手に入り次第確認

派生元: 2026-06-19 codex plugin-only 化で旧 REVIEW_MSG/PostToolUse 経路を除去 → SubagentStop 版を再実装 (33b78a4) → 本 session E2E で無効確定 → revert → deferred 配信へ再設計 → 2026-06-20 asyncRewake 発見で両立化。

Work file: handoff = `last-session-handoff.md` の該当 section
