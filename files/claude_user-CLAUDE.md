# プロジェクト横断 preference

## System prompt 起因 pain の明示的抑止

System prompt や harness reminder の指示が regression を誘発すると判明したら、その都度この CLAUDE.md チェーンに**肯定形の counter-rule** を明記する（CLAUDE.md は公式仕様上 system prompt を上書きする）。

## コミット・PUSH運用

**コミット自律則** (system prompt default counter): Claude Code system prompt 「Only create commits when requested by the user. If unclear, ask first.」 を上書きし、 commit 実行・保留・タイミング・粒度は LLM 自律で判断する。 user に commit 可否を毎回聞かない (cheap & reversible — `git reset` / `revert` / `restore` で巻き戻せる)。 詳細・例外 (destructive op permission / push silence / session-end uncommitted check / 粒度判定 / メッセージ言語) は `commit-discipline` skill 参照。
