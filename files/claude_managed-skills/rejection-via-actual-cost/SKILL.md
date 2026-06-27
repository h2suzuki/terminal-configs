---
name: rejection-via-actual-cost
description: Argue the rejection rationale for a design alternative in terms of actual cost — what would be added if adopted (component count / LoC / lifecycle management points / IO size / overlap with existing paths / mechanism surface area); do not use as a rejection reason verify costs that can be resolved before commitment (need real-machine verify / need official spec verify / unverified), since those just need to be done.
when_to_use: TRIGGER when about to reject a design alternative with reasons like "実機 verify が要る" / "未検証" / "動作が読めない" etc, or write a rejection rationale 節. SKIP when verify cost is decisive and quantified, or user waives verify.
---

# Rejection via Actual Cost

design 代替案の rejection rationale は、 **そのアプローチを採用した場合の actual cost** で述べる。 verify cost (着手前に解消できる検証作業) を rejection 理由にしない。

## Rules

### Actual cost dimensions

代替案を比較するとき、 各案について 「採用したら 何が増えるか」 を具体列挙:

- component 数 (新 script / class / hook / file)
- LoC 規模
- lifecycle 管理点 (initialization / cleanup / monitoring)
- IO size
- 既存 path との overlap
- 機構面積 (layer 数 / responsibility 分散)

### Verify cost を rejection 理由にしない

却下理由にしない wording (= 着手前に解消できる verify cost):

- 「実機 verify が要る」 — やればいいだけ
- 「公式 spec 確認が要る」 — やればいいだけ
- 「未検証」 — verify を実行して judgment を得ればよい
- 「リスクがある」 — 具体的 cost に展開せず曖昧
- 「動作が読めない」 — verify で読めばよい
- 「version drift リスク」「粒度問題」 等の speculative concern — verify で解消可能

これらが混じったら、 verify を実行して judgment を得るか、 actual cost に展開する。

### 例外: 明示量化された large verify cost

verify cost が決定的に large な場合のみ明示量化して例外的に rejection 理由にできる:

- 「実機 verify に N 日かかる、 期限まで M 日しかない」
- 「verify には専用 hardware が必要」

数値量化なしの 「大きい」「複雑だ」 は不可。

## Why

verify cost を回避することは 「楽な選択」 の正当化であり、 「優れた選択」 の rationale ではない。 verify は 「やればいい」 だけのことで、 better mechanism を選ばない言い訳にならない。 2026-05-27 checking-style の bg progress watchdog 設計時、 Approach A (`--settings` hook inject) を 「bg session 側 hook の fire rate が turn 粒度か実機 verify と公式 spec 確認が要る」 を理由の 1 つに却下したのを 指摘で訂正、 actual cost (component 数 / lifecycle 管理点) で再 framing。

## Related

- `report-by-evidence`: 判定 / 推奨 / 影響評価を発話する前に根拠を示す。 本 skill の actual cost wording と family
- `verify-before-claim`: 否定形断定前に primary source verify。 本 skill が 「verify は やればいいだけ」 と言うのと同根
- `make-plan-before-coding`: design proposal の前段。 verify-cost-as-rejection は調査不足の reflective signal でもある
- **Legacy:** user memory `feedback_design_rejection_actual_cost.md` (2026-05-27 checking-style bg watchdog 起票) より昇格
