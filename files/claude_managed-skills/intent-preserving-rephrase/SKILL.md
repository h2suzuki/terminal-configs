---
name: intent-preserving-rephrase
description: CLAUDE.md / ルール / spec / handoff / SKILL.md の言い換え (compliance 目的の否定形→肯定形変換 / 整理リライト / 翻訳) は意味を 1mm も変えない。 真の論理反転で同義になる時のみ変換し、 そうでなければ否定形のまま維持する。 指摘されたサンプルだけ直さず、 全変換を同じ drift class で self-audit する
when_to_use: TRIGGER when about to rephrase / rewrite / 言い換え / 整理 / translate a rule / CLAUDE.md / spec / handoff / SKILL.md (compliance 目的の否定形→肯定形 / 「より自然な書き方」 / 「簡潔化」 等), or when about to claim 「意味は同じ」 / 「同義です」 for a rule rewording. SKIP for new content creation (no prior intent to preserve) or for purely typographical fixes (spacing / punctuation / typo) that do not touch semantics.
---

# Intent-Preserving Rephrase

CLAUDE.md / ルール / spec の言い換え時 (compliance 目的の否定形→肯定形変換、 整理リライト、 翻訳)、 意味を 1mm も変えない。 真の論理反転で同義になる時のみ変換し、 そうでなければ否定形のまま維持する。

## Rules

### Before/after diff for intent

ルール / CLAUDE.md / doc を言い換える前に before/after の intent を diff する。 肯定形が scope ・ default ・ 正当性 を変える / 他ルールと矛盾するなら否定形を維持する。

### 4 drift classes to watch

過去事例 (2026-05-16) で観測した 4 つの drift class:

| Class | 説明 | 例 (Bad: 言い換えで変質) |
|---|---|---|
| **(a) 禁止対象の正当化** | 否定形が禁じている行為を、 肯定形が許容する形に変質 | 「skipped を completed と報告しない」 → 「skipped は skipped と報告する」 (原意 = *skip せず completed まで遂行* が、 *正直に skip 報告すれば可* に変質) |
| **(b) Default の反転 / 過剰制限** | 狭い除外 (奨励される利用) を、 過剰制限 (原則使わない) に反転 | 「小さい lookup には使わない」 → 「overhead を上回る探索にのみ使う」 (「原則使わない」 posture に反転) |
| **(c) Load-bearing な否定の脱落** | 否定の語が肯定形化で消える | 「silently fork せず surface する」 → 「surface してから対応」 (*fork せず* が消え fork を含意) |
| **(d) 他ルール矛盾の生成** | 肯定形が他の必須ルールと矛盾 | push 「能動的な催促・予告をしない」 → 「指示時のみ言及する」 が、 project CLAUDE.md の *session 終了時に未 push commit を知らせる* 必須ルールを禁止 |

GRIT / 正直さ guard / 奨励行動からの除外 / 他ルール非矛盾 を担う否定形は構造的に肯定形化できない。

### Sample-only correction を避ける

user がサンプルで指摘したら、 残り全件を同じ class で **self-audit してから報告** する。 指摘されたサンプルだけ直して 「修正済」 と返さない。

## Why

2026-05-16、 `/etc/claude-code/CLAUDE.md` の compliance 書き換えで、 私の肯定形化が intent を反転させ user が訂正。 言い換えは意味保存が大前提だが、 LLM は 「より自然」「より簡潔」 という美しさ判断で意味を drift させる calibration error を起こす。

## Related

- `document-editor`: 永続 artifact 編集規律 (intent change を伴う書き換えは scope 外)。 本 skill は intent 保存の **判定基準** を提供
- `honest-attribution`: 「段階的拡張」 等の framing で responsibility を blur しない (rule 言い換えの honest attribution と同根)
- `verify-before-asserting`: 「同義です」 と言う前に before/after diff で verify
- **Legacy:** project memory `feedback_intent_preserving_rephrase.md` (2026-05-16 起票) より昇格
