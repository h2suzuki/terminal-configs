---
name: mytask
description: Record user requests, break large work into concrete steps, and review your own plan against the request as work evolves. Use when starting or resuming work, receiving additions or corrections, or deciding what remains. Use the mytask MCP in both Claude Code and Codex, not Claude native Task tools.
when_to_use: TRIGGER when starting or resuming work, when the user adds, corrects, or reprioritizes a request ("追加" / "訂正" / "やっぱり"), when splitting large work into steps, or before reporting completion or remaining work. SKIP for a one-shot answer that needs no tools.
---

<!-- skill-lint: allow — Codex と共有する Skill のため、Claude Code 用 Skill の節構成に揃えない -->

# Mytask

## 目的

依頼を忘れないこと、大きな作業を分解すること、自分で立てた計画を見直せることが目的。状態を更新するだけで運用を済ませない。ユーザーの依頼を基準に計画を修正し、計画に合わせて依頼を狭めたり広げたりしない。

## 依頼を記録する

- 開始・再開時に既存の項目を確認し、依頼の目的、求められた成果物、制約、完了条件を残す。既存項目があれば重複登録しない。
- 途中の追加・訂正・優先順位の変更も記録する。最新の発言だけで当初の依頼を置き換えず、取り消された部分と継続する部分を区別する。
- 単純な依頼は一項目でよい。作業を増やすための細分化や、コマンド一つごとの項目化は不要。
- 「後で対応」「別作業にする」と判断した項目も、理由と再開条件を記録する。記録したことを実施済みと扱わない。

## 分解して、自分で計画を見直す

大きな依頼は、親項目に依頼と完了条件を残し、実行・検証できる単位の子項目に分解する。必要な調査、変更、検証、引き渡しを含め、依存関係と実行順序を明らかにする。

作業着手前、調査で前提が変わったとき、ユーザーから訂正されたとき、再開時、完了を報告する前に、依頼と計画を照合する。

- 各要求に、それを満たす手順と確認方法があるか。
- 不要な作業、抜け、重複、依存関係の逆転がないか。
- 想定が外れた手順を惰性で続けていないか。
- 完了条件に達しているか。残った作業を報告から落としていないか。

見直した結果を項目に反映してから次の作業へ進む。ここでのレビューはまず自分で行う。毎回ユーザーに計画の承認を求める手順にはしない。既存の合意は引き継ぎ、依頼範囲の変更やユーザーにしか決められない判断が必要な場合に確認する。

## 遂行と共有

- 着手する項目を `in_progress`、サブエージェントや別セッションに任せて動いている項目を `delegated`、外部依存で進められない項目を `blocked`、未着手を `pending` にする。成果物と完了条件を検証してから `completed` にする。取り消しや計画変更で不要になった項目は `cancelled`、理由があって今回は実施せず再開もしない項目は `skipped` で閉じ、どちらも実施済みとして報告しない。`skipped` は報告で未実施と理由を明示し、後で対応する項目には使わない。
- 任せた結果を受け取ったら `delegated` のまま放置せず、検証して `completed` にするか、自分で引き取って `in_progress` に戻す。
- 大きな区切りや計画変更時には、依頼、現在の到達点、次の作業を短く照合する。説明できなければ元の依頼と項目を読み直す。
- 初回の計画と重要な変更、完了・保留・残作業を、項目番号を添えてユーザーに分かる言葉で示す。MCP の応答には ID が含まれるが、一覧が画面に自動表示されるとは限らないので、本文にも番号付きで要約する。機械的に全項目を毎回転記しない。
- セッションを跨ぐ作業は、リポジトリの既存運用に従って `todos.md` や引き継ぎ資料にも残す。隣のセッションから担当プロジェクトへ来た依頼も記録し、着手時期をユーザーと調整する。完了後は関連資料も更新する。

## クライアントと操作

### 項目番号

- 親は `4`、子は `4-1`、孫は `4-1-2` のように、直属の親の番号へ `-連番` を追加する。兄弟ごとに 1 から採番し、完了・非表示になった番号も再利用せず、既存番号を振り直さない。
- mytask MCP では返された自動採番 ID をそのまま項目番号として使う。子・孫は直属の親の ID を `parent` に指定し、本文の `#4` だけで親子関係を代用しない。訂正・計画変更を別項目に残す場合も、対象項目の子として登録する。

### Claude Code

mytask MCP を使う。Claude 標準の Task ツール (`TaskCreate`・`TodoWrite` など) は使わない。必要なら ToolSearch でツールを取得する。Skill の読み込みとツールの取得を済ませ、実作業のツールを呼ぶ前に依頼を登録・更新する。

### Codex

mytask MCP の `TaskList`、`TaskCreate`、`TaskUpdate` を使う。Claude Code 固有の ToolSearch は前提にしない。

### mytask MCP

- `TaskList()`：未完了の項目を読む。`completed`・`cancelled`・`skipped` の閉じた履歴が必要なら `TaskList(completed_limit=5)` のように件数を指定する（最大100件）。未完了項目は省略されない。
- `TaskCreate(content, parent?, activeForm?)`：依頼や手順を登録する。子・孫など任意の深さで、直属の親の id を `parent` に渡す。応答は作成した項目だけ。
- `TaskUpdate(id, status, owner?)`：状態を更新する。`in_progress` は一件で、新しく着手すると前の項目は `pending` に戻る。`delegated` は何件でもよく、自動で戻らない。`owner` には任せた相手 (サブエージェント名など) を書き、`delegated` の間だけ一覧に表示される。`cancelled` と `skipped` は `completed` と同じく既定の一覧から隠れる。応答は更新した項目と自動変更された ID だけ。
- 現在の MCP は本文の編集・削除を提供しない。訂正や計画変更は元の id を参照する新しい項目に明記する。取り消した作業を実施済みとして報告しない。
- 保存先はセッション／スレッドごとのローカル領域で、コミットしない。完了項目は保存したまま既定の一覧から隠す。

ツールを利用できない場合は、依頼と計画を本文または既存の作業メモで保持して作業を続ける。MCP に保存したとは主張しない。Claude 側で court 汚染の警告が出た場合は、警告を伝えてセッションのリセットを案内する。
