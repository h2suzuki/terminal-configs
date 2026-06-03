---
name: writing-python
description: Rules for writing Python scripts and hooks.
when_to_use: TRIGGER when editing or creating a .py file. SKIP for bash, Ruby, fish, or other non-Python scripts.
---

# Python Writing Rules

Python の add-on rule 集。 `writing-code` (universal) の上に積む。 主に hook / CLI として実行される .py の deploy 時 mode ミスを防ぎ、 ruff で lint / format し、 ty で type check する。

## Rules

- **実行される .py スクリプトには exec bit を必ず立てる。** `#!/usr/bin/env python3` shebang 付きで bare command（hook の `command` field / `./x` / `$PATH` 経由）として起動される .py は mode 644 だと `Permission denied` で exec 不能（`python3 x.py` と明示起動する場合のみ exec bit 不要）。
  - 作成したら `chmod +x`。 git 管理下なら `git ls-files -s <path>` が `100755` か確認（`100644` は実行不可）
  - `cp` / `cp -r` / `install`（`-m` 無し）は **source の mode をそのまま deploy 先へ複製**する。 deploy script が `-m` で上書きしない限り、 source の mode 誤りは deploy 先の exec 失敗に直結する

- **編集した .py は ruff で lint + format する。** ruff は Python の linter + formatter（system-wide 導入済: standalone installer で `/usr/local/bin/ruff`）。 編集後に `ruff check --extend-select B,C4,PIE,RET,RUF100,PLW1510,UP015 <path>`（lint）と `ruff format <path>`（整形）を通す。
  - 自動修正できる指摘は `--fix` で直す。 **設定ファイルは置かず CLI 引数で運用**（no-config 方針）。 base default は `E4/E7/E9/F`（**E501（行長）は非対象**ゆえ bilingual な長行コメントは誤検知しない）。 `--extend-select` で上乗せする実バグ系: `B`(bugbear) / `C4` / `PIE` / `RET`（現状 0 hit の前方保険）、 `PLW1510`（subprocess の `check=` 漏れ）、 `UP015`（冗長 open mode）、 `RUF100`（unused-noqa）。 **noisy な group は足さない**: `SIM`（fail-open try/except に誤爆）・`I`/`PLC0415`（意図的 lazy import）・`S101`（test の assert）・`UP031`/`RUF001-3`（printf 様式 / 全角句読点）。
  - `ruff format` は Black 互換（double-quote）で **コードを reflow する**（コメント / 文字列は折り返さない）。 手書き整形の hook では適用後に diff を確認してから commit する。

- **編集した .py は ty で type check する。** ty は Astral の Python type checker（system-wide 導入済: standalone installer で `/usr/local/bin/ty`）。 編集後に `ty check <path>` を通し、 自分が書いた / 触った範囲の型エラーを解消する。 設定ファイルは置かず default で運用（ruff と同じ無設定方針）。 これは `writing-code`「Run linters / formatters / type-checkers」 universal rule の Python 具体化。

- **post-edit check は inline 実行で workflow 化しない**（決定的 oracle ゆえ。 universal な扱いは `writing-code`）。 ruff / ty は dir・project 単位で native batch するので repo 全体でも 1 プロセスで足り、 per-file で agent を fan out する必要がない。

- **抑制構文**（適用判定は `writing-code`「指摘は修正が基本、 抑制は例外」）:
  - ruff lint: `# noqa: <code>`（例 `# noqa: F401`）。 bare `# noqa` は全 rule 抑制ゆえ code を指定する
  - ruff format: `# fmt: skip`（1 行）/ `# fmt: off` … `# fmt: on`（ブロック）。 Black 互換 reflow が手書き整形を崩して逆に読みにくくする時に使う
  - ty: `# ty: ignore[<rule>]`（例 `# ty: ignore[invalid-argument-type]`）。 **ty は mypy 形式の `# type: ignore[CODE]` を honor しない**（bracket code 無効）。 bare `# type: ignore` は効くが全 rule 抑制ゆえ、 rule 限定は ty native 形式で書く

## Related

- `writing-code` — universal source code rule (mode 分類 / convention / 浪費 pattern 等)。 add-on は universal を replace せず上に積む
- `writing-bash` — sibling の language-specific add-on。 同じ exec-bit / deploy-mode / lint rule を bash 文脈で持つ（lint/format は shellcheck）
