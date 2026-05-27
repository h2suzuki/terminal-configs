---
name: post-edit-read
description: 同一 file への N 件の Edit / MultiEdit を 並列発行すると 1 件目以外 cache invalidated (mtime tracker stale) で blocked になるので、 シリアル化 + 各 Edit 直後に target region を Read して tracker を refresh する。 Read は結果 verify も兼ねる。 別 file 間は並列で OK
when_to_use: TRIGGER when about to issue multiple Edit / MultiEdit calls on the same file (in parallel or sequence), or when an Edit fails with 「前回の Read から内容が変化。 編集前に、 再 Read で現内容の確認が必要。」 / mtime cache error. SKIP for single Edit on a file, or for Edit operations on different files (file-independent mtime trackers — parallel OK).
---

# Post-Edit Read

同一 file に複数 Edit / MultiEdit を続ける場合、 各 Edit の直後に該当 region を Read してから次の Edit を発行する。 Read は変更結果の verify も兼ねる。

## Rules

### 並列発行は同 file で 1 件しか通らない

同一 file に対する N 個の Edit を **並列に** 発行すると、 最初の 1 件しか成功しない (1 件成功 → mtime 進む → 残り N-1 件は cache invalidated)。 並列にせずシリアル化する。

### Post-edit Read で tracker refresh

同一 file への 2 件目以降の Edit の前に target region の Read を 1 回挟む。 offset / limit で edit 対象行のみ拾えば cheap。

### 別 file 間は並列 OK

別 file の Edit は並列のままで OK (file 別に tracker は独立)。

## Why

Claude Code harness は Read / Write 時点の mtime を tracker に持っており、 Edit 成功後の新しい mtime は (Edit 自身では tracker 更新されないため) 次の Edit 試行時に "直近 Read/Write 以降に disk 側 mtime が変化" と判定されて hook で blocked になる。 Read を挟むと tracker が refresh されて次の Edit が通る。

2026-05-26 session で 8 件編集 (4 箇所 × 2 file) を並列発行し、 1 round で 2 件しか通らず 3 round に分けるはめになって read tool 最小化原則と矛盾する re-Read を量産した経験から起票。

## Related

- `writing-code`: Pause before tool calls (token 効率の側面)。 本 skill は harness mtime semantics の側面 (orthogonal)
- **Legacy:** user memory `feedback_post_edit_read_for_mtime_tracker.md` (2026-05-26 起票) より昇格
