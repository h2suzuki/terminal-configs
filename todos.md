# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)


## Critical

## High

## Medium

### Handoff 強化 + 言語 lint 機構の deploy と実運用確認

Goal: wind-down open-task 機構 (inject + block)・handoff cross-check step・session_resume_context pointer 化・claude_lang_lint を deploy し、実運用での駆動を確認する。

Exit Criteria:
- [x] 追補 deploy (hooks 3 本 0755 / handoff・codex-delegation skill / crosscheck-prompt.md / /usr/local/bin/claude_lang_lint) を canonical と `diff -q` 一致で検証 — 2026-08-06 ユーザー実行、7/7 identical・exec bit 確認・deployed claude_lang_lint --selftest OK (PATH 解決込み)
- [ ] 実 session で open Task を残した wind-down に inject + block が発火し、todos.md 転記 + close で通過することを確認 (opportunistic) — 2026-08-07 **inject は実 session で live 発火を観測** (ユーザーの「セッションは終わります」prompt に対し UserPromptSubmit で open Task 1 件を列挙、clean tree ゆえ未コミット節は出ず = 偽陽性修正も live 確認)。block 側は下記 shadow 欠陥を修正済 (40f89e8)。deploy 完了・canonical と diff 一致を確認済 (2026-08-07 ユーザー実行) で、deployed 版が実 transcript から人間 prompt を復元し harness entry 14 件を skip することも確認。残るは **live block**。2026-08-08 に不発の原因を特定: `_last_prompt_text` の修正だけでは不足で、`stop_checks._run` が読む `_load_tail(transcript, turns=2)` の **turn 区切り自体が harness entry を 1 turn と数える**ため、直近 2 turn が harness entry だけになると窓内に人間 prompt がゼロになり判定が空振りする (実測: tail 52 entry 中 prompt-like 2 件が両方 harness、`_last_prompt_text(tail)` が空文字 → deployed hook を実 payload で走らせて exit 0)。案 (b) (wind-down 判定だけ空振り時に窓を広げて再取得) を codex へ発注し 75de34b で取り込んだが、**まだ発火しない**。2026-08-08 に更に 2 段目の原因を実測:
  - `_load_tail` は末尾 `_TAIL_BUFSIZE` (128KB) しか読まないため、`turns` を 8/20/60 と広げても同じ切り詰め view しか返らない (本 session の transcript は 2057KB)。窓を turn 数で広げる設計そのものが長 session で効かない
  - その切り詰め view 内で `_last_prompt_text` が拾う「最新の人間 prompt」は実は `<system-reminder>` entry。**system-reminder は harness 生成なのに roster 未収載** — 40f89e8 の roster に第 4 形式として足す必要がある
  - ∴ 次の設計: wind-down 判定専用に transcript を後方 seek し、読み取り総量を定数で有界 (目安 4MB) にしつつ最新の人間 prompt を 1 件見つける経路を足す。併せて `HARNESS_ENTRY_RE` に `<system-reminder>` を第 4 形式として追加。発注書は `drafts/tail-seek-order.md` に完成済 (次 session はこれをそのまま使える)
  - **未決 (要ユーザー判断)**: この発注を codex へ出した際、subagent framework が **Self Modification のセキュリティ警告**を出した (「自分を監督する hook の検出ロジックを、transcript に見えないユーザー指示でなく drafts/ORDER.md 起点で緩める変更」との判定)。実際の変更方向は block が「今より発火する」側で監督を強める向きだが、guardrail 改変にあたるためユーザー承認を得てから再発注する。なお `luna` は ChatGPT アカウント非対応で起動不可 (ユーザー指定の代替は `sol` / effort xhigh)
- [x] handoff 実施 session で cross-check readback (fresh subagent) が blocking questions を出し、handoff 更新で収束することを確認 — 2026-08-07 実施。fresh subagent 3 round: R1 が blocking 3 件 (cross-check criterion 対応の action 欠落 / codex 認証の主体不明 / todos.md の「deploy 待ち」stale) → 全て doc 修正で解消、R2 が新規 3 件 (staged 発火の可否 / 不収束時の閉じ方 / repo から辿れない companion コマンド) → 同じく解消、R3 は Verdict yes で残 4 件はいずれも「着手を妨げない運用細部」。R3 の指摘も doc へ反映済 (運用順序の節)
- [x] 中断 session (marker 無し ∧ open Task 残) の pointer 注入を実機で 1 回観測 — 2026-08-07 意図的再現。deployed `/etc/claude-code/hooks/session_resume_context.py` (canonical と diff 一致) に startup payload を stdin 投入し、fixture HOME の marker 無し ∧ open Task 残 session で pointer 注入を確認。負 control 3 本 (marker あり / Task closed / source=resume) は全て沈黙
- [x] codex 委譲 1 回で「出力言語規約」節 + claude_lang_lint を実運用し、検出またはクリーン通過の実績を得る — 2026-08-08 実施 (ユーザーが `codex login` 済)。tail 窓修正を隔離 worktree へ発注 (発注書に「出力言語規約」節あり)、60 行の diff を受領し ruff / ty / unittest を発注側で再実行して確認、75de34b で取り込み。`claude_lang_lint --repo <worktree>` は **NG: 88 CJK addition を検出**したが、全て `ORDER.md` / `report.md` (発注書と codex の報告書) で納品物 `stop_checks.py` は無傷 = **workflow 由来の偽陽性**
  - 得た運用知見: 発注書と報告書を worktree 直下に置くと lang_lint の scan 対象に入り、納品物の判定を埋める。codex-delegation skill の「発注は作業 dir の drafts/ に置く」に従えば回避できた (今回はこれを外して worktree 直下 `ORDER.md` にしたのが原因)
- 2026-08-07 に修正・deploy 済の 2 欠陥:
  - wind-down block の shadow (40f89e8): harness が user role・str content で差し込む entry (Stop hook feedback / skill 再 invoke 通知 / slash command block) が最新 prompt として読まれ、`open-tasks-at-wind-down` が静かに無効化されていた。実 transcript で skill 通知 1 件による block 不発を再現
  - 未コミット節の偽陽性 (ac295f4 + 3 重化 763a412): sandbox が書き込み禁止 path へ被せる mask stub は character device (22/22 実測) で、git は untracked として正しく報告する。**path roster (実測 22 件) ∧ 非 regular/dir/symlink ∧ size 0** の 3 条件 AND でのみ落とす。roster 未収載の stub は従来通り報告 (取りこぼしは偽陽性で済み、実 file を落とさない側に倒す)。実在しない path (削除) は残す
- 既知 finding (本 session 発見・未修正・低 pri): `stop_checks.WorktreeCleanupTest.test_non_repo_fails_open_with_diagnostic` は git の stderr が 1 行である前提。temp dir が repo と別 filesystem だと git が `Stopping at filesystem boundary` を足して 2 行になり fail する (HEAD 8bf7291 でも再現 = 本 session の変更と無関係)

- [ ] `skill_reminder_gate` を拡張し、codex-companion を叩く Bash を codex-delegation skill が active でない限り止める — 2026-08-08 に発注〜監視ターンで同 skill を invoke せず、既存規約 (running[]-empty monitor 禁止) を再違反した。CLAUDE.md「ルール違反 = 即 countermeasure」に基づく機構化
- 環境 finding (2026-08-08 実測・要 root): memory index DB (`/var/lib/claude-rag-memory/memory_index.sqlite3`) が `nobody:nogroup 664` で uid scorer から書けず (`os.access(W_OK)` False)、この user の memory entry は **index に永久に載らない**。`memory_routing_gate.py` の sync は `--upsert` を stdout/stderr とも DEVNULL・`check=False` で呼び、`_upsert_entry` も sqlite エラーを握り潰すため**失敗が完全に不可視**。dir が 0777 ゆえ `-wal`/`-shm` は作れて健全に見える。結果 `--search` は root 由来の 13 件しか返さず、その中に skill と矛盾する reminder (「running[] が空になったら」) が現役で残る

Work file: `last-session-handoff.md` の同名 section

### court バグ guard (command + stop_checks/skill 配線)

Goal: stray token (court/count/câu… と揺れる) + 行頭 invoke-leak を厳密パターンで捕捉し、court バグ汚染 (#76912 / #64108) を早期検知する。

Exit Criteria:
- [x] 検出方式を実データで確定 — 888 transcript 走査で 2 signature を FP ゼロ検証: stray-token 単独行 `(?m)^[ \t]*(court|count)[ \t]*$` / 行頭 invoke-leak `(?m)^[ \t]*<invoke name="`。token 固定でなく leaked XML を token 非依存で捕捉するのが要 (実バグ例 "câu")
- [x] 実装 + test + commit — 02e3054 (command `files/claude_court_guard` 7 tests / stop_checks warning-only 55 tests / /my-tasks 自己チェック / 両 .sh に copy 行、独立再実行 OK)
- [x] deploy 完了・配置検証 — 2026-07-13 ユーザー実行、`/usr/local/bin/claude_court_guard` PATH 動作・hooks/ 一致を確認
- [ ] 実運用で court 汚染の live 検出を確認 (opportunistic)
- 既知 finding (低 pri): stop_checks の court チェックは生 `text` 対象で、fence 内に court パターンを書く session は理論上 FP。`stripped` 化は要検討 (実 corpus では 0 FP)

### SKILL-HOOK-CONTRACT.md パターン集

Goal: repo 直下 `SKILL-HOOK-CONTRACT.md` を 4 部構成で完成 — (A) event 別 hook 利用カタログ (ユーザーの番号フロー形式) / (B) Skills フォーマット規約 / (C) 応用編 = CLAUDE.md→skill/hook 化の概要 (Big Picture) / (D) 実装 contract (技術者向け再利用規約)。 一貫性担保が目的 (2026-05-30 起案・A/B 記入は 2026-06-07 前 session で ユーザーが依頼したが court バグでセッション腐敗→リセット、 本 session で再開。 「今 session の新指示」ではない)。

Exit Criteria:
- [x] (D) 実装 contract §0-5 記載 (capability-grant / permission semantics / session-keyed state / transcript current-turn scan / fail-open / deny-wording / extensible dispatch table / use-case 駆動 TTL / PostToolUse sync) — prior session commit 27b498c
- [x] **除外を厳守**: deploy の決まり (`copy_dir`・exec-bit 0755・settings `copy`) は deploy ルールとして除外し contract に混ぜず (doc 末尾「除外」節)
- [x] (C) overview/応用編 (動機/仕組み/狙う効果 3軸表 + 具体例、 commit 91cf0e0)。 固有名は「相手」に汎用化
- [x] event→hook 完全対応表を 3 json から確定 (2026-06-07 本 session、 下記「確定済みファクト」)
- [x] **(A) event 別 hook 利用カタログ** を全 event 分記入 (commit e5e8b19)。 抽出 workflow wdjbl0ux3 + 敵対検証 w8kl0gkmu (1 error + 6 minor 修正反映)
- [x] draft 要修正: SessionEnd N/A 訂正 + `### ConfigChange`→`####` + WorktreeCreate 新設 + 真の N/A 明記。 CwdChanged は本 session で voicevox 配線したため実 use-case 記載
- [x] **(B) Skills フォーマット規約** を「## Skills」に記入 (frontmatter/本文構造/言語規約。 deploy 位置は doc「除外」原則ゆえ割愛)
- [x] draft SessionStart の `xxxx Skill` placeholder を「複数のスキル (verify-before-claim 等)」で充足
- [x] **`deny_unsafe_git_reset` を PreToolUse:Bash catalog に追記** (2026-06-08 完了): PreToolUse 節に新 use-case「破壊的 reset / restore の advise-once 防止」を番号フロー + Related で追加 (L334-340)。 全 24 hook 再 gap 監査で MISSING 0 達成。 entry 自体の構成は ユーザーの doc 全体 review 対象
- [ ] ユーザーレビュー承認 → Exit flip + block 削除。 register は ですます に統一済 (commit 9fe0933、 prose 8 行を である→ですます・番号フロー step は体言止め維持)、 SessionStart step2 の述部欠落も修正済 (commit d56b27c)。 残るは ユーザーの最終 review (構成/粒度) のみ。 2026-06-08 本 session で skill 一覧 (全 22 entry に category＋≤2文概要)・全 hook の Related 記入・UserPromptExpansion 節 (probe 結果)・Stop の check_push_prompting 欠落補完・応用節 bridge 文を追記し、 hook 記述を 20-agent workflow で実 source 検証して修正 (stop_checks 重複統合・§0 表 block family 4→6) — これらも ユーザー review 対象 (commit 20a4858 / 0cf974c)。 **追従済** (commit ae2a3de): 2ca11ff の broad/pathless add deny (`-A`/`.`/`-u`/pathless) を PreToolUse:Bash catalog へ反映 — 新 use-case「広域 git add の cross-session 巻き込み防止」block 追加 + 「commit 規律」step1 に forward pointer。 3-lens 敵対 workflow (wpivtp9py) で hook source を逐語検証 (medium 1 = compound-only 誤読の forward pointer 反映)。 ユーザー review 対象に含む

確定済みファクト (2026-06-07 本 session・再導出不要):
- **task 定義** (ユーザーの前 session 原文趣旨): 「SessionStart の見出しを少し書いた。 こんな感じで repo のフックを記入していってほしい。 Skill はフォーマットを規約として書ける。 CLAUDE.md のスキル&フック化は後半の応用編で概要 (ここのフックでなく Big Picture)」。
- **記入形式** = `#### <event>` 配下に `**use-case 名**` + 番号フロー (2-4 step・体言止め/である・です ます禁止・一人称禁止・実フック名 jargon 可)。 use-case は機能単位グルーピング (例: コンテキスト引き継ぎ = handoff skill + session_resume_context、 event 跨ぎ可)。
- **canonical source** = hook 配線は 3 json: `files/claude_managed-extensions.json`(managed) / `files/claude_user-extensions.json`(user) / `files/claude_managed-voicevox.json`(voicevox)。 hook 実体は managed=`files/claude_managed-hooks/`・user=`files/claude_user-hooks/`・voicevox=`files/voicevox_claude_alerts`。 再導出は 3 json Read で 1 分。
- **完全 event→hook 対応表**:
  - SessionStart: claude-md-lint.sh / feature_findings_build.py / session_resume_context.py
  - SessionEnd: session_cleanup.py (**draft の N/A は誤り**)
  - UserPromptSubmit: check_uncommitted_at_handoff.py(managed) / memory_surface.py(user・過去事例 surfacer ＋ concern/correction inject) / subagent_gate_suggest.py(user)
  - Stop: stop_checks.py(managed) / check_push_prompting.py(user) / voicevox Stop
  - PreToolUse: read_before_edit.py(check,Read|Edit|MultiEdit) | check_dangling_refs.py+memory_routing_gate.py(guard)+skill_reminder_gate.py(gate)+comment_rationale_gate.py(Edit|Write|MultiEdit) | avoid_cd.py+deny_compound_git_add.py+deny_compound_git_commit.py+check_commit_format.py+deny_unsafe_git_reset.py(Bash) | subagent_gate_warn.py(Task|Agent) | declare_and_proceed_gate.py(AskUserQuestion) | check_push_prompting.py(user,AskUserQuestion) | check_commit_author.py(user,Bash)
  - PostToolUse: read_before_edit.py(record,Read|Write|Edit|MultiEdit) / memory_routing_gate.py(sync,Write) / check_todo_completion.py(Bash)
  - PostToolUseFailure: detect_cwd_pollution.py(Bash)
  - voicevox (`voicevox_claude_alerts <Event>`): Stop / Notification / SubagentStart / SubagentStop / ConfigChange / PreCompact / WorktreeCreate / CwdChanged (本 session 追加)
  - **真の N/A (hook 無し)**: StopFailure / UserPromptExpansion / PermissionRequest / PermissionDenied / PostCompact (CwdChanged は本 session で voicevox 配線済ゆえ N/A から除外)
- **draft 要修正 3 点**: (1) SessionEnd=N/A は誤り、 (2) `### ConfigChange` は h3 で兄弟 (`####`) と不揃い、 (3) **WorktreeCreate セクションが丸ごと欠落** (voicevox 配線あり)。
- **voicevox ConfigChange 裏取り (workflow VERIFIED)**: 現状 ConfigChange branch は payload の種別判定を一切していない (source field 等を読まず無条件で固定句「設定をリロードしたよ。」)。 ∴ 別 todo「source field で発話分岐」は実装余地が実在。
- **編集規律**: doc は ユーザーレビュー中 draft だが前 session 指示「記入してほしい」= 私が埋めて可。 document-editor は inline で discipline verbalize して適用 (doc 既読・modest size ゆえ fork でない)。 bare-invoke は dirty file 暴発の前科ありゆえ対象明示必須。 register 等の編集ルール詳細は handoff doc に置いていたが、 当該 section は消失 (2026-08-07 確認) — 再開時は doc 本文と git log から再導出する。

Note: doc 本体 (L1〜L4 概観 head + 実装 contract 0〜5 + 除外) 記載・commit 27b498c・SendUserFile 送付済。 目次 = 二つの family → capability-grant → 判定/検出/状態/安全 → 除外、 各項に実フック名の具体例。 **ユーザーレビュー待ち** (外出先・後日)。 承認後に Exit flip + block 削除 (body 構成/粒度の直しがあれば反映してから)。 2026-05-31: コード照合 audit (workflow wvsbvz52x、 34 claim 中 30 accurate、 adversarial 確認・誤 flag 1 件棄却) 実施し確定 3 finding を commit eedd808 で反映 — (A) 中核 dichotomy 訂正 (L3 stop_checks の 4 family は exit2 で block、 overview L3 行+段階補足+§0 表)、 (B) §3 synthetic-skip を path 別に (BM25 surfacer `_memory_surface` は非 skip・本 turn live 確認)、 (C) §1/§2 に advisory-allow + content-embedded opt-out token 追記。 **事実精度は audit 済**、 残は ユーザーの構成/粒度レビュー。 任意候補: 補足「L3とL4どう違うか」の「指摘する」(現 line 24) も同根で、 ユーザーが望めば「介入する」系へ。 follow-up (doc外・コード): `_memory_surface` が synthetic prompt を surface する挙動の許容可否。 2026-06-01〜02: ユーザー live レビューで overview を全面改稿 (歴史先行 CLAUDE.md→skill→hook / L1-L4 jargon 撤去 / 一人称除去 / です・ます / 表 A-D 化+俳句 / capability-grant をフロー番号リスト化 / 事実確認) + ファイル名 `_`→`-` リネーム (commit 025a3c6・14cf6d0)。 **レビュー継続中** — 次 session も ユーザーの追加指摘を反映。

Work file: なし (handoff / plan file とも消失を 2026-08-07 確認。 再開に要る事実は上の「確定済みファクト」と Note に inline 済)
