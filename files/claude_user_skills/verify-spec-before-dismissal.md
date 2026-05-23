---
name: verify-spec-before-dismissal
description: >
  否定形断定を発しかけた瞬間、 結論前に公式一次情報で裏とり。 許可を求めず自分で調べる (ドメイン不問)。
  TRIGGER when: 「できない」「ない」「非対応」「サポートされていない」「機能が無い」「未対応」「使えない」「知らないので別物だと思った」 と発しかけたとき;
  Claude hook / subagent / plugin / skill / Anthropic API 等の existing spec に依存する断定;
  「今回は別ケース」「該当しない」 と発火を抑止しかけたとき。
  SKIP: 自分が直接読んだ一次情報を根拠に否定する場合 (URL / cite を本文に出すなら OK)。
legacy: user CLAUDE.md「一次情報の確認」 + org CLAUDE.md「token 効率」 より
---

# Verify Spec Before Dismissal

「できない」「ない」「非対応」 等の否定形断定は、 LLM の cut-off で古い記憶に基づいて間違える代表 pattern。 推論では、 記憶は cut-off で古いという前提を置く。 結論を出す前に必ず一次情報で裏とりする。

## Trigger phrases

以下を発しかけた瞬間が trigger (ドメイン不問 — Claude Code / Anthropic API / 他 LLM / プログラミング言語 / OS / 一般知識 すべて):

- 「できない」「ない」「非対応」「サポートされていない」「未対応」「機能が無い」「使えない」
- 「知らないので別物だと思った」「今回は別ケース」「該当しない」

「言いかけたこと自体が該当の証拠」 として発火させる。

## Procedure

1. 否定形断定を発しかけた瞬間に **停止**
2. **許可を求めず自分で調べる** — 「確認しますか?」 と尋ねて止めない、 調査は clarifying question ではない
3. 公式一次情報で裏とり (下記 sources の優先順で)
4. 確認できた → 根拠を本文に示して結論を出す
5. 確認できなかった → 「公式情報が確認できなかった」 と明示。 見つからなくても存在を否定したことにはならない

## Sources (公式一次情報)

特に Claude hook / subagent / plugin / skill / Anthropic API / 公式エコシステムのツール採否では、 以下を裏とりする:

- **CLI `--help` 出力** — 実機で確認できる最新 spec
- **`docs.claude.com`** — Anthropic 公式 docs
- **`code.claude.com`** — Claude Code 公式 docs
- **`github.com/anthropics/*`** — Anthropic OSS repos (source code 本体)
- **`claude.com/plugins`** — plugin marketplace
- **`claude-code-guide` subagent** — 上記を網羅 search する専門 agent

## 出典数 / 公式要件

出典 **2 点以上** で結論の裏を取り、 うち **最低 1 点は公式・一次情報** (公式 doc / 公式サイト / source code / artifact 本体 / 設定実体 / 専門 agent のいずれか)。 Reddit / 個人ブログ等は点数に算入してよいが公式 1 点の要件は満たさない。

## Token efficiency exception

一次情報確認のための Read (公式 doc / source / 設定実体 / artifact 本体) と専門 agent (claude-code-guide 等) の spawn は **token 効率則・簡潔さ・anti-overreach の例外**。 token / コスト / scope を理由に確認を 「冗長・過剰・scope 外」 と自己抑制しない。

**誤判断によるやり直しで消費するコストは、 read や spawn コストより遥かに甚大** (局所最適に陥らない)。 判定・推奨・結論の前提となる確認は token 効率に優先する。
