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
- [x] feature-research dispatch fail: **root cause 確定 + fix 完了・実機検証済 (2026-05-29 session2、commit `0b0fe9b`、rebase 前 c6bb0db)** — `user_prompt` に inline 埋込んだ CHANGELOG (341,668 byte) が Linux `MAX_ARG_STRLEN` (131072 固定) 超過で `execve` E2BIG → `claude --bg` が起動前失敗。hook は `\|\| true` + `2>/dev/null` + exit code 非チェックで完全 silent 化 (commit `5a3b96f`「Capture CHANGELOG inline」起因)。fix: dump を `--add-dir` 配下 file へ出し Read させ argv 縮小 + CHANGELOG を awk で delta range trim (342KB→~15KB) + `trap EXIT`/reaper で context file cleanup 徹底 + dispatch stderr/rc を `dispatch.log` 記録。verify: cache clear → deployed hook 実行で id `c948e50f` 取得・508KB context file 生成・`dispatch.log` 空・child reap・cascade なし
- [ ] **deploy script integration** (`ubuntu2404-wsl.sh` / `debian12.sh` に `files/claude-emergency-stop` → `/usr/local/bin/claude-emergency-stop` の install 行追加、 CLAUDE.md 「deploy 先だけ編集して repo を放置するな」 厳守)

> **2026-05-29 session2 user 指示**:
> - **#1 (env vs file guard 判別、上記 L15 criterion) は保留** — risky な bg 再trigger 実験の safety net である emergency-stop が **未承認 + 有効性に疑義**。承認・有効性検証 (上記 L13 criterion) が済むまで #1 着手不可。
> - **deploy script integration も「このまま」不可** — emergency-stop の内容が未承認のため、install 行追加の前に emergency-stop の **内容レビュー + 有効性検証 (L13) + user 承認** が前提。
> - 着手順: **feature-research fix (root cause 確定済) → deploy 統合 (emergency-stop 承認後)**。

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

### ターン数の chat 表示 hook (UserPromptSubmit) (2026-05-29 session2 user 要望)

Goal: 現在のセッションの **ターン数 + 現在時刻 + 前回ターンからの経過時間** を、 LLM context に渡らない形でチャット画面に表示する (旧称「statusline にターン数」は obsolete — statusline は 1 行幅が厳しく chat 挿入に変更)。

Exit Criteria:
- [x] 仕様調査完了 (workflow `wf_7b53c4e1-0d4` + `wf_309fe061-3dc`、 source `code.claude.com/docs/en/hooks`): (1) statusLine payload に直接 turn-count field 無し; (2) hook 出力チャネルの LLM 可視性 — **`systemMessage` は user 表示・LLM 非可視** (docs verbatim "A systemMessage field is shown to you, not to Claude")、 `additionalContext` は逆 (LLM 可視・chat 非表示) → **chat 挿入は systemMessage を使う**
- [x] 設計確定: `UserPromptSubmit` hook (turn 毎 1 回・非 re-entrant・`session_id`/`transcript_path`/`cwd` 取得可) が transcript と同 dir の per-session counter file を flock→read→count+1+last-epoch→write し、 `{"systemMessage":"⟳N · HH:MM:SS · +Δs"}` を exit 0 で emit
- [x] 実装 + smoke + deploy + commit (`b8ad39d`): `turn_counter.py` (`<transcript>.turns` を flock RMW、 fail-open で prompt を絶対 block しない) + managed-settings の `UserPromptSubmit` に登録 + /etc deploy sync。 smoke: count 増分・初回 start・seed 65s で +1m05s・systemMessage のみ (LLM 非可視)・malformed→無出力 exit 0
- [x] **実機確認 (2026-05-29 session3)**: 新 session 開始時の実機 trigger で hook が `/bin/sh: ... turn_counter.py: Permission denied` で fail。 root cause = source が git 上 100644 で commit されていた (sibling hook は全 100755)、 `copy_dir` は `cp -r` で source mode を保存するため /etc deploy も 644 → bare-path 起動の exec 拒否。 **fix 完了 (commit `6cdfad3`)**: canonical source に実行ビット (両 deploy script は `copy_dir` 共有のため source mode 1 修正で cover) + live /etc を sudo chmod 755 + deployed hook smoke (⟳1 start → ⟳2 +1s, exit 0)。 残: live fix 後の次プロンプトで **systemMessage が chat に表示されるか + rendering が煩くないかを user が目視確認** (systemMessage は LLM 非可視のため私からは観測不可)。 OK なら close、 不満なら format/event 調整
- [x] **format 改修 (2026-05-29 session3、 commit `03bde12`)**: live 確認で user feedback — (1) `⟳`/`·` glyph が端末で文字化け、 (2) format 不満。 新 format に変更: `HH:MM:SS Turn #N Context <n>K (<gap> passed since the last prompt)` (pure ASCII で文字化け解消、 gap は sec/min/hr の人間可読、 turn1 は `(first prompt)`)。 **context size は statusline.sh の出力 cache (`~/.cache/claude-tui-statusline/stdin.json` の `.stdin.context_window.total_input_tokens`) から取得** (前 session 決定通り)、 cache 無時は Context field を省略。 smoke 4 ケース pass (Context 142K 表示 / cache 無で省略 / 65s→`1 min` / exec bit 維持)。 → **user が live で新 format を確認し「close して」指示 = 文字化け解消・format 妥当を承認 (2026-05-29 session3)**

Work file: `files/claude_managed-hooks/turn_counter.py`、 `files/claude_managed-settings.json`、 `files/claude_statusline.sh`(context cache source)、 `last-session-handoff.md`(次 session の実機確認 step)

## Medium

### memory entry: evaluative term in table cell の違反事例

Goal: 2026-05-28 session で発生した「比較表 cell に評価形容詞 (`大改造`) を ungrounded で混入」 事例を memory entry に save、 advisory hook 完成までの reminder とする。

Exit Criteria:
- [ ] `feedback_evaluative_term_in_table_cell.md` を user memory (`~/.claude/memory/`、 cross-project applicable な評価語 hedge pattern) に作成
- [ ] user MEMORY.md index に新 entry を追加 (user explicit authorize 必要)
- [ ] hook DB sync (`memory_surface.py --upsert`)

Note: 上記 High task (advisory hook) 完成後は本 entry を `~/.claude/memory/OLD-MEMORY.md` に移動 (= memory-routing rule 通り、 Managed hook で cover された退役 entry)

Work file: 現 session の議論
