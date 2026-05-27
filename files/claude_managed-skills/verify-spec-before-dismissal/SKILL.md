---
name: verify-spec-before-dismissal
description: When about to assert a negation, verify against official primary sources before concluding; investigate without asking permission.
when_to_use: TRIGGER when about to say "できない" / "ない" / "非対応" / "サポートされていない" / "未対応" / "機能が無い" / "使えない" / "知らないので別物だと思った" (any domain), when about to issue a claim depending on Claude hook / subagent / plugin / skill / Anthropic API or other official-ecosystem spec, when about to dismiss a subagent's bonus claim as "hallucinate 可能性" without verifying the cited URL / command output yourself, or when about to suppress firing with "今回は別ケース" / "該当しない". SKIP only when basing the denial on a primary source **you directly read yourself** (cite the URL / quoted excerpt in the body); subagent-relayed citations do not qualify as direct reading.
---

# Verify Spec Before Dismissal

「できない」「ない」「非対応」 等の否定形断定は、 LLM の cut-off で古い記憶に基づいて間違える代表 pattern。 推論では、 記憶は cut-off で古いという前提を置く。 結論を出す前に必ず一次情報で裏とりする。

## Process

1. 否定形断定を発しかけた瞬間に **停止**
2. **許可を求めず自分で調べる** — 「確認しますか?」 と尋ねて止めない、 調査は clarifying question ではない
3. 公式一次情報で裏とり (下記 Sources の優先順で)
4. 確認できた → 根拠を本文に示して結論を出す
5. 確認できなかった → 「公式情報が確認できなかった」 と明示。 見つからなくても存在を否定したことにはならない

## Rules

### Token efficiency exception

一次情報確認のための Read (公式 doc / source / 設定実体 / artifact 本体) と専門 agent (claude-code-guide 等) の spawn は **token 効率則・簡潔さ・anti-overreach の例外**。 token / コスト / scope を理由に確認を 「冗長・過剰・scope 外」 と自己抑制しない。

**誤判断によるやり直しで消費するコストは、 read や spawn コストより遥かに甚大** (局所最適に陥らない)。 判定・推奨・結論の前提となる確認は token 効率に優先する。

### Subagent bonus claim も自分で verify

subagent (claude-code-guide 等) が primary source URL 引用付きで出した bonus claim を 「hallucinate 可能性」 と推定して verify せず dismiss しない。 URL fetch / command 実行 (`--help` 等) で primary verify した上で accept / reject する。 SKIP 条件の 「primary source を直接読んで cite」 は **自分が直接 fetch / 実行する** ことを意味し、 subagent 越しの引用は該当しない。 否定主張 ("X はない") に倒す前は特に必須。 2026-05-26 起票 (claude-code-guide subagent が `claude agents` mode を URL 付き claim、 dismiss → user 指摘で `claude agents --help` 実行で実存判明、 verify 1 step で防げた事例)。

## Sources

特に Claude hook / subagent / plugin / skill / Anthropic API / 公式エコシステムのツール採否では、 以下を裏とりする:

- **CLI `--help` 出力** — 実機で確認できる最新 spec
- **`docs.claude.com`** — Anthropic 公式 docs
- **`code.claude.com`** — Claude Code 公式 docs
- **`github.com/anthropics/*`** — Anthropic OSS repos (source code 本体)
- **`claude.com/plugins`** — plugin marketplace
- **`claude-code-guide` subagent** — 上記を網羅 search する専門 agent

出典 **2 点以上** で結論の裏を取り、 うち **最低 1 点は公式・一次情報** (公式 doc / 公式サイト / source code / artifact 本体 / 設定実体 / 専門 agent のいずれか)。 Reddit / 個人ブログ等は点数に算入してよいが公式 1 点の要件は満たさない。

## Related

- **Legacy:** user CLAUDE.md「一次情報の確認」 + org CLAUDE.md「token 効率」 より
