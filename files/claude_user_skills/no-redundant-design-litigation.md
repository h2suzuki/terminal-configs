---
name: no-redundant-design-litigation
description: >
  Documented rationale (code comment / canonical doc / handoff) のある設計選択を user に確認 question で再 litigate しない、 継承して進む。
  TRIGGER when: 既存の定数値 / 閾値 / metric / アーキ選択を user に再提示しようとしたとき;
  「X にしますか? Y にしますか?」 と既存設計を再選択させそうなとき;
  「この値の根拠は?」 を user に聞く前 (まず doc / commit message を読む)。
  SKIP: 前提変化 / 新規 trade-off が発生、 rationale が陳腐化、 documented 化されていない新規 design choice。
legacy: user CLAUDE.md「一次情報の確認」 § documented な設計選択は再 litigate しない より
---

# No Redundant Design Litigation

documented rationale が code comment / canonical doc / handoff に既に書かれている設計選択を、 user への確認 question で再 litigate しない。 設計案を提示する前に関連 comment / doc を必要範囲で読み、 既存 rationale があれば継承して実装に進む。

## Trigger phrases

設計提示の前 / 設計選択を user に問い返そうとする前に発火:

- 既存の定数値・閾値・metric を提示するとき (例: 「7 日 TTL にしますか?」)
- アーキ選択を提示するとき (例: 「fork で行きますか? inline で行きますか?」)
- 「これ X にしますか? それとも Y にしますか?」 と既存設計を再選択させようとしたとき
- 「この値の根拠は?」 を user に聞こうとしたとき (まず doc / commit message を読む)

「言いかけたこと自体が該当の証拠」。

## Procedure

1. 設計案を提示する / question を発しかけた瞬間に **停止**
2. 関連 code comment / canonical doc / handoff / commit message を 必要範囲 で読む
3. 「この選択は既に documented な rationale を持たないか?」 を 1 拍 verbalize
4. rationale 発見 → 継承して実装に進む (user に再 litigate しない)
5. rationale 不在 → 新規 design として user に提示するのは OK

## SKIP 条件

以下の場合は再 litigate / user 確認が正当:

- **前提変化や新規 trade-off が発生**: 元 rationale が想定していなかった条件が出現
- **rationale が見当たらず documented 化されていない**: 純粋に新規 design choice
- **rationale が陳腐化**: 元の理由が今では成立しないと判明 (この場合も user 提示前に観測結果を 1 文 verbalize)

## Anti-pattern 例

- 悪い: 「`TTL_SECONDS` を 7 日にしますか? 30 日にしますか?」 (既に docstring に 「7 days because session usually completes within a week」 と書いてある場合)
- 悪い: 「`--bg` flag を使う / 使わないどちらにしますか?」 (handoff に 「async が要求なので --bg」 と書いてある場合)
- 良い: 「commit message に明記された通り fork 方式を採用、 実装に進みます」 (documented rationale 継承)
- 良い: 「既存 doc に rationale が見当たらないので、 新規に 3 案提示します: A / B / C」 (新規 design)
