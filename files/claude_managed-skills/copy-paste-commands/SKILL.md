---
name: copy-paste-commands
description: user が手動実行する必要があるコマンド (host 側 cp / git checkout / git push / claude invocation / curl 等) は、 毎回そのままコピペで使える形 — 独立 fenced code block + 完全 path (絶対 or repo 相対) + 余分な inline prose なし — で提示する
when_to_use: TRIGGER when about to instruct user to run a command manually (host 側 / cp / git push etc), or write prose like "以下のコマンドを実行" etc. SKIP when describing a command for explanation only.
---

# Copy-Paste Commands

user に手動実行を依頼するコマンドは、 毎回そのままコピペで実行できる形で提示する。

## Rules

### 形式要件

- **独立した fenced code block に置く** (` ``` `)。 inline backtick (`cmd`) は readability 用で、 実行用ではない
- **1 コマンド 1 行を基本** とする。 複数コマンド連続実行が必要なら同 code block 内に並べる (selection が連続範囲なので OK)
- **ファイル path は完全形** で、 user が cd しなくても貼り付けて動くもの。 絶対 path か repo root 相対、 半端な相対 path は避ける
- **prose 説明は code block の外**、 code block 内に混ぜない

### Trigger context

「user に host 側で実行してもらう」「ホスト側ターミナルから」「ユーザーの手動で」「お手元で」 等の文脈が出たら、 その直後に独立 code block で完全コマンドを置く。

### 適用先

- `cp` (例: drafts/... → .claude/... の patch-handoff)
- `git checkout` / `git pull` / `git push`
- `claude invocation` (`claude --bg ...` 等)
- `curl` / `gh pr create`
- HEREDOC を含む長い `git commit -F` も同様

## Why

patch-handoff モデルでは host 側 cp / git 等の手動実行が頻繁に発生する。 コピペで動く形でないと user の手間が増える。 2026-05-23 user feedback: 「cp コマンド、 私が必要なら、 毎回コピペできる形で出してくれると助かります」。

## Related

- `document-editor`: 永続 artifact の編集規律。 本 skill は chat 内で user に出すコマンドが対象 (orthogonal)
- **Legacy:** user memory `feedback_user_actionable_commands_copy_pasteable.md` (2026-05-23 起票) より昇格
