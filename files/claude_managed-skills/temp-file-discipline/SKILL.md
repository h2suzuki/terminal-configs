---
name: using-tmp
description: Place temporary files by lifetime and size — ephemeral small files under a per-session /tmp scratch dir, large or mmap'd temp files in /var/tmp, session-spanning work files in drafts/ — and delete temp files when done.
when_to_use: TRIGGER when about to write a temporary / scratch / intermediate file, pick a path for generated output, or say 「/tmp に」「一時ファイル」「scratch」「中間ファイル」. SKIP for editing tracked source files or files the user gave an explicit destination for.
---

# Using /tmp, /var/tmp, and drafts/

一時ファイルの置き場を寿命とサイズで選ぶ skill。 /tmp を temp で埋めて満杯にした事故の再発防止。

## Definitions

- **/tmp** — 再起動で消失する。 しばしば tmpfs (RAM 上の FS) で実装され、 非常に軽量・高速だが **容量が小さい**。 大きな file を置くと RAM を圧迫して満杯になる。
- **/var/tmp** — ディスク上にあり再起動でも消えない。 **より大きい一時 file** を置け、 mmap して使うこともできる。
- **drafts/** — repo 直下、 `.gitignore` 対象。 **session を跨いでしばらく永続させる作業 file** はここに置く (handoff の work file と同じ場所)。

## Rules

- **小さく短命な temp は /tmp、 ただし per-session scratch dir の下**: `/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID/` に置く (`mkdir -p` で lazy 作成)。 session 終了時に SessionEnd hook (session_cleanup.py) がこの dir を確実に全削除するので、 取りこぼしが残らない。
- **使い終わったら即削除が基本**: temp file は用が済んだら `rm` する。 SessionEnd の全削除は最後の安全網であって、 session 中に溜め込んで良い言い訳ではない (tmpfs の RAM を食う)。
- **大きい / mmap / reboot を跨ぐ temp は /var/tmp**: tmpfs の RAM を消費しない。 これも用済みで `rm` する。
- **session を跨ぐ作業 file は drafts/**: 次 session で再開する中間成果物は drafts/ に置き、 /tmp には置かない (/tmp は再起動で消えるため永続させられない)。
- **Docker container 内**: container 内で temp を作るときは container 内 (`/tmp` 等) に作る — container 破棄で消える。 ただし host から bind-mount された `/tmp` に書く場合は **host 側の本ルール (scratch dir + 削除) に準拠**する。

## Output

temp file は `/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID/` 下に作り用済みで `rm`。 大容量・mmap・reboot 跨ぎは /var/tmp、 session 跨ぎは drafts/。 session 終了時は session_cleanup.py が scratch dir を全削除する。

## Related

- `handoff` — session 跨ぎ work file の drafts/ 規約はこの skill と共有する。
- `writing-bash` — temp file 操作 (`mktemp` 等) の shell 規約。
