---
name: evidence-reporting
description: Rules to consult before asserting 判定 / 推奨 / 結論 / 規模影響評価.
when_to_use: TRIGGER when about to use evaluative terms like "大改造" / "軽微" / "影響大" / "リスクが高い" / "具体的" / "必要範囲" / "アーキテクチャ見直し". SKIP for mechanical tool output reports.
---

# Evidence Reporting

判定・推奨・結論・規模影響評価を発話する直前に参照するルール。 抽象的なフレーズに precise meaning を与え、friction を減らす。

## Rules

### Scale and impact terms

「大改造」「軽微」「影響大」「アーキテクチャの見直し」「こちらの方が改造が少ない」「リスクが高い」 等を主張するためには、 何ファイル / 何節 / どの呼び出し元が影響するかを併記しなければならない。抽象的な形容だけでは reader が scope を infer できないので、動機を抑制するための脅しと解釈され、非常に悪い印象を与える。

改造方法の多くの可能性の中の、たった１つのやり方について述べているに過ぎないことを踏まえて報告する。
他の方法なら規模・影響を 1/100 にできるかもしれないが、まだ思いついていないだけかもしれないという可能性を否定しない。

憶測を避け、実際のコードを判断根拠として報告する。時間や人月は、不確実が高いので見積もらない（「改造は一週間かかります」などと言うのは全体禁止）。

### Defining 「具体的」

「具体的に確認」「具体的に説明」 等で 「具体的」 を使う時は、 以下のいずれかの単位で表現する:

- 影響ファイル数
- 節 / パラグラフ
- 呼び出し元
- 触れるレイヤー
- 変わる依存関係

### Defining 「必要範囲」

「必要範囲を Read する」 等の文脈での 「必要範囲」 とは:

- 全体 Read **ではない**
- offset / limit / grep を先行使用
- 判定根拠だけを最小限取得
- token / rate limit 保全と両立

## Related

- **Legacy:** org CLAUDE.md §報告・応答 (§1.3.2.2 sub-bullets 3 行) より
