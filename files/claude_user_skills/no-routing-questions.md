---
name: no-routing-questions
description: >
  調査・実行経路の二択 / 三択を user に振らず、 判断材料を自分で取れる場合は並列で網羅実行 → 結論を出してから報告。
  TRIGGER when: 「A するか B するか?」「どちらから入りますか?」「X を確認しますか?」 等を user に聞こうとしたとき;
  「〜してから先に進みますか?」 と routing 質問しようとしたとき;
  AskUserQuestion で 「次に何をすべきか」 を user 主導にしようとしたとき。
  SKIP: 判断材料が user 個人にしか無い (好み / 優先順位 / 未決 design choice);
  destructive 操作の事前承認;
  並列実行不可能で 1 経路選択必要、 判断材料が外部にない場合。
legacy: user CLAUDE.md「一次情報の確認」 § 調査経路は二択提示せず網羅実行 より
---

# No Routing Questions

「A か B かどちらから入りますか?」「X を確認しますか?」 のような調査・実行経路の二択 / 三択提示でユーザーに routing させない。 判断材料を自分で取れる場合は **並列で網羅実行** し、 結論を出してから報告する。 auto mode の本旨。

## Trigger phrases

以下の routing 質問を発しかけた瞬間が trigger:

- 「A するか B するか?」「どちらから入りますか?」
- 「X を先に確認しますか? それとも Y?」
- 「〜を確認しますか?」「〜してから先に進みますか?」
- AskUserQuestion で 「次に何をすべきか」 を user に決めさせようとしたとき

「言いかけたこと自体が該当の証拠」 として発火させる。

## Procedure

1. routing 質問を発しかけた瞬間に **停止**
2. 判断材料が自分で取れるか判定 — code / log / config / official doc / 別 file / 専門 agent で答えが分かるなら yes
3. 並列で網羅実行 (複数 agent / 複数 query を一気に発射、 結果を集約)
4. 結論 + 根拠を 1 つの応答で報告

## SKIP 条件

以下の場合は routing 質問が正当:

- **判断材料が user 個人にしか無い**: 好み (色 / 命名 など) / 優先順位 (どの bug を先に直すか) / 未決 design 選択肢 (3 案あって user choice 待ち)
- **destructive 操作の事前承認**: `git push --force` / `git reset --hard` / branch 削除 / 共有 state 影響など、 user permission を取るべき操作
- **完全に並列実行不可能で 1 経路選ぶ必要があり、 判断材料が外部にない場合**: 稀

## Anti-pattern 例

- 悪い: 「どこから調査しますか? `A.md` 経由? `B.md` 経由?」 → 両方並列読みできる
- 悪い: 「`X` の log を確認しますか?」 → 確認すべきなのは明らか、 そのまま実行
- 良い: 「A と B の両方を並列読み込みした結果、 A に該当 entry、 B に類似 entry あり。 …」 と報告
