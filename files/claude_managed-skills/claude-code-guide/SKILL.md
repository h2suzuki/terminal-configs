---
name: claude-code-guide
description: Verify Claude Code specs (hook / subagent / plugin / skill / settings / MCP / CLI) against primary sources in a fork.
when_to_use: 'TRIGGER when about to make design or adoption decisions in these areas, when about to issue a negation claim within Claude Code scope ("feature が無い" / "該当 event が無い" etc.), or when about to make a specific positive assertion about Claude Code spec ("`UserPromptSubmit` hook で X" / "`context: fork` は Y" / "`disable-model-invocation` は Z" etc.). Manual invocation: `/claude-code-guide <topic>`. SKIP for Claude API / SDK / other Anthropic products / model pricing / non-Claude-Code tools (return as out-of-scope).'
argument-hint: <topic>
arguments: topic
context: fork
agent: general-purpose
---

# Claude Code Guide

**Verify the following Claude Code spec question:** $topic

下記の protocol に従って一次情報で裏とりし、 末尾の Output 形式で報告すること。

## Process

- **公式 1 点以上を必須**、 全体で **2 点以上** で交差確認
- 1 経路で見つからなくても存在を否定しない: 公式 doc 未記載でも実機で動くケースあり、 逆に docs にあっても deprecated のケースあり — 複数経路 confirm が必須
- **conflicting** (Anthropic 内で情報が割れている) 場合は両方提示

## Sources

優先順 (上から):

1. **CLI `--help` 出力**: `claude --help` / `claude <subcommand> --help` (agents / mcp / plugins 等)
2. **`docs.claude.com`**: Anthropic 公式 docs
3. **`code.claude.com`**: Claude Code 公式 docs
4. **`github.com/anthropics/claude-code`**: docs / source code 本体 / issues / discussions / changelog / releases
5. **`claude.com/plugins`**: plugin marketplace
6. (補助) **2026 年以降のコミュニティ報告**: 個人ブログ / Reddit / X 等。 公式 1 点要件は満たさない

## Output

5 部構成で main session に返却:

1. **結論** (1-2 文): "Yes, X works as Y" / "No, X is not supported" / "Conflicting: A says X, B says Y" 等
2. **公式情報源 URL list**: cite した公式 URL を列挙
3. **確認した経路と未確認の経路**: 「CLI --help / docs.claude.com / GitHub issues は確認、 plugins / community blog は未確認」 等
4. **関連 issue / regression** (任意): GitHub issue / discussion URL + 1 行要約
5. **確信度**:
   - 「確認済」 — 公式 1 点以上 + 交差確認 2 点以上
   - 「未確認: 範囲明示」 — 公式 0 点 or 交差未達 (何が未確認か明示)
   - 「conflicting」 — 公式同士で割れている

## What to leave out

以下は scope 外として 「本 skill は Claude Code 仕様に限定」 と明示して返す:

- Claude API 一般 / SDK 仕様 (Anthropic Python SDK / TypeScript SDK 等)
- Anthropic 製品全般 (Claude consumer app / claude.ai / Console 等)
- モデル料金 / pricing
- Claude Code 以外のツール (Cursor / Aider / Codex 等)

## Reference notes

- **Claude Code の system prompt 本文は非公開** (binary 内 minify 埋込、 版別 checksum も非公開)。 Anthropic が verbatim 公開しているのは claude.ai consumer (web / iOS / Android) のみで Claude Code / API は対象外 (`platform.claude.com/docs/en/release-notes/system-prompts` 明記)。 第三者の reverse-engineered dump は非公式。 verify 対象が prompt 本文自体の case では 「非公開」 と明示し、 dump を根拠にしない (2026-05-17 一次情報検証)

## Related

- **Legacy:** user CLAUDE.md「一次情報の確認」 より
