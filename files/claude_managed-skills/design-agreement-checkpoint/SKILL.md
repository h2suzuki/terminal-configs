---
name: design-agreement-checkpoint
description: 調査 / probe / blast radius 把握から実装 / コード改造へ移る手前で、 設計概要 (ゴール再述・中核原則・変更点・合意 fork・検証順序) を提示してユーザー明示合意を得るチェックポイントを必ず置く。 合意なき実装着手はトークン浪費・手戻りの元
when_to_use: TRIGGER when about to start implementation / コード改造 after a research / 調査 / probe / blast radius / spec 確認 phase, when the investigation phase reaches "一段落" / "落ち着いた" / "前提が見えた", or when about to write substantive Edit / Write tool calls that constitute implementation (not exploratory probes). SKIP when the user has explicitly approved the design in this session, when the change is trivial / mechanical (typo / single-line fix / mechanical rename), or when the design was agreed in a prior turn that's still load-bearing.
---

# Design Agreement Checkpoint

調査 / 探索 phase が一段落し、 実装に着手しようとする手前で、 設計概要を提示してユーザーの明示合意を得るチェックポイントを必ず置く。

## Process

研究 phase の終わり (probe 群が出揃った / blast radius が確定した / 複数の設計 fork が見えた 等) を検出したら、 自発的に次を簡潔提示:

1. **ゴールの再述**
2. **中核原則**
3. **具体的変更点**
4. **合意が要る設計判断 fork**
5. **検証順序**

最後に 「この設計で合意か」 を問う。 ユーザーが 「進めて良い」 と言っても、 それが設計合意を含むか曖昧なら 設計概要を先に出す。

## Rules

### 概要は合意可能な粒度

冗長にせず、 合意可能な粒度に絞る。 詳細実装は合意後に展開する。

### 合意なき実装着手禁止

合意なしに実装へ進まない。 改造内容が大きい / blast radius が広い 場合は特に厳守。

### 長時間調査後の lost track 配慮

長時間の調査の後はユーザー側も文脈を見失いやすい。 概要再述で context を共有する。

## Why

2026-05-16 C01 (claude -p 課金分離対応) の長い調査 session 中、 ユーザーが lost track し 「実装に進む前にデザインを合意しないとトークンが無駄になる。 デザインの合意は大切なチェックポイント」 と明言。 合意なき実装は手戻り = トークン浪費に直結する。

## Related

- `investigate-before-design`: 設計提案の前段。 broad investigation → design agreement → implementation の workflow
- `verbalize-before-action`: 判断 / 推奨を発話前に self-rebut。 設計概要提示は本 skill の verbalize
- `no-redundant-design-litigation`: 既決定の設計を再 litigate しない (本 skill は新規 design 局面、 別 family)
- **Legacy:** user memory `feedback_design_agreement_checkpoint.md` (2026-05-16 C01 起票) より昇格
