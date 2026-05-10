---
name: bash-writing-rules
description: >
  Rules for writing bash scripts and shell functions.
  TRIGGER when: user is editing or creating a .sh file; user asks to write a shell
  script, bash function, or multi-line shell pipeline.
  SKIP: Python, Ruby, fish, or other non-bash scripts.
---

# Bash Writing Rules

## Safety

- `set -euo pipefail` をすべてのスクリプト先頭に置く。
- 関数内変数は `local` で宣言する。
- 一時変数はスコープを抜ける前に `unset` する。慣習として `_` プレフィックスを付ける。

## プロセス spawn の最小化

- `echo "$var" | cmd` ではなく here-string `cmd <<< "$var"` を使う（サブシェル不要）。
- 複数フィールドを個別の `jq` 呼び出しで取得せず、1 回の `jq` 呼び出しにまとめる。
- jq 式の中で現在時刻が必要なら `date +%s` を spawn せず jq 組み込みの `now` を使う。

## jq

- 条件チェックには `jq -e '...'` を使う。`true` → exit 0、`false/null` → exit 1 を利用して `&&` / `if` に繋げられる。
- フィールド欠損時のデフォルト: `(.foo // default_value)`。`resets_at` のように「欠損なら条件 false にしたい」場合は `(.resets_at // now)` のように現在値をデフォルトにする。

## ファイル操作

- `cp` + `chmod` の二段階ではなく `install -m MODE src dst` を使う。
- 既存ファイルへのアトミック書き込みは mktemp → 書き込み → `mv` の順で行う。
  ファイルが壊れた状態で読まれるリスクを防ぐため、直接上書きしない。

## Git 操作

- `cd /repo && git ...` ではなく `git -C /repo ...` を使う（cwd を汚染しない）。
- コミットで変更されたファイル一覧の取得: `git diff-tree --no-commit-id -r --name-only HEAD`
  （plumbing コマンドのため初回コミットでも動作する）。

## 文字列・検索

- 固定文字列の検索には `grep -qF` を使う（正規表現エンジンを起動しない）。
- 単純なプレフィックス・サフィックス除去は `sed` を呼ばず `${var#prefix}` / `${var%suffix}` を使う。
