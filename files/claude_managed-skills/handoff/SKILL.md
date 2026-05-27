---
name: handoff
description: Produce a session-boundary handoff document with fixed schema so next-me can resume within 5 minutes.
when_to_use: TRIGGER when user signals session end ("handoff" / "セッションリセット" / "お疲れさま" etc) AND 作業が途中で次 session で再開必要。 SKIP for mid-session task updates / todos.md progress flips / 完結し再開不要な session 終了。
---

# Session Handoff

session 境界で context を時間軸越しに伝達し、 next-me が handoff だけで 5 分以内に再開 step を確定できる状態を作る。 設計核 (I-PASS / SITREP / Commander's Intent 等 handover protocol から抽出): 固定 schema・Status 1 文・Action+Contingency・受信側 readback・Intent retention。

## 目的を絞る

handoff は **作業再開** のためにだけ書く。 作業再開に役立たない情報は書かない:

- git log で取れる commit list / 履歴記録
- 既に CLAUDE.md / memory entry / commit message body / code comment に書かれた rationale
- 完了済 cleanup の経緯
- 受動的 observation (課金 spike 観察待ち等、 次 session で action しない項目)
- 「念のため書いておく」 系の boilerplate

session 終了時に作業が完結し次 session 再開不要なら、 **handoff 自体を skip**。 file を増やさない。

## Process

### 1. Pre-handoff checks

1. **作業途中判定**: 次 session で再開が必要か? 完了済なら handoff skip、 todos.md と commit log で充分
2. `git status` で working tree clean か確認、 未 commit は `commit-discipline` skill で処理
3. `todos.md` の Critical / High open items が本 session の closure / 部分進捗を反映しているか verify (`writing-todos` skill)
4. 本 session で触れた canonical doc (`.claude/CLAUDE.md` / `~/.claude/CLAUDE.md` / `/etc/claude-code/CLAUDE.md`) に新規 rule が反映済か確認 — rule 追加分は当該 file に書き、 handoff には pointer のみ
5. `todos.md` 冒頭 `active handoffs` section に本 handoff への pointer があるか確認、 無ければ追加

### 2. Project-specific extension (optional)

`ls .claude/skills/handoff-extension/SKILL.md` で存在確認、 あれば Skill tool で invoke、 project-specific pre-check (spec / style guide / chapter index sync) を実行させる。

### 3. Write the document

**書き込み先と方式**:

- 一般的なセッション境界: `last-session-handoff.md` (repo top、 `.gitignore` 対象)
- task-lineage が長期化している作業: `drafts/<task-slug>-handoff.md` (`drafts/` も `.gitignore` 対象、 必要なら作成)
- **append-only**: 新 session 分を file 冒頭に prepend、 既存 section は触らない (並行 session で前 section を破壊しない安全策)
- session ID は transcript path (`/home/...<sessionid>.jsonl`) basename の先頭 8 文字 (例: `c3175320`)

**session section schema (該当無い節は省略)**:

````markdown
## Session <id> (YYYY-MM-DD EOD)

> 1-2 行 — 今どこで、 次は何をするか

### Status
- Stable / Watcher / Unstable
- blocker (無ければ「なし」)

### 次の action
- 着手 step (1-3 行)
- contingency: `if X happens, do Y` (該当時のみ)

### 必読 (該当時のみ)
- 手動 Read 推奨 file: priority 順、 各 1 行で why

### Caveat (該当時のみ)
- 作業再開に関わる罠 / format dependency / 動かせない uncertainty
- rule / memory 更新の存在 (場所付き pointer のみ、 詳細は当該 file)
````

### 4. Self-audit

handoff を書いた後 1 拍 verbalize:

- next-me が本 handoff だけで 5 分以内に再開できるか? Read 順は明確か?
- Status (Stable/Watcher/Unstable) が現状を正しく表現しているか?
- Action に Contingency が網羅されているか (単なる todo list で終わっていないか)?
- **削った情報は本当に作業再開に不要か?** 「念のため」 で膨らませていないか?
- `todos.md` の `active handoffs` pointer は追加 / 維持済か?

### 5. Next-me readback (session 開始時)

next-me は handoff を read 後 1 拍 verbalize する: Status / 次の action と why / 読むべき前提 file / 動かせない Caveat。 答えられない項目があれば handoff doc 自体に gap があるので、 user に質問する前に handoff doc を update する。

### 6. Consume cleanup (session 開始時)

next-me が handoff を read / consume したら、 該当 session section を `last-session-handoff.md` から削除して良い (file が空なら file ごと削除可)。 file は「未 consume の handoff collection」 として運用。 並行 session で複数 section が並ぶのは、 複数 session が再開待ち中である状態を意味する。

## Rules

- **作業再開に役立たないことは書かない**: git log / 履歴記録 / 完了済 cleanup の経緯 / 受動的 observation / 既に CLAUDE.md・memory・commit body・code comment に書かれた rationale は省く。 詳細は当該 file に書く、 handoff は pointer のみ
- **完結 session は handoff を書かない**: 作業途中じゃない / 次 session 再開不要なら skip
- **append-only / 既存 section を破壊しない**: file 冒頭への section prepend で書き込む。 全体上書きは厳禁 (並行 session で前 section が消える regression)
- **session start consume cleanup**: read 後の section は削除して良い、 file は最小に保つ
- **todos.md との役割分担**: todos.md = 永続 task ledger (canonical state、 auto-load)、 handoff = session 境界 context bridge (再開のための minimum delta)。 矛盾時は **todos.md が canonical**
- **active handoffs pointer 必須**: handoff 作成時は `todos.md` 冒頭 `active handoffs` section に `- <path> — <lineage 名 + 直近 status 1 行>` 追記、 lineage close 時は pointer も削除
- **Memory / rule 更新は当該 file に書き handoff には pointer のみ**: `~/.claude/CLAUDE.md` や memory entry に rule 追加した場合は当該 file 本体に書き、 handoff Caveat には「rule X 追加 (@<file>)」 形式の参照だけ
- **Intent retention は当該 commit / comment / rule file に**: 「なぜそうしたか」 は commit message body / code comment / rule file に残す (Commander's Intent)。 handoff にダブって書かない

## Output

- `last-session-handoff.md` または `drafts/<task-slug>-handoff.md` の冒頭に新 session section を prepend (作業途中で再開必要な場合のみ、 そうでなければ skip)
- `todos.md` 冒頭 `active handoffs` section の pointer 追加 / 維持
- session 内の commit 完了 (`commit-discipline`)

## Related

- `writing-todos` — todos.md format と verify-before-flip / block-level deletion 規律、 handoff と todos.md の更新責任の片側
- `commit-discipline` — pre-handoff の commit 整理、 session-end の uncommitted 残禁止
- `writing-skills` — 本 skill や project-local `handoff-extension` を書く時の format reference
- `verbalize-before-action` — self-audit / next-me readback の verbalize 義務の基盤
