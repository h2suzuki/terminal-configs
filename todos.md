# Todos

## Critical

## High

### memory entry 書式の決定論的 enforcement hook (設計検討中・詳細未合意)

Goal: memory-routing を使わず (skill self-invoke 漏れで) memory entry を直接 Write/Edit しても、 正しい書式 (reminder:/keywords:) と DB 同期が決定論的に担保される hook を設計・実装。 今 session 完成の retrieval 層 (reminder/keywords surface) の上に乗る hard enforcement 層。

現状: たたき台スケッチのみで H.S. と**詳細未合意** (次 session で詰めてから実装)。 たたき台 = PreToolUse deny (Write が reminder:/keywords: 不在なら block) + PostToolUse auto-upsert (DB sync self-heal) / warn のハイブリッド。

詰める論点 (次 session):
- deny vs warn のバランス (hard block の false-positive risk vs 確実性)、 deny を Write のみに絞るか
- Edit の扱い (差分しか来ず最終 format 判定不確実 → warn 止まりか file 再構成して判定か)
- keyword 選択性 (過度に広い語) を機械判定して warn するか・閾値化
- deny field の正確な spec (`code.claude.com/docs/en/hooks`: permissionDecision:deny / exit 2)
- path 判定範囲 (`~/.claude/memory/*.md` ・`projects/*/memory/{feedback,reference,project}_*.md`、 MEMORY.md/OLD-MEMORY.md 除外)

Exit Criteria (合意後):
- [ ] 上記論点を H.S. と解決し設計合意
- [ ] hook 実装 (`files/claude_managed-hooks/`) + `files/claude_managed-settings.json` の Pre/PostToolUse 登録 + deploy script copy 行
- [ ] 実機 smoke (deny / 通過+auto-upsert / Edit warn / fail-open)

経緯: 2026-05-30 session (793504ee) で reminder/keywords 移行 (retrieval 層) 完成後、 H.S.「memory-routing 未使用で書いた時 detect/deny できるか」提起。 broad「skill 発火率 system 対策」の memory 特化・skill 起動非依存の決定論的 enforcement 具体例。

Work file: last-session-handoff.md

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
