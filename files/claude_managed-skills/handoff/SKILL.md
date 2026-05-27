---
name: handoff
description: Produce a session-boundary handoff document with fixed schema so next-me can resume within 5 minutes.
when_to_use: TRIGGER when user signals session end ("handoff" / "セッションリセット" / "お疲れさま" etc) AND 作業が途中で次 session で再開必要 (= todos.md に open task block がある)。 SKIP for mid-session task updates / todos.md progress flips / 完結し再開不要な session 終了。
---

# Session Handoff

session 境界で context を時間軸越しに伝達し、 next-me が handoff だけで 5 分以内に再開 step を確定できる状態を作る。 設計核 (I-PASS / SITREP / Commander's Intent 等 handover protocol から抽出): 固定 schema・Status 1 文・Action+Contingency・受信側 readback・Intent retention。

## 目的を絞る

handoff は **作業再開** のためにだけ書く。 1 handoff section は **1 todos.md parent task block** に対応 (1-to-1)、 lifecycle 同期。 作業再開に役立たない情報は書かない:

- git log で取れる commit list / 履歴記録
- 既に CLAUDE.md / memory entry / commit message body / code comment に書かれた rationale
- 完了済 cleanup の経緯
- 受動的 observation (課金 spike 観察待ち等、 次 session で action しない項目)
- 「念のため書いておく」 系の boilerplate

session 終了時に作業が完結し次 session 再開不要なら、 該当 task の handoff section を書かない / 削除する。 todos.md に対応 task block が無いなら handoff section も持たない。

## Process

### 1. Pre-handoff checks

1. **作業途中判定**: 次 session で再開が必要か? 完了済なら handoff section 不要、 todos.md と commit log で充分
2. `git status` で working tree clean か確認、 未 commit は `commit-discipline` skill で処理
3. `todos.md` の Critical / High / Medium に対応 parent task block が登録済か確認 (`writing-todos` skill format: Goal + Exit Criteria + `Work file:`)。 task block が無いまま handoff section だけ書くのは禁止 (lifecycle 紐付けが切れる)
4. 本 session で触れた canonical doc (`.claude/CLAUDE.md` / `~/.claude/CLAUDE.md` / `/etc/claude-code/CLAUDE.md`) に新規 rule が反映済か確認 — rule 追加分は当該 file に書き、 handoff には pointer のみ
5. 該当 task block の `Work file:` フィールドに handoff doc path が記載されているか確認、 無ければ追加

### 2. Project-specific extension (optional)

`ls .claude/skills/handoff-extension/SKILL.md` で存在確認、 あれば Skill tool で invoke、 project-specific pre-check (spec / style guide / chapter index sync) を実行させる。

### 3. Write the document

**書き込み先と方式**:

- 一般的なセッション境界: `last-session-handoff.md` (repo top、 `.gitignore` 対象)
- task-lineage が長期化・分離している作業: `drafts/<task-slug>-handoff.md` (`drafts/` も `.gitignore` 対象、 必要なら作成)
- **section header = todos.md parent task name** (1-to-1 紐付け、 例 `## feature-cache-rename — bg dispatch verify`)
- **update**: 同名 section が既にあれば該当 section を **overwrite** (最新進捗のみ保持、 history は残さない)、 無ければ **file 冒頭に append**
- 既存の異 task section は触らない (並行 task の handoff section を破壊しない安全策)

**section schema (該当無い節は省略)**:

````markdown
## <task-name> (todos.md と一致)

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

- next-me が本 section だけで 5 分以内に再開できるか? Read 順は明確か?
- Status (Stable/Watcher/Unstable) が現状を正しく表現しているか?
- Action に Contingency が網羅されているか (単なる todo list で終わっていないか)?
- **削った情報は本当に作業再開に不要か?** 「念のため」 で膨らませていないか?
- 対応する todos.md task block の `Work file:` が本 doc を指しているか? section header が task name と一致しているか?

### 5. Next-me readback (session 開始時)

next-me は handoff の該当 section を read 後 1 拍 verbalize する: Status / 次の action と why / 読むべき前提 file / 動かせない Caveat。 答えられない項目があれば section 自体に gap があるので、 user に質問する前に handoff を update する。

### 6. Consume cleanup (task 完了時)

`writing-todos` の block-level deletion (commit B、 parent task block 削除) と **同じ commit** で、 handoff の対応 section も削除する。 file が空になれば file ごと削除可。 lifecycle が todos.md task block と handoff section で同期する。

## Rules

- **作業再開に役立たないことは書かない**: git log / 履歴記録 / 完了済 cleanup の経緯 / 受動的 observation / 既に CLAUDE.md・memory・commit body・code comment に書かれた rationale は省く。 詳細は当該 file に書く、 handoff は pointer のみ
- **完結 section は書かない・残さない**: 作業途中じゃない / 次 session 再開不要 = 該当 task が closed なら、 handoff section は持たない。 todos.md block 削除と同期して section も削除
- **1 task = 1 section の 1-to-1 紐付け**: section header は todos.md parent task name と完全一致。 異なる name で複数 section を持たない。 異 task の section は互いに独立 (並行 task の context が混ざらない)
- **既存 section を破壊しない**: 同名 section があれば該当 section だけ overwrite、 異名 section は触らない。 file 全体上書きは禁止 (並行 task の section が消える regression)
- **lifecycle 同期 (todos.md と handoff)**: task block 作成時は `Work file:` に handoff doc を記載。 task block 削除と handoff section 削除を同 commit に揃える
- **同一 task の並行 session は user 運用で回避**: 同じ task を 2 session で同時進行すると section overwrite で進捗ロスト risk あり。 「1 task 1 active session」 ルールで回避 (skill が race 検出する機構は持たない)
- **Memory / rule 更新は当該 file に書き handoff には pointer のみ**: `~/.claude/CLAUDE.md` や memory entry に rule 追加した場合は当該 file 本体に書き、 handoff Caveat には「rule X 追加 (@<file>)」 形式の参照だけ
- **Intent retention は当該 commit / comment / rule file に**: 「なぜそうしたか」 は commit message body / code comment / rule file に残す (Commander's Intent)。 handoff にダブって書かない

## Output

- `last-session-handoff.md` または `drafts/<task-slug>-handoff.md` に新 section を append または既存 section を overwrite (作業途中で再開必要な場合のみ、 そうでなければ skip)
- `todos.md` 対応 parent task block の `Work file:` フィールドに handoff doc path を記載・維持
- session 内の commit 完了 (`commit-discipline`)

## Related

- `writing-todos` — todos.md parent task block format (Goal + Exit Criteria + Work file)、 block-level deletion 規律 (commit A / B 分離)。 handoff section の lifecycle は本 skill の block-level deletion と同期
- `commit-discipline` — pre-handoff の commit 整理、 session-end の uncommitted 残禁止
- `writing-skills` — 本 skill や project-local `handoff-extension` を書く時の format reference
- `verbalize-before-action` — self-audit / next-me readback の verbalize 義務の基盤
