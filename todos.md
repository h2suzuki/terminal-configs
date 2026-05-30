# Todos

## Critical

## High

### memory entry 書式の決定論的 enforcement hook (Core 完成・deploy・実機検証済 / Haiku layer deferred)

Goal: memory-routing skill 非発火時も、 memory entry の正書式 (reminder:/keywords:) と DB 同期が決定論的に担保される managed hook。 retrieval 層 (reminder/keywords surface, commit 済) の上の hard enforcement 層。

確定設計 (2026-05-30 session, H.S. 承認):
- 検出機構 = capability grant: /memory-routing skill が entry P を Write する直前に grant ファイル `~/.claude/hooks/state/memory-routing/grants/<basename(P)>` を Write tool で mint。 hook が存在確認し consume (allow 時削除)。 turn_counter / 時刻 window 非依存、 1 turn 複数 entry 対応、 乱数不要 (path basename に束ねる)。
- Write on entry: grant 不在 → deny「/memory-routing を使え」。 内容不備 (reminder/keywords 欠落・oneline_summary・FTS token 0 / 広すぎ stopword のみ・50KB 超) → deny (是正指示)。 warn は廃止 (Edit を塞いだので一発 Write 原則)。 両 OK で allow + grant consume。
- Edit/MultiEdit on entry: 無条件 hard deny → full content で Write 誘導。 index (MEMORY/OLD-MEMORY) は gate 対象外で Edit 可。
- 対象: memory dir 下の全 *.md (prefix 不問、 index 除外)。 deny は JSON permissionDecision (read_before_edit 同型・fail-open)、 opt-out `memory-guard: allow`。
- 配線: managed hook (memory_routing_gate.py、 guard/sync 2 mode 1 script)。 copy_dir 自動 deploy で copy 行不要。

実装状況:
- [x] Layer A 実装: memory_routing_gate.py (PreToolUse guard + PostToolUse sync) + settings 登録 + SKILL.md 改訂 (grant mint 節 + skill 経由必須の警告 + 退役 footer の Edit→Write 注記)
- [x] Layer A unit-smoke: 25/25 PASS (path 判定/内容 check/Edit deny/no-grant deny/grant+不備 deny 保持/grant+正常 allow consume/sync filter)。 Write tool の親 dir 自動作成も確認
- [x] commit fa12009 (hook+settings+skill+todos)
- [x] deploy 済 (sudo install で /etc/claude-code/ へ hook+settings+skill)。 managed-settings は mid-session hot-reload されるため即 live active
- [x] Layer A 実機統合検証 (2026-05-30 deploy 後 同 session): grant 無し直接 Write→deny / grant mint→allow / grant 有り Write→allow+consume / live PostToolUse sync→DB upsert / Edit→deny、 全 PASS (throwaway entry で実施・後始末済)。 LIKE クエリは FTS5 UNINDEXED 列で誤動作するので DB 確認は exact / instr を使う

RESOLVED — Layer B (reminder actionability の Haiku 判定): **drop** (H.S. 決定 2026-05-30)。
- 判断根拠 (cost 分析): sync Haiku deny / async advisory は共に、 Layer A が意図的に脱した LLM 依存・非決定性 (fail-open) を、 actionability という品質グラデーション 1 点のため再導入する。 sync は毎 Write latency + cascade 事故歴のある hook→claude 起動、 async は「直すには Edit=deny」の詰みを抱える。
- actionability の control point は SKILL.md の著者時 guidance に既存 (著者 = /memory-routing 実行中の Claude、 Haiku より高能力)。
- 再訪条件: summary-drift な reminder が実際に surface して無価値と観測されたら、 evidence 付きで再検討。 今は未計測ゆえ投機実装しない。

経緯: 2026-05-30 session で reminder/keywords 移行 (retrieval 層) 完成後、 H.S.「memory-routing 未使用で書いた時 detect/deny できるか」提起。 同 session で 4 論点 + 検出機構 (capability grant) まで詰め H.S. 承認、 Core 実装。 broad「skill 発火率 system 対策」の memory 特化・skill 起動非依存の決定論的 enforcement 具体例。

Work file: last-session-handoff.md (contingency 用)

### skill 発火率 system 対策

Goal: 既存 skill (verify-before-claim / report-by-evidence / scope-mismatch-detector / illuminate-not-reassure / 他) と 本 session で追加した user memory entry 4 個が、 LLM の「trigger 該当時の self-invoke」 に依存して発火率低い問題への system 対策を設計 + 実装。

Exit Criteria:
- [ ] system 設計案を 2-3 案 verbalize (例: Stop hook で output pattern match + advisory inject、 UserPromptSubmit hook で trigger keyword 強調、 等)、 各案の cost / 効果を `rejection-via-actual-cost` skill に従い評価
- [ ] user に設計案提示 + 合意
- [ ] 実装 (`files/claude_managed-hooks/` + settings.json wiring + deploy script) + smoke test (false positive / false negative の率を実機計測)
- [ ] commit
- [ ] hook で cover された skill / memory entry を OLD 移動 (= memory-routing rule 通り)

経緯: 2026-05-28/29 session b188f677 で user 提起: 「信用を高めるためのスキルをたくさん作ったのだけれど、 それを高確率で発火できないシステム上の問題があるようだから、 そこをなんとかできると、 本当はベスト。 今回の緊急対応も、 非常に良い経験になるフローで、 セッションを振り返ってスキル化できたとしても、 発火できなければ無価値」。 本 session 内で私が writing-todos / memory-routing / report-by-evidence 等の trigger 該当時に invoke 漏らした事例多数。

Work file: 本 entry が単独 reference (chat log U[1155])

### advisory hook for evaluative term post-hoc check

Goal: LLM 最終 output 内の evaluative term (`大改造` / `軽微` / `影響大` / `アーキテクチャの見直し` 等) を Stop hook で pattern match して advisory feedback を返し、 次 turn の self-correction の材料にする (deny でなく soft、 false positive 許容)。 上記 High task (skill 発火率 system 対策) の特殊 case として、 統合候補。

Exit Criteria:
- [ ] Stop hook の event spec を一次資料で確認 (`code.claude.com/docs/en/hooks-guide`: payload 形、 `additionalContext` / `systemMessage` 出力規約)
- [ ] hook script 実装 (`files/claude_managed-hooks/` 配下、 pattern match + advisory message 出力、 deny フィールドは設定しない)
- [ ] `files/claude_managed-settings.json` に hook 登録、 deploy script (`ubuntu2404-wsl.sh` / `debian12.sh`) の `copy` 行追加
- [ ] 実機で evaluative term を含む output → advisory が次 turn additionalContext に出ることを確認

経緯: 2026-05-28 session で「大改造」 を実コード未読で発話 → user 指摘で `report-by-evidence` skill 違反確定。 既存 skill の trigger は文末 judgment 想定で structured doc (table cell) の評価語混入が射程外。 user 指針「skill 減・hook 増・trigger 単純化」 に従い hook 化で対応。

Work file: 現 session の議論 (本 entry が単独 reference)

## Medium

### memory entry: evaluative term in table cell の違反事例

Goal: 2026-05-28 session で発生した「比較表 cell に評価形容詞 (`大改造`) を ungrounded で混入」 事例を memory entry に save、 advisory hook 完成までの reminder とする。

Exit Criteria:
- [ ] `feedback_evaluative_term_in_table_cell.md` を user memory (`~/.claude/memory/`、 cross-project applicable な評価語 hedge pattern) に作成
- [ ] user MEMORY.md index に新 entry を追加 (user explicit authorize 必要)
- [ ] hook DB sync (`memory_surface.py --upsert`)

Note: 上記 High task (advisory hook) 完成後は本 entry を `~/.claude/memory/OLD-MEMORY.md` に移動 (= memory-routing rule 通り、 Managed hook で cover された退役 entry)

Work file: 現 session の議論
