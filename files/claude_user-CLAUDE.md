# ~/.claude/CLAUDE.md: プロジェクト横断 preference

## コミット
- author は `Hideaki Suzuki <h2suzuki@gmail.com>` で統一する（`noreply.*` は使わない）。コミット前に `git config user.email` を確認する。

## Bash 運用

system prompt の「絶対パスで `cd` を避ける」に加えて以下を実施する。

- **cwd 汚染を疑うエラーパターン**: `no such file` / `cannot open directory` / `pathspec did not match` が routine コマンドで突然出たら推測 retry せず `pwd` で確認する
- **git は cwd 不変で切替**: `cd /repo && git ...` ではなく `git -C /repo ...` を使う
- **1 行複数操作**: `cd /a/b && mkdir c && mv x c/` ではなく `mkdir /a/b/c && mv /a/b/x /a/b/c/`

## グローバルメモリ
プロジェクト横断で適用すべき memory（LLM 一般の認知バイアス対策、ユーザーの普遍的 preference、複数プロジェクトで再現したパターンなど）は、project-local の `<project>/memory/` ではなく `~/.claude/global-memory/` に保存する。`MEMORY.md` の代わりに `INDEX.md` を使う。

カテゴリ判断に迷う場合は project-local を優先（後で global に昇格させやすい）。

@/home/h2suzuki/.claude/global-memory/INDEX.md
