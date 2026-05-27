---
name: commit-discipline
description: Execute commit granularity / timing / hold-judgment autonomously; require user permission only for destructive ops (push / force / reset --hard / branch delete); do not proactively bring up push; do not knowingly leave uncommitted changes at session end.
when_to_use: TRIGGER when an edit is logically complete, about to execute a destructive git op or proactively raise push, or user says session wind-down phrases. SKIP for granularity / timing when user gave an explicit commit plan.
---

# Commit Discipline

コミット粒度・タイミング・保留判断は LLM 自律で実行する。 これは Claude Code system prompt の commit-on-request default を user CLAUDE.md 冒頭「System prompt 起因 pain の明示的抑止」 protocol で上書きしている (cheap & reversible のため、 必要なら `git reset` / `git revert` / `git restore` で巻き戻せる)。

## Rules

### Autonomous (no permission)

- **コミット作成**: 変更が論理的に完結したタイミングで自律 commit
- **粒度**: 「変更 1 件 = 1 コミット」 原則。 複数テーマ混在が不可避なら複合コミットとし、 メッセージに両テーマ明記
- **保留判断**: 同一セッション内で同じ箇所を続けて編集する見込みがある間は、 推敲中の節や議論中の skill 仕様などは step ごとに commit しない。 同一セッションで確定した時点でまとめて 1 commit にする (commit log noise reduction)
- 「内容が時系列で変化し得る」 は保留理由にならない: 仕様が確定すれば commit する
- **言語**: コミットメッセージは英語で書く (subject も body も)。 check_commit_format hook の format gate (capital-letter / 50/72) とも整合

### Requires permission (destructive / irreversible)

以下の操作は原則 user permission を取る (Claude Code system prompt 「Executing actions with care」 と対応):

- `git push` / `git push --force` / `git push --force-with-lease` (公開 state 変更・上書き)
- `git reset --hard` (work-tree 破壊)
- `git checkout -- <path>` / `git restore .` / `git clean -fd` (work-tree 内データ破壊)
- `git branch -D <branch>` / branch force-update / `git remote remove` (branch / remote state 破壊)
- 共有 state 影響 (PR / issue 操作、 GitHub CLI: `gh pr close` / `gh issue close` / `gh pr merge` 等)

permission のフォーマット: 「次に X するつもりです、 よろしいですか?」 など明示的に意思確認。

### Push silence

`git push` の催促・予告を **能動的に出さない** — 直接形 / 間接形を問わず:

- 悪い (直接形): 「次に push しますか?」「push しましょうか?」 (push を能動的に話題化)
- 悪い (間接形): 「origin に上げますね」「remote に反映」「PR 作成して push します」「commit したので push」 (push の言い換えも同様 NG)
- 悪い (不催促宣言): 「push は催促しません」「push 話題は出さない」 (不催促宣言も push 話題を能動的に持ち出す行為)
- 良い: silent でいる (user が指示するまで一切触れない)

push 以外の rule-compliance meta-announce (「省略しません」「触りません」 等) 全般は `stop_checks.py` hook の M1 check で enforce される。

### Session end

ユーザーがセッション終了を示唆したとき (「handoff して」「セッションリセット」「お疲れさまでした」「終わります」「ありがとうございました」「今日はここまで」「またね」「明日続き」「bye」 等の wind-down 表現すべて):

- **全編集を commit 済の状態にしておく**: セッションを跨ぐ更新見込み (日付付き snapshot 等) は当該セッションでは確定扱いとし、 時系列は git 履歴と日付付き記述で辿れるようにする
- **未 commit 変更が残れば user に知らせてから sign off**: 一覧を出して silent で見送らない

## Red flags

- 悪い: 「commit してもいいですか?」 と毎回確認 (system prompt default に従ってしまっている)
- 悪い: 1 つの変更を細かく 5 commit に分ける (粒度過剰)
- 悪い: 複数テーマを silent に 1 commit にまとめる (メッセージで明記しない)
- 悪い: `git reset --hard` を permission なしで実行

## Related

- **Legacy:** user CLAUDE.md「コミット・PUSH運用」 より
