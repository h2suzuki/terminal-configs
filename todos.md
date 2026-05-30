# Todos

## Critical

## High

### skill 発火率 system 対策

Goal: 既存 skill (verify-before-claim / report-by-evidence / scope-mismatch-detector / illuminate-not-reassure / 他) と 本 session で追加した user memory entry 4 個が、 LLM の「trigger 該当時の self-invoke」 に依存して発火率低い問題への system 対策を設計 + 実装。

Exit Criteria:
- [x] system 設計: 4-layer 設計を adversarial 監査込みで確定 (2026-05-30 workflow w3zrkuwwh)。 核心原則 = 「trigger が機構的に検出できる skill は check を hook に移して発火依存を消す」 (raise でなく eliminate)。 23/27 skill が trigger 機構検出可、 真の semantic residual は 4 個。 全 layer / build order / must-have 3 性質 / cut / residual は handoff doc 参照
- [ ] L1 (最優先・本 session の writing-code/python 漏れを直撃): PreToolUse(Edit|Write|MultiEdit) `skill_reminder_gate.py` — file_path → 該当 skill 名を additionalContext で **1 consolidated block** 提示 (source→writing-code / .py→+writing-python / .sh|shebang→+writing-bash / writing-tests の paths glob→+writing-tests / `*/skills/*/SKILL.md`・hook path→+writing-skills / todos.md→writing-todos)。 `read_before_edit.py` の _emit_allow/_canonical/_extract を clone、 allow-only、 同 file 同 session throttle (habituation 対策)。 既存 `^(Edit|Write|MultiEdit)$` matcher に append
- [ ] L2: PreToolUse(`^AskUserQuestion$`) `declare_and_proceed_gate.py` (`subagent_gate_warn.py` の twin、 additionalContext で /declare-and-proceed)
- [ ] L3: `stop_checks.py` 拡張 — provide-user-instructions family (host-command phrase が fenced block 外、 warn) + verify-before-claim positive side (網羅した 等、 warn)。 既存 family+pairing+advise-once 再利用
- [ ] L4 (任意・観測後・最低 leverage・最大 noise risk): UserPromptSubmit concern/correction injector を `memory_surface.py` に **1 block 統合** (tight phrase set)。 illuminate-not-reassure/memory-routing の trigger 半分のみ raise、 discipline body は semantic 残
- [ ] CUT: attribute-existing-issues の PreToolUse arm (SKIP 条件 = pattern が真に既存 AND session 未触、 git-blame 要で FP) → Stop warn のみに留める
- [ ] 各 layer ごと smoke (emit-vs-comply 計測、 fail-open) → commit → cover された skill / memory entry を OLD 移動 (memory-routing)

経緯: 2026-05-28/29 session b188f677 で user 提起: 「信用を高めるためのスキルをたくさん作ったのだけれど、 それを高確率で発火できないシステム上の問題があるようだから、 そこをなんとかできると、 本当はベスト。 発火できなければ無価値」。 本 session でも writing-code/writing-python を .py hook 編集前に invoke 漏らした (= 本 task が解く問題の live 実例。 debug-guardrail 分析: ambient trigger 低 salience + 親 skill frame crowding + tool 層 enforcement 不在 = self-recall 構造不信頼)。

Work file: `last-session-handoff.md` の 「skill 発火率 system 対策」 section

### advisory hook for evaluative term post-hoc check

Goal: LLM output 内の評価語 (`大改造` / `影響大` / `アーキテクチャ再設計系` / `改造が少ない`) を Stop hook で捕捉し、 同 turn に証拠 tool (EVIDENCE_TOOLS) が無ければ block して report-by-evidence へ誘導する。 Stop の model 到達 channel は exit2 / decision:block の 2 つだけで両方 block と一次資料で確定 → soft 不可 → block route + `stop_hook_active` advise-once gate で自己 block loop を断つ設計に pivot 済 (H.S. 承認)。

Exit Criteria:
- [x] Stop hook spec 一次資料確認 (stop_hook_active 意味論 / exit2・decision:block の 2 channel / additionalContext は Stop 非対応 / 8-block override cap)
- [x] hook 実装: 評価語 family (bare-term, EVIDENCE_TOOLS free-pass) + 全 block family への advise-once gate + docstring rewrite (commit f1dab94, e2800b8 を rebase で rewrite)
- [x] settings/copy 行は不要と確認 (`copy_dir claude_managed-hooks/` で hooks dir 丸ごと deploy 済、 既存 file 改造ゆえ新規 wiring 不要)
- [x] smoke 12/12 (block / free-pass / 既存 family 無回帰 / stop_hook_active demote + marker 1-bump guard / F2 形容詞除外)
- [x] bg `/code-review` triage 完了 (F1 confirm-intent=全 family advise-once は意図的・docstring に regression-proof 明記 / F2 影響大(?!き) で形容詞 影響大きい 除外 / F4 `_check` を warnings·blocking 分離返しに refactor → f1dab94 に fixup-autosquash / F3 accept-v1 / F5 no-defect)。 session 自己終了済
- [ ] deploy: 別 session で `copy_dir claude_managed-hooks/` 再実行 (本 session は評価語討議中で live deploy = 即自己 block のため defer) → deploy で f1dab94 が live 化
- [ ] 実機確認: deploy 後、 table cell に評価語 + 証拠なし → block、 retry で advise-once pass を観測
- [ ] (candidate) `/tmp/smoke_stop_checks.py` を committed regression test 化するか判断 (現状 repo に hook test 基盤なし、 cross-hook 不変条件 = 価値あり)
- [ ] (v1 known-FP, 観測ベース) F3: `アーキテクチャの見直しを行います` 等の plan 文も発火 (advise-once で 1 回 backstop)。 観測増えたら predicate-proximity で tighten 検討

経緯: 2026-05-28 session で「大改造」 を実コード未読で発話 → report-by-evidence 違反。 既存 skill trigger は文末 judgment 想定で structured doc (table cell) の評価語混入が射程外。 hook 化で補完。

Work file: `last-session-handoff.md` + commit f1dab94。 残 = deploy (別 session) + 実機確認

## Medium

### memory entry: evaluative term in table cell の違反事例

Goal: 2026-05-28 session で発生した「比較表 cell に評価形容詞 (`大改造`) を ungrounded で混入」 事例を memory entry に save、 advisory hook 完成までの reminder とする。

Exit Criteria:
- [ ] `feedback_evaluative_term_in_table_cell.md` を user memory (`~/.claude/memory/`、 cross-project applicable な評価語 hedge pattern) に作成
- [ ] user MEMORY.md index に新 entry を追加 (user explicit authorize 必要)
- [ ] hook DB sync (`memory_surface.py --upsert`)

Note: 上記 High task (advisory hook) 完成後は本 entry を `~/.claude/memory/OLD-MEMORY.md` に移動 (= memory-routing rule 通り、 Managed hook で cover された退役 entry)

Work file: 現 session の議論
