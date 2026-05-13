## 禁則事項: deploy 先だけ編集して repo を放置するな

このリポジトリは `ubuntu2404-wsl.sh` / `debian12.sh` の `copy` 行で `files/` 配下の source を `/etc/claude-code/`・`~/.claude/`・`/usr/local/bin/` などへ deploy する構造である。 **canonical source は常に `files/` 側であり、deploy 先はその出力**。

- deploy 先（`/etc/claude-code/<name>`、`~/.claude/settings.json`、`/usr/local/bin/<name>` など）を編集したら、対応する `files/<name>` を**必ず同じセッション内で**同内容に更新し、両方を含めて commit する。 deploy 先だけ直して終わるのは禁止
- 編集前に対応 source の有無を確認する手順: `grep -rn '<basename>' /home/h2suzuki/terminal-configs/`（`copy` 行で deploy 元 path が判明する）
- 既に deploy 先だけ編集してしまった場合は、その場で `cp <deployed> files/<source>` で back-port してから commit。 「あとでやる」を許さない

**Why:** repo を放置すると、次に repo から再 deploy した時点で改造が静かに消える regression を抱える。 過去にこのパターンを実際に起こし、ユーザーから明示的に禁止指示が出ている。

## セッション終了時
- ユーザーがセッション終了を示唆した時（「終わります」「お疲れさまでした」「また」など）、`git status` で未コミット変更・未 push commit を確認し、漏れがあれば簡潔に知らせてから sign off する。沈黙で見送らない。
