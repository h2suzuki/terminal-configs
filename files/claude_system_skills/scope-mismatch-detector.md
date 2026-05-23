---
name: scope-mismatch-detector
description: Before reusing a rule / past experience / skill in a different situation, verify trigger and scope match; detect both Overapplied and Underapplied (LLM calibration error correction).
when_to_use: TRIGGER when about to apply a known rule / past experience / another skill to the current situation, when about to say "これは前にやった〜と同じ" / "あの時の〜が使える" / "経験から〜だ", or when about to suppress firing with "このケースは別" / "文脈が違う". SKIP for first-time rule definition or initial application, or when the user explicitly says "別件として扱え".
---

# Scope Mismatch Detector

ルール・経験・skill を別状況に流用する前に、 想定 trigger / scope を抽出し、 目前の状況とすべて一致するか 1 拍確認する。 「文脈は理解した」 という主観は信用しない (LLM 一般の calibration error)。 逆に trigger / scope が一致するなら 「別に見える」 主観で抑止せず発火させる (言いかけたこと自体が該当の証拠)。

## Process

1. **trigger / scope の抽出**: 元ルール / 経験 / skill が想定していた発火条件と適用範囲を 1 文で言葉にする。
2. **目前状況との一致確認**: 抽出した条件と目前の状況を点単位で照合する。 1 拍置いて自分で反論を試みる。
3. **2 種類の誤りを別個に検査**:
   - **Overapplied**: trigger / scope が違うのに発火しようとしている。 似て見えて発火条件が異なる別物の混同。
   - **Underapplied**: 一致しているのに 「このケースは別」 と判断して未発火。

## Examples

- **Overapplied**: skill 要件 (SKILL.md 形式の制約) を agent (subagent 起動時のシステムプロンプト) に適用する。 production の retry 設計 (idempotency / backoff) を Claude Code 作業手順 (人間との対話) に適用する。
- **Underapplied**: ある rule が 「LLM が判断・提案を出すとき」 を trigger としているのに、 自分が判断を述べる場面で 「これは判断じゃなくて報告だから」 と恣意的に発火を抑止する。

## Related

- **Legacy:** org CLAUDE.md 判断の心構え より (bullet 4)
