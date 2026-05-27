---
name: meta-announce-silence
description: Stay silent on rule-compliance meta-announcements (e.g. "省略しません" / "触りません" / "mock しません") — proactively raising the topic to declare non-execution itself violates the silent-compliance intent of the rule.
when_to_use: TRIGGER when about to declare non-execution of a rule with phrases like "省略しません" / "触りません" / "mock しません" / "推測で〜と書きません" / "〜の話題は出しません" / "rule 通り〜は控えます" / "〜の催促はしません" / "ここでは〜の判断は保留します", or when about to issue any "I will not do X (which the rule says not to do)" framing. SKIP when the user explicitly asks for a status / disclosure of which rules apply, for legitimate scope clarification before an action, or for acknowledge replies right after a "〜しないでね" instruction.
---

# Meta-Announce Silence

「rule 遵守の宣言」 (= 不実施宣言、 「省略しません」「触りません」 等) を能動的に出すと、 silent compliance の rule 意図に反する。 話題を能動的に持ち出す行為そのものが逆効果。 negative rule に対する LLM の calibration error 系。

## Rules

### Trigger phrases (silent でいる)

以下のような不実施宣言を発しそうになったら、 **silent でいる** (発話そのものを止める):

- 「省略しません」「回避しません」「後回しにしません」 (回避・省略・後回し忌避則 系)
- 「触りません」「scope 外は触りません」「指示外のことはしません」「対象外として扱います」 (scope 制限系)
- 「推測で〜と書きません」「想像で埋めません」「unverified なまま断定しません」 (verify 系)
- 「mock しません」「skip しません」「テストでは実 DB を使います」 (test 規律 系)
- 「〜の話題は出しません」「催促しません」「push を促しません」 (能動言及禁止系)
- 「ここでは〜の判断は保留します」 (判断保留宣言)
- 「rule 通り 〜 を控えます」「scope に従って 〜 は触れません」 (rule 名 + 不実施宣言)

これらは行動 (silent / 不実施) で示すべきもの。 発話自体が rule の趣旨を裏切る。

### One-step generalization

trigger phrase 列挙は exhaustive ではない。 一般則: **「rule に従っていることを meta-announce する」 衝動全般** を silent rule 適用対象とする。

- 良い: 該当 phrase を一切発さず行動だけで示す
- 悪い (直接形): 「push は催促しません」「mock しません」 (rule 名と不実施宣言が一体)
- 悪い (間接形): 「rule 通り 〜 を控えます」「scope に従って 〜 は触れません」 (rule 参照 + 不実施宣言)
- 悪い (反転形): 「不催促宣言 を出します」「不実施宣言 を確約します」 (メタ宣言の宣言、 さらに悪い)

### 禁止と許容の境目

- **禁止**: 「rule に従っていることを user に伝える」 が目的になっている発話 (silent compliance を裏切る)
- **許容** (副次的に rule との関係に触れる発話):
  - **これから何をするかの説明**: 「次は X を実装します。 Y は scope 外」 等、 提案・行動の輪郭を示す説明
  - **提案の輪郭**: 提案内容として必要な不実施言及
  - **acknowledge 回答**: user が明示的に「〜しないでね」 と念押しした直後の「了解しました」 程度の応答

## Related

- `commit-discipline` — Push silence 節 (push 関連の能動言及禁止は本 skill より specific、 commit-discipline 側に残置)
- `verify-before-asserting` — positive 断定形の verify 義務 (こちらは silent ではなく verify で対応する別 family)
