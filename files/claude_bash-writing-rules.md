---
name: bash-writing-rules
description: >
  Rules for writing bash scripts and shell functions.
  TRIGGER when: user is editing or creating a .sh file; user asks to write a shell
  script, bash function, or multi-line shell pipeline.
  SKIP: Python, Ruby, fish, or other non-bash scripts.
---

# Bash Writing Rules

- **パイプを避けられる時は避ける。** 例: `grep regex | awk '{ do-something }'` の代わりに `awk '/regex/ { do-something }'`
- **プロセス生成はなるべく避ける。** 例: jq 式の中で現在時刻が必要なら `date +%s` を spawn せず jq 組み込みの `now` を使う
- **shellcheck が使えるなら使う。** スクリプトを書いたら `shellcheck script.sh` で検証する
