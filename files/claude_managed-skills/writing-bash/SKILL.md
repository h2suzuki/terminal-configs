---
name: writing-bash
description: Rules for writing bash scripts and shell functions.
when_to_use: TRIGGER when editing or creating a .sh file, or when writing a shell script / bash function / multi-line shell pipeline. SKIP for Python, Ruby, fish, or other non-bash scripts.
---

# Bash Writing Rules

## Rules

- **パイプを避けられる時は避ける。**
  - `grep regex | awk '{ do-something }'` → `awk '/regex/ { do-something }'`
  - `echo "$var" | cmd` → `cmd <<< "$var"`（here-string; サブシェルを生成しない）

- **プロセス生成はなるべく避ける。**
  - jq 式の中で現在時刻が必要なら `date +%s` を spawn せず jq 組み込みの `now` を使う
  - `cp src dst && chmod 0755 dst` → `install -m 0755 src dst`（1 プロセスで完結）

- **実行されるスクリプトには exec bit を必ず立てる。** shebang 付きで bare command（`./x` / hook の `command` field / `$PATH` 経由）として起動されるファイルは mode 644 だと `Permission denied` で exec 不能。
  - 作成したら `chmod +x`。 git 管理下なら `git ls-files -s <path>` が `100755` か確認（`100644` は実行不可）
  - `cp` / `cp -r` / `install`（`-m` 無し）は **source の mode をそのまま deploy 先へ複製**する。 deploy script が `-m` で上書きしない限り、 source の mode 誤りは deploy 先の exec 失敗に直結する

- **プログラム名をハードコードしない。**
  - コマンドパスを絶対パスで書かず PATH に任せる（`/usr/bin/jq` → `jq`）
  - スクリプト自身の名前はリテラルではなく `$(basename "$0")` を使う

- **core-utils 以外のコマンドは存在確認してから使う。**
  `command -v foo >/dev/null 2>&1 || { echo "foo not found"; exit 1; }`
  あるいは任意実行なら `if command -v foo >/dev/null 2>&1; then foo ...; fi`

- **shellcheck が使えるなら使う。** スクリプトを書いたら `shellcheck script.sh` で検証する
