# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108


## Critical

## High

## Medium

### skill_reminder_gate.py が subagent の Edit/Write を deny し続ける

Goal: subagent セッションで skill invoke を検出できず Edit/Write が常に deny される問題 (2026-07-10 実装 agent 2 体で再現、Bash heredoc 編集で回避) の原因を特定し、gate を subagent 対応にする。

Note: stale-transcript freshness guard (commit 5a0d1ff, 2026-07-10 deploy 済) では直らないことを deploy 後の live subagent 再演で確認済み — invoke 直後の Edit が同一 deny 文言で拒否された。つまり subagent 変種は「transcript は fresh (または timestamp 無しで fresh 扱い) だが Skill invoke が gate から見えない」経路であり、staleness とは別原因。

Exit Criteria:
- [x] 原因確定 — H1: Claude Code 2.1.206 が subagent 内 PreToolUse payload の `transcript_path` に親 session の path を渡す (バイナリの `Cf(o,void 0,n)` → `transcript_path:QI(n)` を実抽出、replay で親=DENY/子=ALLOW を再現、Claude が独立 spot-check 済)。gate 側の構造不整合 (H2)・flush 遅延 (H3) は却下
- [ ] 修正 (subagent では skip する等) を canonical `files/claude_managed-hooks/skill_reminder_gate.py` に実装し deploy・commit
- [ ] subagent から Edit が通ることを実証

Work file: 診断レポート = `drafts/subagent-gate-diagnosis.md` (実験ログ verbatim + 修正方針 5 案のコスト評価)

### skill_reminder_gate の恒久策: PostToolUse Skill 記録方式 (要相談)

Goal: transcript 依存を排し、PostToolUse `^Skill$` で invoke を session/agent-key state に記録して gate が参照する方式へ移行する。subagent hotfix (agent_id skip = subagent で enforcement 喪失) と resume 系 flush lag <120s の両残穴を同時に塞ぐ。

Exit Criteria:
- [ ] 方針合意 (実装規模 1.5-3 日 + managed-settings.d/extensions.json への hook 配線追加。診断 = `drafts/subagent-gate-diagnosis.md` 案 2/5 参照)
- [ ] PostToolUse:Skill が subagent 含む全成功経路で発火することの live probe
- [ ] 実装・deploy・commit し、subagent skip を撤去して enforcement 回復

### stop_checks.py の intent-without-task を Task tools 不在セッションで満たせない (要相談)

Goal: Fable 5 ハーネスは TaskCreate/TaskUpdate/TodoWrite を提供せず (subagent 含む、settings 要因ではないことを 2026-07-10 に確認済み)、intent-without-task 指摘に機構的に応答不能。hook 側の対応方針を H.S. と合意して実装する。

Exit Criteria:
- [ ] 方針合意 (案: Task tools 不在セッションでは skip / todos.md 追跡に代替 / 上流 issue 報告)
- [ ] 合意した対応を実装・deploy・commit


### memory surface の閾値をモデル別に変えられるか調査

Goal: Opus セッション向け調整の memory surface (UserPromptSubmit `memory_surface.py` / Stop `stop_checks.py` の RAG surface) が Fable 5 では過剰という H.S. の体感に対し、走行モデルを hook 側から検出してモデル別に閾値・頻度を変える実装の可否と方針を確定する。

Exit Criteria:
- [ ] hook から走行モデルを検出する手段の有無を実測で確定 (hook stdin payload / env / `~/.claude/sessions/<pid>.json` / transcript 等。 2026-07-03 時点の既知: PreToolUse/PostToolUse stdin に model field は無い)
- [ ] 対象 hook の surface 閾値・頻度パラメータの所在を特定 (`files/claude_user-hooks/memory_surface.py` / `files/claude_managed-hooks/stop_checks.py`)
- [ ] 可否の結論とモデル別チューニング方針 (やらない選択肢含む) を H.S. と合意

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
