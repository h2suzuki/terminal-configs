# Todos

## Critical

### feature-cache-rename — bg dispatch verify

Goal: 新規 `claude` session で SessionStart hook の bg dispatch が permission ask なしで走り、 `~/.cache/claude-code-feature-research/findings.md` が生成されることを実機 verify する。

Exit Criteria:
- [ ] 新規 session 起こして bg dispatch が走った (`claude agents --json` で `busy` または `idle`)
- [ ] 10 分後に `~/.cache/claude-code-feature-research/findings.md` が生成されている

進捗 (root cause fix 関連、 Exit Criteria とは別):
- [x] root cause 特定: `acceptEdits` 射程は file edit + filesystem command のみ、 WebFetch は対象外で permission ask が出て detached bg session で stall (一次資料: `code.claude.com/docs/en/permissions`)
- [x] hook 改造 (CHANGELOG-driven selective fetch): `capture_changelog()` 追加、 `--tools Read,Write` (WebFetch 削除)、 prompt-md の Sources / Process / Failure modes 改訂
- [ ] `/etc/claude-code/hooks/` への deploy 完了 (sudo cp 必要、 user 操作待ち)

Work file: `last-session-handoff.md`

## High

### advisory hook for evaluative term post-hoc check

Goal: LLM 最終 output 内の evaluative term (`大改造` / `軽微` / `影響大` / `アーキテクチャの見直し` 等) を Stop hook で pattern match して advisory feedback を返し、 次 turn の self-correction の材料にする (deny でなく soft、 false positive 許容)。

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
- [ ] `feedback_evaluative_term_in_table_cell.md` を `/home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/memory/` に作成 (違反事例 + scope: 構造的 risk「比較表 / list の cell に評価語混入」 + 対策: advisory hook が cover)
- [ ] MEMORY.md index に新 entry を追加

Note: 上記 High task (advisory hook) 完成後は本 entry を OLD-MEMORY.md に移動 (skill / hook で cover される設計通り、 `memory-routing` skill 参照)

Work file: 現 session の議論
