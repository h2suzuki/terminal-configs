# Todos

## Critical

## High

### memory_surface 誤発火修正 (BM25_SURFACE_FLOOR 厳格化)

Goal: 緊急 entry (`feedback_no_other_work_or_worsening_commands_during_emergency.md`) 等が非緊急 prompt ("stop hook" 等) で誤 surface する over-fire を、 誤検出を最小化しつつ recall を保って解消する。

Exit Criteria:
- [x] root-cause 特定 + 承認方針の再検証 (2026-06-04): 前 session 承認の approach (1) `bm25(…,10,1)` keyword 重み付けは FP に対し**実機 no-op** と判明 — 緊急 entry の "stop"/"hook" は **body のみ**マッチ (keywords に無い) ため keywords 重みを上げても score 不変 (-2.396→-2.396)。 bm25 列重みは「その列にマッチした行」にのみ効く正しい仕様 (バグでない。 keywords match を持つ bg_session は -2.137→-2.377 と変化し機構の生存を確認)。 ∴ body-only FP は keyword 上げでなく **floor 厳格化 (approach 3) でしか消せない**。 H.S. 再承認: 重み付け (1) は破棄、 floor 厳格化のみ採用
- [ ] corpus calibration で `BM25_SURFACE_FLOOR` の値を決定 (現 -1.0 → 約 -3.0 見込み。 正規マッチ -4〜-12 と FP -2.4 が明確分離)。 realistic prompt corpus (recall+ / FP / adversarial-FP) で FP 抑止 vs recall を実測。 sweep harness = read-only で source の `_build_query` を import し live DB に当てる scratch script (本 session の `/tmp/cal_memory_floor.py`、 消えたら再生成可)
- [ ] source 編集: `files/claude_user-hooks/memory_surface.py` の `BM25_SURFACE_FLOOR` (line 43) を更新 + コメント。 `BM25_STRONG_FLOOR` (line 45, rank1 gate) も要否判断。 **重み付けは入れない** (no-op ゆえ)
- [ ] smoke (calibration sweep が回帰になる) → deploy 両 user: `~/.claude/hooks/memory_surface.py` (debian12.sh + ubuntu2404-wsl.sh の copy 行、 root + login_user 両方)。 `~/.claude` 配下ゆえ sudo 不要。 source==deploy 確認

経緯: 前 session (b1b20622、 count-glitch で中断) が「keyword 重み + floor」=「1+3」で H.S. 承認を得たが、 本 session で (1) の実機 no-op を発見し floor-only に修正 (H.S. 再承認)。 同 session の他の回収 idea (Stop hook haiku watcher / malformed tool-call 自動復旧) は未起票 — 着手時に起票する。

### skill 発火率 system 対策

Goal: 既存 skill (verify-before-claim / report-by-evidence / scope-mismatch-detector / illuminate-not-reassure / 他) と 本 session で追加した user memory entry 4 個が、 LLM の「trigger 該当時の self-invoke」 に依存して発火率低い問題への system 対策を設計 + 実装。

Exit Criteria:
- [x] system 設計: 4 機構の設計を adversarial 監査込みで確定 (2026-05-30 workflow w3zrkuwwh)。 核心原則 = 「trigger が機構的に検出できる skill は check を hook に移して発火依存を消す」 (raise でなく eliminate)。 (**最優先機構 = skill-active gate (`skill_reminder_gate.py`) は 2026-05-30 に pivot・plan 承認済。 当初の additionalContext advisory 案は破棄**。 他 3 機構は据置)
- [x] skill-active gate `skill_reminder_gate.py` (最優先・本 session の writing-code/python 漏れを直撃) 実装・deploy 済 (2026-05-30 commit c585671 / smoke 51/51 / adversarial review 5 confirmed fix 反映 / `/etc/claude-code/hooks/` deploy mode 0755 / 当 session で `.sh` write が writing-bash 要求 deny される live 実機確認)。 PreToolUse(Edit|Write|MultiEdit) で「関連 writing-* skill が**当 turn に invoke 済か**」を gate — 正規ルート (skill 発動→同 turn で edit) は通し、 skip=detour は JSON deny → 正しい kind を `declare` → skill invoke → edit。 kind は sniff でなく **model の declare が真実源** (語彙 python/bash/code/test/skills/todos/memory/**else**、 else=skill 無し file で Write 不能を防ぐ)。 skill-active は **現 turn ∪ 直近 5 分の timestamp 窓** (2026-05-31 commit 1267bd0 で H.S. 指定により current-turn-only から拡張、 毎 turn 再 invoke の friction 解消)。 拡張子あり file は auto-detect、 拡張子なし file のみ declare 要。 memory_routing_gate の JSON-deny/fail-open 継承・stop_checks の current-turn 解析流用。 **spike (advisory 版) は誤設計ゆえ破棄済**。 full 設計は plan file 参照
- [x] declare-and-proceed gate: PreToolUse(`^AskUserQuestion$`) `declare_and_proceed_gate.py` 実装・commit・deploy 済。 **deny-gate** (skill_reminder_gate の twin。 当初 advisory additionalContext で作ったが bg review #8「dead-on-arrival = 質問が出た後に届き止められない」を受け H.S. 承認で deny-gate に作り直し)。 decidable な routing/per-batch-confirm に match かつ declare-and-proceed が当 turn (∪直近5分) 未 invoke なら JSON deny → skill invoke で 3-check を ask 前に強制、 invoke 後 (自分で決める or genuine 例外で再 ask) は通す。 検出 = CONFIRM (「これで良い?」「進めて良い?」「この方針で良い」系) + ROUTING (「どちらから調査」「A経由かB経由か」「A するか B するか」系、 SKILL 正典 trigger 込)、 open which-X の design 質問 / force-push pre-approval / user-taste は silent pass。 turn-boundary scan・5分窓・fail-open は skill_reminder_gate 流用。 deploy: `/etc/claude-code/hooks/` mode 0755 + managed-settings に `^AskUserQuestion$` matcher、 source/live 一致。 smoke 9/9 (deny: confirm/routing/A-or-B 各 skill 不在時 / pass: design-naming・force-push・skill invoke 後・no-transcript・wrong-tool・malformed)。 commit 7020107 (deny-gate) + 156c671 (review#1 bare このスタイルで除去)。 sudo deploy は最初 auto classifier deny → H.S. 許可で成功 (host-side ops は許可だけ必要・memory entry 更新済)
- [x] bg adversarial review (whurf7uox) triage: 15 findings 全 confirmed だが大半 adjusted LOW (非 block advisory ゆえ blast radius 小)。 #8 dead-on-arrival → deny-gate 化で構造的解消、 #1 bare-このスタイルで over-fire → anchored alternation に畳んで解消、 #11 SKIP-category leak (適用して/方針で良い等が destructive/design に漏れる) → deny-gate で skill 経由を強制し model が genuine 例外を再 ask する設計で許容、 残 FN 系 (#4/#5 conjugation/介在名詞) は narrow-recall の意図内で観測後 tighten。 fixup 不要 (新規 deny-gate に最新知見反映済)
- [x] stop_checks 拡張 (commit 5b7baf3・deploy 済 LIVE): provide-user-instructions family (manual-exec 文脈 + host-cmd が fence/inline-backtick 外に残れば warn、strip_fences・ホスト側 は exec 動詞必須化) + verify-before-claim positive side (網羅した等 completeness self-claim を EVIDENCE_TOOLS 無しで warn、確認済み除外・reasonable default は assertion anchor 要・strip_fences 適用)。 設計 = corpus calibration workflow (wirtge98z、8295 blocks/2115 turns 実測) → 実装 → adversarial review workflow (wzfly2hxj、3 lens 再現) で HIGH FP 2 件 (bare ホスト側 over-fire = 156c671 と同型) 修正 → smoke 36/36 (9 既存 regression + 21 family + 6 review-FP guard、work file `/tmp/smoke_stop_checks_l3.py`)。 warning-only・advise-once 継承・block/turn-marker 不変
- [x] UserPromptSubmit concern/correction injector (L4, commit b30363d・deploy 済 LIVE): `memory_surface.py` に `_concern_inject` を 1 block 統合。 user prompt を走査し concern→illuminate-not-reassure / correction→memory-routing を raise (enforce 不可ゆえ reminder 注入のみ、 discipline body は semantic 残)。 corpus calibration workflow (w32196ybw、 890 実 prompt) で tight phrase set 確定 → adversarial review (wuc1k7zmz) で 間違 を DROP (一般的「誤り」に発火し off-target・本 repo 最大 FP)・compaction continuation skip・OSError fail-open→drop を修正 → smoke 24/24 (work file `/tmp/smoke_l4_concern.py`)。 既存 throttle を sentinel key で channel ごと 900s 再利用・reminder は名前非埋込・fail-open。 発火率実測 ~2.8% (throttle 後 <1-2%)
- [ ] CUT: attribute-existing-issues の PreToolUse arm (SKIP 条件 = pattern が真に既存 AND session 未触、 git-blame 要で FP) → Stop warn のみに留める
- [ ] 各機構ごと smoke (emit-vs-comply 計測、 fail-open) → commit → cover された skill / memory entry を OLD 移動 (memory-routing)

経緯: 2026-05-28/29 session b188f677 で user 提起: 「信用を高めるためのスキルをたくさん作ったのだけれど、 それを高確率で発火できないシステム上の問題があるようだから、 そこをなんとかできると、 本当はベスト。 発火できなければ無価値」。 本 session でも writing-code/writing-python を .py hook 編集前に invoke 漏らした (= 本 task が解く問題の live 実例。 debug-guardrail 分析: ambient trigger 低 salience + 親 skill frame crowding + tool 層 enforcement 不在 = self-recall 構造不信頼)。

Work file: `last-session-handoff.md` の 「skill 発火率 system 対策」 section ＋ plan `~/.claude/plans/breezy-bubbling-quiche.md` (skill-active gate の full 設計 + 本 session の訂正 + 次 session 手順の durable copy)

### advisory hook for evaluative term post-hoc check

Goal: LLM output 内の評価語 (`大改造` / `影響大` / `アーキテクチャ再設計系` / `改造が少ない`) を Stop hook で捕捉し、 同 turn に証拠 tool (EVIDENCE_TOOLS) が無ければ block して report-by-evidence へ誘導する。 Stop の model 到達 channel は exit2 / decision:block の 2 つだけで両方 block と一次資料で確定 → soft 不可 → block route + `stop_hook_active` advise-once gate で自己 block loop を断つ設計に pivot 済 (H.S. 承認)。

Exit Criteria:
- [x] Stop hook spec 一次資料確認 (stop_hook_active 意味論 / exit2・decision:block の 2 channel / additionalContext は Stop 非対応 / 8-block override cap)
- [x] hook 実装: 評価語 family (bare-term, EVIDENCE_TOOLS free-pass) + 全 block family への advise-once gate + docstring rewrite (commit f1dab94, e2800b8 を rebase で rewrite)
- [x] settings/copy 行は不要と確認 (`copy_dir claude_managed-hooks/` で hooks dir 丸ごと deploy 済、 既存 file 改造ゆえ新規 wiring 不要)
- [x] smoke 12/12 (block / free-pass / 既存 family 無回帰 / stop_hook_active demote + marker 1-bump guard / 評価語 影響大(?!き) で形容詞除外)
- [x] bg `/code-review` triage 完了 (confirm-intent: 全 family advise-once は意図的・docstring に regression-proof 明記 / 影響大(?!き) で形容詞 影響大きい 除外 / `_check` を warnings·blocking 分離返しに refactor → f1dab94 に fixup-autosquash / plan 文発火は accept (v1) / no-defect 確認)。 session 自己終了済
- [x] deploy 済 (LIVE): L3 と同一 file ゆえ bundle、`sudo install -m 0755 files/claude_managed-hooks/stop_checks.py /etc/claude-code/hooks/stop_checks.py` で deploy (source==deploy・mode 755 確認)。 f1dab94 の評価語 family も同時 live 化
- [ ] 実機確認: deploy 後、 table cell に評価語 + 証拠なし → block、 retry で advise-once pass を観測
- [ ] (candidate) `/tmp/smoke_stop_checks.py` を committed regression test 化するか判断 (現状 repo に hook test 基盤なし、 cross-hook 不変条件 = 価値あり)
- [ ] (v1 known-FP, 観測ベース): `アーキテクチャの見直しを行います` 等の plan 文も発火 (advise-once で 1 回 backstop)。 観測増えたら predicate-proximity で tighten 検討

経緯: 2026-05-28 session で「大改造」 を実コード未読で発話 → report-by-evidence 違反。 既存 skill trigger は文末 judgment 想定で structured doc (table cell) の評価語混入が射程外。 hook 化で補完。

Work file: `last-session-handoff.md` + commit f1dab94。 残 = deploy (別 session) + 実機確認

### stop_checks: known-possible-denial family

Goal: 既知で可能と判明済みの操作 (KNOWN_POSSIBLE 表 = 部分 stage / rebase autosquash 等) を「できない/不可/無理」と同一行で断定したら Stop hook で block し、 verify させ直さず既知 method を実行させる (verify-before-claim の不可断定側、 2026-06-04 H.S. 依頼)。

Exit Criteria:
- [x] 実装: `stop_checks.py` に `KNOWN_POSSIBLE` 表 + `IMPOSSIBLE_RE` (lookahead で 不可能/不可避/不可逆/不可分/不可欠/不可侵 除外) + `_known_possible_denial()` helper + `_check()` 内 block 呼出 + docstring family。 strip_fences 適用・pairing 無し (op が既知可能ゆえ証拠の有無に関わらず否定が誤り)。 advise-once gate は既存 `_run` が demote するので再 block loop 無し
- [x] smoke 15/15 (`/tmp/smoke_known_denial.py`): 5 block ケース (partial+不可 / git add -p+できない / autosquash+できない / 部分コミット+無理 / 部分ステージ+no-op) + 8 non-block ケース (op only / impossible only / fenced / inline-backtick / できないか exploratory / 不可避 lookahead / 不可能 lookahead / cross-line) + 2 regression (eval 大改造 / clean text)。 ruff lint+format + ty + 既存 unittest 7/7 全 clean
- [x] deploy 済: `sudo install -m 0755` で `/etc/claude-code/hooks/stop_checks.py`、 source==deployed、 mode 755 確認
- [ ] live self-test: 部分 stage で本 entry を commit + trigger 文言を発話 → 自分の Stop hook に block される実証 (本 turn 進行中)

経緯: 2026-06-04 session、 私が「partial staging は不可」「foreign hunk 検出は無理」と未検証で 2 度断定し H.S. に「メモリに保存すべき案件・git add で surface されるべきだった」「verify させるのでなく、 できると分かっているのだから、 させろ」と指摘された (= 本機構の core motivation)。 同根 sibling entries: `feedback_partial_stage_foreign_changes` (2026-06-04) / `feedback_rebase_autosquash_needs_interactive` (2026-06-03) / `feedback_rebut_user_concern_with_inference` (2026-06-04)。

Work file: `files/claude_managed-hooks/stop_checks.py` + smoke `/tmp/smoke_known_denial.py`

## Medium

### feature-research に Claude Developer Platform source 追加

Goal: SessionStart の `feature_findings_build.py` に第 2 source (Claude Developer Platform release notes) を足し、 cutoff 後の公式ツール (`ant` CLI 等) / API / Managed Agents の delta も findings.md で認知できるようにする (2026-06-04 H.S. 依頼)。

Exit Criteria:
- [x] builder に platform parser + section emit 追加 (commit 2a52abd): `parse_platform` + `build_platform_section`、 source `platform.claude.com/docs/en/release-notes/overview.md`、 `### <date>` ブロック verbatim、 cutoff>=2026-01、 `_parse_date` を序数 `15th` 許容の superset 拡張。 findings.md 先頭 `## v<claude_ver>` 不変・platform fetch fail-soft (CC のみ出力+`_log_err`)・rebuild trigger は claude version 据置
- [x] smoke offline (`--platform-input` sample `--stdout`): pre-cutoff 序数 (`Dec 20th, 2025`/`Jul 15th, 2024`) DROP・`Jan 1, 2026` 境界 KEEP・nested 子 bullet 保全・`<Tip>` 前文 skip を確認。 ruff lint+format + ty all clean
- [x] 消費側 5 skill 文言更新 (commit beec079): 「Claude Code 仕様 delta」→「Claude Code ＋ Claude Developer Platform」へ broaden、 核心の「不明 spec は findings.md を Read」は保持
- [x] findings.md 実 fetch 再生成 (`--force` exit0): 先頭 `## v2.1.161` (=`claude --version` 一致で version 整合維持)、 platform section (line 1469) に実物 ant CLI entry (line 1548「We've launched the `ant` CLI …」) 着地、 pre-cutoff 漏れ無し・fetch error log 無し
- [x] deploy 済: `/etc/claude-code/hooks/feature_findings_build.py` (mode 0755) + 5 skill を `sudo install`、 全 6 件 source==deployed 確認 (symlink `~/.claude/skills/*` 経由で反映)

Note: 機能は完成・LIVE deploy 済・end-to-end 検証済。 残は H.S. レビュー (skill 文言の broaden 表現 + platform section の verbatim-by-date 書式が意図通りか)。 承認後に block 削除。

Work file: builder = `files/claude_managed-hooks/feature_findings_build.py`

### Claude Code 拡張 installer (extra/claude_extensions.sh)

Goal: agent-browser (Vercel skill+CLI) / Playwright MCP (Microsoft @playwright/mcp) / Figma plugin (Anthropic marketplace) を per-user (scope=user) で入れる opt-in script を提供し、 再実行で in-place upgrade できる。

Exit Criteria:
- [x] 実装 + 静的検証 (shellcheck clean / `bash -n` / 全 claude サブコマンド syntax を live 2.1.161 binary で裏とり)、 再実行 upgrade 対応 — commit 38d511f
- [ ] 実機 fresh provisioning で end-to-end 実行確認: (a) skills CLI が `--agent claude-code` を受理し `~/.claude/skills` へ global install / (b) `agent-browser install` の apt-sudo 挙動 (system lib 不足時) / (c) figma plugin の install/update が非対話で通る / (d) playwright が system Chrome を headless 起動 / (e) PW_MCP_VER の runtime 解決が機能

決定事項 (rejected — 再検討時の参照): GitHub MCP 不採用 (gh と重複・優位性 incremental・Linux remote OAuth 不可 #3433、 案内のみ) / managed-mcp.json 不採用 (排他制御で plugin + claude.ai connector を suppress・単一ユーザー機に過剰) / Vercel Plugin 未採用 (依頼外・Next.js 開発向けの束、 欲しければ `npx plugins add vercel/vercel-plugin`) / per-user `claude mcp add -s user` 採用 (files/ deploy でなく runtime config ゆえ canonical-source 非該当)。

Work file: extra/claude_extensions.sh

### memory entry: evaluative term in table cell の違反事例

Goal: 2026-05-28 session で発生した「比較表 cell に評価形容詞 (`大改造`) を ungrounded で混入」 事例を memory entry に save、 advisory hook 完成までの reminder とする。

Exit Criteria:
- [ ] `feedback_evaluative_term_in_table_cell.md` を user memory (`~/.claude/memory/`、 cross-project applicable な評価語 hedge pattern) に作成
- [ ] user MEMORY.md index に新 entry を追加 (user explicit authorize 必要)
- [ ] hook DB sync (`memory_surface.py --upsert`)

Note: 上記 High task (advisory hook) 完成後は本 entry を `~/.claude/memory/OLD-MEMORY.md` に移動 (= memory-routing rule 通り、 Managed hook で cover された退役 entry)

Work file: 現 session の議論

### SKILL-HOOK-CONTRACT.md パターン集

Goal: repo 直下に `SKILL-HOOK-CONTRACT.md` を作り、 hook/skill の**実装 contract** 再利用パターンを集約して一貫性を担保する (2026-05-30 H.S. 依頼)。

Exit Criteria:
- [ ] `SKILL-HOOK-CONTRACT.md` を repo 直下に作成。 含める実装 contract: capability-grant (skill/declare が mint・hook が check, fail-open) / permission semantics (additionalContext 省略=passthrough・deny は JSON・allow は auto-approve 回避) / session-keyed state (`$CLAUDE_CODE_SESSION_ID`==payload session_id) / transcript current-turn scan (stop_checks 方式) / fail-open (例外 exit0・deny は JSON) / deny-wording 規律 / extensible `LANGUAGES` dispatch table / **use-case 駆動の TTL 選定 (盲目流用しない)** / PostToolUse sync
- [ ] **除外を厳守** (H.S. 指摘・種類が違う): deploy の決まり (`copy_dir`・exec-bit 0755・settings `copy`) は contract でなく **deploy ルール** ゆえ混ぜない
- [x] (H.S. 追加依頼) 文書先頭に jargon-free な L1〜L4 概観 (動機/仕組み/狙う効果 の3軸表 + 補足 + 具体例) を記載 (commit 91cf0e0)。 固有名は「相手」に汎用化。 実装 contract 本体は placeholder

Note: doc 本体 (L1〜L4 概観 head + 実装 contract 0〜5 + 除外) 記載・commit 27b498c・SendUserFile 送付済。 目次 = 二つの family → capability-grant → 判定/検出/状態/安全 → 除外、 各項に実フック名の具体例。 **H.S. レビュー待ち** (外出先・後日)。 承認後に Exit flip + block 削除 (body 構成/粒度の直しがあれば反映してから)。 2026-05-31: コード照合 audit (workflow wvsbvz52x、 34 claim 中 30 accurate、 adversarial 確認・誤 flag 1 件棄却) 実施し確定 3 finding を commit eedd808 で反映 — (A) 中核 dichotomy 訂正 (L3 stop_checks の 4 family は exit2 で block、 overview L3 行+段階補足+§0 表)、 (B) §3 synthetic-skip を path 別に (BM25 surfacer `_memory_surface` は非 skip・本 turn live 確認)、 (C) §1/§2 に advisory-allow + content-embedded opt-out token 追記。 **事実精度は audit 済**、 残は H.S. の構成/粒度レビュー。 任意候補: 補足「L3とL4どう違うか」の「指摘する」(現 line 24) も同根で、 H.S. が望めば「介入する」系へ。 follow-up (doc外・コード): `_memory_surface` が synthetic prompt を surface する挙動の許容可否。 2026-06-01〜02: H.S. live レビューで overview を全面改稿 (歴史先行 CLAUDE.md→skill→hook / L1-L4 jargon 撤去 / 一人称除去 / です・ます / 表 A-D 化+俳句 / capability-grant をフロー番号リスト化 / 事実確認) + ファイル名 `_`→`-` リネーム (commit 025a3c6・14cf6d0)。 **レビュー継続中** — 次 session も H.S. の追加指摘を反映。 確立した編集ルールは handoff doc 参照。

Work file: handoff = `last-session-handoff.md` の「SKILL-HOOK-CONTRACT.md パターン集」 section ＋ plan `~/.claude/plans/breezy-bubbling-quiche.md` の「並行 deliverable」節
