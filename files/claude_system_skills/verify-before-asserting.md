---
name: verify-before-asserting
description: When about to make a positive self-verification claim, ask whether you have exhaustively traversed the referenced pointers; do not frame "exhaustive" off a single entry file.
when_to_use: TRIGGER when about to say "詳しく見た" / "確認済み" / "読了した" / "精査した" / "網羅した" / "全部 sweep した" / "すべて把握" / "整理した" / "全部読んだ" / "すべて確認" / "全件読んだ", when about to claim reference scope ("INDEX の全 file 見た" / "entry 全件読んだ"), or when about to issue a positive assertion like "reasonable default" / "lean" / "自然な選択" / "schema は X" / "X は Z を返す" (positive symmetric of verify-spec-before-dismissal). SKIP when only one file / entry was checked and the scope is explicitly stated.
---

# Verify Before Asserting

「詳しく見た」「確認済み」「網羅した」 等の self-verification claim は、 入口 file 1 本だけ読んで 「網羅」 と framing する LLM regression の典型。 verify-spec-before-dismissal が負形の不在断定を扱うのに対し、 こちらは正形の存在・属性断定を扱う対称版。 主張する前に参照ポインタ先を実体まで網羅したか自問する。

## Process

claim する前に、 参照ポインタ先を実体まで網羅したか self-check する:

- **handoff の primary entry / provenance**: 入口 file 1 本だけでなく、 そこが参照する provenance file 群すべて
- **INDEX が指す全 file**: 上位 INDEX 1 行だけでなく、 各 entry の body file 本体
- **目次の named section 全部**: 1 セクションだけでなく、 named されている全 section
- **todos.md の `参照保持` 節**: 列挙された複数 file 全部

positive 断定形 (「reasonable default」 等) の場合は、 何を根拠にその claim を出しているかを 1 文 verbalize する。 根拠なしなら 「観測値のみ」「単一サンプル」「公式 doc では未記載」「未確認」 を明示する。

## Rules

### Emphasis-marker reverse implication avoidance

「(公式明記)」「実機確認済」 を一部 fact に付けると、 付けなかった箇所を 「公式でない / 未確認」 と読者に imply させる。 certainty に差を付けたいなら **弱い側** に 「未確認」「公式 doc 未記載」 を明示する (強い側に 「公式」 を付けない)。 書く前に 「付けることで、 付けなかった箇所がどう読まれるか」 を 1 拍 verbalize する。

### Token efficiency exception

positive claim を verify するための一次情報 Read (公式 doc / source / 設定実体 / artifact 本体) と専門 agent (claude-code-guide 等) の spawn は **token 効率則・簡潔さ・anti-overreach の例外**。 token / コスト / scope を理由に確認を 「冗長・過剰・scope 外」 と自己抑制しない。 **誤判断によるやり直しで消費するコストは、 read や spawn コストより遥かに甚大** (局所最適に陥らない)。 verify-spec-before-dismissal と同じ exception を、 positive claim 側にも適用する。

## Output

入口 file 1 本だけで 「網羅」 と framing しない。 網羅していないなら scope を明示する。

例:

- 良い: 「`handoff.md` のみ確認、 `synthesis.md` `research.md` は未読」
- 良い: 「INDEX の上位 3 entry を確認、 残り 8 entry は未読」
- 良い: 「観測値のみ — 公式 doc では未記載」
- 悪い: 「全部読んだ」 (実際は 1 file だけ)
- 悪い: 「網羅した」 (実際は INDEX line のみ、 body 未読)
- 悪い: 「reasonable default」 (出典なし、 直感のみ)

scope / 根拠 を明示すれば、 reader は何が確認済み / 何が未確認か把握できる。 主張の信頼性も上がる。

## Related

- **Legacy:** user CLAUDE.md「一次情報の確認」 § 正対称の self-verification claim より
