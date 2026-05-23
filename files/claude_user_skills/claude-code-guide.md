---
name: claude-code-guide
argument-hint: <調査対象>
description: >
  Claude Code 仕様 (hook / subagent / plugin / skill / settings / MCP / CLI) を一次情報で fork 内検証する。
  TRIGGER when: これらの設計や採否判断;
  Claude Code 範疇の否定形断定 (「feature が無い」「該当 event が無い」 等);
  Claude Code spec の具体的肯定形断定 (「`UserPromptSubmit` hook で X」「`context: fork` は Y」「`disable-model-invocation` は Z」 等);
  手動: `/claude-code-guide <調査対象>`。
  SKIP: Claude API / SDK / Anthropic 他製品 / モデル料金 / 非 Claude Code ツール (scope 外として返却)。
context: fork
agent: general-purpose
legacy: user CLAUDE.md「一次情報の確認」 より
---

# Claude Code Guide

**Verify the following Claude Code spec question:** $ARGUMENTS

下記の protocol に従って一次情報で裏とりし、 末尾の Output 形式で報告すること。

## 確認経路 (優先順)

1. **CLI `--help` 出力**: `claude --help` / `claude <subcommand> --help` (agents / mcp / plugins 等)
2. **`docs.claude.com`**: Anthropic 公式 docs
3. **`code.claude.com`**: Claude Code 公式 docs
4. **`github.com/anthropics/claude-code`**: docs / source code 本体 / issues / discussions / changelog / releases
5. **`claude.com/plugins`**: plugin marketplace
6. (補助) **2026 年以降のコミュニティ報告**: 個人ブログ / Reddit / X 等。 公式 1 点要件は満たさない

## 確認 protocol

- **公式 1 点以上を必須**、 全体で **2 点以上** で交差確認
- 1 経路で見つからなくても存在を否定しない: 公式 doc 未記載でも実機で動くケースあり、 逆に docs にあっても deprecated のケースあり — 複数経路 confirm が必須
- **conflicting** (Anthropic 内で情報が割れている) 場合は両方提示

## Output (main session に返す)

5 部構成で返却:

1. **結論** (1-2 文): "Yes, X works as Y" / "No, X is not supported" / "Conflicting: A says X, B says Y" 等
2. **公式情報源 URL list**: cite した公式 URL を列挙
3. **確認した経路と未確認の経路**: 「CLI --help / docs.claude.com / GitHub issues は確認、 plugins / community blog は未確認」 等
4. **関連 issue / regression** (任意): GitHub issue / discussion URL + 1 行要約
5. **確信度**:
   - 「確認済」 — 公式 1 点以上 + 交差確認 2 点以上
   - 「未確認: 範囲明示」 — 公式 0 点 or 交差未達 (何が未確認か明示)
   - 「conflicting」 — 公式同士で割れている

## Out of scope

以下は scope 外として 「本 skill は Claude Code 仕様に限定」 と明示して返す:

- Claude API 一般 / SDK 仕様 (Anthropic Python SDK / TypeScript SDK 等)
- Anthropic 製品全般 (Claude consumer app / claude.ai / Console 等)
- モデル料金 / pricing
- Claude Code 以外のツール (Cursor / Aider / Codex 等)
