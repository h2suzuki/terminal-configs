---
name: declare-and-proceed
description: Decide routing and per-batch choices yourself when material exists or a default is reasonable; do not outsource the decision to the user via AskUserQuestion or prose binary prompts.
when_to_use: TRIGGER when about to ask "A するか B するか?" / "この style で良い?" (routing or per-batch confirmation) via AskUserQuestion or prose. SKIP for user-taste, destructive-op pre-approval, or design-level decisions.
---

# Declare And Proceed

「A か B かどちらから入りますか?」 系の routing 質問と、 batch / iterative 作業中の per-unit / per-batch 採否確認は、 どちらも 「決められるものを user に投げる」 同根の anti-pattern。 自分で fetch / parallel 実行 / verbalize 宣言で proceed すれば user の judgment を浪費しない。 user は事後 chat log で review して指摘する流れに任せる。

## Why

user に質問するのは一見 cheap だが、 累積すると ownership ぼかし / flow 中断 / user の judgment を同じ topic で N 回繰り返させる cost を生む。 一方、 自分で fetch / parallel / 1 度の verbalize 宣言で proceed できるなら、 user が事後に chat log を 1 度読んで指摘するだけで済む (1 wording 修正 vs N 件の per-unit 承認)。 質問前に 1 拍 verbalize して、 投げる先が本当に user しか持っていない判断材料かを check する。

## Process

1. 質問を発しかけた瞬間に **停止**
2. 1 拍 verbalize: 「これは material existing か? default で進めるか? parallel 実行で両立できるか?」
3. いずれかで yes なら自分で決めて proceed (1 unit 目で style 方針 / 結論方針を verbalize 宣言)
4. 残るのは genuine user-taste / unrecoverable destructive op の pre-approval / design-level (architecture / naming / priority / scope) の 3 case — そこは ask

## Rules

### No routing questions

investigation / execution route の binary / ternary 質問抑止。 判断材料を自分で取れる (code / log / config / official doc / 別 file / subagent で answer が分かる) 場合は **並列で網羅実行** し、 結論を出してから報告する。 auto mode の本旨。

- 悪い: 「どこから調査しますか? `A.md` 経由? `B.md` 経由?」 → 両方並列読みできる
- 悪い: 「`X` の log を確認しますか?」 → 確認すべきなのは明らか、 そのまま実行
- 良い: 「A と B の両方を並列読み込みした結果、 A に該当 entry、 B に類似 entry あり。 …」 と報告

### No per-unit confirmation in batch work

batch / iterative work では per-entry / per-batch に user 確認を求めない。 適用範囲:

- memory entry の oneline_summary draft
- 多数 file の一括 Edit / sweep
- mechanical bulk transform (rename / format 統一 等)
- 同種 review pass
- migration / promotion / retirement の batch 化

最初の 1 unit で **style 方針を verbalize 宣言** する:

- どんな draft style か (例: 「3+字 CJK keyword + 絶対日付 + bilingual の 1 文」)
- どの scope か (例: 「user memory 11 entry」)
- 件数 / 完了基準

宣言後は per-unit の 「これで良い?」 を user に聞かない。 user が tone / depth / 用語を変えたい時は事後 chat log review で指摘する流れに任せる。

### Exceptions (依然 user 合意を取る case)

- **Genuine user-taste / priority**: design-level choice (architecture / naming / priority / scope 境界) は依然 ask。 `make-plan-before-coding` の例外条件と同等
- **Unrecoverable destructive op の pre-approval**: push --force / reset --hard / branch 削除 等は `commit-discipline` の通り user 明示承認を取る
- **1 unit 目で style 方針が verbalize 未宣言の場合**: 最初の 1 件で宣言を行う (skip しない)

## Output

適用後の典型 — routing 質問 / per-batch 確認の代わりに、

```
方針: <X 件を Y style で batch 処理。 完了基準は Z>。 進めます。
```

と 1 度 verbalize 宣言してから proceed。 user は事後 chat log を見て redirect する。

## Related

- `verbalize-before-action` — 宣言の base。 本 skill の 1 度 verbalize 宣言はこの skill の特殊例
- `make-plan-before-coding` — design-level は依然 user 合意、 既 documented rationale は再 litigate せず継承 (本 skill の design-level 例外と同根)
- `commit-discipline` — destructive op の pre-approval ルール
