---
name: no-routing-questions
description: Do not delegate investigation / execution route decisions to the user via binary or ternary prompts; if you can fetch the decision material, run paths in parallel and report a conclusion.
when_to_use: TRIGGER when about to ask the user "A するか B するか?" / "どちらから入りますか?" / "X を確認しますか?" / "〜してから先に進みますか?", or when about to use AskUserQuestion to make the user drive "what to do next". SKIP when the decision material exists only with the user (taste / priority / undecided design choice), when seeking pre-approval for destructive ops, or in the rare case parallel execution is impossible and external info cannot inform the route.
---

# No Routing Questions

「A か B かどちらから入りますか?」「X を確認しますか?」 のような調査・実行経路の二択 / 三択提示でユーザーに routing させない。 判断材料を自分で取れる場合は **並列で網羅実行** し、 結論を出してから報告する。 auto mode の本旨。

## Process

1. routing 質問を発しかけた瞬間に **停止**
2. 判断材料が自分で取れるか判定 — code / log / config / official doc / 別 file / 専門 agent で答えが分かるなら yes
3. 並列で網羅実行 (複数 agent / 複数 query を一気に発射、 結果を集約)
4. 結論 + 根拠を 1 つの応答で報告

## Examples

- 悪い: 「どこから調査しますか? `A.md` 経由? `B.md` 経由?」 → 両方並列読みできる
- 悪い: 「`X` の log を確認しますか?」 → 確認すべきなのは明らか、 そのまま実行
- 良い: 「A と B の両方を並列読み込みした結果、 A に該当 entry、 B に類似 entry あり。 …」 と報告

## Related

- **Legacy:** user CLAUDE.md「一次情報の確認」 § 調査経路は二択提示せず網羅実行 より
