# Todos

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108


## Critical

## High

## Medium

### codex write 委譲の worktree 隔離 gate

Goal: `codex-companion.mjs task --write` を主 checkout で起動したら deny する PreToolUse hook を入れ、共有ツリーへの委譲で並行セッションの変更が混在する事故を防ぐ。

Exit Criteria:
- [x] 判定方法を実測で確定 — `git rev-parse --absolute-git-dir` と `--git-common-dir` を abspath 正規化して比較し、異なれば linked worktree。当初は「`--absolute-git-dir` の親ディレクトリ名が `worktrees`」で確定したが、top directory 名が literal `worktrees` の主 checkout を誤判定するためレビューを経て比較方式へ変更 (2026-07-22)
- [x] 発注書作成 — `drafts/codex-worktree-gate-order.md`
- [x] hook 実装 + 登録 + test — commit f03c3b6 (`files/claude_managed-hooks/codex_worktree_gate.py` 796 行 + `claude_managed-extensions.json` 登録 1 行、index mode 100755)。codex 3 round + sonnet 手直し 1 round + opus 3 回のレビュー。**受け入れ時に司令塔が 14 payload を自ら実行し全件期待通り**を確認 (主 checkout の `task --write` deny / linked worktree allow / 多段 segment / `cd` 追跡 / subshell 継承 / 相対 `--cwd` / 改行と CRLF の segment 境界 / escape hatch の segment スコープ / read-only allow)。in-file unittest 39 件 green、ruff・ty exit 0。mutation は 15 種中 13 kill で、生存 2 件は git 失敗時の診断文言のみ (どちらの変異でも決定は fail-open のまま不変)
- [x] 起動 cwd 判定の全面修正 — commit 0c66d25、2026-07-23 deploy 済 (canonical と `diff` 一致・mode 755)。**当初「`segment[1] == "--"` を採るだけの穴 1 個」と記録していたが、H.S. の「payload cwd では不十分なのか」という問いを起点に検分したところ、deploy 済み hook が 6 形を素通りさせていた**: `#` コメントが以降を全消去 / symlink 経由の主 checkout を linked worktree と誤判定 / 引数の `$( )` で起動 segment を破棄 / backtick で write flag 検出漏れ / `{ cd ...; }` 等の shell keyword 前置で cd 未追跡 / 行継続で起動が分断。敵対レビュー 3 巡 (12 + 14 + 2 件、いずれも独立反証を生存) を全件修正し、tokenizer が quote 情報を保持する形へ作り替え、`cd` は option と `$HOME` / `~` を解し、`--cwd` は実 CLI と同じ last-wins + 展開 + 解決不能時 fallback にした。確定できない cwd は追跡 cwd へ落とし、失敗 token を名指しする診断を出す。test 39 → 68 件、**受け入れ時に司令塔が 35 payload を自ら実行し全件期待通り**。deploy 後の live 発火も確認 (直接 `task --write` と、以前は無言 allow だった `--log=$(date +%s).log` 前置き形の双方が deny、read-only `status` は 2 形とも allow)
- [x] 網羅の打ち切り基準を明文化 — 3 巡とも新しい抜け道が出たため、任意 bash の静的解析で網羅を目指すのは終わらないと判断。**脅威モデルを docstring に明記**した (commit gate 系と同じ基準: 防ぐのは発注側自身の不注意であって agent による意図的 bypass ではない)。静的に解けない形 (変数展開・コマンド置換・`cd -`・`popd`・裸 `pushd`・`&` と pipeline の subshell 内 cd・条件付き非実行・`bash -c` / `eval`・`$'...'` 内 escape) は caveat に列挙し、確実に判定させたいときは `--cwd <絶対 path>` を使うと明記。次 session が同じ探索を再開しないための境界線
- [x] 発注経路を機械で固定する — commit 1d4d813、2026-07-23 deploy 済 (canonical と `diff` 一致・mode 755)。`task` と `task-worker` を本 session の Bash (payload に `agent_id` が無い) から起動したら deny し `codex:codex-rescue` 経由を指示する。`status` / `cancel` / `result` は本 session から許可を維持 (`codex-cli-runtime` skill が rescue から呼ぶなと規定)。`task-resume-candidate` は `/codex:rescue` が本 session から呼ぶ設計ゆえ対象外。`task-worker` を含めたのは保存済み write task を再実行するため。判定根拠は公式 doc (`agent_id` は subagent 呼び出しのときだけ payload に入る) で、この依存と壊れる条件を docstring に明記。opus 3 lens レビューで 5 件確定 (実質 3 項目) を全て修正 — **escape hatch 2 つが `segment[0]` しか見ておらず併用がどの順序でも不成立、かつ既存 tree hatch 利用者に後方非互換**だった点と、**codex が既存 test を通る形に書き換えて判別力を失わせていた**点 (検証 cwd を linked worktree へ移し `task` を `review` に置換) を含む。test 68 → 77 件、**受け入れ時に司令塔が 26 payload を自ら実行し全件期待通り**。deploy 後の live 発火も確認 (`task --write` と `task-worker` が route deny、`status` allow、`CODEX_ROUTE_OK=1` で経路だけ外れ tree deny が残る)
- [ ] 変数展開でコマンド名を隠す形が両規則を素通りする件の扱いを決める — 2026-07-23 の live 検証中に**司令塔が probe を短く書こうとして自ら踏んだ**: 直前の Bash 呼び出しで `CC="node .../codex-companion.mjs"` と代入し `$CC task --write` を実行したところ route/tree 両方を素通りし、主 checkout で write task が実起動した (即 cancel、ツリーへの変更なし)。docstring の caveat に列挙済みの既知の限界だが、**敵対的意図なく単に短く書いただけで踏んだ**ため「発注側自身の不注意を防ぐ」という脅威モデルの射程内に入る。変数代入が別の Bash 呼び出しにあると hook からは原理的に見えないため静的解決は不能。検討した 4 案のうち **(d) を採用し (a) を併存**させると 2026-07-23 に決定 (caveat はそのまま維持)。(a) 現状維持のみ = 塞がらない。(b) `node`/`npx` + 引数 `task` の advisory 警告 = 今日の実測 (advisory 8 回・78 回とも読み飛ばし) が効果を反証、deny 化は `node build.js task` 等を巻き込み false deny 面積が大きい。(c) 起動 helper で素の `node` 起動を減らす = 動機は減るが能力は残り、4 箇所 (実行ファイル + `.sh` 2 本の copy 行 + excludedCommands) の追加コスト。命名と excludedCommands 登録は設計判断を含むため (d) 実装後に独立評価する
- [ ] (d) codex job 状態による事後検知を実装する — コマンド文字列の静的解析をやめ、companion の `status --json` が返す各 job の `workspaceRoot` を読む。**綴りに依存しない**ため変数展開・コマンド置換・`env -C` 等を一括で迂回できる。主 checkout を `workspaceRoot` に持つ task を検知したら鳴らす。予防でなく事後検知だが、この事故の害は「長時間かけて共有ツリーへ変更が溜まる」ことなので turn 単位の検知で実害はほぼ防げる (2026-07-23 の実事故も起動 26 秒後に気づき cancel、ツリー変更ゼロ)。配線先は PostToolUse か Stop (`stop_checks.py` への分岐追加を含めて検討)
- [x] 委譲用 worktree `<repo>/.claude/worktrees/codex-gate` を削除 — 2026-07-22 に `git worktree remove --force` + `prune` 実行、`worktree list` が主 checkout のみ・`.claude/worktrees/` が空であることを確認
- [x] 委譲時の worktree の作り方を確定 — `Agent` の `isolation: "worktree"` は**使わない**。harness が agent 終了時に unchanged な worktree を自動削除するため、agent より長生きする codex の作業ツリーが走行中に消える (2026-07-21 実測: codex が「requested worktree does not exist / filesystem is read-only」で何も書けずに完了)。発注側が `git worktree add --detach` で作り、codex の `--cwd` に渡す。`--background` を付けなければ同期実行なので Bash job の終了が真の完了シグナルになる
- [x] deploy 反映 — 2026-07-22 H.S. 実行。deploy 先 3 file が canonical と `diff` 一致、hook は mode 755、`extensions.json:28` に登録を確認。**PreToolUse チェーン経由の live 発火も確認**: 共有 checkout から `node .../codex-companion.mjs task --write` を実行して deny を取得 (セッション再起動を待たず反映)。`/etc/claude-code/` は root 所有かつ `no_new_privs` で sudo 不可のため deploy は H.S. 実行が必要。`copy_dir claude_managed-hooks/` が dir 丸ごと配るので per-file の copy 行は不要

Work file: `drafts/codex-worktree-gate-order.md`

### commit gate の射程: 非敵対的な commit 生成経路のカバー

Goal: `git commit` 文字列を含まないが実際に commit を作る経路のうち、迂回意図なく普通に踏むものを gate 対象に加える。敵対的回避経路は対象外とする。

脅威モデル (2026-07-21 調査で確定・再導出不要): 4 hook (`deny_compound_git_commit.py` / `check_commit_format.py` / `check_commit_author.py` / `deny_compound_git_add.py`) は「文字列に `git` と `commit` がこの順で現れる」regex 検出で、shell 文法パーサではない。射程限定は `skill_reminder_gate.py:17-26` docstring と `git_corpus_cases.py` の既知ケース群で明示済みの設計判断。gate の目的は自分の commit の品質担保であり、迂回主体は agent 自身ゆえ**敵対的 bypass は脅威に数えない**。

- covered: `git commit` 単独形 / `-a`・`-i`・pathless (deny) / compound (deny) / `git -C`・`git -c`・先頭 env 代入 / `-F`・stdin
- **対象とする穴** (非敵対・実害あり): `merge` / `cherry-pick` / `revert` / `rebase --continue` / `am` / `stash push` / `gh pr merge` / `gh api .*/git/commits`
- **対象としない穴** (敵対的回避のみ): `bash -c` / heredoc / `eval` / Python・Node subprocess / shell alias。再帰的 quote パーサという機構を足す費用に見合わない

Exit Criteria:
- [ ] `commit-tree` の記述と挙動の食い違いを訂正 — docstring は「射程外」と書くが `\bcommit\b` が `commit-tree` 内に一致して実際は deny される。`-- <token>` 1 つで外れる偶然の防御であり、docstring か実装のどちらを正とするか決めて揃える
- [ ] 非敵対経路のうち author / format チェックを適用すべきものを確定し実装
- [ ] test 追加 (`git_corpus_cases.py` の既知ケースから昇格) + deploy

### skill_reminder_gate の恒久策: PostToolUse Skill 記録方式 (要相談)

Goal: transcript 依存を排し、PostToolUse `^Skill$` で invoke を session/agent-key state に記録して gate が参照する方式へ移行する。subagent hotfix (agent_id skip = subagent で enforcement 喪失) と resume 系 flush lag <120s の両残穴を同時に塞ぐ。

確定済み実態 (2026-07-22 実測・再導出不要):
- **gate mode は false-allow**: `cmd_gate` が `agent_id` で早期 return する (`skill_reminder_gate.py:842-843`)。subagent の Edit/Write は skill 未 invoke でも素通りし enforcement を喪失。実例 = 本 repo の hook file を sonnet subagent に編集させ、Skill invoke 0 件で Edit 5 件成功
- **commit-gate mode は false-deny**: `cmd_commit_gate` は `agent_id` で分岐せず staleness fail-open も適用しない (`:953-958` の意図的設計)。subagent が規約 skill を正しく invoke しても痕跡は親 transcript に無いため必ず deny。同一 payload で transcript だけ差し替えると allow/deny が反転することを実測
- **共通の原因**: subagent の PreToolUse payload に渡る `transcript_path` が親 session のものになり、subagent 自身の Skill invoke が載らない (2026-07-22 実測。同一 payload で transcript だけ差し替えると判定が反転する)。subagent の実 transcript は `<session>/subagents/agent-<id>.jsonl` に別途存在する。**採用する案 2 はこの挙動に依存しない** — invoke を hook 側の state に記録するため、payload がどの transcript を指すかと無関係に判定できる。仮に上流が child transcript を渡すようになれば commit-gate の false-deny は自然消滅するが、gate mode の false-allow は `agent_id` 早期 return 由来なので残る
- **hotfix の履歴**: `ff1129e` (2026-07-10) で `agent_id` early return を追加、`59c3925` (2026-07-21) はコメント文言のみ
- **案 3 (child transcript path 導出) は不採用**: transcript 配置レイアウト依存 + flush race が残る。案 2 が両穴を同時に塞ぐ
- **gate 起動には argv が必須**: `main()` は `len(sys.argv) < 2` で stdin を読まず exit 0 (`:1009-1010`)。配線は `managed-settings.d/extensions.json:13` (`gate`) と `:25` (`commit-gate`)。payload だけ流して「allow」と読むと hook が動いていない誤診になる

別セッションからのバグ報告 (`drafts/terminal-config-request-skill-gate.md`) は hotfix 前の状態を記述しており、回答を `drafts/terminal-config-request-skill-gate-response.md` に作成済み。

Exit Criteria:
- [ ] 方針合意 (実装規模 1.5-3 日 + managed-settings.d/extensions.json への hook 配線追加。診断 = `drafts/subagent-gate-diagnosis.md` 案 2/5 参照)
- [ ] PostToolUse:Skill が subagent 含む全成功経路で発火することの live probe
- [ ] 実装・deploy・commit し、subagent skip を撤去して enforcement 回復

### court バグ guard (command + stop_checks/skill 配線)

Goal: stray token (court/count/câu… と揺れる) + 行頭 invoke-leak を厳密パターンで捕捉し、court バグ汚染 (#76912 / #64108) を早期検知する。

Exit Criteria:
- [x] 検出方式を実データで確定 — 888 transcript 走査で 2 signature を FP ゼロ検証: stray-token 単独行 `(?m)^[ \t]*(court|count)[ \t]*$` / 行頭 invoke-leak `(?m)^[ \t]*<invoke name="`。token 固定でなく leaked XML を token 非依存で捕捉するのが要 (実バグ例 "câu")
- [x] 実装 + test + commit — 02e3054 (command `files/claude_court_guard` 7 tests / stop_checks warning-only 55 tests / /my-tasks 自己チェック / 両 .sh に copy 行、独立再実行 OK)
- [x] deploy 完了・配置検証 — 2026-07-13 H.S. 実行、`/usr/local/bin/claude_court_guard` PATH 動作・hooks/ 一致を確認
- [ ] 実運用で court 汚染の live 検出を確認 (opportunistic)
- 既知 finding (低 pri): stop_checks の court チェックは生 `text` 対象で、fence 内に court パターンを書く session は理論上 FP。`stripped` 化は要検討 (実 corpus では 0 FP)

### memory surface の閾値をモデル別に変えられるか調査

Goal: Opus セッション向け調整の memory surface (UserPromptSubmit `memory_surface.py` / Stop `stop_checks.py` の RAG surface) が Fable 5 では過剰という H.S. の体感に対し、走行モデルを hook 側から検出してモデル別に閾値・頻度を変える実装の可否と方針を確定する。

Exit Criteria:
- [x] hook から走行モデルを検出する手段の有無を実測で確定 — 2026-07-21 workflow で 4 チャネル並列 probe。**transcript JSONL の `.message.model` (type=="assistant") のみ可**、他は不可。全 hook event に共通して渡る payload field は `{session_id, transcript_path, cwd, prompt_id, permission_mode, agent_id, agent_type, effort}` で model は無く、`model` を持つのは `SessionStart` のみ (2026-07-21 に導入済み binary v2.1.216 を走査して確認)。**依存が壊れる条件**: transcript の assistant record が `message.model` を持たなくなれば transcript tail 方式は成立しなくなるため、実装時は取得失敗を現行挙動への fallback として扱う。`~/.claude.json` の `lastModelUsage` は 3 model が recency 順序なく同居し現行 model を取れず、`~/.claude/sessions/<pid>.json` は model field 自体が無い。transcript は 12.8MB でも tail 抽出 0.009s、assistant message 単位 stamp ゆえ mid-session `/model` 切替に追随する
- [x] 対象 hook の surface 閾値・頻度パラメータの所在を特定 — 計 9 個 / 2 file。`memory_surface.py`: `THROTTLE_SECONDS` / `BM25_SURFACE_FLOOR` / `BM25_STRONG_FLOOR` / `HYBRID_FLOOR` / `HYBRID_STRONG_FLOOR` / `DENSE_RESCUE_FLOOR` / `BM25_CANDIDATES` / `max_emit`(UPS=2)、`stop_checks.py`: `max_emit`(Stop=1)。体感頻度に効く第一段は 4 個 (`max_emit`(UPS) / `THROTTLE_SECONDS` / `HYBRID_FLOOR` / `HYBRID_STRONG_FLOOR`)、残る BM25_* は embedding 不在時の legacy path 用。9 個中 7 個が module-level 定数で chain は model 引数を持たないため分類は**改造 (surgical)**
調査フェーズは 2026-07-21 で完了・打ち切り。H.S. 指示により方針決定は別途検討とし、当時の session scope 外とした。上記 2 項目は一次実測済みゆえ**再調査は不要**で、再開時は下記の推奨をそのまま合意の議題にすればよい。

- [ ] 可否の結論とモデル別チューニング方針 (やらない選択肢含む) を H.S. と合意 — 推奨は transcript tail 方式 + `main()` 入口で profile を解決し module global を rebind する `_apply_model_profile(model)` 1 関数 (chain 全段への plumbing 不要)。SessionStart の `model` は `/model` 切替後も恒久 stale ゆえ不採用。global 引き下げ案は Opus 側の recall を確実に落とすため却下。**未 probe**: env var チャネルは probe が placeholder を返し未検証 — ただし launch 時静的ゆえ SessionStart と同じ恒久 stale 欠陥を持ち、結論は変わらない

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
- [x] **`deny_unsafe_git_reset` を PreToolUse:Bash catalog に追記** (2026-06-08 完了): PreToolUse 節に新 use-case「破壊的 reset / restore の advise-once 防止」を番号フロー + Related で追加 (L334-340)。 全 24 hook 再 gap 監査で MISSING 0 達成。 entry 自体の構成は H.S. の doc 全体 review 対象
- [ ] H.S. レビュー承認 → Exit flip + block 削除。 register は ですます に統一済 (commit 9fe0933、 prose 8 行を である→ですます・番号フロー step は体言止め維持)、 SessionStart step2 の述部欠落も修正済 (commit d56b27c)。 残るは H.S. の最終 review (構成/粒度) のみ。 2026-06-08 本 session で skill 一覧 (全 22 entry に category＋≤2文概要)・全 hook の Related 記入・UserPromptExpansion 節 (probe 結果)・Stop の check_push_prompting 欠落補完・応用節 bridge 文を追記し、 hook 記述を 20-agent workflow で実 source 検証して修正 (stop_checks 重複統合・§0 表 block family 4→6) — これらも H.S. review 対象 (commit 20a4858 / 0cf974c)。 **追従済** (commit ae2a3de): 2ca11ff の broad/pathless add deny (`-A`/`.`/`-u`/pathless) を PreToolUse:Bash catalog へ反映 — 新 use-case「広域 git add の cross-session 巻き込み防止」block 追加 + 「commit 規律」step1 に forward pointer。 3-lens 敵対 workflow (wpivtp9py) で hook source を逐語検証 (medium 1 = compound-only 誤読の forward pointer 反映)。 H.S. review 対象に含む

確定済みファクト (2026-06-07 本 session・再導出不要):
- **task 定義** (H.S. 前 session 原文趣旨): 「SessionStart の見出しを少し書いた。 こんな感じで repo のフックを記入していってほしい。 Skill はフォーマットを規約として書ける。 CLAUDE.md のスキル&フック化は後半の応用編で概要 (ここのフックでなく Big Picture)」。
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
- **編集規律**: doc は H.S. レビュー中 draft だが前 session 指示「記入してほしい」= 私が埋めて可。 document-editor は inline で discipline verbalize して適用 (doc 既読・modest size ゆえ fork でない)。 bare-invoke は dirty file 暴発の前科ありゆえ対象明示必須。 register 等の編集ルール詳細は handoff doc。

Note: doc 本体 (L1〜L4 概観 head + 実装 contract 0〜5 + 除外) 記載・commit 27b498c・SendUserFile 送付済。 目次 = 二つの family → capability-grant → 判定/検出/状態/安全 → 除外、 各項に実フック名の具体例。 **H.S. レビュー待ち** (外出先・後日)。 承認後に Exit flip + block 削除 (body 構成/粒度の直しがあれば反映してから)。 2026-05-31: コード照合 audit (workflow wvsbvz52x、 34 claim 中 30 accurate、 adversarial 確認・誤 flag 1 件棄却) 実施し確定 3 finding を commit eedd808 で反映 — (A) 中核 dichotomy 訂正 (L3 stop_checks の 4 family は exit2 で block、 overview L3 行+段階補足+§0 表)、 (B) §3 synthetic-skip を path 別に (BM25 surfacer `_memory_surface` は非 skip・本 turn live 確認)、 (C) §1/§2 に advisory-allow + content-embedded opt-out token 追記。 **事実精度は audit 済**、 残は H.S. の構成/粒度レビュー。 任意候補: 補足「L3とL4どう違うか」の「指摘する」(現 line 24) も同根で、 H.S. が望めば「介入する」系へ。 follow-up (doc外・コード): `_memory_surface` が synthetic prompt を surface する挙動の許容可否。 2026-06-01〜02: H.S. live レビューで overview を全面改稿 (歴史先行 CLAUDE.md→skill→hook / L1-L4 jargon 撤去 / 一人称除去 / です・ます / 表 A-D 化+俳句 / capability-grant をフロー番号リスト化 / 事実確認) + ファイル名 `_`→`-` リネーム (commit 025a3c6・14cf6d0)。 **レビュー継続中** — 次 session も H.S. の追加指摘を反映。 確立した編集ルールは handoff doc 参照。

Work file: handoff = `last-session-handoff.md` の「SKILL-HOOK-CONTRACT.md パターン集」 section ＋ plan `~/.claude/plans/breezy-bubbling-quiche.md` の「並行 deliverable」節
