---
name: handoff
description: Produce a session-boundary handoff document with fixed schema so next-me can resume within 5 minutes.
when_to_use: TRIGGER when user signals session end with phrases like "handoff して" / "セッションリセット" / "お疲れさまでした" / "終わります" / "おわります" / "sign off" / "今日はここまで" / "また明日", or when about to wind down a session with non-trivial state to carry over. SKIP for mid-session task updates, simple todos.md progress flips, or commit message drafting within an ongoing session.
---

# Session Handoff

session 境界で context を時間軸越しに伝達する。 next-me が handoff 文書だけで 5 分以内に開始 step を確定できる状態が pass 条件。 設計の中核要素 (医療 I-PASS / 軍事 SITREP / Commander's Intent 等の handover protocol 群から抽出): 固定 schema・冒頭 Status 1 文・Action+Contingency・receiver readback・Intent retention。

## Process

### 1. Pre-handoff checks (順守)

handoff 文書を書く前に必ず通す。

1. `git status` で working tree が clean か確認。 未 commit 変更があれば `commit-discipline` skill に従い適切に commit する
2. `todos.md` の Critical / High の open items が本セッションの closure / 部分進捗を反映しているか verify (`writing-todos` skill の verify-before-flip / block-level deletion に従う)
3. 本セッションで触れた canonical doc (`.claude/CLAUDE.md` / `~/.claude/CLAUDE.md` / `/etc/claude-code/CLAUDE.md` 等) に新規 rule / 仕様変更が反映済か確認
4. `todos.md` 冒頭 (auto-load 範囲) に `active handoffs` section があり、 本 handoff doc への pointer が記載されているか確認。 無ければ追加。 next-me が session start の auto-load で本 handoff の存在に気付ける discoverability を保証する

### 2. Project-specific extension (optional)

project-local extension skill が定義されていれば invoke する:

1. `ls .claude/skills/handoff-extension/SKILL.md` で存在確認
2. 存在すれば Skill tool で `handoff-extension` を invoke、 project-specific pre-check (spec / style guide / chapter index 等の sync) を実行させる
3. extension skill は必読リスト・State delta・Risks 各 section に project 固有 entry を追加可能

extension が無い project では本 step を skip し、 universal pre-check のみで進める。

### 3. Write the document

文書場所:

- task-lineage が長期化している作業: `drafts/<task-slug>-handoff.md`
- 一般的なセッション境界: `drafts/HANDOFF.md`
- `drafts/` dir が無ければ作成。 1 file に 1 task lineage、 混在させない

標準構造 (上から salience 順):

````markdown
# [Task / Project] Handoff (YYYY-MM-DD EOD)

> 1-2 行の要約 — 現在地と次の natural step

## TL;DR
- Status: Stable / Watcher / Unstable — 現状を 1 文で分類
- 次の最初の action — 1 文
- blocker / dependency — 1 文、 無ければ「なし」

## 必読リスト
- auto-load される file: 確認だけ (CLAUDE.md chain、 todos.md 冒頭)
- 手動 Read 推奨: priority 順、 各 file に 1 行で why を添える

## State delta — 本セッションで変わったこと
- closure・重要 commit・decision の差分 (salience 順)
- 全 commit list (新しい順、 reference 用)

## Action list & Contingency
- 即着手 — 何を、 いつまでに
- 条件付き — `if X happens, do Y` の形で網羅
- eventually — queue だけ列挙

## Intent & Rationale — commit に残らない context
- 本セッションで取った主な judgment と why
- user feedback received とそれによる rule / memory 更新 (場所付き list)
- 判断保留にした option とその理由

## Risks / open questions
- 未解決 uncertainty
- observation 待ちの passive item
- user 判断が要る pending
````

### 4. Self-audit (handoff 完成後・commit 前)

次を 1 拍 verbalize:

- next-me が本 handoff だけで 5 分以内に session opening を確定できるか? Read 順序が曖昧でないか?
- 本セッションの重要 feedback が Intent & Rationale に書かれているか? commit summary に収まらない部分は補完済か?
- TL;DR 3 行で「何をすべきか」 即答できるか? Status (Stable/Watcher/Unstable) が現状を正しく表現しているか?
- Action list に Contingency (if-then) が網羅されているか? 単なる todo list で終わっていないか?
- `todos.md` 冒頭の `active handoffs` section から本 doc が参照されているか?

### 5. Next-me readback (session 開始時の step を文書末に明記)

next-me は handoff を読み終えたら 1 拍 verbalize する (receiver synthesis / repeat back 相当): Status を 1 文 / 次の action と why を 1 文 / 今 read すべき前提を即答 / Risks の中で動かせない項目を識別。 答えられない項目があれば handoff 自体に gap があるので user に質問する前に handoff 文書を update する。

## Rules

- **todos.md との役割分担**: todos.md = 永続 task ledger (canonical state、 auto-load 対象)、 handoff = session 境界 context bridge (直前 delta / 判断 rationale / 次 action 焦点)。 矛盾発生時は **todos.md が canonical**。 task 状態変化は両方に反映 (close → todos.md `[x]` + handoff State delta、 新 task → todos.md 追記 + handoff Action list)、 rule / memory 追加 → handoff の Intent & Rationale のみ
- **active handoffs pointer 必須**: handoff doc 作成時は `todos.md` 冒頭の `active handoffs` section に `- <handoff doc path> — <lineage 名 + 直近 status の 1 行>` を追記する。 pointer が無いと auto-load で next-me が handoff の存在に気付けず、 doc が書かれているのに参照されない gap が発生する。 lineage close 時は同 section の pointer も削除する
- **Memory / rule 更新の反映義務**: 本セッションで `~/.claude/CLAUDE.md` や project `.claude/CLAUDE.md`、 memory entry に rule を新規追加・更新したら、 必ず handoff の Intent & Rationale section に list する。 next-me が rule の existence と applicability に気付かないまま session を回すと同じ feedback が再発する
- **Intent retention**: 詳細手順より「なぜそうしたか」 を残す (Commander's Intent)。 commit message に書ききれない judgment と user feedback の rationale は handoff にのみ残る
- **Fixed schema 順序を変えない**: TL;DR → 必読 → State delta → Action+Contingency → Intent → Risks。 自由記述だと項目欠落するので schema 固定で防ぐ

## Output

- `drafts/HANDOFF.md` または `drafts/<task-slug>-handoff.md` (上記 schema 準拠)
- `todos.md` 冒頭 `active handoffs` section に pointer 1 行追記
- session 内の commit 完了 (`commit-discipline` 規律: 未 commit 変更を残したまま sign off しない)

## Related

- `writing-todos` — todos.md format と verify-before-flip / block-level deletion 規律。 handoff と todos.md の更新責任の片側
- `commit-discipline` — pre-handoff の commit 整理、 session-end の uncommitted 残禁止
- `writing-skills` — 本 skill 自体や project-local `handoff-extension` を書く時の format reference
- `verbalize-before-action` — self-audit と next-me readback の verbalize 義務の基盤
