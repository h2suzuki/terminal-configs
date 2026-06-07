# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108


## Critical

## High

### memory_surface BM25+RAG hybrid (OSS 調査 → 導入)

Goal: BM25 surfacer に意味検索 (embedding) 層を足し、 lexical で拾えない recall (terse/言い換え prompt・緊急 trigger) と precision を両立する。 SQLite 同等の導入容易さが理想 (2026-06-04 H.S. 方針)。

Exit Criteria:
- [ ] OSS 調査 (deep-research 候補): 最も導入が楽な構成を提示。 候補 = vector store **sqlite-vec** (既存 FTS5 と同一 SQLite file で hybrid 可)、 local embedding **model2vec / fastembed** 等 (hook 内 offline・高速・日本語対応が要件)。 軸 = 導入容易さ / 依存の軽さ / 日本語 embedding 品質 / hook 実行コスト
- [ ] 構成決定 → hybrid scoring (FTS5 BM25 ⊕ vector) 実装 → calibration (本 session の corpus 流用) → deploy 両 user

経緯/前提: BM25 層は 2026-06-04 commit c7dbcea で deploy 済。 緊急 entry は BM25 lexical に原理的不向き (本物 trigger 血が出てる/暴走 は trigram-phrase の脆さで弱マッチ、 body の英語 ops 語が benign に強マッチ、 両立 weight/floor 無し)。 recall 上限 ~24% も lexical の限界。 ∴ これ以上の精度は H.S. 判断で BM25+RAG hybrid。 現 session は context 長 (crash 多発) ゆえ調査は fresh session 推奨。 corpus = 本 session workflow wyjhtnr4x 出力 (`/tmp/…` 揮発・要再生成)、 sweep harness `/tmp/cal_memory_floor.py` (揮発・read-only で source の `_build_query` import し live DB に当てる)

回収した未起票スレッド (前 session b1b20622、 着手時に正式起票): (a) Stop hook haiku watcher (第三者 LLM が会話状態をメタ解析し助言、 H.S. idea) (b) malformed tool-call ("count") 自動復旧 + Anthropic bug report (c) MCP per-host 多重 spawn 懸念 — root+login 両 install で増幅、 前 session L497 で H.S. 提起・未対応 (d) Medium「Claude Code 拡張 installer」 block の decision-list が commit 35ba90e の rebuild で陳腐化 (dual-loop / GCP / Vercel plugin 採用へ scope 反転) — 要 update

### skill 発火率 system 対策

Goal: 既存 skill (verify-before-claim / report-by-evidence / scope-mismatch-detector / illuminate-not-reassure / 他) と 本 session で追加した user memory entry 4 個が、 LLM の「trigger 該当時の self-invoke」 に依存して発火率低い問題への system 対策を設計 + 実装。

Exit Criteria:
- [x] system 設計: 4 機構の設計を adversarial 監査込みで確定 (2026-05-30 workflow w3zrkuwwh)。 核心原則 = 「trigger が機構的に検出できる skill は check を hook に移して発火依存を消す」 (raise でなく eliminate)。 (**最優先機構 = skill-active gate (`skill_reminder_gate.py`) は 2026-05-30 に pivot・plan 承認済。 当初の additionalContext advisory 案は破棄**。 他 3 機構は据置)
- [x] skill-active gate `skill_reminder_gate.py` (最優先・本 session の writing-code/python 漏れを直撃) 実装・deploy 済 (2026-05-30 commit c585671 / smoke 51/51 / adversarial review 5 confirmed fix 反映 / `/etc/claude-code/hooks/` deploy mode 0755 / 当 session で `.sh` write が writing-bash 要求 deny される live 実機確認)。 PreToolUse(Edit|Write|MultiEdit) で「関連 writing-* skill が**当 turn に invoke 済か**」を gate — 正規ルート (skill 発動→同 turn で edit) は通し、 skip=detour は JSON deny → 正しい kind を `declare` → skill invoke → edit。 kind は sniff でなく **model の declare が真実源** (語彙 python/bash/code/test/skills/todos/memory/**else**、 else=skill 無し file で Write 不能を防ぐ)。 skill-active は **現 turn ∪ 直近 5 分の timestamp 窓** (2026-05-31 commit 1267bd0 で H.S. 指定により current-turn-only から拡張、 毎 turn 再 invoke の friction 解消)。 拡張子あり file は auto-detect、 拡張子なし file のみ declare 要。 memory_routing_gate の JSON-deny/fail-open 継承・stop_checks の current-turn 解析流用。 **spike (advisory 版) は誤設計ゆえ破棄済**。 full 設計は plan file 参照
- [x] declare-and-proceed gate: PreToolUse(`^AskUserQuestion$`) `declare_and_proceed_gate.py` 実装・commit・deploy 済。 **deny-gate** (skill_reminder_gate の twin。 当初 advisory additionalContext で作ったが bg review #8「dead-on-arrival = 質問が出た後に届き止められない」を受け H.S. 承認で deny-gate に作り直し)。 decidable な routing/per-batch-confirm に match かつ declare-and-proceed が当 turn (∪直近5分) 未 invoke なら JSON deny → skill invoke で 3-check を ask 前に強制、 invoke 後 (自分で決める or genuine 例外で再 ask) は通す。 検出 = CONFIRM (「これで良い?」「進めて良い?」「この方針で良い」系) + ROUTING (「どちらから調査」「A経由かB経由か」「A するか B するか」系、 SKILL 正典 trigger 込)、 open which-X の design 質問 / force-push pre-approval / user-taste は silent pass。 turn-boundary scan・5分窓・fail-open は skill_reminder_gate 流用。 deploy: `/etc/claude-code/hooks/` mode 0755 + managed-settings に `^AskUserQuestion$` matcher、 source/live 一致。 smoke 9/9 (deny: confirm/routing/A-or-B 各 skill 不在時 / pass: design-naming・force-push・skill invoke 後・no-transcript・wrong-tool・malformed)。 commit 7020107 (deny-gate) + 156c671 (review#1 bare このスタイルで除去)。 sudo deploy は最初 auto classifier deny → H.S. 許可で成功 (host-side ops は許可だけ必要・memory entry 更新済)
- [x] bg adversarial review (whurf7uox) triage: 15 findings 全 confirmed だが大半 adjusted LOW (非 block advisory ゆえ blast radius 小)。 #8 dead-on-arrival → deny-gate 化で構造的解消、 #1 bare-このスタイルで over-fire → anchored alternation に畳んで解消、 #11 SKIP-category leak (適用して/方針で良い等が destructive/design に漏れる) → deny-gate で skill 経由を強制し model が genuine 例外を再 ask する設計で許容、 残 FN 系 (#4/#5 conjugation/介在名詞) は narrow-recall の意図内で観測後 tighten。 fixup 不要 (新規 deny-gate に最新知見反映済)
- [x] stop_checks 拡張 (commit 5b7baf3・deploy 済 LIVE): provide-user-instructions family (manual-exec 文脈 + host-cmd が fence/inline-backtick 外に残れば warn、strip_fences・ホスト側 は exec 動詞必須化) + verify-before-claim positive side (網羅した等 completeness self-claim を EVIDENCE_TOOLS 無しで warn、確認済み除外・reasonable default は assertion anchor 要・strip_fences 適用)。 設計 = corpus calibration workflow (wirtge98z、8295 blocks/2115 turns 実測) → 実装 → adversarial review workflow (wzfly2hxj、3 lens 再現) で HIGH FP 2 件 (bare ホスト側 over-fire = 156c671 と同型) 修正 → smoke 36/36 (9 既存 regression + 21 family + 6 review-FP guard、work file `/tmp/smoke_stop_checks_l3.py`)。 warning-only・advise-once 継承・block/turn-marker 不変
- [x] UserPromptSubmit concern/correction injector (L4, commit b30363d・deploy 済 LIVE): `memory_surface.py` に `_concern_inject` を 1 block 統合。 user prompt を走査し concern→illuminate-not-reassure / correction→memory-routing を raise (enforce 不可ゆえ reminder 注入のみ、 discipline body は semantic 残)。 corpus calibration workflow (w32196ybw、 890 実 prompt) で tight phrase set 確定 → adversarial review (wuc1k7zmz) で 間違 を DROP (一般的「誤り」に発火し off-target・本 repo 最大 FP)・compaction continuation skip・OSError fail-open→drop を修正 → smoke 24/24 (work file `/tmp/smoke_l4_concern.py`)。 既存 throttle を sentinel key で channel ごと 900s 再利用・reminder は名前非埋込・fail-open。 発火率実測 ~2.8% (throttle 後 <1-2%)
- [ ] (要相談) attribute-existing-issues は PreToolUse arm を**未構築** (2026-06-08 audit: find＋両 extensions json で不在確認、 CUT 対象なし)。 残るは design 判断 — (i) skill を semantic-only 据置で本項 close か (ii) stop_checks.py に honest-attribution warn family (既存/繰り越し/段階的拡張 等を誤 pattern 文脈と対で warn・advise-once) 新設か。 (ii) は 既存/段階的拡張 が通常散文に出る FP risk (POS_CLAIM/HOST_CMD と同 class) ゆえ H.S. 判断要
- [ ] smoke 再現: skill_reminder_gate / declare_and_proceed_gate のみ embedded unittest 無し (stop_checks=12・memory_surface=10 は既存) → 2 gate の emit-vs-comply smoke を再作成 (旧 /tmp 揮発) → commit。 OLD 移動は**ほぼ完了** (illuminate/honest-commit/declare の 3 entry を 2026-05-27 退役済、 active MEMORY.md に 4 機構 cover 対象の残無し)

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
- [x] (candidate) `/tmp/smoke_stop_checks.py` を committed regression test 化 → **実施**: 評価語 family の block / free-pass / 形容詞除外 を stop_checks.py の embedded `EnforcementFamilyTest` (tracked) に追加 (commit d4b068f、 `python3 -m unittest stop_checks` で 17/17 green)
- [ ] (v1 known-FP, 観測ベース): `アーキテクチャの見直しを行います` 等の plan 文も発火 (advise-once で 1 回 backstop)。 観測増えたら predicate-proximity で tighten 検討

経緯: 2026-05-28 session で「大改造」 を実コード未読で発話 → report-by-evidence 違反。 既存 skill trigger は文末 judgment 想定で structured doc (table cell) の評価語混入が射程外。 hook 化で補完。

Work file: `last-session-handoff.md` + commit f1dab94。 残 = deploy (別 session) + 実機確認

### declare-and-proceed gate: 散文の二択質問への coverage 拡張

Goal: `declare_and_proceed_gate` は PreToolUse(`^AskUserQuestion$`) のみを gate するため、 AskUserQuestion tool を使わず **散文で二択質問** (「A するか B するか?」「これで良いですか?」) を出すと素通りする。 `stop_checks.py` には既に `order-question-to-user` block family (順序質問の user 投げを block) があるが narrow で、 CONFIRM/ROUTING 系の散文質問は漏れる。 この coverage gap を埋める。

Exit Criteria:
- [x] `stop_checks.py` に CONFIRM/ROUTING family を**新設** (order-question は順序専用ゆえ拡張でなく新設)。 検出 regex は `declare_and_proceed_gate` の prose 版 copy、 `_declare_proceed_active()` で当 turn invoke 判定 → 未 invoke かつ match なら blocking.append (advise-once 自動流用)。 **spec 逸脱**: 「∪直近5分」でなく「当 turn 内 invoke」(Stop は turn 終端発火で 5 分窓が long-turn FP 源ゆえ・H.S. review 対象)
- [x] SKIP category (destructive pre-approval / user-taste / open which-X design) は skill-active escape hatch で `declare_and_proceed_gate` と同一基準 silent pass
- [x] smoke (embedded `EnforcementFamilyTest` 9 件: 散文 confirm/routing→block / open design→pass / declare invoke 後→pass / 既存 family 無回帰) + deploy (`/etc/claude-code/hooks/stop_checks.py` parity OK)。 commit d4b068f・unittest 17/17・ruff/ty clean
- [ ] H.S. review + 観測: (1) spec 「∪直近5分」→「当 turn 内 invoke」変更 (turn-blocking hook の FP 最小化) の承認可否、 (2) 散文 CONFIRM/ROUTING を whole-message 走査する prose-FP (declarative 文の誤発火) を観測 → 必要なら `?` anchor / tail-only 走査で tighten (sibling family の v1-FP 同様 observe-then-tighten)

経緯: 2026-06-08 H.S. 提起。 本 session で assistant が UPE probe の続行可否を AskUserQuestion でなく **散文の二択** で H.S. に問い、 declare-and-proceed 違反 (decidable を自分で決めず外注)。 `declare_and_proceed_gate` は tool matcher ゆえ不発火。 PreToolUse で散文出力を pre-block する手段は無く (= 評価語 post-hoc check と同型の「dead-on-arrival」制約)、 Stop の decision:block で「待たずに自分で決めて続行せよ」と差し戻すのが唯一の channel。 当初 todo は「stop_checks に新規 family 追加」と書いたが、 同 session の SKILL-HOOK-CONTRACT 検証で `order-question-to-user` block family が既存と判明 (私の質問は順序でなく routing ゆえ既存 pattern に漏れた) → 「既存機構の coverage 拡張」へ訂正。

Work file: `files/claude_managed-hooks/stop_checks.py` (拡張先・既存 `order-question-to-user` family L185/491) + `files/claude_managed-hooks/declare_and_proceed_gate.py` (検出 regex の流用元)

## Medium

### Claude Code 拡張 installer (extra/claude_extensions.sh)

Goal: agent-browser (Vercel skill+CLI) / Playwright MCP (@playwright/mcp) / Figma plugin / security-guidance plugin / serena・codegraph・cloud-run・toolbox・vercel MCP を per-user (scope=user) で入れ、 managed/user の hook・skill も両ユーザーへ deploy する opt-in script を提供し、 再実行で in-place upgrade できる。 (2026-06-08 audit: 実装は当初 Goal より広く、 5 MCP＋hook/skill deploy を既に実施済)

Exit Criteria:
- [x] 実装 + 静的検証 (shellcheck: SC2145/SC2068 は base script の `run()` 由来の repo 規約として既知・許容 / `bash -n` / 全 claude サブコマンド syntax を live 2.1.161 binary で裏とり)、 再実行 upgrade 対応 — commit 38d511f (HEAD は +256/-90 で大幅拡張済)
- [ ] 実機 fresh provisioning で end-to-end 実行確認: (a) skills CLI が `--agent claude-code` を受理し `~/.claude/skills` へ global install / (b) `agent-browser install` の apt-sudo 挙動 (system lib 不足時) / (c) figma・security-guidance plugin の install/update が非対話で通る / (d) playwright が system Chrome を headless 起動 (現状 `@playwright/mcp@latest` 直指定・PW_MCP_VER は撤去済) / (e) serena(uvx)・codegraph(npm)・cloud-run・toolbox・vercel MCP add が全成功
- [ ] 実機確認 (2026-06-05 hook settings 分離): managed hooks drop-in (`/etc/claude-code/managed-settings.d/extensions.json`) と user hooks の `claude_user_settings inject` が root / LOGIN_USER 双方の `~/.claude/settings.json` に反映され、 base-only 機は hook 登録ゼロ (dangling なし) であること

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

Goal: repo 直下 `SKILL-HOOK-CONTRACT.md` を 4 部構成で完成 — (A) event 別 hook 利用カタログ (H.S. の番号フロー形式) / (B) Skills フォーマット規約 / (C) 応用編 = CLAUDE.md→skill/hook 化の概要 (Big Picture) / (D) 実装 contract (技術者向け再利用規約)。 一貫性担保が目的 (2026-05-30 起案・A/B 記入は 2026-06-07 前 session で H.S. が依頼したが court バグでセッション腐敗→リセット、 本 session で再開。 「今 session の新指示」ではない)。

Exit Criteria:
- [x] (D) 実装 contract §0-5 記載 (capability-grant / permission semantics / session-keyed state / transcript current-turn scan / fail-open / deny-wording / extensible dispatch table / use-case 駆動 TTL / PostToolUse sync) — prior session commit 27b498c
- [x] **除外を厳守**: deploy の決まり (`copy_dir`・exec-bit 0755・settings `copy`) は deploy ルールとして除外し contract に混ぜず (doc 末尾「除外」節)
- [x] (C) overview/応用編 (動機/仕組み/狙う効果 3軸表 + 具体例、 commit 91cf0e0)。 固有名は「相手」に汎用化
- [x] event→hook 完全対応表を 3 json から確定 (2026-06-07 本 session、 下記「確定済みファクト」)
- [x] **(A) event 別 hook 利用カタログ** を全 event 分記入 (commit e5e8b19)。 抽出 workflow wdjbl0ux3 + 敵対検証 w8kl0gkmu (1 error + 6 minor 修正反映)
- [x] draft 要修正: SessionEnd N/A 訂正 + `### ConfigChange`→`####` + WorktreeCreate 新設 + 真の N/A 明記。 CwdChanged は本 session で voicevox 配線したため実 use-case 記載
- [x] **(B) Skills フォーマット規約** を「## Skills」に記入 (frontmatter/本文構造/言語規約。 deploy 位置は doc「除外」原則ゆえ割愛)
- [x] draft SessionStart の `xxxx Skill` placeholder を「複数のスキル (verify-before-claim 等)」で充足
- [ ] H.S. レビュー承認 → Exit flip + block 削除。 register は ですます に統一済 (commit 9fe0933、 prose 8 行を である→ですます・番号フロー step は体言止め維持)、 SessionStart step2 の述部欠落も修正済 (commit d56b27c)。 残るは H.S. の最終 review (構成/粒度) のみ。 2026-06-08 本 session で skill 一覧 (全 22 entry に category＋≤2文概要)・全 hook の Related 記入・UserPromptExpansion 節 (probe 結果)・Stop の push_prompting_check 欠落補完・応用節 bridge 文を追記し、 hook 記述を 20-agent workflow で実 source 検証して修正 (stop_checks 重複統合・§0 表 block family 4→6) — これらも H.S. review 対象 (commit 20a4858 / 0cf974c)

確定済みファクト (2026-06-07 本 session・再導出不要):
- **task 定義** (H.S. 前 session 原文趣旨): 「SessionStart の見出しを少し書いた。 こんな感じで repo のフックを記入していってほしい。 Skill はフォーマットを規約として書ける。 CLAUDE.md のスキル&フック化は後半の応用編で概要 (ここのフックでなく Big Picture)」。
- **記入形式** = `#### <event>` 配下に `**use-case 名**` + 番号フロー (2-4 step・体言止め/である・です ます禁止・一人称禁止・実フック名 jargon 可)。 use-case は機能単位グルーピング (例: コンテキスト引き継ぎ = handoff skill + session_resume_context、 event 跨ぎ可)。
- **canonical source** = hook 配線は 3 json: `files/claude_managed-extensions.json`(managed) / `files/claude_user-extensions.json`(user) / `files/claude_managed-voicevox.json`(voicevox)。 hook 実体は managed=`files/claude_managed-hooks/`・user=`files/claude_user-hooks/`・voicevox=`files/voicevox_claude_alerts`。 再導出は 3 json Read で 1 分。
- **完全 event→hook 対応表**:
  - SessionStart: claude-md-lint.sh / feature_findings_build.py / session_resume_context.py
  - SessionEnd: session_cleanup.py (**draft の N/A は誤り**)
  - UserPromptSubmit: handoff_uncommitted_check.py(managed) / memory_surface.py(user・過去事例 surfacer ＋ concern/correction inject) / subagent_gate_suggest.py(user)
  - Stop: stop_checks.py(managed) / push_prompting_check.py(user) / voicevox Stop
  - PreToolUse: read_before_edit.py(check,Read|Edit|MultiEdit) | dangling_ref_check.py+memory_routing_gate.py(guard)+skill_reminder_gate.py(gate)+comment_rationale_gate.py(Edit|Write|MultiEdit) | avoid_cd.py+deny_compound_git_add.py+deny_compound_git_commit.py+check_commit_format.py(Bash) | subagent_gate_warn.py(Task|Agent) | declare_and_proceed_gate.py(AskUserQuestion) | check_commit_author.py(user,Bash)
  - PostToolUse: read_before_edit.py(record,Read|Write) / memory_routing_gate.py(sync,Write) / todos_completion_check.py(Bash)
  - PostToolUseFailure: detect_cwd_pollution.py(Bash)
  - voicevox (`voicevox_claude_alerts <Event>`): Stop / Notification / SubagentStart / SubagentStop / ConfigChange / PreCompact / WorktreeCreate / CwdChanged (本 session 追加)
  - **真の N/A (hook 無し)**: StopFailure / UserPromptExpansion / PermissionRequest / PermissionDenied / PostCompact (CwdChanged は本 session で voicevox 配線済ゆえ N/A から除外)
- **draft 要修正 3 点**: (1) SessionEnd=N/A は誤り、 (2) `### ConfigChange` は h3 で兄弟 (`####`) と不揃い、 (3) **WorktreeCreate セクションが丸ごと欠落** (voicevox 配線あり)。
- **voicevox ConfigChange 裏取り (workflow VERIFIED)**: 現状 ConfigChange branch は payload の種別判定を一切していない (source field 等を読まず無条件で固定句「設定をリロードしたよ。」)。 ∴ 別 todo「source field で発話分岐」は実装余地が実在。
- **編集規律**: doc は H.S. レビュー中 draft だが前 session 指示「記入してほしい」= 私が埋めて可。 document-editor は inline で discipline verbalize して適用 (doc 既読・modest size ゆえ fork でない)。 bare-invoke は dirty file 暴発の前科ありゆえ対象明示必須。 register 等の編集ルール詳細は handoff doc。

Note: doc 本体 (L1〜L4 概観 head + 実装 contract 0〜5 + 除外) 記載・commit 27b498c・SendUserFile 送付済。 目次 = 二つの family → capability-grant → 判定/検出/状態/安全 → 除外、 各項に実フック名の具体例。 **H.S. レビュー待ち** (外出先・後日)。 承認後に Exit flip + block 削除 (body 構成/粒度の直しがあれば反映してから)。 2026-05-31: コード照合 audit (workflow wvsbvz52x、 34 claim 中 30 accurate、 adversarial 確認・誤 flag 1 件棄却) 実施し確定 3 finding を commit eedd808 で反映 — (A) 中核 dichotomy 訂正 (L3 stop_checks の 4 family は exit2 で block、 overview L3 行+段階補足+§0 表)、 (B) §3 synthetic-skip を path 別に (BM25 surfacer `_memory_surface` は非 skip・本 turn live 確認)、 (C) §1/§2 に advisory-allow + content-embedded opt-out token 追記。 **事実精度は audit 済**、 残は H.S. の構成/粒度レビュー。 任意候補: 補足「L3とL4どう違うか」の「指摘する」(現 line 24) も同根で、 H.S. が望めば「介入する」系へ。 follow-up (doc外・コード): `_memory_surface` が synthetic prompt を surface する挙動の許容可否。 2026-06-01〜02: H.S. live レビューで overview を全面改稿 (歴史先行 CLAUDE.md→skill→hook / L1-L4 jargon 撤去 / 一人称除去 / です・ます / 表 A-D 化+俳句 / capability-grant をフロー番号リスト化 / 事実確認) + ファイル名 `_`→`-` リネーム (commit 025a3c6・14cf6d0)。 **レビュー継続中** — 次 session も H.S. の追加指摘を反映。 確立した編集ルールは handoff doc 参照。

Work file: handoff = `last-session-handoff.md` の「SKILL-HOOK-CONTRACT.md パターン集」 section ＋ plan `~/.claude/plans/breezy-bubbling-quiche.md` の「並行 deliverable」節

### KNOWN_POSSIBLE 表の自動拡張

Goal: `stop_checks.py` の `KNOWN_POSSIBLE` (既知で可能な op × 既知 method hint 表) は手で 1 行ずつ追加する設計だが、 「実は可能」 が判明する度に user memory entry も書かれるので、 memory entry から KNOWN_POSSIBLE への追記を semi-automated にする余地を検討する。 ※2026-06-08 audit 訂正: 当初想定の `feedback_*_can_*.md` 命名規約は**存在しない** (47 entry 中 0)。 machine-detectable な signal は entry の `reminder:` 行の 可能/不可断定 phrasing。 現状 KNOWN_POSSIBLE は 2 行 (partial-stage / autosquash) で両方とも既に配線済・未配線の「可能」候補は 0 ゆえ ROI は現時点ほぼ無し (手追加の痛みが再発したら着手で可)。

Exit Criteria:
- [ ] 設計: memory entry の命名規約や frontmatter で「KNOWN_POSSIBLE 候補」 を mark する仕組みを置くか、 hook が memory dir を scan して候補を列挙し人 review するか、 設計 trade-off を verbalize
- [ ] 実装方針が決まれば実装 + smoke + deploy

Work file: `files/claude_managed-hooks/stop_checks.py` の `KNOWN_POSSIBLE` 表 + `~/.claude/memory/feedback_partial_stage_foreign_changes.md` 等の既存 sibling entries

### document-editor の bare-invoke 暴発対策

Goal: forked execution の `document-editor` skill が対象ファイル無指定で呼ばれた時、 git working tree の dirty file を勝手に編集対象化して未コミット作業を破壊する挙動を塞ぐ。

Exit Criteria:
- [ ] SKILL.md の fork 起動部を読み、 「無指定時に dirty file を対象化」 の出所を特定 (skill 本文の指示か fork agent の自律判断か)
- [ ] 対策方針を決定 (要相談): (a) skill 本文に「対象が args/会話で明示されていなければ編集せず問い返す」 を明記 / (b) skill は据置し呼び出し側規律 (下記 memory entry) のみで運用
- [ ] 採択方針を実装 → source↔deploy 同期 → 再 deploy 時に反映確認

経緯: 2026-06-06 README 更新 session で実害発生。 README 編集の規律を借りるつもりで `document-editor` を引数なし invoke → fork が `M` だった `SKILL-HOOK-CONTRACT.md` (H.S. のレビュー中 draft、 触らない指示済) を勝手に整理し作業途中スカフォールドを削除。 fork の単一 Edit を transcript から byte 逆適用して復旧済。 cross-project の behavioral 記録は `~/.claude/memory/feedback_document_editor_fork_overwrite.md`。

Work file: `files/claude_managed-skills/document-editor/SKILL.md`

### voicevox_claude_alerts: CwdChanged 発話 + ConfigChange の種別分岐

Goal: voicevox 通知を 2 点拡充 — (a) `CwdChanged` event で cwd 変化を発話、 (b) `ConfigChange` を payload 種別で発話文言を分岐 (現状は固定句「設定をリロードしたよ。」で種別無視)。

Exit Criteria:
- [x] CwdChanged: `HOOK_EVENTS` + `case` + `EVENT_PHRASES` + json wiring 追加・30s marker throttle・bg silent (commit 22ce4fd)。 cwd は H.S. 指定で Haiku カタカナ読み (専用 `speak_cwd`、 path→読みを STATE_DIR に cache し再訪で Haiku 省略)
- [x] ConfigChange: `source` field 実在を**公式 hooks reference で確認** (payload に `"source"` あり・値 user/project/local/policy_settings + skills の 5 種) → source 別に発話分岐、 未知 source は既定句 fallback
- [x] no-audio smoke (voicevox_paplay/claude を stub・隔離 XDG dir) で 全 5 source 分岐 + 未知 fallback + CwdChanged の Haiku→cache HIT を spoken.log で確認
- [x] source↔deploy sync 済 (`sudo install`: script→`/usr/local/bin/voicevox_claude_alerts` 0755、 json→`/etc/claude-code/managed-settings.d/voicevox.json`、 両 `diff -q` 一致)
- [ ] 実機で実 event 発火 + 音声を H.S. が確認 (deploy 済み LIVE だが stub smoke のみで live audio 未観測。 audio 経路自体は既存 7 event と同一の proven path)

経緯: 2026-06-07 H.S. が SKILL-HOOK-CONTRACT.md 作業中に脱線提起 → 本 session で実装。 CwdChanged は v2.1.83 の実 event。 **ConfigChange の `source` field は findings.md に無かったが公式 hooks reference で実在確認** (入力例 `"source":"project_settings"`、 verify-before-claim 充足)。 CwdChanged 読み上げ文面は H.S. 指定「作業ディレクトリが変わりました。スラッシュ ホーム …」。 編集は拡張子なし script ゆえ declare bash + writing-bash/code invoke 経由。

Work file: `files/voicevox_claude_alerts` + `files/claude_managed-voicevox.json`

### skill_reminder_gate: PreToolUse:Skill で発火検出を state 化 (transcript-scan 簡素化)

Goal: `skill_reminder_gate` の skill 発火検出を、 現在の transcript 末尾 scan から `PreToolUse(matcher:"Skill")` hook による state 刻印方式へ移行できるか検討し、 移行すれば fragile な turn-boundary 判定群を削減する。

Exit Criteria:
- [ ] `PreToolUse(matcher:"Skill")` で model 自己 invoke を skill 名付きで捕捉し `(sid, skill, ts)` を session state に刻印する record arm を実装 (gate arm はその state を読む)
- [ ] 移行 trade-off を verbalize: 現 transcript-scan (実機 verified・smoke 51/51) の維持コスト vs state 方式の利得 (turn-boundary/isMeta/5分窓ロジック削減) と新リスク (state 永続化・PreToolUse 発火順・edit が skill invoke と同 batch のとき record が gate より先に走るか) → 移行 or 据置を決定
- [ ] 移行する場合: smoke (model invoke → record → 同 turn edit allow / skill 無し → deny / fail-open) + deploy。 据置なら本 block を理由付きで close

経緯: 2026-06-08 UPE 調査の副産物 (probe 実機確認)。 UserPromptExpansion は user-typed slash command 展開でのみ発火し model 自己 invoke では鳴らない (→ UPE は skill_reminder_gate 代替に使えない) 一方、 PreToolUse は `tool_name:"Skill"` / `tool_input.skill` 付きで model 自己 invoke を直接捕捉すると判明 (先の claude-code-guide subagent「PreToolUse は Skill を intercept 不可」は実機で誤りと確認)。 現 gate は transcript 末尾を後方読みして Skill block を探す (docstring 56-66 行が turn-boundary 判定を load-bearing と明記) が、 PreToolUse:Skill なら検出を event 化でき fragile ロジックを削れる可能性。

Work file: `files/claude_managed-hooks/skill_reminder_gate.py` (SKILL-HOOK-CONTRACT.md の UserPromptExpansion 節は本 session で "user-typed のみ発火" を記載済 — commit 20a4858)

### hooks in skills へ移行可能な hook の洗い出し

Goal: Claude Code の「hooks in skills」(v2.1.0+、 特定 skill 限定の hook を settings.json でなく SKILL.md frontmatter に書ける機能) に移せる既存 hook があるか洗い出す。

Exit Criteria:
- [ ] feature 仕様確認: SKILL.md frontmatter の hook 書式・発火条件 (skill ロード中のみ発火)・scope を公式 hooks reference / findings.md (v2.1.0「hooks support for skill frontmatter」・v2.1.152 `reloadSkills`) で確定
- [ ] 既存 hook (3 json の managed + user) を「特定 1 skill 専属 かつ その skill ロード済を前提に成立するか」で判定。 **skill ロード自体を目的とする gate (skill_reminder_gate / declare_and_proceed_gate / memory_routing_gate guard) は対象外** (skill 未ロードでは hook も不発火 = chicken-and-egg、 H.S. 指摘)。 候補を列挙 (ゼロも可)
- [ ] 候補ごと移行 trade-off (settings.json 集中管理から外れる影響・常時発火要否・deploy 経路変更) を verbalize → 移行 or 据置を決定

経緯: 2026-06-07 H.S. 提起。 feature 実在は findings.md (v2.1.0「Added hooks support for skill and slash command frontmatter」) で確認済。

Work file: 3 json (`files/claude_managed-extensions.json` / `claude_user-extensions.json` / `claude_managed-voicevox.json`) + `SKILL-HOOK-CONTRACT.md` (hook カタログ・移行時に更新)
