---
name: claude-code-guide
argument-hint: <調査対象>
legacy: user CLAUDE.md「一次情報の確認」 より
description: >
  Claude Code の hook・subagent・plugin・skill・settings・MCP・CLI 仕様に関する一次情報確認を fork 内で実行する。

  Auto-invoke triggers: (a) これらの設計や採否判断を行う場面、 (b) 「feature が無い」「対応していない」「該当 event が無い」 等の Claude Code 範疇の否定形断定を発しかけた瞬間、 (c) Claude Code の hook event 名 / payload schema / SKILL.md frontmatter field / settings.json hook 構造 / CLI flag に関する具体的な肯定形断定 (例: 「`UserPromptSubmit` hook で X できる」「`context: fork` は Y を意味する」「`disable-model-invocation` は Z 挙動」) を発しかけた瞬間。 手動呼び出しは `/claude-code-guide <調査対象>`。

  確認経路 (複数併用、 1 経路で見つからなくても存在を否定しない): CLI `--help` (`claude --help`・`claude <subcommand> --help` 等)、 `docs.claude.com`、 `code.claude.com`、 `github.com/anthropics/claude-code` (docs / issues / changelog / discussions)、 `claude.com/plugins`、 補助として 2026 年以降のコミュニティ報告 (個人ブログ等)。 公式 1 点以上を必須として 2 点以上で交差確認する。

  返却は (a) 結論 1-2 文、 (b) 公式情報源 URL list、 (c) 確認した経路と未確認の経路、 (d) 関連 issue・regression があれば URL + 1 行要約、 (e) 確信度 (公式 1 点以上で 「確認済」、 未満なら 「未確認: 範囲明示」、 Anthropic 内で情報が割れていれば 「conflicting」)。 Claude API 一般・SDK 仕様・Anthropic 製品全般・モデル料金など Claude Code 仕様の範囲外は scope 外として返す。
context: fork
agent: general-purpose
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
