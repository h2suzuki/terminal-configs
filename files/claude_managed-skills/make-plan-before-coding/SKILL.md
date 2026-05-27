---
name: make-plan-before-coding
description: Align design space exploration, agreement, and documented rationale inheritance before entering implementation.
when_to_use: TRIGGER when about to propose a design / 方針, start substantive Edit / Write after research, or ask "X にしますか?" for already-documented choices. SKIP for mechanical changes or when user has approved the design.
---

# Make Plan Before Coding

coding に着手する前に plan を立てる discipline。 設計の option space を尽くし (investigate)、 概要を提示して user 合意を取り (agree)、 既 documented な rationale は再 litigate せず継承する (inherit) — 3 phase を 1 skill に統合。

## Why

設計 phase で頻発する 3 失敗 mode:

1. **Premature commit**: 既知範囲だけで設計が早期収束し、 productized 先行実装 / 他者解法を見落とす
2. **Silent assumption**: 調査が一段落した瞬間に user 合意を取らず実装に突入し、 手戻り = token 浪費
3. **Redundant litigation**: 既に documented な rationale を user 確認で再 litigate し、 合意済の判断を蒸し返す

共通 root cause = **着手 momentum**。 調査が進むほど 「もう分かった」 「早く書きたい」 という慣性が働き、 phase gate を skip しがちになる LLM calibration error。

## Process

### Phase 1: Investigate

設計案を verbalize する前に option space を能動列挙:

1. mechanism / API / library / framework は?
2. productized 先行実装 / 他者の公開解法 (blog / issue / repo) は?
3. 一次情報で mechanism 確認したか?
4. 「今知っている範囲」 で収束していないか self-rebut?

新事実が判明したら過去の設計判断を再評価して verbalize する (新事実発見後の古設計維持は calibration error)。

### Phase 2: Agree

調査が一段落 (probe 群が出揃った / blast radius が確定した / 複数の fork が見えた) したら、 自発的に **設計概要** を提示:

1. **ゴールの再述**
2. **中核原則**
3. **具体的変更点**
4. **合意が要る設計判断 fork**
5. **検証順序**

最後に 「この設計で合意か」 を問う。 user 合意 phrase が明示されるまで substantive Edit / Write は hold する。 user の 「進めて良い」 が設計合意を含むか曖昧なら概要を先に出す。

### Phase 3: Inherit (skip when applicable)

設計案を提示しかけた瞬間に **停止** し、 関連 code comment / canonical doc / handoff / commit message を必要範囲で読む:

- rationale 発見 → 継承して実装に進む (user 再 litigate しない)
- rationale 不在 → 新規 design として Phase 2 へ
- 前提変化 / 新 trade-off / obsolete rationale → 再 litigate OK

## Rules

### Investigation 完成判定

「これ以上調べる事はない」 と感じたら 1 拍 self-rebut: 既知範囲だけで収束していないか? 一次情報 / productized 実装 / 他者解法を踏んだか? token を理由に一次情報確認を省略しない。

### Agreement form

概要は **合意可能な粒度** に絞る (冗長禁止、 詳細実装は合意後に展開)。 長時間調査後は user 側も lost track しやすいので概要再述で context を共有する。 改造が大きい / blast radius が広い 場合は特に厳守。

### Inheritance gate

過去 rejected 提案を再持出ししない:

1. 過去に止められた追加提案・marker・機能は **user が明示的に再要求した時のみ** 着手
2. user 拒否理由は **paraphrase せず** そのまま認識
3. **逆 framing 禁止**: 拒否理由 (例 「分かりにくい」) の逆方向 framing (例 「分かりやすさのため」) で再提案するのは LLM の典型 rationalization 癖

### Examples

- 悪い (Phase 1 skip): 「思いついた A 案を出します」 → option space 未列挙
- 悪い (Phase 2 skip): 「調査終わったので実装します」 → 概要提示なく substantive Edit
- 悪い (Phase 3 skip): 「`TTL_SECONDS` を 7 日にしますか? 30 日にしますか?」 (docstring に 「7 days because session usually completes within a week」 記載済)
- 良い: 「A / B / C を比較した結果 B を提案、 概要は…、 この設計で合意か?」
- 良い: 「commit message に明記された通り fork 方式を採用、 実装に進みます」

## Output

適用後の典型 work flow:

```
research (option space 列挙)
  → 設計概要提示 (Goal / 中核原則 / 変更点 / fork / 検証順序)
  → user 合意 phrase 取得
  → implementation (substantive Edit / Write)
```

documented rationale 継承 case:

```
読む (comment / doc / handoff)
  → rationale 発見
  → 「documented 通り X 採用、 実装に進みます」 と verbalize
  → implementation
```

## Related

- `verify-before-claim` — 否定形断定前の primary source verify (Phase 1 「一次情報で mechanism 確認」 と family)
- `verbalize-before-action` — 判断 / 推奨を発話前に self-rebut (Phase 2 の verbalize 規律)
- `evidence-reporting` — 判定 / 推奨 / 影響評価の根拠提示
- `commit-discipline` — 実装後の commit 規律
