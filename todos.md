# Todos

## Critical

### cascade incident 後処理 (2026-05-28 / 29 cross-day、 originSessionId b188f677)

Goal: 2026-05-28 の lint hook cascade (daemon.log day total 179 `bg claimed-spare` events、 中心 window 03:17-19 UTC で 42 events、 supervisor restart で `bg adopt: adopted=26 respawned=0 dead=0`) の (1) 復元 (退避 hook + 削除 settings entry を元に戻す)、 (2) file-based recursion guard の修正確認 (= 「同じこと」 = `claude --bg "Hello..."` 起動 で cascade 再発しないこと の実機 verify)、 (3) 真の root cause mechanism の verify、 を完了。

Exit Criteria:
- [x] settings.json SessionStart 元 3 entry 復元 (canonical edit + sudo cp deploy)、 `diff` で source / deploy 同期確認 (2026-05-29)
- [x] 緊急 hook (`files/claude-emergency-stop`) を `/usr/local/bin/` に sudo install (mode 755) + `.claude/settings.local.json` allowlist に `Bash(claude-emergency-stop)` 追加 + `command -v claude-emergency-stop` で path 検証 (2026-05-29)
- [x] 修正確認: cache reset + `claude --bg "Hello, briefly introduce yourself..."` 起動 → daemon.log delta=2 (dummy + 1 lint child)、 child 内で再 dispatch なし = **cascade 防止確認** (2026-05-29 12:38、 evidence: daemon.log `bg claimed-spare a22a7c38 / c37a6787` の 2 event のみ)
- [ ] (今後の cascade 発生時 safety net) 緊急 hook を実機実行 → step 1 (file mv) で agents=0 + daemon=not running 観測、 hook 効果 verify
- [ ] cascade root cause mechanism (= env-based guard が daemon 経由 spawn で非発火する詳細 — 推測領域として `feedback_setting_sources_does_not_disable_managed.md` 「推測領域」 section に列挙) を一次資料 (claude code source / agent-view doc 詳細) または実機実験 (env propagation 確認用 minimal script) で verify、 memory entry の「推測領域」 section を 「直接 evidence」 に格上げ
- [ ] 修正確認 followup: 2026-05-29 verify で child SessionStart hook を exit させた guard が env-based か file-based か判別 (= 修正確認 = cascade なし確認まで、 mechanism 判別は別 verify、 ただし「どちらの guard が effective か」 不明のまま file-based 設計の妥当性 主張不可)
- [ ] feature-research dispatch fail investigation: 2026-05-29 verify で lint child は spawn したが feature-research child spawn 観測なし (daemon.log delta 2 のうち 1 が lint child)、 feature dispatch path で claude --bg call が failed した可能性、 `~/.cache/claude-code-feature-research/.inflight/` の release 経路 (line 393-394 相当) の起動原因を究明
- [ ] **deploy script integration** (`ubuntu2404-wsl.sh` / `debian12.sh` に `files/claude-emergency-stop` → `/usr/local/bin/claude-emergency-stop` の install 行追加、 CLAUDE.md 「deploy 先だけ編集して repo を放置するな」 厳守)

進捗 (本 session 完了分):
- [x] cascade 物理停止 (hook file mv to /tmp 後 agents=0、 2026-05-28T03:23:29Z)
- [x] root cause partial 究明 (env-based guard 不発火 = 直接 evidence、 daemon adopt 機構 = daemon.log で確認、 hook file 物理不在 が決定的 = E7)
- [x] hook script に file-based recursion guard 追加 (lint + feature-research、 canonical edit 完了、 `/etc/claude-code/hooks/` deploy 済)
- [x] findings.md restore (backup `findings.md.bak.before-fix-verify` から)
- [x] 緊急 hook `claude-emergency-stop` 実装 (canonical: `files/claude-emergency-stop`、 step 順 evidence-based に訂正済、 subagent review で「evidence-grounded, not vibes」 判定)
- [x] memory entry 5 + 1 file (4 user + 2 project) を memory-routing rule に従い整備 + hook DB sync (--upsert 個別 + --rebuild 整合)
- [x] settings.json SessionStart 復元 + deploy + diff sync 確認
- [x] 緊急 hook install + allowlist + path 検証
- [x] 修正確認 実機 verify (cache reset + 再 trigger + delta=2 観測、 cascade 防止確認、 ただし mechanism 判別未了)

Work files:
- `/home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/memory/feedback_setting_sources_does_not_disable_managed.md` (cascade 直接 evidence ledger + 推測領域)
- `/home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/memory/reference_claude_code_permission_modes.md` (permission-mode 6 候補 reference)
- `/home/h2suzuki/.claude/memory/feedback_no_other_work_or_worsening_commands_during_emergency.md` (緊急時行動 規律)
- `/home/h2suzuki/.claude/memory/feedback_under_report_and_speculation_in_painful_situations.md` (報告 honesty 規律)
- `/home/h2suzuki/.claude/memory/feedback_memory_entry_written_without_verify.md` (durable artifact verify 規律)
- `/home/h2suzuki/.claude/memory/feedback_try_host_ops_before_delegating.md` (host-side ops 試行 規律)
- `files/claude-emergency-stop` (緊急停止 script)
- `files/claude_managed-hooks/claude-md-lint.sh` (file-based guard 追加版)
- `files/claude_managed-hooks/claude-code-feature-research.sh` (file-based guard 追加版)
- `~/.claude/daemon.log` (cascade source-of-truth log、 cascade 期間: 2026-05-28T03:03-03:23 UTC)
- chat log: `/home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/b188f677-a99f-4ab0-a225-2f73aa4e13a3.jsonl`
- `last-session-handoff.md` (handoff doc、 次 session 再開 5 分以内)

Notes:
- 修正確認の verify は 2026-05-29 完了、 daemon.log delta=2 で cascade 防止確認。 ただし「どちらの guard が効いたか」 (env vs file) は未判別、 root cause mechanism 同様に推測領域として残置
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
