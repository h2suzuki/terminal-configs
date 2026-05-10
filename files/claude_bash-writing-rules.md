---
name: bash-writing-rules
description: >
  Rules for writing bash scripts and shell functions.
  TRIGGER when: user is editing or creating a .sh file; user asks to write a shell
  script, bash function, or multi-line shell pipeline.
  SKIP: Python, Ruby, fish, or other non-bash scripts.
---

# Bash Writing Rules

- **パイプを避けられる時は避ける。**
  - `grep regex | awk '{ do-something }'` → `awk '/regex/ { do-something }'`
  - `echo "$var" | cmd` → `cmd <<< "$var"`（here-string; サブシェルを生成しない）

- **プロセス生成はなるべく避ける。**
  - jq 式の中で現在時刻が必要なら `date +%s` を spawn せず jq 組み込みの `now` を使う
  - `cp src dst && chmod 0755 dst` → `install -m 0755 src dst`（1 プロセスで完結）

- **プログラム名をハードコードしない。**
  - shebang: `#!/bin/bash` ではなく `#!/usr/bin/env bash`
  - コマンドパスを絶対パスで書かず PATH に任せる（`/usr/bin/jq` → `jq`）
  - スクリプト自身の名前はリテラルではなく `$(basename "$0")` を使う

- **shellcheck が使えるなら使う。** スクリプトを書いたら `shellcheck script.sh` で検証する
