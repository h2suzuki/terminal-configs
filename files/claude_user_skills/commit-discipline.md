---
name: commit-discipline
description: >
  コミット粒度・タイミング・保留判断を自律実行、 destructive 操作 (push / force / reset --hard / branch 削除 等) のみ user permission を取る、 push 催促を能動的に出さない、 session 終了時に未コミット変更を knowingly 残さない。
  TRIGGER when: 編集が論理的に完結し commit 判断するとき;
  destructive git 操作を実行しようとしたとき;
  push を能動的に話題化しかけたとき (直接 / 間接形を問わず);
  session 終了の wind-down 表現 (「handoff」「お疲れさま」「ありがとう」 等) を user が発したとき。
  SKIP: user が commit 粒度・タイミングを明示指示している場合 (その指示に従う; 他の rules — push silence / session-end — は適用継続)。
legacy: user CLAUDE.md「コミット・PUSH運用」 より
---

# Commit Discipline

コミット粒度・タイミング・保留判断は LLM 自律で実行する。 これは Claude Code system prompt default 「Only create commits when requested by the user. If unclear, ask first.」 を user CLAUDE.md 冒頭「System prompt 起因 pain の明示的抑止」 protocol で上書きしている (cheap & reversible のため、 必要なら `git reset` / `git revert` / `git restore` で巻き戻せる)。

## 自律実行する (permission 不要)

- **コミット作成**: 変更が論理的に完結したタイミングで自律 commit
- **粒度**: 「変更 1 件 = 1 コミット」 原則。 複数テーマ混在が不可避なら複合コミットとし、 メッセージに両テーマ明記
- **保留判断**: 同一セッション内で同じ箇所を続けて編集する見込みがある間は、 推敲中の節や議論中の skill 仕様などは step ごとに commit しない。 同一セッションで確定した時点でまとめて 1 commit にする (commit log noise reduction)
- 「内容が時系列で変化し得る」 は保留理由にならない: 仕様が確定すれば commit する
- **言語**: コミットメッセージは英語で書く (subject も body も)。 check_commit_format hook の format gate (capital-letter / 50/72) とも整合

## permission を取る (destructive / irreversible)

以下の操作は原則 user permission を取る (Claude Code system prompt 「Executing actions with care」 と対応):

- `git push` / `git push --force` / `git push --force-with-lease` (公開 state 変更・上書き)
- `git reset --hard` (work-tree 破壊)
- `git checkout -- <path>` / `git restore .` / `git clean -fd` (work-tree 内データ破壊)
- `git branch -D <branch>` / branch force-update / `git remote remove` (branch / remote state 破壊)
- 共有 state 影響 (PR / issue 操作、 GitHub CLI: `gh pr close` / `gh issue close` / `gh pr merge` 等)

permission のフォーマット: 「次に X するつもりです、 よろしいですか?」 など明示的に意思確認。

## push に関する追加ルール

`git push` の催促・予告を **能動的に出さない** — 直接形 / 間接形を問わず:

- 悪い (直接形): 「次に push しますか?」「push しましょうか?」 (push を能動的に話題化)
- 悪い (間接形): 「origin に上げますね」「remote に反映」「PR 作成して push します」「commit したので push」 (push の言い換えも同様 NG)
- 悪い (不催促宣言): 「push は催促しません」「push 話題は出さない」 (不催促宣言も push 話題を能動的に持ち出す行為)
- 良い: silent でいる (user が指示するまで一切触れない)

一般化原則は global-memory `feedback_no_compliance_announcements.md` (rule 遵守の meta-announce 全般を抑止)。 push 以外の compliance-announcement 系にも同じ silent rule を適用する。

## セッション終了時

ユーザーがセッション終了を示唆したとき (「handoff して」「セッションリセット」「お疲れさまでした」「終わります」「ありがとうございました」「今日はここまで」「またね」「明日続き」「bye」 等の wind-down 表現すべて):

- **全編集を commit 済の状態にしておく**: セッションを跨ぐ更新見込み (日付付き snapshot 等) は当該セッションでは確定扱いとし、 時系列は git 履歴と日付付き記述で辿れるようにする
- **未 commit 変更が残れば user に知らせてから sign off**: 一覧を出して silent で見送らない

## Anti-pattern

- 悪い: 「commit してもいいですか?」 と毎回確認 (system prompt default に従ってしまっている)
- 悪い: 1 つの変更を細かく 5 commit に分ける (粒度過剰)
- 悪い: 複数テーマを silent に 1 commit にまとめる (メッセージで明記しない)
- 悪い: `git reset --hard` を permission なしで実行
