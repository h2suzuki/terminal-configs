# Todos

## Critical

### cascade incident 後処理 (2026-05-28 / 29 cross-day、 originSessionId b188f677)

Goal: 2026-05-28 の lint hook cascade (daemon.log day total 179 `bg claimed-spare` events、 中心 window 03:17-19 UTC で 42 events、 supervisor restart で `bg adopt: adopted=26 respawned=0 dead=0`) の (1) 復元 (退避 hook + 削除 settings entry を元に戻す)、 (2) file-based recursion guard の修正確認 (= 「同じこと」 = `claude --bg "Hello..."` 起動 で cascade 再発しないこと の実機 verify)、 (3) 真の root cause mechanism の verify、 を完了。

Exit Criteria:
- [x] settings.json SessionStart 元 3 entry 復元 (canonical edit + sudo cp deploy)、 `diff` で source / deploy 同期確認 (2026-05-29)
- [x] 修正確認: cache reset + `claude --bg "Hello, briefly introduce yourself..."` 起動 → daemon.log delta=2 (dummy + 1 lint child)、 child 内で再 dispatch なし = **cascade 防止確認** (2026-05-29 12:38、 evidence: daemon.log `bg claimed-spare a22a7c38 / c37a6787` の 2 event のみ)
- [x] cascade root cause mechanism verify **完了 (2026-05-30)**: claude-code-guide doc 調査で確定 — daemon worker は dispatch client の inline env 非継承 (agent-view.md、 E9) / managed hook は `--setting-sources` 不可侵 (settings.md・hooks.md「What Cannot Be Disabled via CLI」、 E10) / git で両 guard が cascade 前 (`eaa9d4d` 05-25) から存在し無効と独立裏付け (E11)。 ledger 「推測領域」→「## mechanism (直接 evidence)」 に格上げ済
- [x] env-vs-file guard 判別 **完了 (2026-05-30)**: E9 より env guard は child に届かず不発火 = 再 dispatch を停めたのは **file-based LOCK_FILE guard** (C4)。 file-based 設計の妥当性を一次資料で裏付け
- [x] guard 実効性 両パス実証 **完了 (2026-05-30、 H.S. 要件)**: 原 cascade は hook 起点でなく私の直接 `claude --bg` 起点 (H.S. 記憶、 E3 と整合) のため hook 起点と直接実行の双方で実証。 (A) offline stub 4 ケース全 PASS (cold→1 / fresh-lock→0 / env→0 / stale→1+refresh) / (B) live probe `claude --bg` → daemon.log claimed-spare 2 件 (probe+lint child) で頭打ち・3 件目なし・adopt/respawn/dead=0・cascade なし (E12)
- [x] feature-research dispatch fail: **root cause 確定 + fix 完了・実機検証済 (2026-05-29 session2、commit `0b0fe9b`、rebase 前 c6bb0db)** — `user_prompt` に inline 埋込んだ CHANGELOG (341,668 byte) が Linux `MAX_ARG_STRLEN` (131072 固定) 超過で `execve` E2BIG → `claude --bg` が起動前失敗。hook は `\|\| true` + `2>/dev/null` + exit code 非チェックで完全 silent 化 (commit `5a3b96f`「Capture CHANGELOG inline」起因)。fix: dump を `--add-dir` 配下 file へ出し Read させ argv 縮小 + CHANGELOG を awk で delta range trim (342KB→~15KB) + `trap EXIT`/reaper で context file cleanup 徹底 + dispatch stderr/rc を `dispatch.log` 記録。verify: cache clear → deployed hook 実行で id `c948e50f` 取得・508KB context file 生成・`dispatch.log` 空・child reap・cascade なし

> **2026-05-30 session (originSessionId 793504ee) update — emergency-stop 廃止**: emergency-stop script を multi-agent audit にかけ致命的欠陥多数を確認 (step1 が誤 path `/etc/claude-code/settings.json` で no-op / step4 が step3 で停止した daemon を respawn / step2 が daemon stop 前で race / step5 pkill が無関係プロセス誤爆 / そもそも未 deploy・未 invocable)。 H.S. 判断で:
> - deployed binary (`/usr/local/bin/claude-emergency-stop`) 削除 + `.claude/settings.local.json` allowlist entry 除去、 canonical source (`files/claude-emergency-stop`) も `git rm` 済
> - 正しい最小手順を **manual runbook** 化し ledger `feedback_setting_sources_does_not_disable_managed.md` の 対策(C) + 「緊急停止 runbook」 section に保存
> - 旧 Exit Criteria 「緊急 hook install」「緊急 hook 実機 verify」「deploy script integration」 を退役 (検証 / deploy 対象が消滅)
> - 副次発見: audit で本 cascade ledger の citation 誤り 3 件 (E6 path / C2 欠番 E5 / C3 誤引用 E6) を修正。 過去「evidence-grounded」と判定された script が依拠した台帳自体に誤記があった
> - 残 open criterion: cascade root cause mechanism verify と env-vs-file guard 判別 の 2 件。 旧 instruction の「emergency-stop 承認まで guard 判別を保留」 は前提消滅。 risky な再trigger 実験の safety-net は manual runbook に置換。 再着手是非は H.S. 判断

進捗 (本 session 完了分):
- [x] cascade 物理停止 (hook file mv to /tmp 後 agents=0、 2026-05-28T03:23:29Z)
- [x] root cause partial 究明 (env-based guard 不発火 = 直接 evidence、 daemon adopt 機構 = daemon.log で確認、 hook file 物理不在 が決定的 = E7)
- [x] hook script に file-based recursion guard 追加 (lint + feature-research、 canonical edit 完了、 `/etc/claude-code/hooks/` deploy 済)
- [x] findings.md restore (backup `findings.md.bak.before-fix-verify` から)
- [x] 緊急 hook `claude-emergency-stop` 実装 (2026-05-29) → **2026-05-30 audit で欠陥多数と判明し削除**。 当時の subagent review 「evidence-grounded, not vibes」 判定は誤りだった (依拠 ledger に E6 誤 path / C3 誤引用、 step1 が実環境で no-op)
- [x] memory entry 5 + 1 file (4 user + 2 project) を memory-routing rule に従い整備 + hook DB sync (--upsert 個別 + --rebuild 整合)
- [x] settings.json SessionStart 復元 + deploy + diff sync 確認
- [x] 緊急 hook install + allowlist + path 検証 (2026-05-29) → **2026-05-30 削除・allowlist 除去**
- [x] 修正確認 実機 verify (cache reset + 再 trigger + delta=2 観測、 cascade 防止確認、 ただし mechanism 判別未了)

Work files:
- `/home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/memory/feedback_setting_sources_does_not_disable_managed.md` (cascade 直接 evidence ledger + 推測領域)
- `/home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/memory/reference_claude_code_permission_modes.md` (permission-mode 6 候補 reference)
- `/home/h2suzuki/.claude/memory/feedback_no_other_work_or_worsening_commands_during_emergency.md` (緊急時行動 規律)
- `/home/h2suzuki/.claude/memory/feedback_under_report_and_speculation_in_painful_situations.md` (報告 honesty 規律)
- `/home/h2suzuki/.claude/memory/feedback_memory_entry_written_without_verify.md` (durable artifact verify 規律)
- `/home/h2suzuki/.claude/memory/feedback_try_host_ops_before_delegating.md` (host-side ops 試行 規律)
- `files/claude_managed-hooks/claude-md-lint.sh` (file-based guard 追加版)
- `files/claude_managed-hooks/claude-code-feature-research.sh` (file-based guard 追加版)
- `~/.claude/daemon.log` (cascade source-of-truth log、 cascade 期間: 2026-05-28T03:03-03:23 UTC)
- chat log: `/home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/b188f677-a99f-4ab0-a225-2f73aa4e13a3.jsonl`
- `last-session-handoff.md` (handoff doc、 次 session 再開 5 分以内)

Notes:
- 修正確認 verify: 2026-05-29 (delta=2) + 2026-05-30 offline 4 ケース / live probe で cascade 防止再実証。 「どちらの guard が効いたか」 は file-based と判別済 (C4)、 root cause mechanism も verify 済 (ledger ## mechanism)。 残置 2 点 (過去非発火理由 / adopt の SessionStart 発火) は file guard が理由不問で防ぐため実効性低と判断し未 verify
- 退避 hook (`/tmp/{claude-md-lint,claude-code-feature-research,claude-code-feature-research-prompt,session_resume_context}.{sh,md,py}.disabled`) は復元 sudo cp で /etc 上書き済、 退避 file は session 末まで残置 (rollback evidence 用)、 別 session で cleanup

## High

### skill 発火率 system 対策

Goal: 既存 skill (verify-before-claim / report-by-evidence / scope-mismatch-detector / illuminate-not-reassure / 他) と 本 session で追加した user memory entry 4 個が、 LLM の「trigger 該当時の self-invoke」 に依存して発火率低い問題への system 対策を設計 + 実装。

Exit Criteria:
- [ ] system 設計案を 2-3 案 verbalize (例: Stop hook で output pattern match + advisory inject、 UserPromptSubmit hook で trigger keyword 強調、 等)、 各案の cost / 効果を `rejection-via-actual-cost` skill に従い評価
- [ ] user に設計案提示 + 合意
- [ ] 実装 (`files/claude_managed-hooks/` + settings.json wiring + deploy script) + smoke test (false positive / false negative の率を実機計測)
- [ ] commit
- [ ] hook で cover された skill / memory entry を OLD 移動 (= memory-routing rule 通り)

経緯: 2026-05-28/29 session b188f677 で user 提起: 「信用を高めるためのスキルをたくさん作ったのだけれど、 それを高確率で発火できないシステム上の問題があるようだから、 そこをなんとかできると、 本当はベスト。 今回の緊急対応も、 非常に良い経験になるフローで、 セッションを振り返ってスキル化できたとしても、 発火できなければ無価値」。 本 session 内で私が writing-todos / memory-routing / report-by-evidence 等の trigger 該当時に invoke 漏らした事例多数。

Work file: 本 entry が単独 reference (chat log U[1155])

### advisory hook for evaluative term post-hoc check

Goal: LLM 最終 output 内の evaluative term (`大改造` / `軽微` / `影響大` / `アーキテクチャの見直し` 等) を Stop hook で pattern match して advisory feedback を返し、 次 turn の self-correction の材料にする (deny でなく soft、 false positive 許容)。 上記 High task (skill 発火率 system 対策) の特殊 case として、 統合候補。

Exit Criteria:
- [ ] Stop hook の event spec を一次資料で確認 (`code.claude.com/docs/en/hooks-guide`: payload 形、 `additionalContext` / `systemMessage` 出力規約)
- [ ] hook script 実装 (`files/claude_managed-hooks/` 配下、 pattern match + advisory message 出力、 deny フィールドは設定しない)
- [ ] `files/claude_managed-settings.json` に hook 登録、 deploy script (`ubuntu2404-wsl.sh` / `debian12.sh`) の `copy` 行追加
- [ ] 実機で evaluative term を含む output → advisory が次 turn additionalContext に出ることを確認

経緯: 2026-05-28 session で「大改造」 を実コード未読で発話 → user 指摘で `report-by-evidence` skill 違反確定。 既存 skill の trigger は文末 judgment 想定で structured doc (table cell) の評価語混入が射程外。 user 指針「skill 減・hook 増・trigger 単純化」 に従い hook 化で対応。

Work file: 現 session の議論 (本 entry が単独 reference)

## Medium

### memory entry: evaluative term in table cell の違反事例

Goal: 2026-05-28 session で発生した「比較表 cell に評価形容詞 (`大改造`) を ungrounded で混入」 事例を memory entry に save、 advisory hook 完成までの reminder とする。

Exit Criteria:
- [ ] `feedback_evaluative_term_in_table_cell.md` を user memory (`~/.claude/memory/`、 cross-project applicable な評価語 hedge pattern) に作成
- [ ] user MEMORY.md index に新 entry を追加 (user explicit authorize 必要)
- [ ] hook DB sync (`memory_surface.py --upsert`)

Note: 上記 High task (advisory hook) 完成後は本 entry を `~/.claude/memory/OLD-MEMORY.md` に移動 (= memory-routing rule 通り、 Managed hook で cover された退役 entry)

Work file: 現 session の議論
