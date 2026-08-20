# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)


## Critical

## High

### codex_task_sentinel: 敵対レビューの収束と上流依存 1 件

Goal: 監視判定が plugin の実挙動と skill の 4 分岐に一致する状態にする。

Exit Criteria:

- [ ] レビューの新規 material 指摘がゼロで安定する — **53 巡完走、未達**。17〜53 巡で 179 件。
  巡ごとの件数・処理ブロック・原因タイプ・由来・修正の効果は `docs/sentinel-review-analysis.md`
  (毎巡ここへ追記する)。要点は 3 つ: self 率が 46〜53 巡で **88%**、修正が次巡に生んだ指摘が
  **93 件 (52%)**、効果判定が **worsened 34 巡 / improved 0 巡**。件数自体は 12 (r19) → 2〜6 に
  収束したが、中身が preexisting から自作欠陥に置き換わっただけである。
  なお 53 巡で分かったが、**自作欠陥は直前の巡のものとは限らない** — 5 件の出所は r52 が 3 件、
  r34 が 1 件、r19 が 1 件で、34 巡ぶん残っていたものがある
- [ ] **指摘を生成側の癖として潰す** — 5 つの形 (配り漏れ / comment が code を追い越す /
  虚偽の完了報告 / 再検査の半径不足 / 同一 commit 内の同型再発) を user memory の
  `feedback_reading_the_outside_world.md` に記録済み。それでも 52 巡目の指摘 1 は 48 巡目と
  同じ「期限 gate 外の early return」で、4 巡後の再演だった。**記録しただけでは止まっていない**
- [x] **test で守れていない修正をゼロにする** — 51・52 巡と 2 巡続けて「差の出る fixture を作れない」として
  test 無しで閉じていた 2 件 (`pin_hold` の持ち越しと `resolved_unknown` の非クリア) に、53 巡で test が付いた。
  53 巡の発注書でその判断自体を開示して裁定を求めたところ、両方とも観測可能と返り、`complete=False` で
  周を跨がせる 3 周 fixture の作り方まで示された。**作れないと思ったものが、開示したら作れた**
- [ ] **収束対策 4 本柱の採否をユーザーが判断し、決定した柱を実行する** — 2026-08-12 に立案済
  (詳細は `last-session-handoff.md` 同 section)。柱: (1) 構造 refactor = watch() の return 22 箇所を
  単一 finish() funnel に集約 + 4 読取経路の Observation 層統一 (裁定 21 は「1 点に集約」と言うが実体は
  `deadline_reached()` 手書き 12 箇所と実測)、(2) 47 裁定の機械化 = AST/grep の決定的 meta-test 化 +
  裁定本文の docs/ 移管、(3) TOCTOU enumerator harness、(4) 体制 = codex 実装 / opus 5 xhigh 巡内レビュー /
  収束認定は codex sol xhigh 2 巡連続ゼロ。根拠: 179 件の 73% (forgot 85 + contradictory 34 +
  unfinished 12) が per-site 手配り型で、閉じたクラスは全て機構化 or 全数突合によるもの。
  **ユーザー判断待ち 2 点**: 柱 1 の refactor まで踏み込むか / refactor 実装を sol medium から xhigh に上げるか
- [x] **deploy の 23 巡分の遅れを解消する** — 2026-08-13 00:05 にユーザーが
  `sudo install` を実行。`diff -q /usr/local/bin/codex_task_sentinel files/codex_task_sentinel`
  IDENTICAL (meta-test 込みの `55c618e` 相当)・mode 0755 を確認済み
- [x] log 由来の曖昧さが正常 job の cancel を招かない — 既定で cancel 導線 (exit 4/3) を出さず、
  exit 14 で evidence を示して判断を呼び手に渡す (206ce7a)。断定したい呼び手は `--trust-log`。
  12 巡目が 504 case の直積で「既定の exit 3/4 は 0 件」「`--trust-log` は旧判定と mismatch 0」を実測
- [x] **worktree を作り直したときの plugin state dir 掃除を機構化する**: 同じ path で
  `git worktree add` し直すと `plugin data/state/<worktree>-<hash>/` が再利用され、job が
  `failed to load configuration: No such file or directory` で即死する (2026-08-09 に実際に踏んだ)。
  `files/claude_managed-hooks/codex_worktree_gate.py` が plugin と同じ規則で state dir を導き
  (`_state_dirs` / `_oldest_record`)、worktree より古い state dir が残っていれば deny して
  `rm -rf` を指示する

Work file: `last-session-handoff.md` の同名 section (再開手順)、
`docs/sentinel-review-analysis.md` (17 巡以降の全指摘の集計)、
`drafts/sentinel-review-r{17..53}.md` (発注書)、`drafts/sentinel-review-r{17..30,52,53}-report.md` (報告書)

## Medium

### 方法論の実証: 小規模ツール新規作成で敵対レビューの収束を実測する

Goal: sentinel 級に小さな要件 (またはそこまでブレイクダウンした要件) の新規ツール作成を
数ケース、方法論 (docs/adversarial-review-methodology.md の G/L/R) を適用して実施し、
収束の成否・round 数・token を台帳で実測して最終成果を測る (2026-08-13 ユーザー指示)。

Exit Criteria:

- [ ] 前提: sentinel の収束対策 (柱 1〜3 + 収束認定) が完了している
- [ ] ケース選定と成功基準 (収束 round 数の上限・material 残ゼロ・token 量) をユーザーと合意する
- [ ] 各ケースの台帳 (由来列つき) を docs/ に記録し、結果を方法論 doc へ反映する

Work file: `docs/adversarial-review-methodology.md` (§6 チェックリストを各ケースの入場 gate に使う)
