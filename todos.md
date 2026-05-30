# Todos

## Critical

## High

### skill 発火率 system 対策

Goal: 既存 skill (verify-before-claim / report-by-evidence / scope-mismatch-detector / illuminate-not-reassure / 他) と 本 session で追加した user memory entry 4 個が、 LLM の「trigger 該当時の self-invoke」 に依存して発火率低い問題への system 対策を設計 + 実装。

Exit Criteria:
- [x] system 設計: 4 機構の設計を adversarial 監査込みで確定 (2026-05-30 workflow w3zrkuwwh)。 核心原則 = 「trigger が機構的に検出できる skill は check を hook に移して発火依存を消す」 (raise でなく eliminate)。 (**最優先機構 = skill-active gate (`skill_reminder_gate.py`) は 2026-05-30 に pivot・plan 承認済。 当初の additionalContext advisory 案は破棄**。 他 3 機構は据置)
- [x] skill-active gate `skill_reminder_gate.py` (最優先・本 session の writing-code/python 漏れを直撃) 実装・deploy 済 (2026-05-30 commit c585671 / smoke 51/51 / adversarial review 5 confirmed fix 反映 / `/etc/claude-code/hooks/` deploy mode 0755 / 当 session で `.sh` write が writing-bash 要求 deny される live 実機確認)。 PreToolUse(Edit|Write|MultiEdit) で「関連 writing-* skill が**当 turn に invoke 済か**」を gate — 正規ルート (skill 発動→同 turn で edit) は通し、 skip=detour は JSON deny → 正しい kind を `declare` → skill invoke → edit。 kind は sniff でなく **model の declare が真実源** (語彙 python/bash/code/test/skills/todos/memory/**else**、 else=skill 無し file で Write 不能を防ぐ)。 skill-active は **現 turn ∪ 直近 5 分の timestamp 窓** (2026-05-31 commit 1267bd0 で H.S. 指定により current-turn-only から拡張、 毎 turn 再 invoke の friction 解消)。 拡張子あり file は auto-detect、 拡張子なし file のみ declare 要。 memory_routing_gate の JSON-deny/fail-open 継承・stop_checks の current-turn 解析流用。 **spike (advisory 版) は誤設計ゆえ破棄済**。 full 設計は plan file 参照
- [~] declare-and-proceed gate: PreToolUse(`^AskUserQuestion$`) `declare_and_proceed_gate.py` 実装・commit 済 (2026-05-31 commit 1d3243b)。 deploy のみ残 (下記)。 `subagent_gate_warn.py` の twin だが **非 block の additionalContext** (model 可視・PreToolUse で v2.1.9 以降サポートと findings+docs で verify 済) で /declare-and-proceed へ nudge。 narrow-recall/high-precision: CONFIRM (「これで良い?」「進めて良い?」「この方針で良い」系) + ROUTING (「どちらから調査」「A経由かB経由か」系) のみ発火、 open which-X の design 質問 / force-push pre-approval / user-taste / wrong-tool / malformed は silent pass (smoke 7/7 通過)。 managed-settings に `^AskUserQuestion$` matcher 追加済 (JSON valid)。 **deploy 未了**: auto mode classifier が sudo での `/etc/claude-code/` hook 配置＋managed-settings 上書きを self-modification として deny (auto-mode-denial-recovery: classifier 自身の gate ゆえ settings 追加では迂回不可、 H.S. の手動 `!` 実行が必要)。 deploy cmd は `sudo install -m 0755 files/claude_managed-hooks/declare_and_proceed_gate.py /etc/claude-code/hooks/` ＋ `sudo install -m 0644 files/claude_managed-settings.json /etc/claude-code/managed-settings.json` (注: live target は `managed-settings.json`、 install script の `copy --nobackup` 行と一致)。 deploy 後に実機で AskUserQuestion 発火→nudge を観察。 bg adversarial review は denial で cancel されたので未実施 — deploy 前に再 spawn 推奨
- [ ] stop_checks 拡張: provide-user-instructions family (host-command phrase が fenced block 外、 warn) + verify-before-claim positive side (網羅した 等、 warn)。 既存 family+pairing+advise-once 再利用
- [ ] UserPromptSubmit concern/correction injector (任意・観測後・最低 leverage・最大 noise risk): `memory_surface.py` に **1 block 統合** (tight phrase set)。 illuminate-not-reassure/memory-routing の trigger 半分のみ raise、 discipline body は semantic 残
- [ ] CUT: attribute-existing-issues の PreToolUse arm (SKIP 条件 = pattern が真に既存 AND session 未触、 git-blame 要で FP) → Stop warn のみに留める
- [ ] 各機構ごと smoke (emit-vs-comply 計測、 fail-open) → commit → cover された skill / memory entry を OLD 移動 (memory-routing)

経緯: 2026-05-28/29 session b188f677 で user 提起: 「信用を高めるためのスキルをたくさん作ったのだけれど、 それを高確率で発火できないシステム上の問題があるようだから、 そこをなんとかできると、 本当はベスト。 発火できなければ無価値」。 本 session でも writing-code/writing-python を .py hook 編集前に invoke 漏らした (= 本 task が解く問題の live 実例。 debug-guardrail 分析: ambient trigger 低 salience + 親 skill frame crowding + tool 層 enforcement 不在 = self-recall 構造不信頼)。

Work file: `last-session-handoff.md` の 「skill 発火率 system 対策」 section ＋ plan `~/.claude/plans/breezy-bubbling-quiche.md` (skill-active gate の full 設計 + 本 session の訂正 + 次 session 手順の durable copy)

### advisory hook for evaluative term post-hoc check

Goal: LLM output 内の評価語 (`大改造` / `影響大` / `アーキテクチャ再設計系` / `改造が少ない`) を Stop hook で捕捉し、 同 turn に証拠 tool (EVIDENCE_TOOLS) が無ければ block して report-by-evidence へ誘導する。 Stop の model 到達 channel は exit2 / decision:block の 2 つだけで両方 block と一次資料で確定 → soft 不可 → block route + `stop_hook_active` advise-once gate で自己 block loop を断つ設計に pivot 済 (H.S. 承認)。

Exit Criteria:
- [x] Stop hook spec 一次資料確認 (stop_hook_active 意味論 / exit2・decision:block の 2 channel / additionalContext は Stop 非対応 / 8-block override cap)
- [x] hook 実装: 評価語 family (bare-term, EVIDENCE_TOOLS free-pass) + 全 block family への advise-once gate + docstring rewrite (commit f1dab94, e2800b8 を rebase で rewrite)
- [x] settings/copy 行は不要と確認 (`copy_dir claude_managed-hooks/` で hooks dir 丸ごと deploy 済、 既存 file 改造ゆえ新規 wiring 不要)
- [x] smoke 12/12 (block / free-pass / 既存 family 無回帰 / stop_hook_active demote + marker 1-bump guard / 評価語 影響大(?!き) で形容詞除外)
- [x] bg `/code-review` triage 完了 (confirm-intent: 全 family advise-once は意図的・docstring に regression-proof 明記 / 影響大(?!き) で形容詞 影響大きい 除外 / `_check` を warnings·blocking 分離返しに refactor → f1dab94 に fixup-autosquash / plan 文発火は accept (v1) / no-defect 確認)。 session 自己終了済
- [ ] deploy: 別 session で `copy_dir claude_managed-hooks/` 再実行 (本 session は評価語討議中で live deploy = 即自己 block のため defer) → deploy で f1dab94 が live 化
- [ ] 実機確認: deploy 後、 table cell に評価語 + 証拠なし → block、 retry で advise-once pass を観測
- [ ] (candidate) `/tmp/smoke_stop_checks.py` を committed regression test 化するか判断 (現状 repo に hook test 基盤なし、 cross-hook 不変条件 = 価値あり)
- [ ] (v1 known-FP, 観測ベース): `アーキテクチャの見直しを行います` 等の plan 文も発火 (advise-once で 1 回 backstop)。 観測増えたら predicate-proximity で tighten 検討

経緯: 2026-05-28 session で「大改造」 を実コード未読で発話 → report-by-evidence 違反。 既存 skill trigger は文末 judgment 想定で structured doc (table cell) の評価語混入が射程外。 hook 化で補完。

Work file: `last-session-handoff.md` + commit f1dab94。 残 = deploy (別 session) + 実機確認

### turn counter (UserPromptSubmit) 表示 regression

Goal: `memory_surface.py` の UserPromptSubmit turn marker (`_turn_marker` → systemMessage「Turn #N starting」) が通常の prompt 送信時に表示されず workflow 完了通知等の変な箇所に紛れて出る regression を root-cause 究明し修正する (Stop hook 側 `stop_checks.py` `_emit_turn_marker` は正常表示)。

Exit Criteria:
- [x] root cause 究明 (一次資料/log・workflow forensics wtd0adknm で確定): 原因は **systemMessage channel**。UPS marker は当初 (b8ad39d) から一貫して `systemMessage` 経由 (= channel regression は無し)。fullscreen TUI は UPS の systemMessage を inline 描画しない**未文書 CC rendering gap** (closed-as-stale issue #16289 SubagentStop と同型・changelog 2.1.139-158 に修正無し)。Stop は turn 末の安定スロットで描画されるため出る。「変な所に出た」= dynamic workflow 完了が合成 `<task-notification>` を prompt 経路注入し marker 発火 (forensics L421→L422)。throttle/RMW 競合は無関係と反証済 (marker は throttle 対象外・11/11 で 1:1)
- [x] 修正 (commit 399a42e): marker を `systemMessage` → **`additionalContext`** (model 可視・TUI が実 surface する channel) に移動、memory-surface と 1 つに merge。`_turn_marker` に合成 `<task-notification>` prompt の gate 追加。smoke: real→marker via additionalContext / synthetic→gated / no-transcript→fail-open / combined merge OK。deploy 済 (`~/.claude/hooks/memory_surface.py` と diff 一致)
- [ ] 実機確認: deploy は本 turn 実行ゆえ本 turn の hook は旧 code で発火済。**次 prompt 以降**で additionalContext に「Turn #N starting」が私の context に出るか H.S. と観察 (= H.S. 依頼の「しばらくデバッグ」)

経緯: 2026-05-30 H.S. 観測「Stop hook の turn counter は表示されるが UserPromptSubmit hook の turn counter が出ていない (regression)。 start の turn counter が変な所に出た — Dynamic workflow completed 通知に『18:03:35 Turn #4 starting (3 sec passed since the last stop)』と紛れた」。H.S. 指定: **後で調査** (skill-active gate 完了後)。2026-05-31 究明・修正完了 (上記)。

Note: H.S. 提案「systemMessage を LLM 可視 message に変えてデバッグ」が正解だった (= additionalContext 化)。当初の私の「hook では直せない (CC rendering 制約)」判定は誤りで、channel 変更で解決。

Work file: `last-session-handoff.md` の turn counter section。canonical source = `files/claude_user-hooks/memory_surface.py` (`_turn_marker` / `_main_query`)、比較 = `files/claude_managed-hooks/stop_checks.py` (`_emit_turn_marker`)。

## Medium

### memory entry: evaluative term in table cell の違反事例

Goal: 2026-05-28 session で発生した「比較表 cell に評価形容詞 (`大改造`) を ungrounded で混入」 事例を memory entry に save、 advisory hook 完成までの reminder とする。

Exit Criteria:
- [ ] `feedback_evaluative_term_in_table_cell.md` を user memory (`~/.claude/memory/`、 cross-project applicable な評価語 hedge pattern) に作成
- [ ] user MEMORY.md index に新 entry を追加 (user explicit authorize 必要)
- [ ] hook DB sync (`memory_surface.py --upsert`)

Note: 上記 High task (advisory hook) 完成後は本 entry を `~/.claude/memory/OLD-MEMORY.md` に移動 (= memory-routing rule 通り、 Managed hook で cover された退役 entry)

Work file: 現 session の議論

### SKILL_HOOK_CONTRACT.md パターン集

Goal: repo 直下に `SKILL_HOOK_CONTRACT.md` を作り、 hook/skill の**実装 contract** 再利用パターンを集約して一貫性を担保する (2026-05-30 H.S. 依頼)。

Exit Criteria:
- [ ] `SKILL_HOOK_CONTRACT.md` を repo 直下に作成。 含める実装 contract: capability-grant (skill/declare が mint・hook が check, fail-open) / permission semantics (additionalContext 省略=passthrough・deny は JSON・allow は auto-approve 回避) / session-keyed state (`$CLAUDE_CODE_SESSION_ID`==payload session_id) / transcript current-turn scan (stop_checks 方式) / fail-open (例外 exit0・deny は JSON) / deny-wording 規律 / extensible `LANGUAGES` dispatch table / **use-case 駆動の TTL 選定 (盲目流用しない)** / PostToolUse sync
- [ ] **除外を厳守** (H.S. 指摘・種類が違う): deploy の決まり (`copy_dir`・exec-bit 0755・settings `copy`) は contract でなく **deploy ルール** ゆえ混ぜない

Note: draft は skill-active gate (`skill_reminder_gate.py`) 確定後が自然 (それが grant/declare パターンの最新例)。

Work file: plan `~/.claude/plans/breezy-bubbling-quiche.md` の「並行 deliverable」節
