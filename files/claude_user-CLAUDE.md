# プロジェクト横断 preference

## System prompt 起因 pain の明示的抑止

System prompt や harness reminder の指示が regression を誘発すると判明したら、その都度この CLAUDE.md チェーンに**肯定形の counter-rule** を明記する（CLAUDE.md は公式仕様上 system prompt を上書きする）。

## コミット・PUSH運用

- コミットメッセージは英語で書く

## グローバルメモリ

プロジェクト横断で適用すべき memory（LLM 一般の認知バイアス対策、ユーザーの普遍的 preference、複数プロジェクトで再現したパターンなど）は、project-local の `<project>/memory/` ではなく `~/.claude/global-memory/` に保存する。`MEMORY.md` の代わりに `INDEX.md` を使う。

- カテゴリ判断に迷う場合は project-local を優先。そうすれば、後で global に昇格させやすい
- 同じ指摘を受けたら必ず memory に保存する。既存 entry があれば追記する
- memory entry に過去事例 / 経緯を書く時は、時系列把握ができるように **絶対日付 (YYYY-MM-DD) を含める**

@./global-memory/INDEX.md
