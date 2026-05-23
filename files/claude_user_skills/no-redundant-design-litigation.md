---
name: no-redundant-design-litigation
description: For design choices with documented rationale (code comment / canonical doc / handoff), do not re-litigate via user-confirmation; inherit the rationale and proceed.
when_to_use: TRIGGER when about to present an existing constant / threshold / metric / arch choice for user reconfirmation, when about to ask "X にしますか? それとも Y にしますか?" on an already-decided choice, or when about to ask "この値の根拠は?" before reading code comment / commit message / handoff. SKIP when the premise has changed or new trade-off appeared, when the rationale is documented but proven obsolete, or for genuinely new design choices that are not documented yet.
---

# No Redundant Design Litigation

documented rationale が code comment / canonical doc / handoff に既に書かれている設計選択を、 user への確認 question で再 litigate しない。 設計案を提示する前に関連 comment / doc を必要範囲で読み、 既存 rationale があれば継承して実装に進む。

## Process

1. 設計案を提示する / question を発しかけた瞬間に **停止**
2. 関連 code comment / canonical doc / handoff / commit message を 必要範囲 で読む
3. 「この選択は既に documented な rationale を持たないか?」 を 1 拍 verbalize
4. rationale 発見 → 継承して実装に進む (user に再 litigate しない)
5. rationale 不在 → 新規 design として user に提示するのは OK

## Examples

- 悪い: 「`TTL_SECONDS` を 7 日にしますか? 30 日にしますか?」 (既に docstring に 「7 days because session usually completes within a week」 と書いてある場合)
- 悪い: 「`--bg` flag を使う / 使わないどちらにしますか?」 (handoff に 「async が要求なので --bg」 と書いてある場合)
- 良い: 「commit message に明記された通り fork 方式を採用、 実装に進みます」 (documented rationale 継承)
- 良い: 「既存 doc に rationale が見当たらないので、 新規に 3 案提示します: A / B / C」 (新規 design)

## Related

- **Legacy:** user CLAUDE.md「一次情報の確認」 § documented な設計選択は再 litigate しない より
