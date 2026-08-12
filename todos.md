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

### Handoff 強化 + 言語 lint 機構の deploy と実運用確認

Goal: wind-down open-task 機構 (inject + block)・handoff cross-check step・session_resume_context pointer 化・claude_lang_lint を deploy し、実運用での駆動を確認する。

Exit Criteria:
- [x] 追補 deploy (hooks 3 本 0755 / handoff・codex-delegation skill / crosscheck-prompt.md / /usr/local/bin/claude_lang_lint) を canonical と `diff -q` 一致で検証 — 2026-08-06 ユーザー実行、7/7 identical・exec bit 確認・deployed claude_lang_lint --selftest OK (PATH 解決込み)
- [x] 実 session で open Task を残した wind-down に inject + block が発火し、todos.md 転記 + close で通過することを確認 — **2026-08-08 04:26 に full loop を live 観測**: ユーザー発言「セッションを閉じます」に対し UserPromptSubmit で inject (open Task #7 を列挙) → ターン終了時に stop_checks が exit 2 で block (#7 を名指し) → todos.md へ転記済みのうえ Task を close して通過。以下は経緯: 2026-08-07 **inject は実 session で live 発火を観測** (ユーザーの「セッションは終わります」prompt に対し UserPromptSubmit で open Task 1 件を列挙、clean tree ゆえ未コミット節は出ず = 偽陽性修正も live 確認)。block 側は下記 shadow 欠陥を修正済 (40f89e8)。deploy 完了・canonical と diff 一致を確認済 (2026-08-07 ユーザー実行) で、deployed 版が実 transcript から人間 prompt を復元し harness entry 14 件を skip することも確認。残るは **live block の観測のみ** (実装は 3a6a2c5 で完了・deploy 済)。ユーザー指摘により設計から作り直した: Stop payload には prompt が無いため transcript を遡っていたが、これをやめ **prompt を受け取る UserPromptSubmit hook 側で判定し session 単位の控えに記録**、Stop 側はそれを読むだけにした。未処理項目は従来どおり Task store + mytask の両対応。transcript を読まなくなったので下記 2 段の不発原因は原因ごと消滅し、widen-once (75de34b) も削除。通し試験で「合図なし→素通り / 合図あり→block / 通常発言で上書き→素通り」を確認、deploy 後は本番 hook が実際に控えを書くことも確認済 (04:11)。
  - 旧原因の記録 (再発時の手がかり): (1) harness 生成 entry が人間 prompt を shadow、(2) `_load_tail` が末尾 128KB しか読まず長 session で人間 prompt に届かない、(3) `<system-reminder>` も harness 生成だが roster 未収載だった

- [x] **発注書の規約適合を発注スクリプト内で deterministic に検査する** — `files/codex_order_lint` (17 tests・9 変異すべて catch・`47cbd29`) が節の有無・報告書 path の綴り・終端 token・調査しきい値の倍率・裁定の採番・kill-by-port 禁止を検査する。実在の発注書 36 本に当てると 48〜52 巡の 5 本が同じ採番ずれを 5 巡持ち越していた。方針確定 (2026-08-12・ユーザー判断)。発注は結局スクリプト実行になるので、LLM の敵対レビューに頼らず**スクリプト側で決定的に検査して、規約違反なら発注を拒否する**
  - 却下した案 2 つ: (a) 「codex-delegation skill が active でない限り codex-companion の Bash を止める」hook — gate の state が agent 単位で subagent から見えず詰んでいた。(b) 発注書を codex に敵対レビューさせる — LLM 判定は確率的で、決定的にできるものを LLM に投げるのは `writing-code` の「deterministic transform を LLM に投げるな」に反する
  - 検査すべき規約は codex-delegation skill に既にある (worktree 隔離 / `--write` の扱い / running[]-empty monitor 禁止 等)。これらを発注スクリプトの引数・発注文から機械的に判定する
  - **起動そのものもスクリプトが担う**: 2026-08-12 の 2 回の発注で、起動側の失敗が 3 件出た。
    (a) 同じ発注が 2 job 走り、報告書 path が衝突しかけた (先発は default model、後発が指定どおり)。
    (b) `task --help` が flag と解されず task 本文として起動され、本線 checkout に無関係な job が
    走った (read-only だったため実害なし)。(c) `--model` / `--effort` が job record に届かず、
    default model で敵対レビューが走りかけた — 弱いレビューの「指摘ゼロ」は空の合格になる。
    いずれも「発注書の内容」ではなく「起動の手つき」の失敗で、スクリプトが flag を固定し
    起動の重複を弾けば決定的に消える。job record の `request.model` / `request.effort` が
    指定と一致することを起動直後に検証するところまでを含める
  - 経緯: 2026-08-08 に発注〜監視ターンで codex-delegation skill を invoke せず、既存規約を再違反した
- [x] 環境依存で緑になる test 2 件を、環境に依らず正しい結果を出すようにする — 2026-08-11 に両方修正
  - `test_non_repo_fails_open_with_diagnostic`: stderr の行数を数える assert をやめ、診断の件数を数えるようにした (本来の主張)。git stderr を 2 行に強制する test を追加して、件数が行数に追従しないことを pin
  - `test_corpus_against_current_adapter`: corpus は実 session 履歴から採取するもので repo に入れるべきでないと判断し、tracked 化ではなく不在時 `skipTest` を選択。dir を退避して skip、戻して pass を実測
- [x] index sync の失敗が不可視な設計を塞ぐ — `_main_rebuild()` が「disk にあるがどちらの名簿にも無い entry」を drop 時に full path で名指しする (`_unlisted_entries()`、test 4 件)。retired は報告しないので実 memory dir では 1 件だけ出る。当初の `memory_routing_gate.py` の DEVNULL + `check=False` は、upsert 経路が健全と判明したため原因ではなかった
  - **私が一度「corpus の 46% が index から欠落」と書いたのは誤り。撤回する**。disk 125 件に対し `entries_fts` 67 件なのは事実だが、名簿と突き合わせると欠落 58 件の内訳は roster file 自体が 7 件 (MEMORY.md ×5 / OLD-MEMORY.md ×2)、**OLD-MEMORY.md 収載 = retired が 42 件** (載らないのが正しい)、どちらの名簿にも無い orphan が 8 件。「欠損」と呼べるのは最後の 8 件だけ
  - **orphan は 8 件ではなく 1 件。これも私の誤りで訂正する**: 8 件と数えたとき、project scope の file を user scope の MEMORY.md / OLD-MEMORY.md と突き合わせていた。scope ごとに正しい名簿で測ると unlisted は user scope 1 件・project scope 全 4 dir とも 0 件。`user_profile.md` は feedback entry ではなく、terminal-configs の 6 件は同 project の OLD-MEMORY.md に収載済 = 正しく retired
  - 真の欠損は **`feedback_turn_end_continuation_claim.md` (2026-08-06 / `models: fable-5`) の 1 件のみ**
  - upsert 経路自体は健全: orphan 1 件に `--upsert` を実行すると rc=0 で index に載る (検証後 `--delete` で baseline 67 に戻した)。原因は権限でも parse でもない
  - **機序を code で確定**: `_list_active_entries()` (`memory_surface.py:466-486`) は **MEMORY.md の `- [title](path.md)` link だけ**を active とみなし、`_main_rebuild()` は当該 scope を `DELETE` で全消ししてから listed path のみ再投入する (`:1164-1180`)。つまり **MEMORY.md に link されていない entry は、次の `--rebuild` で無言で index から消える**
  - 実害の実例: `feedback_turn_end_continuation_claim.md` は 2026-08-06 19:14〜08-07 17:17 に **32 回 emit** し 08-08 01:05 まで mismatch を記録していた = 当時は index にいた。その後 rebuild で消え、以降 0 件。同名 skill も無いので retire ではない
- [x] deploy (ユーザー手動): `files/claude_user-hooks/memory_surface.py` → `~/.claude/hooks/memory_surface.py` — 2026-08-12 00:33 に deploy、`diff` 0 hunk 一致。私が渡した `install -m 0644` が原因で一度 0644 になり裸実行が rc=126 で死んだが、`chmod 0755` で復旧 (裸実行 rc=0 を確認)
- [x] `feedback_turn_end_continuation_claim.md` を MEMORY.md に載せ直すか retire するかを決める (内容判断・要ユーザー) — 2026-08-12 に復帰。MEMORY.md へ追記 (40 行) + `--upsert` で `entries_fts` 68 件。deploy 済 hook で `--rebuild` すると `rebuilt 33/33` かつ `dropped` 行が消え、roster 経由で落ちなくなったことを確認。tag は観測どおり `fable-5` のまま
  - 判断材料 (除外ゼロ走査): `継続します` / `自走` / `再開の種` / `continuation-claim` は user skill 33 本・managed skill 30 本・3 つの CLAUDE.md・repo の `files/` 全体で **0 hit**。`遂行宣言` は `stop_checks.py` の intent-without-task family にのみ存在するが、その是正は「Task を登録せよ」であって「未来形の主張をするな」ではない
  - よって本 entry の教訓を代替する skill / hook は存在せず、retire ではなく欠損として扱うのが妥当。なお本 session で intent-without-task から疑問形を除外して発火を弱めているため、この discipline の被覆は以前より薄い

- [ ] **codex への発注そのものを script 化して起動 flag を固定する** — lint は発注書の中身を見るが、
  起動の手つきは依然として手動である。2026-08-12 の 2 回の発注で起動側の失敗が 3 件出た:
  (a) 同じ発注が 2 job 走り報告書 path が衝突しかけた (先発は default model)、
  (b) `task --help` が flag と解されず本文として起動された、
  (c) `--model` / `--effort` が job record に届かず default model で敵対レビューが走りかけた
  (弱いレビューの「指摘ゼロ」は空の合格になる)。script が flag を固定し、起動直後に job record の
  `request.model` / `request.effort` が指定と一致することを検証するところまでを含める

Work file: `last-session-handoff.md` の同名 section

### 失敗時に過去の教訓を自動で引く (優先度低)

Goal: tool 失敗のたびに横断検索を起動し、mute された教訓も含めて提示する。

Exit Criteria:

- [ ] **失敗したら毎回、過去の教訓を横断検索する**: skill には書いたが hook は tool failure を観測しない。**要件変更 (2026-08-12・ユーザー判断): 「2 回目で起動」をやめ、失敗のたびに毎回起動する** — 2 回待つ理由が無い。current turn の tool_result 失敗を検知したら `search_unfiltered()` を回し、mute された候補も含めて提示する
