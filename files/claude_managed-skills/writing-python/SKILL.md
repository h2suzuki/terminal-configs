---
name: writing-python
description: Rules for writing Python scripts and hooks.
when_to_use: TRIGGER when editing or creating a .py file. SKIP for bash, Ruby, fish, or other non-Python scripts.
---

# Python Writing Rules

Python の add-on rule 集。 `writing-code` (universal) の上に積む。 主に hook / CLI として実行される .py の deploy 時 mode ミスを防ぐ。

## Rules

- **実行される .py スクリプトには exec bit を必ず立てる。** `#!/usr/bin/env python3` shebang 付きで bare command（hook の `command` field / `./x` / `$PATH` 経由）として起動される .py は mode 644 だと `Permission denied` で exec 不能（`python3 x.py` と明示起動する場合のみ exec bit 不要）。
  - 作成したら `chmod +x`。 git 管理下なら `git ls-files -s <path>` が `100755` か確認（`100644` は実行不可）
  - `cp` / `cp -r` / `install`（`-m` 無し）は **source の mode をそのまま deploy 先へ複製**する。 deploy script が `-m` で上書きしない限り、 source の mode 誤りは deploy 先の exec 失敗に直結する

## Related

- `writing-code` — universal source code rule (mode 分類 / convention / 浪費 pattern 等)。 add-on は universal を replace せず上に積む
- `writing-bash` — sibling の language-specific add-on。 同じ exec-bit / deploy-mode rule を bash 文脈で持つ
