---
name: report-by-evidence
description: Rules to consult before asserting judgment / recommendation / conclusion / scale-impact assessment / behavior claim / resource cost estimate / defect classification.
when_to_use: TRIGGER when about to use evaluative terms ("大改造" / "影響大" etc), cite source for a code behavior claim, estimate resource cost, or classify a defect as "gap" vs "bug". SKIP for mechanical tool output reports.
---

# Report by Evidence

判定・推奨・結論・規模影響評価・挙動 claim・リソースコスト見積・欠陥分類を発話する直前に参照するルール。 抽象的なフレーズに precise meaning を与え、 friction を減らす。

## Rules

### Scale and impact terms

「大改造」「軽微」「影響大」「アーキテクチャの見直し」「こちらの方が改造が少ない」「リスクが高い」 等を主張するためには、 何ファイル / 何節 / どの呼び出し元が影響するかを併記しなければならない。抽象的な形容だけでは reader が scope を infer できないので、動機を抑制するための脅しと解釈され、非常に悪い印象を与える。

改造方法の多くの可能性の中の、たった１つのやり方について述べているに過ぎないことを踏まえて報告する。
他の方法なら規模・影響を 1/100 にできるかもしれないが、まだ思いついていないだけかもしれないという可能性を否定しない。

憶測を避け、実際のコードを判断根拠として報告する。時間や人月は、不確実が高いので見積もらない（「改造は一週間かかります」などと言うのは全体禁止）。

#### Scope: 計画・ブレスト段階のみ、 対象は code + 文章 repository も含む

本 rule の発火 scope は **計画・ブレスト段階** (実装着手前)。 デバッグ段階の見積もりは別件 (「ここを fix すれば直る」 等の仮説評価は対象外)。

「対象」 は code に限らず **文章 repository (ガイドライン / ドキュメント / 設定 等)** も含む。 ガイドライン文書の更新規模を語る場面でも同じ rule 適用。

#### Root causes (避けるべき bias 3 種)

非定量表現の発話衝動には 3 種の根本原因がある:

1. **Ungrounded estimate (最大要因)**: コードを読む前に評価を発話してしまう。 まず読む、 発話は後
2. **Hedging bias**: 「大変と先に言っておけば外さない / 楽に終われば有能・大変なら警告」 型の非対称報酬 (RLHF 由来 caveat 過多もここに含む)
3. **省力化バイアス**: Claude 自身の読む・書く労力を反映してしまう (自分が大変だから「大改造」 と言う)

これらは自然な衝動として湧くが、 都度 verbalize で抑制する。

### Code vs doc for behavior claims

実 production の挙動を主張するときは **code の行番号 (`file:line` 形式)** を 1 次根拠として cite する。 design doc (ARCH / SKILL / spec / docstring) は intent の宣言であって、 実装と乖離する可能性 (aspirational、 古い、 TBD 状態) が常にある。

「X が動く / X が無い / Y はここに実装されている」 等の挙動 claim を **doc 行だけで根拠付けてはいけない**。 grep / Read で対応する code を確認してから cite する。

doc は補助引用として OK だが、 「実装の場所」 列に doc 行をそのまま書かない。 design intent vs 実装の比較を明示する文脈でのみ doc 行を併記する。

### Resource consumption discipline

cost (token / rate-limit / wall-clock) を見積もる時は **active generation と idle / stalled を区別** する:

- token 消費 = LLM が generate しているとき発生する。 stuck の bg session、 polling 待ち、 deadline 待機中、 idle reaper 内 sleep は token を burn しない
- wall-clock 時間 ≠ token cost。 「N 分 stuck × model = $X 浪費」 という単純積算は誤り。 stuck = no generation = no token burn
- 「コスト浪費」 を語るときは generate 中の総 token 量 (input + output、 usage report / transcript metadata) で測る。 wall-clock は latency や 待機時間の別軸指標として並列管理する

### Gap vs bug terminology

「gap」 は **仕様 / 要件 (scope) の枠内** で使う用語。 spec の更新で対応できる未充足要件、 design intent の段階的拡張、 後追い実装 todo 等は 「gap」 で表現してよい。

一方、 **leak (resource / memory / file descriptor / session)、 security 問題、 data corruption、 race condition による破損** は 「bug」 と明示する。 これらを「gap」 と呼んではならない:

- leak / security / corruption を要件として書ける spec は存在しない (= 仕様化不可能)
- 「gap」 と呼ぶと改修の緊急度が「次 sprint」「いずれ」 トーンに弱まり、 即時対応の signal が消える
- reader が責任範囲を 「未着手 feature」 と誤解する

判別:

- 「これが満たされていない要件は何か」 と問えて答が書けるなら gap
- 「これがあると何が壊れるか」 が即答できるなら bug

bug の起因による sub-classification:

- **仕様逸脱起因 bug (想定外利用)**: bug の原因が 「spec として記述されていない使い方 (想定外利用)」 だった場合、 bug 名義を維持しつつ 「想定外利用に起因する bug」 と framing してよい。 仕様変更の仲間として考えられる — fix が code 修正だけで終わらず、 spec を拡張して当該利用パターンを 「記述」「禁止」「サポート」 のいずれかに位置付けることで完結する場合が多い。 ただし 「想定外利用だったから gap」 と呼び替えるのは誤り。 発生事象自体は resource 破損・state 破損・security 侵害 等の bug なので、 呼称は bug を維持する
- **純粋 bug (仕様内利用で発生)**: spec として記述された使い方の範囲内で発生した bug は **純粋な実装 bug**。 spec 拡張で説明できる余地は無く、 fix も code 側のみで完結する。 これを 「gap」 や 「想定外利用 bug」 と framing するのは責任希釈で、 不正

**「想定外」 の判定基準は ドキュメント**: 「想定外利用」 の framing は **ドキュメントに書かれた使い方との比較** で行う。 doc に記述が無い使い方を 「想定外」 と呼ぶには、 まず想定範囲（＝ doc）が定義されていなければ判定不可能。 doc に書かれていない使用 ≠ 想定外利用; doc に書かれていない時点で 「想定」 自体が存在しない（言えるのは 「私の頭の中に当該パターンが無かった」 のみで、 spec 上の 「想定」 ではない）。

したがって **使用方法の網羅的ドキュメント化は前提として重要**。 doc 不在で 「想定外利用」 と framing するのは 自分の assumption を spec に化けさせる行為で、 責任希釈の典型パターン。 doc を書いてから初めて 「documented usage 内/外」 の区別が成立する。

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
