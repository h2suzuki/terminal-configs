---
name: temp-file-discipline
description: Place temporary files by lifetime and size — ephemeral small files in a per-session /tmp scratch dir reached via TMPDIR so mktemp/tempfile land there, large or mmap'd temp files in /var/tmp, session-spanning work files in drafts/ — and delete temp files when done.
when_to_use: TRIGGER when about to write a temporary / scratch / intermediate file, pick a path for generated output, or say 「/tmp に」「一時ファイル」「scratch」「中間ファイル」. SKIP for editing tracked source files or files the user gave an explicit destination for.
---

# Temp File Discipline

一時ファイルの置き場を寿命とサイズで選ぶ skill。 /tmp を temp で埋めて満杯にした事故の再発防止。

## Definitions

- **/tmp** — 再起動で消失する。 しばしば tmpfs (RAM 上の FS) で実装される、 **非常に軽量・高速だが容量が希少**なエリア。 ためると**すぐ満杯 (disk full) になり**、 自分や他プロセスの temp 確保まで巻き込んで失敗させる。 ゆえに小さく短命なものだけ置き、 使い終わったら消す。
- **/var/tmp** — ディスク上にあり再起動でも消えない。 **より大きい一時 file** を置け、 mmap して使うこともできる。
- **drafts/** — repo 直下、 `.gitignore` 対象。 **session を跨いでしばらく永続させる作業 file** はここに置く (handoff の work file と同じ場所)。

## Rules

- **小さく短命な temp は /tmp の per-session scratch dir に集約**: scratch dir は `/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID/`。 SessionEnd hook (session_cleanup.py) が session 終了時にこの dir を丸ごと削除するので、 取りこぼしが残らない。
- **scratch dir を TMPDIR にして mktemp に任せる**: `mktemp` / 多くの CLI / Python `tempfile` は `$TMPDIR` を respect する。 temp を作る Bash で `export TMPDIR="/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID"; mkdir -p "$TMPDIR"` してから `mktemp` を使えば、 直書きパスを散らさず scratch に落ちる。 shell state は Bash 呼び出し間で persist しないので temp を作る呼び出しごとに設定する (または `mktemp -p "/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID"`)。
- **使い終わったら即削除が基本**: temp は用が済んだら `rm` する。 SessionEnd の全削除は最後の安全網であって、 session 中に溜め込んで良い言い訳ではない (tmpfs の RAM を食う)。
- **大きい / mmap / reboot を跨ぐ temp は /var/tmp**: tmpfs の RAM を消費しない。 これも用済みで `rm` する。
- **session を跨ぐ作業 file は drafts/**: 次 session で再開する中間成果物は drafts/ に置き /tmp には置かない (/tmp は再起動で消えるため永続させられない)。
- **Docker container 内**: container 内部だけで使う temp は、 host に bind-mount されていない container ローカルな書き込み層に置く (container 破棄で一緒に消える)。 **注意**: container の `/tmp` は **host の /tmp を bind-mount したものかもしれない**。 その場合 file の実体は host /tmp に残るので、 mount か否かを確認し、 mount なら **host 側の本ルール (scratch dir + 削除) に準拠**する。

## Output

temp は `TMPDIR=/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID` 下に `mktemp` で作り用済みで `rm`。 大容量・mmap・reboot 跨ぎは /var/tmp、 session 跨ぎは drafts/。 session 終了時は session_cleanup.py が scratch dir を全削除する。

## Related

- `handoff` — session 跨ぎ work file の drafts/ 規約はこの skill と共有する。
- `writing-bash` — `mktemp` 等の temp file 操作の shell 規約。
