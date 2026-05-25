---
name: evidence-reporting
description: 判定・推奨・結論・規模影響評価の発話直前に参照する用語定義集 (規模表現・「具体的」・「必要範囲」 の意味)。
when_to_use: TRIGGER when about to use 「大改造」「軽微」「影響大」「リスクが高い」「具体的」「必要範囲」 等の評価語。 SKIP for mechanical tool output reports。
---

# Evidence Reporting

判定・推奨・結論・規模影響評価を発話する直前に参照する用語定義集。 抽象的なフレーズに precise meaning を与え、 読者の scope 誤解を減らす。

## 用語定義

### 規模・影響表現

「大改造」「軽微」「影響大」「アーキテクチャの見直し」「こちらの方が改造が少ない」「リスクが高い」 等を使う時は、 何ファイル / 何節 / どの呼び出し元が影響するかを併記する。 形容詞単独では reader が scope を infer できない。

### 「具体的」 の意味

「具体的に確認」「具体的に説明」 等で 「具体的」 を使う時は、 以下のいずれかの単位で表現する:

- 影響ファイル数
- 節 / パラグラフ
- 呼び出し元
- 触れるレイヤー
- 変わる依存関係

### 「必要範囲」 の意味

「必要範囲を Read する」 等の文脈での 「必要範囲」 とは:

- 全体 Read **ではない**
- offset / limit / grep を先行使用
- 判定根拠だけを最小限取得
- token / rate limit 保全と両立

## Related

- **Legacy:** org CLAUDE.md §報告・応答 (§1.3.2.2 sub-bullets 3 行) より
