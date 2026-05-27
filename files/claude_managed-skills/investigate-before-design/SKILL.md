---
name: investigate-before-design
description: design proposal の前に option space (mechanism / API / 既存 productized 実装 / 他者解法) を能動的に調査列挙する。 「今知っていることだけ」 では sub-optimal、 LLM は既知範囲で早期収束する calibration error を起こす
when_to_use: TRIGGER when about to propose a design / アーキ選択 / approach / 方針 / 改造概要 / mechanism / library / API choice, or when noticing investigation has settled into "今知っている範囲" / "現時点の理解" without exploring broader options. SKIP for trivial / mechanical fixes where the design is obvious, or when the user has bounded the scope explicitly (e.g., 「この pattern で書き直して」).
---

# Investigate Before Design

design proposal の前に option space を能動的に調査して列挙する。

## Rules

### Active enumeration

設計を始める前に: mechanism / API / 既存 productized 実装 / 他者の解法 を能動的に列挙する。 「今知っていることだけ」 で設計すると sub-optimal。

### Pre-design checklist

設計提案を出す前に、 1 拍チェック:

1. この option space を網羅したか?
2. productized 先行実装 / library / framework はないか?
3. 一次情報で mechanism を確認したか?
4. 他者の解法 (公開実装 / blog / issue) は調べたか?

未調査のまま設計案を出さない。 token を理由に一次情報確認を省略しない。

### Re-evaluate on new findings

調査で設計空間が変わったら、 過去の設計判断を **再評価して verbalize** する。 新事実を発見したのに古い設計を維持するのは calibration error。

## Why

LLM は既知範囲で早期収束しがちで、 これは普遍的 calibration error。 調査して判明した事実が設計空間を繰り返し作り変えるため、 調査は設計の前提作業であって付随作業ではない。 2026-05-16 C01 (claude -p 課金分離対応) session で supervisor 仕様・hook type・`/batch` / `/simplify` の binary 実体・MCP bridge など調べるたびに新 mechanism が判明し、 都度それ以前の設計が sub-optimal と分かった経験から起票。

## Related

- `design-agreement-checkpoint`: 調査後の design proposal を実装に移す前のチェックポイント (本 skill の next stage)
- `verify-spec-before-dismissal`: 否定形断定前に primary source verify。 本 skill の 「一次情報で mechanism 確認」 と family
- `evidence-reporting`: 判定 / 推奨 / 影響評価を発話する前に根拠を示す
- **Legacy:** user memory `feedback_investigate_broadly_before_design.md` (2026-05-16 C01 起票) より昇格
