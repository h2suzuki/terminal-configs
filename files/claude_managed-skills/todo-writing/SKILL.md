---
name: todo-writing
description: Format and operate todos.md (priority-bucketed task ledger at the repo root) — Goal + Exit Criteria per parent task, block-level deletion on completion, verify-before-flip, three-question gate before any scope reduction.
when_to_use: TRIGGER when about to Read / Edit / Write todos.md, when about to append a new task or flip a checkbox to "[x]", when about to delete or shrink a parent task block, when about to utter scope-reduction phrases like "終わり" / "素材化済" / "scope 外" / "役割終了" against a todos.md entry or its work files, or when noticing leftover legacy sections (e.g. "修正済" / "Done") in todos.md. SKIP for projects without a todos.md ledger, for TODO comments inside source code, or for one-off ad-hoc task lists that are not committed to the repo.
---

# Todo Writing

repo top の `todos.md` を Critical・High・Medium 優先度別の task ledger として運用するための format と進捗管理 rule。 親タスクは Goal + Exit Criteria で objective 化し、 完了は block 単位削除で git 履歴に残す。

## Structure

### Priority buckets

todos.md は **Critical**, **High**, **Medium** の 3 つの優先度 section で構成する。 他の section (旧 「修正済」「Done」 等) は作らない。 完了タスクは中間 section に残さず削除する (詳細は Process)。

### Parent task: Goal + Exit Criteria

各親タスクは見出し直後に以下を置く:

- **Goal**: 達成する outcome を 1 文で
- **Exit Criteria**: Goal の各句を客観的・観測可能な acceptance 条件へ分解した checkbox 群

Exit Criteria は Goal の主張と **1:1 で連動** させる:

- Goal が「機構を組込む」 なら Exit Criteria は「組込まれ起動することの確認」
- Goal が「観測を経て判断」 なら Exit Criteria は「観測データ収集」 と 「結論記録」 の確認

Exit Criteria に「全子項目完了」 を completeness 補助として 1 行まで書くことはできるが、 本筋の Exit 条件にしない。 個々の sub-task ID も列挙しない。

### Progress checkbox vs Exit Criteria

Goal に紐づく関連作業の進捗は Exit Criteria と別の checkbox として記載できる。 ただし親タスクの削除判断 (後述 Three-question gate の Q1) は Exit Criteria の客観評価で行い、 進捗 checkbox の主観評価で代えない。

### Work file reference

タスクに関連する work file (progress base file・framework table・途中成果物 等) がある場合、 必ず todos.md から言及する。 さもないと、 次のセッションで work file が lost する。

## Process

### Adding tasks

1. 追記前に Critical・High・Medium 以外の section (旧 「修正済」 等) の残存を確認。 あれば先に掃除 commit を入れる
2. 新しい残課題は適切な優先度 section に追記する
3. 関連 work file があれば task entry 内で path を言及する

誤記・記載不足・参照誤りなど判断容易なものは直接修正して commit。 判断要素が残るものは `(要相談)` 付きで積み、 議論を経て反映する。

### Verifying before `[x]` flip

`[x]` でマークする前に、 その Exit Criterion / sub-task の達成根拠を **実機で確認する**。 todos.md の隣接記述や記憶だけで盲目的に flip しない。 盲目的 `[x]` 化は虚偽 closure の温床。

確認手順の例:

- 根拠 file が実在するか — `ls path/to/spec` で存在確認
- 根拠 file の内容が Exit Criterion を満たしているか — 該当節を `grep` または Read で確認
- 完了 commit が referenced されているなら、 その commit が実際にその変更を含むか — `git show <hash> --stat`

verify を経た上で `[x]` flip を含む commit A を land する。

### Defining task completion

タスクの完了とは、 Exit Criteria も含めた **全 checkbox がチェックされ、 かつ、 その状態で commit までされた** ことをいう。

### Block-level deletion

完了タスクは block 単位で削除する。 commit により全 checkbox のチェックが記録されているので、 履歴は git log で辿れて safe — 削除して良い。 「修正済」「Done」 等の中間 section に完了記録を残すスタイルは禁止。 削除のみ。

削除タイミングは完了 commit の **直後の commit** で行う。 次セッションへ持ち越すと「意図的に残した記録」 に見えて削除されない。

親タスク block の削除判断は、 後述 Three-question gate の 3 質問を verbalize してから行う。

### Separating `[x]` flip and block deletion commits

`[x]` flip と block 削除は別 commit に分ける。 `[ ]` のまま block を削除すると、 git log の diff には「`[ ]` の行が消えた」 とだけ記録され、 closure transition の granular 履歴が残らない。

必ず次の順で land する:

1. **commit A — state record**: 対象の sub-task / Exit Criterion の `[x]` flip と、 完了根拠の 1-2 行追記
2. **commit B — closure**: block 全体の削除 (parent task closure 時のみ。 sub-task close 単独なら commit A だけで終わる)

ショートカットして 1 commit に纏めると、 後で「いつ何が closed したか」 を git log で追えなくなる。 block 削除は state record の上に立てる二段建てが原則。

## Rules

### Three-question gate before scope reduction

todos.md 親タスク entry、 work file (progress base file・framework table)、 handoff 引き継ぎ情報 を「終わり」「素材化済」「scope 外」「役割終了」 と判断する前に、 次の 3 点を text 本文に verbalize する。 内部 thinking で済まさない。

1. **親タスクの定義済みゴールが達成されたか** — todos.md の Goal 文を引用し、 達成を示す客観的根拠 (成果物・テスト結果・確認ログ) を挙げる。 「完了したと思う」 等の主観表明は不可
2. **保持して追従更新する case が本当に無いか** — 反例を 1 つ挙げるよう試みる
3. **自分の「労力削減」 衝動が混じっていないか** — 「捨てると作業が減る」 誘惑があれば認める

3 つすべて clear (1 が Yes 確定、 2 が反例無し、 3 が衝動無し) でない限り、 削除・静的化・scope 縮小を選択肢に入れず、 **保持 + catch-up 更新を default** として提案する。

## Related

- `commit-discipline` — commit A / B 分離など本 skill の commit 粒度規律の基盤
- `verbalize-before-action` — Three-question gate の verbalize 義務の基盤
- `verify-before-asserting` — `[x]` flip 前の verify 義務の基盤
- `code-writing` — work file 参照を扱う際の「No dangling-prone references in persistent files」 が依拠
