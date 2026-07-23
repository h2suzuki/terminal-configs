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

### skill_reminder_gate の恒久策: PostToolUse Skill 記録方式 (方針合意済・次セッション実装)

Goal: transcript 依存を排し、PostToolUse `^Skill$` で invoke を session/agent-key state に記録して gate が参照する方式へ移行する。subagent hotfix (agent_id skip = subagent で enforcement 喪失) と resume 系 flush lag <120s の両残穴を同時に塞ぐ。

確定済み実態 (2026-07-22 実測・再導出不要):
- **gate mode は false-allow**: `cmd_gate` が `agent_id` で早期 return する (`skill_reminder_gate.py:842-843`)。subagent の Edit/Write は skill 未 invoke でも素通りし enforcement を喪失。実例 = 本 repo の hook file を sonnet subagent に編集させ、Skill invoke 0 件で Edit 5 件成功
- **commit-gate mode は false-deny**: `cmd_commit_gate` は `agent_id` で分岐せず staleness fail-open も適用しない (`:953-958` の意図的設計)。subagent が規約 skill を正しく invoke しても痕跡は親 transcript に無いため必ず deny。同一 payload で transcript だけ差し替えると allow/deny が反転することを実測
- **共通の原因**: subagent の PreToolUse payload に渡る `transcript_path` が親 session のものになり、subagent 自身の Skill invoke が載らない (2026-07-22 実測。同一 payload で transcript だけ差し替えると判定が反転する)。subagent の実 transcript は `<session>/subagents/agent-<id>.jsonl` に別途存在する。**採用する案 2 はこの挙動に依存しない** — invoke を hook 側の state に記録するため、payload がどの transcript を指すかと無関係に判定できる。仮に上流が child transcript を渡すようになれば commit-gate の false-deny は自然消滅するが、gate mode の false-allow は `agent_id` 早期 return 由来なので残る
- **hotfix の履歴**: `ff1129e` (2026-07-10) で `agent_id` early return を追加、`59c3925` (2026-07-21) はコメント文言のみ
- **案 3 (child transcript path 導出) は不採用**: transcript 配置レイアウト依存 + flush race が残る。案 2 が両穴を同時に塞ぐ
- **gate 起動には argv が必須**: `main()` は `len(sys.argv) < 2` で stdin を読まず exit 0 (`:1009-1010`)。配線は `managed-settings.d/extensions.json:13` (`gate`) と `:25` (`commit-gate`)。payload だけ流して「allow」と読むと hook が動いていない誤診になる
- **既知の benign 診断 (2026-07-23)**: Pyright は `cmd_gate:838-839` の `isinstance(payload, dict)` 防御 guard を unreachable と flag するが、引数 annotation `dict` による型狭窄 FP (runtime では malformed JSON 防御として有効)。enforcement logic は含まず `agent_id` fail-open (:841-842) とは別物。cmd_gate 改修時に annotation を緩める or 受容

別セッションからのバグ報告 (`drafts/terminal-config-request-skill-gate.md`) は hotfix 前の状態を記述しており、回答を `drafts/terminal-config-request-skill-gate-response.md` に作成済み。

Exit Criteria:
- [x] 方針合意 (H.S. 2026-07-23 承認・案 2 PostToolUse Skill 記録方式で概ね合意。実装は次セッション。実装規模 1.5-3 日 + managed-settings.d/extensions.json への hook 配線追加。診断 = `drafts/subagent-gate-diagnosis.md` 案 2/5 参照)
- [ ] PostToolUse:Skill が subagent 含む全成功経路で発火することの live probe
- [ ] 実装・deploy・commit し、subagent skip を撤去して enforcement 回復

進捗 (2026-07-23 本 session、deploy 直前・host 実行待ちで中断):
- 実装 (codex) → cross-model 敵対 review (opus, 7 findings 検出) → 修正 → 再 review clean → gates green (62 tests / ruff / ty、私が独立再実行) → **commit `fef5a2c` を main へ merge 済**。canonical source は deploy-ready
- H.S. 裁定 (2026-07-23): state file 欠損 → **DENY (fail-closed)**、corrupt/例外のみ fail-open。並行 upsert は flock 直列化、dead transcript 機構 (`_load_tail`/`_active_skills`/`_transcript_stale`/`_is_turn_boundary`) 除去。`agent_id` 早期 return skip は撤去済 (bucketing `agent_id or "main"` のみ)
- **残 = host deploy のみ** (sandbox は sudo 不可 = `no_new_privs` + `/etc`・`~/.claude` read-only mount で実測不可、H.S. の host shell 必須):
  1. probe 先行 (user-level, sudo 不要): `drafts/skill_probe.py` を `~/.claude/hooks/` へ cp + chmod +x + `claude_user_settings inject` で matcher `Skill` の PostToolUse 配線 → Claude が trigger (main/subagent/無効 skill) を回し `~/.claude/skill-probe.log` で recorder 発火・`agent_id` 混入・`prompt_id` turn 安定性 (uncertain #7) を確認
  2. production (sudo): `sudo cp files/claude_managed-hooks/skill_reminder_gate.py /etc/claude-code/hooks/` + `sudo cp files/claude_managed-extensions.json /etc/claude-code/managed-settings.d/extensions.json`
  3. deploy 先 == canonical の diff + mode 755 確認 → 上記 2 criteria flip → block 削除
- fail-closed ゆえ probe 先行推奨 (recorder 未発火だと false-deny、revert 可)。work file: 発注書 `drafts/skill-gate-order.md` / fix 発注 `drafts/skill-gate-fix1.md` / probe `drafts/skill_probe.py`

### court バグ guard (command + stop_checks/skill 配線)

Goal: stray token (court/count/câu… と揺れる) + 行頭 invoke-leak を厳密パターンで捕捉し、court バグ汚染 (#76912 / #64108) を早期検知する。

Exit Criteria:
- [x] 検出方式を実データで確定 — 888 transcript 走査で 2 signature を FP ゼロ検証: stray-token 単独行 `(?m)^[ \t]*(court|count)[ \t]*$` / 行頭 invoke-leak `(?m)^[ \t]*<invoke name="`。token 固定でなく leaked XML を token 非依存で捕捉するのが要 (実バグ例 "câu")
- [x] 実装 + test + commit — 02e3054 (command `files/claude_court_guard` 7 tests / stop_checks warning-only 55 tests / /my-tasks 自己チェック / 両 .sh に copy 行、独立再実行 OK)
- [x] deploy 完了・配置検証 — 2026-07-13 H.S. 実行、`/usr/local/bin/claude_court_guard` PATH 動作・hooks/ 一致を確認
- [ ] 実運用で court 汚染の live 検出を確認 (opportunistic)
- 既知 finding (低 pri): stop_checks の court チェックは生 `text` 対象で、fence 内に court パターンを書く session は理論上 FP。`stripped` 化は要検討 (実 corpus では 0 FP)

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
