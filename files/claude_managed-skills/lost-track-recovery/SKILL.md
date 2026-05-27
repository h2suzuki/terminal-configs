---
name: lost-track-recovery
description: Recovery procedure for Claude lost-track state. USER-INVOKED only (auto-trigger disabled).
disable-model-invocation: true
---

# Lost Track Recovery

Claude が lost track 状態 (現状を 1 文で restate しようとして describe back できない、 直近指示を失念、 文脈散逸) に陥ったときの復旧手順。

**USER-INVOKED ONLY**: lost track 中は Claude 自身の trigger 判断が信頼できない (「lost track している」 という認識自体が corrupted)。 ゆえに `disable-model-invocation: true` で auto-trigger を機械的に禁止し、 user の observation を起動 trigger とする。 復旧手順自体も内部努力では脱出できないので、 外部ソースの read で補う。

## Process

1. **即座に作業を停止する**: 進行中の tool 呼び出しがあれば終わらせる。 新規 spawn / Edit / Write はしない。

2. **外部ソースを順に読み直す**:
   - `todos.md` がもしあれば: 現在のタスク state と pending 承認待ち事項
   - **直近のユーザー指示** (current message と直前数 turn)
   - **元の依頼** (session 冒頭 / handoff 元の意図)
   - **session 履歴** (これまでのやり取りで合意した方向と未完了事項)

3. **現状を 1 文で restate**: 「今、 何を、 なぜやっているか」 を 1 文で書く。 書けない / 自信が無ければ step 2 に戻って追加で読む。

4. **再開**: restate できたら作業を再開する。

5. **中断する場合**: 現在の作業を脇に置いて別作業へ切り替える場合は、 中断することをその経緯と共に `todos.md` に必ずメモする。 再開したら、 このメモは削除して良い。

## Related

- **Legacy:** org CLAUDE.md ワークフローの統制 § 1. 計画と遂行 より (lost track 復旧 bullet)
