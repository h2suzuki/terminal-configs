#!/usr/bin/env python3
r"""Acceptance tests for the stop_checks.py rewrite, written by the ordering side before the implementation.

Black box: a Stop payload on stdin, the verdict read back from exit code, stdout and stderr only.
The hook is never imported. Every fixture (HOME, transcript, task stores, wind-down state, memory
clone) is built by this file in a temp dir, so no test touches a real session or the real clone.

The contract claims below are quoted verbatim from the stop_checks rewrite contract draft §3;
each claim C<N> maps to the tests named test_c<N>_*.

## §3 契約 claim

各 claim は黒箱で検証可能。入力 = stdin payload と transcript の形、出力 = exit code / stdout JSON / stderr 文面。
test は `stop_checks.test.py` の `test_c<N>_*` に対応させる。

### C1 hook protocol と 3 つの出口

入力: stdin に Stop payload `{"session_id", "transcript_path", "cwd", "stop_hook_active", "last_assistant_message"}`。
出力は次の 3 つだけ。

- **block**: exit 2 / stdout 空 / stderr に blocking 行を `"\n".join` で 1 行 1 件。各行は `<family-id>: ` で始まり、
  「何が観測されたか」「本文をどう直すか」「同種を本文全体で掃く指示」をこの順で含む。複数 family が同時に
  成立したら全行を出す。指摘 1 件を直して同じ family を同 session で再発させる比率が 59% (transcript 134 本 /
  401 block の実測) ゆえ、修復指示は指摘箇所でなく class を対象にする。
- **warn / context**: exit 0 / stdout に 1 行の JSON
  `{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":<本文>},"systemMessage":<同じ本文>}`。
  本文は family 行を `"\n\n"` で連結。stderr は空。
- **pass**: exit 0 / stdout は turn-marker (C17) のみ / stderr 空。

`stop_hook_active` が真の Stop では block を warn へ降格し (advise-once)、行頭に
`advise-once (block demoted to pass): ` を付けて exit 0 で返す。降格は pass 扱い (行は stderr、stdout は空、
model には届かない — 同じ block を 2 度目の Stop で繰り返さないための出口であり、助言の配送ではない)。
`stop_hook_active` が真の Stop では warn / context / turn-marker も出さない (harness は additionalContext を受けると
model を再起動するので、継続 Stop で出し続けると無限に再起動する — 2026-08-27 に memory-reminder で実測)。
payload が読めない / dict でない / 内部例外 — いずれも **fail-open** (exit 0 / stdout 空 / stderr 1 行)。
test 方針: 3 出口それぞれを最小 payload で叩き、exit code と stdout/stderr の排他を assert。降格は同 payload の 2 回目で確認。

### C2 turn funnel (単一の抽出点)

入力: `transcript_path` の JSONL。末尾から 512 KB (`TURN_WINDOW_BYTES = 512 * 1024`) を読み、直近の **prompt boundary** 1 個までを turn とする。
prompt boundary = `type == "user"` かつ `message.content` が str かつ、その先頭が
`<task-notification>` / `<system-reminder>` / `<local-command` / `Skill /` / `(Re-invocation of /` (後 2 つは skill 再 invoke の注入) /
`Stop hook feedback` (hook の block 文面の注入) のいずれでもないもの (harness が user 名義で注入する entry は境界にしない)。
skill の初回 invoke は `message.content` が list なので、str 条件だけで境界から外れる。
turn から取り出す値はこの 6 つだけで、全 family はここからしか読まない:
`final_text` (payload の `last_assistant_message`、無ければ turn 最後の assistant text)、`turn_text` (turn 内 assistant text の連結)、
`tool_names` / `tool_paths` / `edited_paths` (Write/Edit の対象) / `bash_commands`。
transcript が無い・壊れている・boundary が見つからない場合は turn 由来の 5 値 (`turn_text` / `tool_names` / `tool_paths` /
`edited_paths` / `bash_commands`) を空にし、`final_text` は payload の `last_assistant_message` から取る。この空 turn では
turn との pairing を要する family (C4〜C8・C11・C12 規則 2・3・C13・C14・C15) は pass し、final_text だけで判定できる
C12 規則 1・4・5 と、state だけを見る family (C9・C10・C16・C17) は通常どおり評価する。
test 方針: `<task-notification>` を含む合成 transcript で turn 境界がそれを跨ぐことと、破損 JSONL 行が skip されることを assert。

### C3 warn の走査範囲 (K4 の 2 挙動を固定)

warn / context family は **当該 Stop の `final_text` だけ**を走査する (`turn_text` を見ない)。
判定前に `final_text` を NFKC 正規化し、fenced block・inline code (backtick 1 個以上で囲まれ改行を含まない区間)・引用行を落とす。
- 過去 turn で既に直した文を再警告しない: turn 内に同じ文言が残っていても、final_text に無ければ warn は出ない。
- 数量表現は序数参照ではない: 「候補 17 件」「案 3 つ」は `communication-lint` の自己採番に当たらず、「候補 12」は当たる。
test 方針: 同一文言を turn_text にだけ持つ payload で 0 件、final_text に持つ payload で 1 件。数量/序数の 4 例を表駆動で assert。

### C4 continuation-claim (block)

入力: `final_text` に未来形の遂行宣言がある。遂行宣言 = 次の語尾のいずれかで終わる文 (文の切り出しは C5 と同じ):
継続します / 再開します / 進めます / 進みます / 続けます / 着手します / 実施します / 実装します / 取り掛かります / 対応します /
調整します / やります / 修正します / 削除します / 追加します / 作成します / 変更します / 反映します / 統合します / 置換します /
コミットします / commit します / デプロイします / deploy します / 始めます / 報告します / 提示します / 検証します /
直します / 自走を続け / 作業を続け (旧 hook が実 corpus 74 件を全て捕えた roster + 実 corpus の 5 語。「お願いします」は含まない)。
文末の装飾 (括弧注記 `(約 10 分)`・全角括弧・三点リーダ・絵文字・記号) は剥がしてから語尾を当てる。
出力: block。ただし次の 3 形式は block しない — (1) **実行中**: 同 turn に起動した background task の id を `final_text` の
どこかで挙げている (当該文の外でよい)、(2) **完了**: 同 turn の tool 呼び出しに裏付けがある過去形、
(3) **停止**: 「ここで停止」と「再開条件」を当該文と同じ行に持つ (`。` で文が切れていてもよい)。
条件提示 (「必要なら〜します」「ご希望であれば」) と、fenced/表/箇条書き label も除外する。
test 方針: 素の宣言で block、3 形式それぞれと条件提示・fence 内で pass。

### C5 done-state-ledger (block)

入力: `final_text` に完了語 (「完了」「done」「終わりました」「済み」) があり、その文が commit / push / gate / E2E / merge の
いずれかに言及している。**gate 言及** = その文が `ruff` / `ty` / `test` / `変異` / `lint` / `selftest` / `gate` のいずれかを含み、
かつ同じ文に数値または `OK` を持つこと。**E2E 言及** = その文が `E2E` / `e2e` / `実機` / `live` / `実測` のいずれかを含むこと。
文の切り出しは `。` `！` `？` `!` `?` と改行 (箇条書き・表の行は各 1 文)。判定は完了語を含む文にだけ掛け、別の文の
commit / gate / E2E 言及は数えない (「完了しました。lint は未実施です」は block しない)。gate 語は語境界で照合する
(`ty` は `\bty\b`、`Priority` に当てない)。
出力: 言及した種別の証跡が turn 内に無ければ block。証跡の対応は逐語で —
commit/push/merge → `bash_commands` の `git commit` / `git push` / `git merge` (`-C <dir>` / `-c <k=v>` / `--<opt>` の前置を許す)、
gate/E2E → `bash_commands` に当該語 (大小文字無視) を含む command が 1 件以上、
実行可能拡張子 (`.py .sh .mjs .js`) を `edited_paths` に持つなら同 turn の Bash でその path が実行されていること、
UI 拡張子 (`.css .scss .tsx .jsx .vue .svelte .html`) を編集したなら screenshot tool の呼び出し。
test 方針: 完了語 × 7 証跡種別 (commit / push / merge / gate / E2E / 実行可能 / UI) で、証跡有り = pass / 無し = block の 14 case を表駆動。

### C6 task-plan-first (block)

入力: turn の先頭が prompt boundary (= 新規 prompt に応答する turn) で、turn 内に 1 つ以上の tool 呼び出しがある。
出力: 最初の非 Task tool 呼び出しより前に `TaskCreate` / `TaskUpdate` / `TodoWrite` / mytask MCP の呼び出しが無ければ block。
`ToolSearch` (deferred tool の schema 読込) は順序判定で tool に数えない — mytask の schema 読込が Task upsert に先行するため。
次の turn は pass — tool 呼び出しが 0 件、**tool 呼び出しが 2 件以下かつ `edited_paths` が 0 件** (質問への即答を block しない)、
prompt boundary から始まらない (継続 Stop)、Task tool が gate off の session
(`~/.claude.json` の `cachedGrowthBookFeatures.tengu_vellum_ash`)。
test 方針: tool 順序を入れ替えた 3 transcript (Task 先行 / Task 後追い / Task 無し) で pass/block/block、
`Read` 1 回だけの turn で pass (除外規則の固定)。

### C7 task-ledger-drift (warn)

入力: (a) `final_text` に作業遂行宣言、(b) 先送り発言 (「別タスクに切り出し」「今は処置しません」)、
(c) `edited_paths` が 3 件以上 — のいずれか。
出力: session の Task store (`~/.claude/tasks/<session_id>/*.json` と `drafts/tasks/<session_id>.json`、status 不問) が
空、かつ turn 内に Task tool 呼び出しも無ければ warn 1 行。
test 方針: (c) の境界を 2 件 = pass / 3 件 = warn で固定し、Task store 非空で全て pass。

### C8 ruling-without-reading (block)

入力: turn 内に subagent 結果 (`Agent` / `Task` tool の呼び出し) または Workflow 結果
(`<task-notification>` を含む user entry。code fence / backtick 内の言及は notification ではないので数えない) が有り、`final_text` が
entry path を挙げて裁定・評価を述べている。path token = backtick 内または裸の token で、`/var/lib/claude-rag-memory/` で
始まるもの (拡張子不問)、または `/` を 1 つ以上含み英字始まりの拡張子 (`\.[A-Za-z][A-Za-z0-9]{0,5}`) で終わるもの
(`.md` に限らない、絶対 / repo 相対とも)。URL (`://` の後ろ)・package 指定 (`@` の後ろ)・数字始まりの拡張子 (`3.11/3.12`、`3/4.5`)
は token にしない。`tool_paths` との一致は包含 (Read した絶対 path の中に本文の相対 path が文字列として現れれば開いたとみなす)。
出力: 挙げた path のいずれも turn 内の `tool_paths` (Read/Grep/Glob の対象) に現れなければ block。
出力文面は「開いていない path」を列挙する。path を挙げない本文、subagent 結果も Workflow 結果も無い turn は pass。
test 方針: 同一 final_text に対し Read 有り = pass / 無し = block、path 3 件中 1 件だけ Read = block で列挙が 2 件、
`<task-notification>` だけの turn でも同じ block が出ること。

### C9 wind-down-open-tasks (block)

入力: 直近の user prompt が wind-down の session (`~/.claude/hooks/state/wind_down_signal/<session_id>` の中身が `1`。
UserPromptSubmit 側が毎 prompt `1` / `0` で上書きし、宣言の履歴は `<session_id>.sticky` に残す)。
出力: Task store に open (status が `completed` / `cancelled` 以外) の task が 1 件以上あれば block し、
その name を列挙する。state file が無い / 中身が `1` でない session、open が 0 件なら pass。
`session_id` が無い / state dir が読めない場合は pass (fail-open)。
test 方針: state file の有無 × open task の有無の 4 象限。

### C10 wind-down-background-unreaped (block)

入力: C9 と同じ wind-down 信号 (中身 `1`)。transcript の**末尾 2 MB** (`BACKGROUND_WINDOW_BYTES = 2 * 1024 * 1024`。
C2 の funnel は 128 KB のままで、この窓を使うのは C10 だけ) から次を数える —
起動 = tool_result の本文が `Command running in background with ID: <id>` または
`Workflow launched in background. Task ID: <id>` に一致した `<id>` の集合。
完了通知 = user entry の文字列に `<task-notification>` があり、その中の `<task-id><id></task-id>` の `<id>` 集合。
出力: 起動 − 完了通知 が空でなければ block し、未回収の id を列挙する。差が空なら pass。
ただし窓が session 先頭に届いていないとき — transcript が窓より大きい、または起動を持たない完了通知 id がある (= 起動 id が窓の外)
— は観測が不完全なので **block せず warn** とし、行に「窓外」を含める (差が空でなければ、transcript が窓より大きいだけの
場合も warn する)。窓外かつ差が空なら何も出さない。
test 方針: 起動 2 / 通知 1 の合成 transcript で 1 件を列挙、起動 2 / 通知 2 で pass、wind-down 未宣言で常に pass、
起動を持たない通知で warn (「窓外」を含み exit 0)、窓内 1.5 MB の起動は block・窓外 3 MB の起動は非 block で上限値を挟む。

### C11 handoff-doc-without-marker (block)

入力: wind-down 宣言済み session (`~/.claude/hooks/state/wind_down_signal/<session_id>.sticky` が存在 —
宣言は session 内で不可逆で、後続 prompt が信号を `0` に戻しても残る) で、turn 内の `edited_paths` に handoff doc
(basename が `handoff` を含む `.md`、または `docs/handoff/` 配下) がある。
出力: `final_text` と当該 doc の本文のいずれにも full-sid marker (payload の `session_id` の全文字列) が無ければ block し、
marker を欠く doc path を列挙する。短縮 sid や template の placeholder は marker と見なさない。
test 方針: full-sid 有り = pass / 先頭 8 文字だけ = block / doc 未編集 = pass。

### C12 self-report-honesty (block)

入力: `final_text`。次の 5 規則をこの family 1 つで持つ。
1. 不実施の meta-announce → 常に block。語形は次の roster に限る (旧 hook の実証 roster + 実 corpus の「実行しません」):
   省略(は)?しません / 省略(は)?控えます / 触りません / 触らないでおきます / (には|は)触れません / mock ?しません /
   ダミー(は)?入れません / (再)?催促(は)?しません / 推測で.{0,10}書きません / 想像で.{0,10}埋めません / 実行しません /
   判断(は)?保留します / (rule|scope) ?(に従って|通り).{0,20}(控えます|触れません)。
2. 内省 phrase (「反省」「以後気をつけ」) があり、turn 内に persistence path
   (`memory` / `skills` / `hooks` / `CLAUDE.md`) への Write/Edit が無い → block。
3. 自分の作業への驚き phrase (「いつの間に」「覚えがない」の 2 語に限る。「想定外」は対象の性質を述べる日常語なので対象外) があり、turn 内に `git log|show|diff` が無い → block。
4. 自分の発話を「誤解を招く記述」等と婉曲評価 → block (設計対象の命名・label への同評価は除外)。
5. 帰属ぼかし (「既存の」「reasonable default」) の 60 字近傍に誤り語がある → block。
出力: 成立した規則ごとに 1 行、行頭は `self-report-honesty: `、続けて規則番号と検出語。
test 方針: 5 規則それぞれの陽性 1 件と陰性 1 件 (計 10 case)。陰性は規則 2-5 が pairing 成立、
規則 1 は「実際に行った作業への rule 言及」で pass すること。

### C13 offload-to-user (block) と host-command-format (warn)

入力: `final_text` (fence 除去後。ただし host-command-format は fence の有無そのものを見るので fence 除去前の本文を使う)。
- **block** (`offload-to-user`): (1) 順序質問 (「どちらを先に」「どの順で」)、(2) 二択確認 / routing (「A にしますか B にしますか」
  「どちらにしますか」「どちらがよいですか」)、(3) `!` prefix 実行の依頼 — (1)(2) は `?` / `？` / `ますか` / `ましょうか` / `ください` /
  `でしょうか` で終わる行 (user への問い掛け) だけを対象にし、「自分で判断しました」のような平叙文は対象外。「ください」で
  終わる行でも、順序・二択の句が「〜かは」「〜かについては」で主題化された報告・案内文 (「どの順で実行したかは報告書を
  確認してください」) は対象外。
  (2) は turn 内に `declare-and-proceed` skill の invoke があれば pass。
- **warn** (`host-command-format`, family 15): host コマンドを user に手動実行させる文脈で、コマンドが独立した fenced block に
  なっていない (prose の inline code に混ざる)、または fenced でも path 引数が絶対 path でも `/` を含む repo root 起点の
  相対 path でもない裸の basename である。inline command は同じ文字列が fence 内にも現れる場合だけ打ち消す
  (無関係な fence があっても打ち消さない)。
出力: severity が違うので family id を分ける。同一 family id が exit 2 側と exit 0 側の両方に出ることを禁じる。
test 方針: 3 block 規則の陽性 / skill invoke による pass / 整形済み fence で warn 無し / 裸の basename を含む fence で warn。

### C14 claim-without-evidence (warn)

入力: `final_text`。否定断定 (「不明」「該当なし」「存在しません」「できません」)、規模・影響評価語 (「大改造」「影響大」)、
既知可能操作への不可断定、網羅・完了の self-claim (「網羅した」「全て確認した」) のいずれか。
出力: turn 内に根拠 tool (`Read` / `Grep` / `Glob` / `WebSearch` / `WebFetch`) の呼び出しが 1 件も無ければ warn 1 行。
**block しない** (K3)。根拠 tool が 1 件でもあれば pass。
test 方針: 4 種の検出語 × 根拠 tool 有無 = 8 case。全 case で exit 0 であることも assert。

### C15 communication-lint (warn)

入力: `final_text` (C3 の正規化・除去後) と直近の user prompt。次の 5 規則を 1 family で持つ。
1. 最終非空行が絵文字始まりでない、または絵文字の直後に `[結論]` / `[質問]` が無い、またはその札が終端と食い違う。
   絵文字 = U+1F000〜1FAFF / U+2300〜23FF (⏸ ⌛ ⏳) / U+2500〜2BFF のいずれかで始まる行。札の前に置けるのは
   絵文字と空白だけ (仮名・漢字・英数が先に来たら札が無いものとして扱う)。`?` / `？` 終端の行は `[質問]`、
   それ以外は `[結論]`。`[事実]` は文章中のどこにでも現れるので、この規則では見ない。
2. 自己採番参照 (「候補 12」「選択肢 3」)。数量表現 (「候補 17 件」「案 3 つ」) は除外 (C3)。
3. 最終行が疑問文なのに、Task store に open な decision 型 task が無い。
4. 直近 user prompt が 20 字以下の短文決裁で、open な decision 型 task がある (記録漏れ)。
5. 最終行が疑問文で、過去参照語 (「さっきの」「先ほどの案」) を含む (質問が自己完結していない)。
**decision 型 task** の判定は逐語で固定する — task 名 (native store の `subject`、mytask store の `content` / `activeForm`)
が「決裁」「裁定」「判断待ち」「承認待ち」「要確認」のいずれかを含むこと。他の語を含む task は decision 型ではない。
出力: 成立した規則の文を 1 行に空白連結して warn。
test 方針: 5 規則の陽性各 1 + 規則 2 の数量 3 例 + 絵文字始まりの正常終端で 0 件 +
decision 型の陽性/陰性 (「決裁待ち」を含む open task で規則 3 が pass、含まない open task では warn) +
規則 1 の札 (欠落 / 食い違い 2 向き / 札の前に本文がある形 / `[事実]` は無関係)。

### C16 memory-reminder (context)

入力: memory clone の root は環境変数 `STOP_CHECKS_MEMORY_ROOT`、未設定時の既定は
`/var/lib/claude-rag-memory/claude-lessons-learned` (C19)。その配下 `org/**`・`user/**` と、payload `cwd` の repo に対応する
`project/<id>/**` (`id` = `.git/config` の origin URL を memory_surface と同じ規則で正規化した `github.com-<owner>-<repo>`、
worktree は共通 dir の config を読む、origin が無ければ cwd の `/` → `-`) の `*.md` の front matter を直接走査 (他 hook を
import しない)。他 project の entry は出さない。`check:` 行を持ち、`when:` に `stop` を含む entry のみ候補。候補のうち `keywords:` の語句 (`,` / `、` 区切り、小文字化) が
当該 Stop の `final_text` (NFKC・小文字化) に含まれる entry だけを選び、一致語句数が最大の 1 件だけを出す (同数なら走査順の
先頭)。同じ entry は 1 session に 2 回まで (latch `<transcript>.turns.memo` = path → 回数の JSON、書くのは行が stdout に
載った Stop だけ)。一致が無ければ何も出さない — 無差別に全 entry を出す形は量で無視される (2026-08-27 に 12 件が毎 Stop
出て実測)。
出力: 選ばれた 1 件の `check:` 本文と path を additionalContext に載せ、末尾に固定文言
「抵触するなら修正してから完了。しなければ何も書かない」を付ける。`when:` に `stop` が無い entry は出さない。
同 family の第 2 規則: 直近 user prompt (harness 注入 prefix 除外後) に「無駄 / 浪費 / もったいない」があり、
turn 内に persistence path への Write が無ければ 1 行を足す — **同一 prompt につき 1 回だけ** (K2(i))。
第 2 規則の latch key は turn ではなく **prompt boundary の identity** (その user entry の `uuid`、無ければ `timestamp`)
で、latch file は `<transcript>.turns.waste`。latch を立てるのはその行が stdout に載った Stop (exit 0 の warn / context) だけで、
block・降格の Stop では書かない。clone が無い / 読めない / 空の場合は何も出さず pass (実 clone を読みに行かない)。
非 UTF-8 や front matter の壊れた entry は skip し、他の entry は出す。
test 方針: `when: prompt` のみの entry が出ないこと、固定文言が entry 数によらず 1 回であること、
同一 prompt の 2 回目の Stop で「無駄」行が消え、別 prompt の Stop では再び出ること。

### C17 turn-marker (systemMessage)

入力: block も warn / context も無い pass 時のみ。
出力: `<transcript>.turns` の counter を 1 増やし、`"<count> <last_stop_epoch>"` の 1 行で書き戻す。
stdout に `systemMessage` だけを持つ JSON を 1 行出す (`additionalContext` は付けない = model には不可視)。
本文は `<ISO 時刻> / Turn #<count> / Context <used>% / 経過 <秒> 秒`。`<used>` は
`$XDG_CACHE_HOME/claude-tui-statusline/<session_id>.json` (既定 `$HOME/.cache/…`) の `stdin.context_window.used_percentage`
(`stdin` は dict、JSON 文字列なら parse する)、経過の基点は同 file の `session_started_epoch`。cache が無い / 読めない場合は
`Context -` とし、経過は前回 Stop の epoch (`.turns` の 2 列目) から数える。counter file が読めない場合は marker を出さず exit 0。
test 方針: 連続 2 回の pass で `Turn #1` → `Turn #2`、warn が出た Stop では counter が動かないこと。

### C18 決定性と純度

LLM 呼び出し無し。stdlib のみ (`json` `os` `re` `sys` `fcntl` `datetime` `unicodedata`)。
hook file は実行 bit を持ち (`os.access(HOOK, os.X_OK)`)、shebang は `#!/usr/bin/env python3` (登録は bare path で起動する)。
他 hook からの import 無し (`check_uncommitted_at_handoff` / `memory_surface` への依存を全廃)。
子プロセス起動無し (`git` を呼ばない — `has_git_verify` は `bash_commands` の文字列から判定する)。
同一 payload + 同一 transcript + 同一状態 file から常に同一 stdout/stderr/exit code。
どの family の例外も他 family を巻き込まず、hook 全体は必ず fail-open。
出力する family id は §2.1 の 15 個の集合に限る (許可集合)。drop した 4 family の id
(`worktree-cleanup` / `codex-shared-write` / `handoff-todos-sync` / `court-guard`) は source にも出力にも現れない。
test 方針: source に `subprocess` / `os.popen` / `os.system` / `import memory_surface` / `import check_uncommitted` /
drop した 4 id が現れないことを assert し、`ast` で全 import が stdlib 集合に収まることを assert し、
代表 payload (block / warn / pass) の出力 family id が許可集合に収まることを assert し、
同一入力の 2 回実行で出力 byte 一致 (counter を書かない warn 経路で) を assert。

### C19 fixture substitution (状態 root の env 差し替え)

黒箱 test の成立に必要なため、決裁 4 で契約本文の claim に取り込んだ。
C16 の memory clone root は環境変数 `STOP_CHECKS_MEMORY_ROOT` で差し替えられる。差し替え先が空 dir・
不在でも C16 は pass する (実 clone を読みに行かない)。 未設定時は `CLAUDE_MEMORY_SYNC_CLI` の `load_clones()` が返す **全 clone** を走査し、 どの clone の
entry も候補になる。 返りが空・CLI 不在・CLI が旧版で `load_clones` を持たない・読込例外のいずれでも、
既定の `<CLAUDE_MEMORY_ROOT>/claude-lessons-learned` 単独へ落ちる (新 installer 未実行の機で挙動不変)。
CLI は test 内で生成する stub で足りる (実 parser の契約は claude_memory_sync.clones.test.py が持つ)。同様に C6 / C7 / C9 / C10 / C11 / C15 / C17 が読む状態 file
(`~/.claude/tasks/`、`~/.claude/hooks/state/wind_down_signal/`、`~/.claude.json`、
`~/.cache/claude-tui-statusline/`) は全て `$HOME` / `$XDG_CACHE_HOME` 起点で解決し、
mytask store は `$CLAUDE_PROJECT_DIR` と payload の `cwd` 起点で解決する。
test 方針: memory root を空 dir に向けた Stop で memory-reminder が 0 件、entry を置いた dir に
向けた Stop で 1 件。temp HOME の task store が C7 の pairing に効くこと。
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stop_checks.py")
SESSION = "11111111-2222-3333-4444-555555555555"
MODEL = "claude-opus-5"
# A conclusion line that satisfies communication-lint rule 1 (emoji-led final line).
TAIL = "\n\n\U0001f537 [結論] 以上です。"
DEFAULT_PROMPT = "stop_checks の契約 test を書いてください"
# §2.1: the only family ids the rewrite may emit.
ALLOWED_FAMILIES = frozenset(
    {
        "continuation-claim",
        "done-state-ledger",
        "task-plan-first",
        "task-ledger-drift",
        "ruling-without-reading",
        "wind-down-open-tasks",
        "wind-down-background-unreaped",
        "handoff-doc-without-marker",
        "self-report-honesty",
        "offload-to-user",
        "claim-without-evidence",
        "communication-lint",
        "memory-reminder",
        "turn-marker",
        "host-command-format",
    }
)
# §2.2: dropped by K3; neither the source nor any exit may mention them.
DROPPED_FAMILIES = (
    "worktree-cleanup",
    "codex-shared-write",
    "handoff-todos-sync",
    "court-guard",
)


def iso(offset: float = 0.0) -> str:
    """Transcript timestamp `offset` seconds from now (skill windows are relative to now)."""
    when = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=offset
    )
    return when.isoformat().replace("+00:00", "Z")


def prompt(text: str = DEFAULT_PROMPT, uid: str = "prompt-1") -> dict:
    return {
        "type": "user",
        "uuid": uid,
        "timestamp": iso(-30),
        "message": {"role": "user", "content": text},
    }


def injected(text: str) -> dict:
    """A user entry with string content that C2 excludes from prompt boundaries."""
    return {
        "type": "user",
        "uuid": "inject-1",
        "timestamp": iso(-20),
        "message": {"role": "user", "content": text},
    }


def skill_preamble(name: str) -> dict:
    """A skill's first invoke: text blocks, not a string, so C2's str check already excludes it."""
    return {
        "type": "user",
        "uuid": "skill-1",
        "timestamp": iso(-18),
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Base directory for this skill: /home/u/.claude/skills/{name}\n\n# {name}\n",
                }
            ],
        },
    }


def tool_result(body: str) -> dict:
    return {
        "type": "user",
        "uuid": "result-1",
        "timestamp": iso(-10),
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": body}],
        },
    }


def assistant(blocks: list[dict], model: str = MODEL) -> dict:
    return {
        "type": "assistant",
        "timestamp": iso(-5),
        "message": {"role": "assistant", "model": model, "content": blocks},
    }


def say(text: str, model: str = MODEL) -> dict:
    return assistant([{"type": "text", "text": text}], model=model)


def call(name: str, **inp) -> dict:
    return assistant([{"type": "tool_use", "name": name, "input": inp}])


def bash(command: str) -> dict:
    return call("Bash", command=command)


def edit(path: str) -> dict:
    return call("Edit", file_path=path)


def read(path: str) -> dict:
    return call("Read", file_path=path)


SUBAGENT = [
    call("Agent", subagent_type="general-purpose", prompt="調査してください"),
    tool_result("subagent report: 候補を 3 件見つけました"),
]


class Fixture:
    """Temp HOME, project cwd, transcript and memory clone: the hook sees nothing real."""

    def __init__(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="stop-checks-")
        self.home = os.path.join(self.tmp, "home")
        self.cwd = os.path.join(self.tmp, "repo")
        self.cache = os.path.join(self.home, ".cache")
        self.memory = os.path.join(self.tmp, "memory")
        for path in (self.home, self.cwd, self.cache, self.memory):
            os.makedirs(path)
        self.transcript = os.path.join(self.tmp, "session.jsonl")
        self.write([])
        # Task tools are gated off by default so C6 stays out of every other claim's way.
        self.gate_tasks_off()

    def write(self, entries: list[dict], extra_lines: tuple[str, ...] = ()) -> None:
        with open(self.transcript, "w", encoding="utf-8") as stream:
            for entry in entries:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
            for line in extra_lines:
                stream.write(line + "\n")

    def turn(self, *entries: dict, prompt_text: str = DEFAULT_PROMPT) -> None:
        self.write([prompt(prompt_text), *entries])

    def filler(self, size: int) -> tuple[str, ...]:
        """Assistant lines totalling `size` bytes, to push earlier entries out of a tail window."""
        line = json.dumps(say("x" * 900), ensure_ascii=False)
        return tuple([line] * (size // (len(line) + 1) + 1))

    def repo_file(self, relative: str, body: str = "content\n") -> str:
        path = os.path.join(self.cwd, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(body)
        return path

    def native_task(self, subject: str, status: str = "in_progress") -> None:
        directory = os.path.join(self.home, ".claude", "tasks", SESSION)
        os.makedirs(directory, exist_ok=True)
        task = {"id": subject, "subject": subject, "status": status}
        with open(
            os.path.join(directory, subject + ".json"), "w", encoding="utf-8"
        ) as stream:
            json.dump(task, stream, ensure_ascii=False)

    def wind_down(self, latest: bool = True) -> None:
        """Mirror the UserPromptSubmit writer: latest-prompt flag plus a sticky declaration."""
        directory = os.path.join(
            self.home, ".claude", "hooks", "state", "wind_down_signal"
        )
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, SESSION), "w", encoding="utf-8") as stream:
            stream.write("1" if latest else "0")
        open(os.path.join(directory, SESSION + ".sticky"), "w").close()

    def gate_tasks_off(self) -> None:
        self.write_claude_json(
            {"cachedGrowthBookFeatures": {"tengu_vellum_ash": [MODEL]}}
        )

    def enable_task_tools(self) -> None:
        self.write_claude_json({"cachedGrowthBookFeatures": {}})

    def write_claude_json(self, config: dict) -> None:
        with open(
            os.path.join(self.home, ".claude.json"), "w", encoding="utf-8"
        ) as stream:
            json.dump(config, stream)

    def memory_entry(
        self,
        name: str,
        check: str,
        when: str = "prompt stop",
        keywords: str = "調査, 契約",
    ) -> str:
        path = os.path.join(self.memory, "org", name + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = (
            "---\n"
            f"name: {name}\n"
            "description: 契約 test の fixture entry\n"
            f"keywords: {keywords}\n"
            f"check: {check}\n"
            f"when: {when}\n"
            "---\n\n## 理由\n\nfixture\n"
        )
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(body)
        return path

    def turns_file(self, contents: str) -> str:
        path = self.transcript[: -len(".jsonl")] + ".turns"
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(contents)
        return path

    def read_turns(self) -> str:
        try:
            with open(
                self.transcript[: -len(".jsonl")] + ".turns", encoding="utf-8"
            ) as stream:
                return stream.read()
        except OSError:
            return ""

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def run_hook(
    fixture: Fixture,
    final_text: str | None = None,
    *,
    transcript: bool = True,
    session_id: str | None = SESSION,
    stop_hook_active: bool = False,
    raw: str | None = None,
    memory_root: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    payload: dict = {"cwd": fixture.cwd, "stop_hook_active": stop_hook_active}
    if session_id is not None:
        payload["session_id"] = session_id
    if transcript:
        payload["transcript_path"] = fixture.transcript
    if final_text is not None:
        payload["last_assistant_message"] = final_text
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": fixture.home,
        "XDG_CACHE_HOME": fixture.cache,
        "CLAUDE_PROJECT_DIR": fixture.cwd,
        "LANG": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
    }
    root = fixture.memory if memory_root is None else memory_root
    if root:  # "" exercises the unset case, where load_clones() picks the roots
        env["STOP_CHECKS_MEMORY_ROOT"] = root
    env.update(env_extra or {})
    body = raw if raw is not None else json.dumps(payload, ensure_ascii=False)
    return subprocess.run(
        [sys.executable, HOOK],
        input=body,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )


def block_lines(proc: subprocess.CompletedProcess) -> list[str]:
    return [line for line in proc.stderr.splitlines() if line.strip()]


def warn_body(proc: subprocess.CompletedProcess) -> str:
    """additionalContext of the single warn/context JSON line on stdout, or ''."""
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        section = data.get("hookSpecificOutput") or {}
        if section.get("additionalContext"):
            return section["additionalContext"]
    return ""


def marker(proc: subprocess.CompletedProcess) -> str:
    """systemMessage of the turn-marker line (no additionalContext), or ''."""
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not (data.get("hookSpecificOutput") or {}).get("additionalContext"):
            return data.get("systemMessage") or ""
    return ""


def family_of(line: str) -> str:
    return line.split(":", 1)[0].strip()


def blocked(proc: subprocess.CompletedProcess) -> set[str]:
    return {family_of(line) for line in block_lines(proc)}


def warned(proc: subprocess.CompletedProcess) -> set[str]:
    body = warn_body(proc)
    return {family_of(part) for part in body.split("\n\n") if part.strip()}


class StopChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def assertBlocks(self, proc: subprocess.CompletedProcess, family: str) -> None:
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(proc.stdout, "", "block writes nothing to stdout")
        self.assertIn(family, blocked(proc), proc.stderr)

    def assertNotBlocked(
        self, proc: subprocess.CompletedProcess, family: str = ""
    ) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if family:
            self.assertNotIn(family, blocked(proc), proc.stderr)

    def assertWarnsFamily(self, proc: subprocess.CompletedProcess, family: str) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "", "warn writes nothing to stderr")
        self.assertIn(family, warned(proc), proc.stdout)

    def assertNotWarned(self, proc: subprocess.CompletedProcess, family: str) -> None:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(family, warned(proc), proc.stdout)

    def assertClean(self, proc: subprocess.CompletedProcess) -> None:
        """Pass: exit 0, empty stderr, and the turn marker as the only stdout line."""
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(warn_body(proc), "", proc.stdout)
        self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)


class ProtocolTest(StopChecksTest):
    """C1: the three exits, their channel exclusivity, advise-once and fail-open."""

    def test_c1_block_uses_exit_two_and_stderr_only(self):
        self.fx.turn(say("作業しました"))
        proc = run_hook(self.fx, "この後 stop_checks の実装を進めます。")
        self.assertBlocks(proc, "continuation-claim")
        self.assertTrue(block_lines(proc)[0].startswith("continuation-claim: "))

    def test_c1_block_line_orders_observation_repair_and_class_sweep(self):
        """C1: a repair aimed at the flagged spot alone leaves the class, where 59% of blocks recur."""
        self.fx.turn(say("作業しました"))
        proc = run_hook(self.fx, "この後 stop_checks の実装を進めます。")
        observed, repair, sweep = block_lines(proc)[0].split(": ", 1)[1].split("。")
        self.assertEqual(observed, "未来の遂行宣言を検出")
        self.assertEqual(repair, "完了した作業だけを報告する")
        self.assertEqual(sweep, "同種の箇所を本文全体で掃く")

    def test_c1_warn_uses_one_stdout_json_line_and_empty_stderr(self):
        self.fx.turn(say("報告します"))
        proc = run_hook(self.fx, "該当なしです。")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)
        data = json.loads(proc.stdout.splitlines()[0])
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertEqual(
            data["hookSpecificOutput"]["additionalContext"], data["systemMessage"]
        )

    def test_c1_pass_emits_only_the_turn_marker(self):
        self.fx.turn(say("調査しました"))
        self.assertClean(run_hook(self.fx, "調査の結果を表にまとめました。" + TAIL))

    def test_c1_simultaneous_families_emit_one_line_each(self):
        self.fx.turn(say("作業しました"))
        text = "この後 実装を進めます。\nrule に従って CLAUDE.md には触れません。"
        proc = run_hook(self.fx, text)
        self.assertBlocks(proc, "continuation-claim")
        self.assertIn("self-report-honesty", blocked(proc))
        self.assertGreaterEqual(len(block_lines(proc)), 2)

    def test_c1_stop_hook_active_silences_warn_and_marker(self):
        """C1: a continuation Stop emits nothing on stdout, or the harness restarts the model forever."""
        self.fx.turn(say("調査しました"))
        proc = run_hook(self.fx, "該当なしです。", stop_hook_active=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "", proc.stdout)

    def test_c1_stop_hook_active_demotes_block_to_advise_once(self):
        self.fx.turn(say("作業しました"))
        proc = run_hook(self.fx, "この後 実装を進めます。", stop_hook_active=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(block_lines(proc), "the demoted line is still delivered")
        for line in block_lines(proc):
            self.assertTrue(
                line.startswith("advise-once (block demoted to pass): "), line
            )

    def test_c1_unreadable_payload_fails_open(self):
        proc = run_hook(self.fx, raw="{not json")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(len(block_lines(proc)), 1, proc.stderr)

    def test_c1_non_dict_payload_fails_open(self):
        proc = run_hook(self.fx, raw="[]")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(len(block_lines(proc)), 1, proc.stderr)


class TurnFunnelTest(StopChecksTest):
    """C2: one extraction point; injected user entries are not prompt boundaries."""

    def test_c2_injected_user_entries_are_not_prompt_boundaries(self):
        for injection in (
            "<task-notification>\n<task-id>bg-1</task-id>\n</task-notification>",
            "<system-reminder>memory を確認してください</system-reminder>",
            "<local-command-stdout>ok</local-command-stdout>",
        ):
            with self.subTest(injection=injection.split(">")[0]):
                self.fx.write(
                    [
                        prompt(),
                        edit(self.fx.repo_file("a.py")),
                        injected(injection),
                        edit(self.fx.repo_file("b.py")),
                        edit(self.fx.repo_file("c.py")),
                        say("編集しました"),
                    ]
                )
                proc = run_hook(self.fx, "3 file を編集しました。" + TAIL)
                self.assertWarnsFamily(proc, "task-ledger-drift")

    def test_c2_corrupt_jsonl_lines_are_skipped(self):
        self.fx.write(
            [prompt(), say("この後 実装を進めます。")],
            extra_lines=("{broken", "", "not json at all"),
        )
        self.assertBlocks(run_hook(self.fx), "continuation-claim")

    def test_c2_final_text_falls_back_to_last_assistant_text(self):
        self.fx.write(
            [prompt(), say("先に調査しました"), say("この後 実装を進めます。")]
        )
        self.assertBlocks(run_hook(self.fx), "continuation-claim")

    def test_c2_missing_transcript_passes_every_family(self):
        os.remove(self.fx.transcript)
        self.assertClean(run_hook(self.fx, "この後 実装を進めます。"))

    def test_c2_turn_without_prompt_boundary_is_empty(self):
        self.fx.write([say("作業しました"), edit(self.fx.repo_file("d.py"))])
        self.assertClean(run_hook(self.fx, "この後 実装を進めます。"))

    def test_c2_injected_skill_and_hook_feedback_entries_are_not_boundaries(self):
        """Harness-injected user entries must not cut the turn: the Task update before them still counts."""
        self.fx.enable_task_tools()
        self.fx.write(
            [
                prompt(),
                call("mcp__mytask__TaskUpdate", id="1", status="in_progress"),
                injected(
                    "Skill /writing-code was loaded earlier (see the invoked-skills reminder above)"
                ),
                edit(self.fx.repo_file("a.py")),
                injected(
                    "Stop hook feedback:\n[stop_checks.py]: continuation-claim: …"
                ),
                edit(self.fx.repo_file("b.py")),
                say("直しました"),
            ]
        )
        self.assertNotBlocked(
            run_hook(self.fx, "2 file を直しました。" + TAIL), "task-plan-first"
        )

    def test_c2_skill_reinvocation_entries_are_not_boundaries(self):
        """C2: skill-reminder-gate forces a skill re-invoke before commit, so its notice must not cut the turn."""
        self.fx.enable_task_tools()
        self.fx.write(
            [
                prompt(),
                call("mcp__mytask__TaskUpdate", id="1", status="in_progress"),
                injected(
                    "(Re-invocation of /writing-todos — the skill instructions were "
                    "previously loaded; the arguments or dynamic output below are new.)"
                ),
                edit(self.fx.repo_file("a.py")),
                bash("git commit -m 'fix'"),
                say("直しました"),
            ]
        )
        self.assertNotBlocked(
            run_hook(self.fx, "1 file を直しました。" + TAIL), "task-plan-first"
        )

    def test_c2_skill_preamble_blocks_are_not_boundaries(self):
        """C2: a skill's first invoke arrives as list content, which is never a boundary whatever its text."""
        self.fx.enable_task_tools()
        self.fx.write(
            [
                prompt(),
                call("mcp__mytask__TaskUpdate", id="1", status="in_progress"),
                skill_preamble("writing-todos"),
                edit(self.fx.repo_file("a.py")),
                bash("git commit -m 'fix'"),
                say("直しました"),
            ]
        )
        self.assertNotBlocked(
            run_hook(self.fx, "1 file を直しました。" + TAIL), "task-plan-first"
        )


class WarnScopeTest(StopChecksTest):
    """C3: warn scans the final text only, after NFKC and code/quote stripping."""

    def test_c3_wording_only_in_earlier_turn_text_is_not_rewarned(self):
        self.fx.turn(say("該当なしです。"))
        proc = run_hook(self.fx, "調査の結果を表にまとめました。" + TAIL)
        self.assertNotWarned(proc, "claim-without-evidence")

    def test_c3_wording_in_final_text_warns(self):
        self.fx.turn(say("調査しました"))
        self.assertWarnsFamily(
            run_hook(self.fx, "該当なしです。"), "claim-without-evidence"
        )

    def test_c3_quantity_is_not_a_self_number_reference(self):
        cases = (
            ("候補 17 件から選びました。", False),
            ("案 3 つを比較しました。", False),
            ("候補 12 を採用しました。", True),
            ("選択肢 3 を採用しました。", True),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.fx.turn(say("整理しました"))
                proc = run_hook(self.fx, text + TAIL)
                self.assertEqual(
                    "communication-lint" in warned(proc), expected, proc.stdout
                )

    def test_c3_fenced_and_quoted_text_is_stripped_before_warn(self):
        self.fx.turn(say("引用しました"))
        text = "検出例を引用します。\n```\n該当なし\n```\n> 該当なし\n" + TAIL
        proc = run_hook(self.fx, text)
        self.assertNotWarned(proc, "claim-without-evidence")


class ContinuationClaimTest(StopChecksTest):
    """C4: a future performance claim blocks unless running / done / stopped."""

    def test_c4_bare_future_declaration_blocks(self):
        self.fx.turn(say("整理しました"))
        self.assertBlocks(
            run_hook(self.fx, "この後 実装を進めます。"), "continuation-claim"
        )

    def test_c4_named_background_task_passes(self):
        self.fx.turn(
            bash("python3 build.py"),
            tool_result("Command running in background with ID: bg-77"),
            say("起動しました"),
        )
        proc = run_hook(self.fx, "bg-77 を起動しました。完了を待って続けます。" + TAIL)
        self.assertNotBlocked(proc, "continuation-claim")

    def test_c4_past_tense_backed_by_a_tool_call_passes(self):
        self.fx.turn(edit(self.fx.repo_file("impl.py")), say("編集しました"))
        proc = run_hook(self.fx, "実装を進めました。" + TAIL)
        self.assertNotBlocked(proc, "continuation-claim")

    def test_c4_explicit_stop_with_resume_condition_passes(self):
        self.fx.turn(say("整理しました"))
        text = "この後 実装を進めます — ここで停止し、再開条件は承認です。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), "continuation-claim")

    def test_c4_conditional_offer_passes(self):
        self.fx.turn(say("整理しました"))
        proc = run_hook(self.fx, "必要なら実装を進めます。" + TAIL)
        self.assertNotBlocked(proc, "continuation-claim")

    def test_c4_declaration_inside_a_fence_passes(self):
        self.fx.turn(say("整理しました"))
        text = "検出例を引用します。\n```\n実装を進めます\n```" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), "continuation-claim")


class DoneStateLedgerTest(StopChecksTest):
    """C5: a done word about commit / push / merge / gate / E2E needs its evidence."""

    def check(self, text: str, entries: list[dict], expected_block: bool) -> None:
        self.fx.write([prompt(), *entries, say("報告します")])
        proc = run_hook(self.fx, text + TAIL)
        if expected_block:
            self.assertBlocks(proc, "done-state-ledger")
        else:
            self.assertNotBlocked(proc, "done-state-ledger")

    def test_c5_commit_claim_requires_a_commit_command(self):
        self.check("commit まで完了しました。", [bash("git commit -m x")], False)
        self.check("commit まで完了しました。", [bash("git status")], True)

    def test_c5_git_global_options_still_count_as_evidence(self):
        """C5: the evidence matcher accepts git global options before the subcommand."""
        self.check(
            "commit まで完了しました。",
            [bash("git -C /repo commit -q -m x -- a.py")],
            False,
        )
        self.check(
            "push は完了です。",
            [bash("git -C /repo --no-pager push origin main")],
            False,
        )

    def test_c5_push_and_merge_claims_require_the_matching_command(self):
        self.check("push は完了です。", [bash("git push origin main")], False)
        self.check("push は完了です。", [bash("git log --oneline -3")], True)
        self.check("merge を完了しました。", [bash("git merge topic")], False)
        self.check("merge を完了しました。", [bash("git branch -a")], True)

    def test_c5_gate_and_e2e_claims_require_the_script_run(self):
        self.check("E2E は完了しました。", [bash("npm run e2e")], False)
        self.check("E2E は完了しました。", [read("/etc/hosts")], True)

    def test_c5_gate_claim_requires_the_gate_run(self):
        """Decree 5: a gate word plus a number or OK is a gate claim; the run must be in the turn."""
        self.check(
            "ruff は 0 件で完了しました。", [bash("ruff check --isolated x.py")], False
        )
        self.check("ruff は 0 件で完了しました。", [bash("git status")], True)
        self.check("契約 test の作成が完了しました。", [bash("git status")], False)

    def test_c5_edited_executable_requires_execution(self):
        path = self.fx.repo_file("tool.py")
        self.check("実装完了です。", [edit(path), bash(f"python3 {path}")], False)
        self.check("実装完了です。", [edit(path)], True)

    def test_c5_edited_ui_file_requires_a_screenshot(self):
        path = self.fx.repo_file("page.tsx")
        shot = call("mcp__playwright__browser_take_screenshot", filename="page.png")
        self.check("実装完了です。", [edit(path), shot], False)
        self.check("実装完了です。", [edit(path)], True)


class TaskPlanFirstTest(StopChecksTest):
    """C6: a prompt-answering turn upserts a Task before its first non-Task tool."""

    def setUp(self) -> None:
        super().setUp()
        self.fx.enable_task_tools()

    def work(self) -> list[dict]:
        return [edit(self.fx.repo_file("x.py")), edit(self.fx.repo_file("y.py"))]

    def test_c6_task_upsert_before_the_first_tool_passes(self):
        self.fx.write([prompt(), call("TaskCreate", subject="契約 test"), *self.work()])
        self.assertNotBlocked(
            run_hook(self.fx, "編集しました。" + TAIL), "task-plan-first"
        )

    def test_c6_task_upsert_after_the_first_tool_blocks(self):
        entries = self.work()
        self.fx.write([prompt(), entries[0], call("TaskUpdate", id="1"), entries[1]])
        self.assertBlocks(run_hook(self.fx, "編集しました。" + TAIL), "task-plan-first")

    def test_c6_turn_without_any_task_tool_blocks(self):
        self.fx.write([prompt(), *self.work()])
        self.assertBlocks(run_hook(self.fx, "編集しました。" + TAIL), "task-plan-first")

    def test_c6_tool_search_before_the_task_upsert_passes(self):
        """C6: loading the mytask schema is not work, so it may precede the upsert."""
        schema = call("ToolSearch", query="select:mcp__mytask__TaskCreate")
        self.fx.write(
            [prompt(), schema, call("TaskCreate", subject="契約"), *self.work()]
        )
        self.assertNotBlocked(
            run_hook(self.fx, "編集しました。" + TAIL), "task-plan-first"
        )

    def test_c6_tool_search_alone_does_not_count_as_an_upsert(self):
        schema = call("ToolSearch", query="select:mcp__mytask__TaskCreate")
        self.fx.write([prompt(), schema, *self.work()])
        self.assertBlocks(run_hook(self.fx, "編集しました。" + TAIL), "task-plan-first")

    def test_c6_turn_without_tool_calls_passes(self):
        self.fx.write([prompt(), say("説明しました")])
        self.assertClean(run_hook(self.fx, "仕様を説明しました。" + TAIL))

    def test_c6_single_read_answer_turn_passes(self):
        """Decree 1: at most two tool calls and no edit is an answer, not an unplanned work turn."""
        self.fx.write([prompt(), read("/etc/hosts")])
        self.assertNotBlocked(
            run_hook(self.fx, "設定を確認しました。" + TAIL), "task-plan-first"
        )

    def test_c6_continuation_turn_passes(self):
        self.fx.write(self.work())
        self.assertNotBlocked(
            run_hook(self.fx, "編集しました。" + TAIL), "task-plan-first"
        )

    def test_c6_gated_off_task_tool_session_passes(self):
        self.fx.gate_tasks_off()
        self.fx.write([prompt(), *self.work()])
        self.assertNotBlocked(
            run_hook(self.fx, "編集しました。" + TAIL), "task-plan-first"
        )


class TaskLedgerDriftTest(StopChecksTest):
    """C7: work without any task record warns (never blocks)."""

    def test_c7_two_edited_paths_pass(self):
        self.fx.write(
            [prompt(), edit(self.fx.repo_file("a.py")), edit(self.fx.repo_file("b.py"))]
        )
        self.assertNotWarned(
            run_hook(self.fx, "編集しました。" + TAIL), "task-ledger-drift"
        )

    def test_c7_three_edited_paths_warn(self):
        self.fx.write(
            [
                prompt(),
                edit(self.fx.repo_file("a.py")),
                edit(self.fx.repo_file("b.py")),
                edit(self.fx.repo_file("c.py")),
            ]
        )
        self.assertWarnsFamily(
            run_hook(self.fx, "編集しました。" + TAIL), "task-ledger-drift"
        )

    def test_c7_deferral_wording_warns(self):
        self.fx.turn(say("整理しました"))
        proc = run_hook(self.fx, "この件は別タスクに切り出します。" + TAIL)
        self.assertWarnsFamily(proc, "task-ledger-drift")

    def test_c7_non_empty_task_store_passes(self):
        self.fx.native_task("契約 test を書く", status="completed")
        self.fx.write(
            [
                prompt(),
                edit(self.fx.repo_file("a.py")),
                edit(self.fx.repo_file("b.py")),
                edit(self.fx.repo_file("c.py")),
            ]
        )
        self.assertNotWarned(
            run_hook(self.fx, "編集しました。" + TAIL), "task-ledger-drift"
        )


class RulingWithoutReadingTest(StopChecksTest):
    """C8: a ruling that names entry paths must have opened them this turn."""

    ONE = "`drafts/prep/alpha.md` の方針は妥当と判断しました。"

    def test_c8_ruling_on_a_read_path_passes(self):
        self.fx.write([prompt(), *SUBAGENT, read("drafts/prep/alpha.md")])
        self.assertNotBlocked(
            run_hook(self.fx, self.ONE + TAIL), "ruling-without-reading"
        )

    def test_c8_ruling_on_an_unread_path_blocks(self):
        self.fx.write([prompt(), *SUBAGENT])
        self.assertBlocks(run_hook(self.fx, self.ONE + TAIL), "ruling-without-reading")

    def test_c8_block_lists_only_the_unopened_paths(self):
        self.fx.write([prompt(), *SUBAGENT, read("drafts/prep/alpha.md")])
        text = (
            "`drafts/prep/alpha.md` `drafts/prep/beta.md` `drafts/prep/gamma.md` "
            "を読み、いずれも妥当と判断しました。"
        )
        proc = run_hook(self.fx, text + TAIL)
        self.assertBlocks(proc, "ruling-without-reading")
        line = next(
            item
            for item in block_lines(proc)
            if family_of(item) == "ruling-without-reading"
        )
        self.assertIn("beta.md", line)
        self.assertIn("gamma.md", line)
        self.assertNotIn("alpha.md", line)

    def test_c8_workflow_result_turn_blocks_the_same_way(self):
        """A Workflow result reaches the turn as a task-notification, not as an Agent call."""
        self.fx.write(
            [
                prompt(),
                injected(
                    "<task-notification><task-id>wf-1</task-id>"
                    "<status>completed</status></task-notification>"
                ),
            ]
        )
        self.assertBlocks(run_hook(self.fx, self.ONE + TAIL), "ruling-without-reading")

    def test_c8_turn_without_a_subagent_result_passes(self):
        self.fx.write([prompt(), say("整理しました")])
        self.assertNotBlocked(
            run_hook(self.fx, self.ONE + TAIL), "ruling-without-reading"
        )

    def test_c8_quoted_task_notification_is_not_a_workflow_result(self):
        """C8: a peer quoting the hook's own source names the token; only a real notification counts."""
        self.fx.write(
            [
                prompt(
                    "PROMPT_PREFIXES を直してください。\n\n```python\n"
                    'PROMPT_PREFIXES = ("<task-notification>", "<system-reminder>")\n'
                    "```\n"
                ),
                say("整理しました"),
            ]
        )
        self.assertNotBlocked(
            run_hook(self.fx, self.ONE + TAIL), "ruling-without-reading"
        )

    def test_c8_inline_quoted_task_notification_is_not_a_workflow_result(self):
        """C8: an inline-backticked mention is a mention; a real notification arrives unquoted."""
        self.fx.write(
            [
                prompt("`<task-notification>` の扱いを教えてください。"),
                say("整理しました"),
            ]
        )
        self.assertNotBlocked(
            run_hook(self.fx, self.ONE + TAIL), "ruling-without-reading"
        )


class WindDownTest(StopChecksTest):
    """C9 / C10: a declared wind-down leaves no open task and no unreaped background id."""

    def setUp(self) -> None:
        super().setUp()
        self.fx.turn(say("片付けました"))

    def test_c9_open_task_after_wind_down_blocks(self):
        self.fx.wind_down()
        self.fx.native_task("契約 test を書く", status="in_progress")
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertBlocks(proc, "wind-down-open-tasks")
        self.assertIn("契約 test を書く", proc.stderr)

    def test_c9_no_open_task_after_wind_down_passes(self):
        self.fx.wind_down()
        self.fx.native_task("契約 test を書く", status="completed")
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertNotBlocked(proc, "wind-down-open-tasks")

    def test_c9_open_task_after_a_later_ordinary_prompt_passes(self):
        """C9 follows the latest prompt: a resumed session may hold open tasks again."""
        self.fx.wind_down(latest=False)
        self.fx.native_task("契約 test を書く", status="in_progress")
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertNotBlocked(proc, "wind-down-open-tasks")

    def test_c9_open_task_without_wind_down_passes(self):
        self.fx.native_task("契約 test を書く", status="in_progress")
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertNotBlocked(proc, "wind-down-open-tasks")

    def test_c9_missing_session_id_passes(self):
        self.fx.wind_down()
        self.fx.native_task("契約 test を書く", status="in_progress")
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL, session_id=None)
        self.assertNotBlocked(proc, "wind-down-open-tasks")

    def launches(self, notified: tuple[str, ...]) -> None:
        entries = [
            prompt(),
            bash("python3 long.py"),
            tool_result("Command running in background with ID: bg-1"),
            call("Skill", skill="loop"),
            tool_result("Workflow launched in background. Task ID: bg-2"),
        ]
        for task_id in notified:
            entries.append(
                injected(
                    f"<task-notification><task-id>{task_id}</task-id>"
                    "<status>completed</status></task-notification>"
                )
            )
        entries.append(say("片付けました"))
        self.fx.write(entries)

    def test_c10_unreaped_background_id_blocks(self):
        self.fx.wind_down()
        self.launches(("bg-1",))
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertBlocks(proc, "wind-down-background-unreaped")
        self.assertIn("bg-2", proc.stderr)

    def test_c10_all_ids_notified_passes(self):
        self.fx.wind_down()
        self.launches(("bg-1", "bg-2"))
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertNotBlocked(proc, "wind-down-background-unreaped")

    def test_c10_after_a_later_ordinary_prompt_passes(self):
        self.fx.wind_down(latest=False)
        self.launches(("bg-1",))
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertNotBlocked(proc, "wind-down-background-unreaped")

    def test_c10_without_wind_down_passes(self):
        self.launches(())
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertNotBlocked(proc, "wind-down-background-unreaped")

    def window(self, padding: int) -> None:
        """One unreaped launch, then `padding` bytes of filler that push it toward the window edge."""
        self.fx.write(
            [
                prompt(),
                bash("python3 long.py"),
                tool_result("Command running in background with ID: bg-1"),
            ],
            extra_lines=self.fx.filler(padding),
        )

    def test_c10_notification_without_a_launch_warns_instead_of_blocking(self):
        """Decree 3: a notified id with no launch proves the window missed the launch."""
        self.fx.wind_down()
        self.launches(("bg-9",))
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertWarnsFamily(proc, "wind-down-background-unreaped")
        self.assertIn("窓外", warn_body(proc))

    def test_c10_launch_inside_the_window_blocks(self):
        self.fx.wind_down()
        self.window(1_500_000)
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertBlocks(proc, "wind-down-background-unreaped")
        self.assertIn("bg-1", proc.stderr)

    def test_c10_launch_beyond_the_window_does_not_block(self):
        """Decree 3: the 2 MB cap is an upper bound, and an unobserved launch never blocks."""
        self.fx.wind_down()
        self.window(3_000_000)
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertNotBlocked(proc, "wind-down-background-unreaped")


class HandoffMarkerTest(StopChecksTest):
    """C11: a handoff doc written at wind-down carries the full session id."""

    def handoff(self, marker_text: str) -> str:
        return self.fx.repo_file(
            "docs/handoff/2026-08-27.md", f"# handoff\n\nsession: {marker_text}\n"
        )

    def test_c11_full_session_id_passes(self):
        self.fx.wind_down()
        path = self.handoff(SESSION)
        self.fx.turn(edit(path), say("書きました"))
        proc = run_hook(self.fx, "handoff を書きました。" + TAIL)
        self.assertNotBlocked(proc, "handoff-doc-without-marker")

    def test_c11_truncated_session_id_blocks(self):
        self.fx.wind_down()
        path = self.handoff(SESSION[:8])
        self.fx.turn(edit(path), say("書きました"))
        proc = run_hook(self.fx, "handoff を書きました。" + TAIL)
        self.assertBlocks(proc, "handoff-doc-without-marker")
        self.assertIn("2026-08-27.md", proc.stderr)

    def test_c11_declaration_outlives_a_later_ordinary_prompt(self):
        """C11 keys on the sticky declaration, not on the latest-prompt flag."""
        self.fx.wind_down(latest=False)
        path = self.handoff(SESSION[:8])
        self.fx.turn(edit(path), say("書きました"))
        proc = run_hook(self.fx, "handoff を書きました。" + TAIL)
        self.assertBlocks(proc, "handoff-doc-without-marker")

    def test_c11_marker_in_the_final_text_passes(self):
        """C11 accepts the marker on either side: the doc body or the final text."""
        self.fx.wind_down()
        path = self.handoff("(本文側に書く)")
        self.fx.turn(edit(path), say("書きました"))
        proc = run_hook(self.fx, f"handoff を書きました。session: {SESSION}" + TAIL)
        self.assertNotBlocked(proc, "handoff-doc-without-marker")

    def test_c11_without_a_handoff_doc_edit_passes(self):
        self.fx.wind_down()
        self.fx.turn(edit(self.fx.repo_file("notes.md")), say("書きました"))
        proc = run_hook(self.fx, "notes を書きました。" + TAIL)
        self.assertNotBlocked(proc, "handoff-doc-without-marker")


class SelfReportHonestyTest(StopChecksTest):
    """C12: five self-report rules, each with its pairing escape."""

    FAMILY = "self-report-honesty"

    def test_c12_meta_announce_of_a_non_action_blocks(self):
        self.fx.turn(say("整理しました"))
        text = "rule に従って CLAUDE.md には触れません。" + TAIL
        self.assertBlocks(run_hook(self.fx, text), self.FAMILY)

    def test_c12_meta_announce_of_a_real_action_passes(self):
        """Rule 1 fires on announcing a non-action, not on naming the rule behind a real edit."""
        self.fx.turn(
            edit(self.fx.repo_file(".claude/skills/x/SKILL.md")), say("書きました")
        )
        text = "rule に従って skill を追加しました。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)

    def test_c12_introspection_without_persistence_write(self):
        text = "同じ誤りを繰り返した点を反省しました。" + TAIL
        self.fx.turn(say("整理しました"))
        self.assertBlocks(run_hook(self.fx, text), self.FAMILY)
        self.fx.turn(
            edit(self.fx.repo_file(".claude/skills/x/SKILL.md")), say("書きました")
        )
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)

    def test_c12_surprise_at_own_work_without_git_history(self):
        text = "いつの間にか構造が変わっていました。" + TAIL
        self.fx.turn(say("整理しました"))
        self.assertBlocks(run_hook(self.fx, text), self.FAMILY)
        self.fx.turn(bash("git log --oneline -5"), say("確認しました"))
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)

    def test_c12_euphemism_for_own_error_blocks(self):
        self.fx.turn(say("整理しました"))
        blocked_text = "先の報告は誤解を招く記述でした。" + TAIL
        self.assertBlocks(run_hook(self.fx, blocked_text), self.FAMILY)
        passing_text = "この label 名は誤解を招く命名なので変えます。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, passing_text), self.FAMILY)

    def test_c12_blurred_attribution_near_an_error_word_blocks(self):
        self.fx.turn(say("整理しました"))
        near = "既存のパターンを踏襲したのが誤りでした。" + TAIL
        self.assertBlocks(run_hook(self.fx, near), self.FAMILY)
        far = (
            "既存のパターンを踏襲しました。"
            "契約 test の family 構成を表にまとめ、各 claim の対応を確認し、"
            "変異器の seam も並べて整理し、証跡の種別まで数え上げました。"
            "その上で誤りを直しました。"
        )
        self.assertNotBlocked(run_hook(self.fx, far + TAIL), self.FAMILY)


class OffloadToUserTest(StopChecksTest):
    """C13: decisions and executions the model can make itself are not handed to the user."""

    FAMILY = "offload-to-user"
    # Decree 2: the warn rule lives in its own family so one id never spans both exits.
    WARN_FAMILY = "host-command-format"

    def test_c13_ordering_question_blocks(self):
        self.fx.turn(say("整理しました"))
        text = "test と変異器、どちらを先に着手しましょうか。"
        self.assertBlocks(run_hook(self.fx, text), self.FAMILY)

    def test_c13_binary_routing_question_blocks(self):
        self.fx.turn(say("整理しました"))
        text = "先に実装するか調査するかを決めてください。"
        self.assertBlocks(run_hook(self.fx, text), self.FAMILY)

    def test_c13_bang_prefix_execution_request_blocks(self):
        self.fx.turn(say("整理しました"))
        text = "`!` を付けて実行してください。"
        self.assertBlocks(run_hook(self.fx, text), self.FAMILY)

    def test_c13_bang_prefix_inside_a_fence_passes(self):
        """m1 seam: a quoted example of the ! form is not a request to the user."""
        self.fx.turn(say("整理しました"))
        text = "検出例を引用します。\n```\n`!` を付けて実行してください\n```" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)

    def test_c13_declare_and_proceed_invoke_passes_the_routing_rule(self):
        self.fx.turn(call("Skill", skill="declare-and-proceed"), say("整理しました"))
        text = "先に実装するか調査するかを決めてください。"
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)

    def test_c13_unfenced_host_command_warns(self):
        self.fx.turn(say("整理しました"))
        text = "お手元で `git push origin main` を実行してください。" + TAIL
        self.assertWarnsFamily(run_hook(self.fx, text), self.WARN_FAMILY)

    def test_c13_fenced_host_command_passes(self):
        self.fx.turn(say("整理しました"))
        text = (
            "お手元のターミナルで実行してください。\n\n"
            "```bash\ngit push origin main\n```" + TAIL
        )
        self.assertNotWarned(run_hook(self.fx, text), self.WARN_FAMILY)

    def test_c13_fenced_command_with_a_bare_basename_warns(self):
        """A path the user cannot paste from the repo root is still an unusable instruction."""
        self.fx.turn(say("整理しました"))
        text = (
            "お手元のターミナルで実行してください。\n\n"
            "```bash\npython3 stop_checks.test.py\n```" + TAIL
        )
        self.assertWarnsFamily(run_hook(self.fx, text), self.WARN_FAMILY)

    def test_c13_block_and_warn_never_share_a_family_id(self):
        self.fx.turn(say("整理しました"))
        blocking = run_hook(self.fx, "test と変異器、どちらを先に着手しましょうか。")
        warning = run_hook(
            self.fx, "お手元で `git push origin main` を実行してください。" + TAIL
        )
        self.assertFalse(blocked(blocking) & warned(warning), "severity split by id")


class ClaimWithoutEvidenceTest(StopChecksTest):
    """C14: unbacked assertions warn and never block."""

    FAMILY = "claim-without-evidence"
    CLAIMS = (
        "該当なしです。",
        "これは大改造になります。",
        "autosquash は非対話では実行できません。",
        "全て確認しました。",
    )

    def test_c14_claims_without_an_evidence_tool_warn(self):
        for claim in self.CLAIMS:
            with self.subTest(claim=claim):
                self.fx.turn(say("報告します"))
                self.assertWarnsFamily(run_hook(self.fx, claim + TAIL), self.FAMILY)

    def test_c14_claims_with_an_evidence_tool_pass(self):
        for claim in self.CLAIMS:
            with self.subTest(claim=claim):
                self.fx.turn(read("/etc/hosts"), say("読みました"))
                self.assertNotWarned(run_hook(self.fx, claim + TAIL), self.FAMILY)

    def test_c14_never_blocks(self):
        for claim in self.CLAIMS:
            for entries in ([say("報告します")], [read("/etc/hosts")]):
                with self.subTest(claim=claim, evidence=len(entries)):
                    self.fx.turn(*entries)
                    proc = run_hook(self.fx, claim + TAIL)
                    self.assertEqual(proc.returncode, 0, proc.stderr)


class CommunicationLintTest(StopChecksTest):
    """C15: five delivery rules on the final text and the latest user prompt."""

    FAMILY = "communication-lint"

    def test_c15_final_line_without_emoji_or_question_warns(self):
        self.fx.turn(say("報告します"))
        self.assertWarnsFamily(run_hook(self.fx, "調査を終えました。"), self.FAMILY)

    def test_c15_full_width_self_number_reference_warns(self):
        self.fx.turn(say("報告します"))
        self.assertWarnsFamily(
            run_hook(self.fx, "候補１２を採用しました。" + TAIL), self.FAMILY
        )

    def test_c15_question_without_an_open_decision_task_warns(self):
        self.fx.turn(say("報告します"))
        self.assertWarnsFamily(
            run_hook(self.fx, "どの案を採るべきでしょうか？"), self.FAMILY
        )

    def test_c15_short_ruling_prompt_with_an_open_decision_task_warns(self):
        self.fx.native_task("決裁待ち: 変異器の形式", status="pending")
        self.fx.write([prompt("採用"), say("反映しました")])
        self.assertWarnsFamily(run_hook(self.fx, "反映しました。" + TAIL), self.FAMILY)

    def test_c15_question_referring_to_an_earlier_turn_warns(self):
        self.fx.native_task("決裁待ち: 変異器の形式", status="pending")
        self.fx.turn(say("報告します"))
        text = "先ほどの案について、次はどこを見ればよいでしょうか？"
        self.assertWarnsFamily(run_hook(self.fx, text), self.FAMILY)

    def test_c15_decision_task_is_recognised_by_its_wording(self):
        """Decree 7: only 決裁 / 裁定 / 判断待ち / 承認待ち / 要確認 make a task a decision task."""
        question = "\U0001f537 [質問] どの案を採るべきでしょうか？"
        self.fx.native_task("契約 test を書く", status="pending")
        self.fx.turn(say("報告します"))
        self.assertWarnsFamily(run_hook(self.fx, question), self.FAMILY)
        self.fx.native_task("変異器の形式を裁定する", status="pending")
        self.assertNotWarned(run_hook(self.fx, question), self.FAMILY)

    def test_c15_final_line_without_a_tag_warns(self):
        """C15 rule 1: the emoji alone no longer says whether the turn concluded or asked."""
        self.fx.turn(say("報告します"))
        self.assertWarnsFamily(
            run_hook(self.fx, "調査を終えました。\n\n\U0001f537 以上です。"),
            self.FAMILY,
        )

    def test_c15_a_tag_that_contradicts_the_ending_warns(self):
        self.fx.native_task("決裁待ち: 変異器の形式", status="pending")
        self.fx.turn(say("報告します"))
        for text in (
            "\U0001f537 [結論] どの案を採るべきでしょうか？",
            "\U0001f537 [質問] 調査を終えました。",
        ):
            self.assertWarnsFamily(run_hook(self.fx, text), self.FAMILY)

    def test_c15_a_tag_after_the_prose_does_not_count(self):
        """C15 rule 1: only the emoji and spacing may precede the tag."""
        self.fx.turn(say("報告します"))
        self.assertWarnsFamily(
            run_hook(self.fx, "\U0001f537 調査を終えました [結論]。"), self.FAMILY
        )

    def test_c15_a_tagged_question_passes(self):
        self.fx.native_task("決裁待ち: 変異器の形式", status="pending")
        self.fx.turn(say("報告します"))
        self.assertNotWarned(
            run_hook(self.fx, "\U0001f537 [質問] どの案を採りますか?"), self.FAMILY
        )

    def test_c15_a_fact_label_is_not_a_final_line_tag(self):
        """C15 rule 1: [事実] appears anywhere in the body, so rule 1 ignores it."""
        self.fx.turn(say("報告します"))
        self.assertWarnsFamily(
            run_hook(self.fx, "\U0001f537 [事実] 調査を終えました。"), self.FAMILY
        )

    def test_c15_emoji_led_conclusion_passes(self):
        self.fx.turn(say("報告します"))
        self.assertNotWarned(
            run_hook(self.fx, "調査を終えました。" + TAIL), self.FAMILY
        )

    def test_c15_technical_symbol_emoji_led_conclusion_passes(self):
        """C15 rule 1: U+2300 block (⏸ U+23F8, ⌛ U+231B) counts as emoji-led."""
        self.fx.turn(say("報告します"))
        for lead in ("\u23f8\ufe0f", "\u231b"):
            self.assertNotWarned(
                run_hook(self.fx, "調査を終えました。\n\n" + lead + " [結論] 停止中。"),
                self.FAMILY,
            )


class MemoryReminderTest(StopChecksTest):
    """C16: `check:` entries scoped to stop, surfaced once with one closing sentence."""

    FAMILY = "memory-reminder"
    CLOSING = "抵触するなら修正してから完了。しなければ何も書かない"

    def test_c16_stop_scoped_entry_is_surfaced(self):
        self.fx.memory_entry("alpha", "完了語の証跡が turn 内にあるか確認せよ")
        self.fx.turn(say("報告します"))
        proc = run_hook(self.fx, "調査を終えました。" + TAIL)
        self.assertWarnsFamily(proc, self.FAMILY)
        self.assertIn("完了語の証跡が turn 内にあるか確認せよ", warn_body(proc))

    def test_c16_prompt_only_entry_is_not_surfaced(self):
        self.fx.memory_entry("beta", "prompt 時にだけ効く check", when="prompt")
        self.fx.turn(say("報告します"))
        self.assertNotWarned(
            run_hook(self.fx, "調査を終えました。" + TAIL), self.FAMILY
        )

    def test_c16_closing_sentence_appears_once(self):
        """Only the best keyword match surfaces, with the closing sentence once."""
        self.fx.memory_entry("alpha", "証跡を確認せよ", keywords="調査, 証跡")
        self.fx.memory_entry("gamma", "台帳を確認せよ", keywords="調査, 台帳")
        self.fx.turn(say("報告します"))
        body = warn_body(run_hook(self.fx, "証跡の調査を終えました。" + TAIL))
        self.assertIn("証跡を確認せよ", body)
        self.assertNotIn("台帳を確認せよ", body)
        self.assertEqual(body.count(self.CLOSING), 1, body)

    def test_c16_entry_without_a_keyword_hit_stays_silent(self):
        self.fx.memory_entry("delta", "台帳を確認せよ", keywords="台帳")
        self.fx.turn(say("報告します"))
        proc = run_hook(self.fx, "調査を終えました。" + TAIL)
        self.assertNotWarned(proc, self.FAMILY)

    def test_c16_same_entry_surfaces_at_most_twice_per_session(self):
        """The latch counts only Stops whose line reached stdout: a blocked Stop does not consume it."""
        self.fx.memory_entry("alpha", "証跡を確認せよ")
        self.fx.turn(say("報告します"))
        self.assertBlocks(
            run_hook(self.fx, "この後 調査を進めます。"), "continuation-claim"
        )
        text = "調査を終えました。" + TAIL
        self.assertWarnsFamily(run_hook(self.fx, text), self.FAMILY)
        self.assertWarnsFamily(run_hook(self.fx, text), self.FAMILY)
        self.assertNotWarned(run_hook(self.fx, text), self.FAMILY)

    def test_c16_waste_keyword_line_appears_once_per_prompt(self):
        self.fx.write([prompt("この待ち時間は無駄では?"), say("報告します")])
        first = run_hook(self.fx, "調査を終えました。" + TAIL)
        self.assertIn("無駄", warn_body(first))
        second = run_hook(self.fx, "調査を終えました。" + TAIL)
        self.assertNotIn("無駄", warn_body(second))

    def test_c16_waste_keyword_line_returns_for_a_new_prompt(self):
        """Decree 6: the latch key is the prompt boundary identity, not the session or transcript."""
        text = "調査を終えました。" + TAIL
        self.fx.write(
            [prompt("この待ち時間は無駄では?", uid="prompt-1"), say("報告します")]
        )
        self.assertIn("無駄", warn_body(run_hook(self.fx, text)))
        self.assertNotIn("無駄", warn_body(run_hook(self.fx, text)))
        self.fx.write(
            [prompt("この待ち時間も無駄では?", uid="prompt-2"), say("報告します")]
        )
        self.assertIn("無駄", warn_body(run_hook(self.fx, text)))

    def test_c16_missing_clone_passes(self):
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx,
            "調査を終えました。" + TAIL,
            memory_root=os.path.join(self.fx.tmp, "absent"),
        )
        self.assertClean(proc)

    def test_c16_only_the_current_project_scope_is_surfaced(self):
        """Project entries of other repos never surface; the cwd fallback id selects this repo's dir."""
        own = os.path.join(self.fx.memory, "project", self.fx.cwd.replace("/", "-"))
        other = os.path.join(self.fx.memory, "project", "github.com-x-other")
        for base, name in ((own, "mine"), (other, "theirs")):
            os.makedirs(base, exist_ok=True)
            with open(
                os.path.join(base, name + ".md"), "w", encoding="utf-8"
            ) as stream:
                stream.write(
                    f"---\nname: {name}\nkeywords: 調査\ncheck: {name} を確認せよ\nwhen: stop\n---\n"
                )
        self.fx.turn(say("報告します"))
        body = warn_body(run_hook(self.fx, "調査を終えました。" + TAIL))
        self.assertIn("mine を確認せよ", body)
        self.assertNotIn("theirs を確認せよ", body)

    def test_c16_project_id_comes_from_the_origin_url(self):
        """A repo with an origin remote maps to github.com-<owner>-<repo> without running git."""
        os.makedirs(os.path.join(self.fx.cwd, ".git"), exist_ok=True)
        with open(
            os.path.join(self.fx.cwd, ".git", "config"), "w", encoding="utf-8"
        ) as stream:
            stream.write(
                '[core]\n\tbare = false\n[remote "origin"]\n\turl = git@github.com:alice/proj.git\n'
            )
        base = os.path.join(self.fx.memory, "project", "github.com-alice-proj")
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, "own.md"), "w", encoding="utf-8") as stream:
            stream.write(
                "---\nname: own\nkeywords: 調査\ncheck: origin 由来の entry を確認せよ\nwhen: stop\n---\n"
            )
        self.fx.turn(say("報告します"))
        self.assertIn(
            "origin 由来の entry を確認せよ",
            warn_body(run_hook(self.fx, "調査を終えました。" + TAIL)),
        )


class TurnMarkerTest(StopChecksTest):
    """C17: the pass-only marker and its counter file."""

    CLEAN = "調査を終えました。" + TAIL

    def setUp(self) -> None:
        super().setUp()
        self.fx.turn(say("報告します"))

    def test_c17_consecutive_passes_increment_the_turn_number(self):
        self.assertIn("Turn #1", marker(run_hook(self.fx, self.CLEAN)))
        self.assertIn("Turn #2", marker(run_hook(self.fx, self.CLEAN)))

    def test_c17_warn_stop_does_not_bump_the_counter(self):
        self.assertIn("Turn #1", marker(run_hook(self.fx, self.CLEAN)))
        run_hook(self.fx, "該当なしです。")
        self.assertIn("Turn #2", marker(run_hook(self.fx, self.CLEAN)))

    def test_c17_marker_carries_no_additional_context(self):
        proc = run_hook(self.fx, self.CLEAN)
        data = json.loads(proc.stdout.splitlines()[0])
        self.assertIn("systemMessage", data)
        self.assertNotIn("hookSpecificOutput", data)

    def test_c17_unreadable_counter_file_emits_no_marker(self):
        os.mkdir(self.fx.transcript[: -len(".jsonl")] + ".turns")
        proc = run_hook(self.fx, self.CLEAN)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(marker(proc), "", proc.stdout)

    def test_c17_existing_turns_file_format_is_preserved(self):
        self.fx.turns_file("7 1000\n")
        self.assertIn("Turn #8", marker(run_hook(self.fx, self.CLEAN)))
        count, epoch = self.fx.read_turns().split()
        self.assertEqual(count, "8")
        self.assertGreater(int(epoch), 1000)


class PurityTest(StopChecksTest):
    """C18: stdlib only, no sibling-hook import, no child process, deterministic output."""

    def source(self) -> str:
        with open(HOOK, encoding="utf-8") as stream:
            return stream.read()

    def test_c18_source_has_no_subprocess_or_cross_hook_import(self):
        source = self.source()
        for banned in ("subprocess", "os.popen", "os.system", "os.exec"):
            self.assertNotIn(banned, source)
        self.assertNotIn("memory_surface", source)
        self.assertNotIn("check_uncommitted", source)

    def test_c18_imports_are_stdlib_only(self):
        roots = set()
        for node in ast.walk(ast.parse(self.source())):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                roots.add(node.module.split(".")[0])
        outside = roots - set(sys.stdlib_module_names)
        self.assertFalse(outside, sorted(outside))

    def test_c18_family_ids_stay_inside_the_contracted_set(self):
        """Decree 8: the four dropped families are gone from the source and from every exit."""
        source = self.source()
        for family in DROPPED_FAMILIES:
            self.assertNotIn(family, source)
        seen: set[str] = set()
        for entries, final in (
            ([say("作業しました")], "この後 実装を進めます。"),
            ([say("報告します")], "該当なしです。"),
            ([say("調査しました")], "調査の結果を表にまとめました。" + TAIL),
        ):
            self.fx.turn(*entries)
            proc = run_hook(self.fx, final)
            seen |= blocked(proc) | warned(proc)
        self.assertTrue(seen, "the battery must exercise at least one family")
        self.assertFalse(seen - ALLOWED_FAMILIES, sorted(seen - ALLOWED_FAMILIES))

    def test_c18_identical_input_yields_identical_output(self):
        self.fx.turn(say("報告します"))
        first = run_hook(self.fx, "該当なしです。")
        second = run_hook(self.fx, "該当なしです。")
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, second.stderr)
        self.assertEqual(first.returncode, second.returncode)


class FixtureSubstitutionTest(StopChecksTest):
    """C19: the memory clone root and every state path are redirectable for tests."""

    def test_c19_memory_clone_root_is_env_substitutable(self):
        self.fx.memory_entry("alpha", "証跡を確認せよ")
        self.fx.turn(say("報告します"))
        text = "調査を終えました。" + TAIL
        self.assertWarnsFamily(run_hook(self.fx, text), "memory-reminder")
        empty = os.path.join(self.fx.tmp, "empty-clone")
        os.makedirs(empty, exist_ok=True)
        proc = run_hook(self.fx, text, memory_root=empty)
        self.assertNotWarned(proc, "memory-reminder")

    def test_c19_state_resolves_under_the_temp_home(self):
        self.fx.turn(say("報告します"))
        self.assertClean(run_hook(self.fx, "調査を終えました。" + TAIL))
        self.fx.wind_down()
        self.fx.native_task("契約 test を書く", status="in_progress")
        proc = run_hook(self.fx, "調査を終えました。" + TAIL)
        self.assertBlocks(proc, "wind-down-open-tasks")


class MemoryCloneRootsTest(StopChecksTest):
    """C19: without the single-valued seam, C16 scans every clone load_clones() returns."""

    FAMILY = "memory-reminder"

    def clone(self, root: str, name: str, check: str) -> str:
        path = os.path.join(root, "org", name + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(
                "---\n"
                f"name: {name}\n"
                "description: 契約 test の fixture entry\n"
                "keywords: 調査, 契約\n"
                f"check: {check}\n"
                "when: prompt stop\n"
                "---\n\n## 理由\n\nfixture\n"
            )
        return path

    def cli(self, body: str) -> dict[str, str]:
        """A stand-in claude_memory_sync; the real parser has its own contract test."""
        path = os.path.join(self.fx.tmp, "sync_cli_" + str(len(body)))
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(body)
        return {"CLAUDE_MEMORY_SYNC_CLI": path}

    def returning(self, *paths: str) -> dict[str, str]:
        listed = ", ".join(f"C({path!r})" for path in paths)
        return self.cli(
            "from typing import NamedTuple\n"
            "class C(NamedTuple):\n"
            "    path: str\n"
            f"def load_clones():\n    return [{listed}]\n"
        )

    def test_c19_the_single_valued_seam_wins_over_the_configured_clones(self):
        other = os.path.join(self.fx.tmp, "other-clone")
        self.clone(other, "beta", "設定側の entry")
        self.fx.memory_entry("alpha", "seam 側の entry")
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx, "調査を終えました。" + TAIL, env_extra=self.returning(other)
        )
        self.assertWarnsFamily(proc, self.FAMILY)
        self.assertIn("seam 側の entry", warn_body(proc))
        self.assertNotIn("設定側の entry", warn_body(proc))

    def test_c19_an_entry_in_any_returned_clone_is_surfaced(self):
        first = os.path.join(self.fx.tmp, "clone-a")
        second = os.path.join(self.fx.tmp, "clone-b")
        os.makedirs(os.path.join(first, "org"), exist_ok=True)
        self.clone(second, "beta", "二つ目の clone の entry")
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx,
            "調査を終えました。" + TAIL,
            memory_root="",
            env_extra=self.returning(first, second),
        )
        self.assertWarnsFamily(proc, self.FAMILY)
        self.assertIn("二つ目の clone の entry", warn_body(proc))

    def test_c19_an_empty_clone_list_falls_back_to_the_default_root(self):
        state = os.path.join(self.fx.tmp, "empty-list")
        self.clone(
            os.path.join(state, "claude-lessons-learned"), "alpha", "既定の entry"
        )
        env = self.returning()
        env["CLAUDE_MEMORY_ROOT"] = state
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx, "調査を終えました。" + TAIL, memory_root="", env_extra=env
        )
        self.assertWarnsFamily(proc, self.FAMILY)
        self.assertIn("既定の entry", warn_body(proc))

    def test_c19_a_cli_without_load_clones_falls_back_to_the_default_root(self):
        state = os.path.join(self.fx.tmp, "old-cli")
        self.clone(
            os.path.join(state, "claude-lessons-learned"), "alpha", "旧 CLI の entry"
        )
        other = os.path.join(self.fx.tmp, "unreachable")
        self.clone(other, "beta", "旧 CLI では出ない entry")
        env = self.cli("PUBLIC = 'public'\n")  # pre-split build: no load_clones
        env["CLAUDE_MEMORY_ROOT"] = state
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx, "調査を終えました。" + TAIL, memory_root="", env_extra=env
        )
        self.assertWarnsFamily(proc, self.FAMILY)
        self.assertIn("旧 CLI の entry", warn_body(proc))
        self.assertNotIn("旧 CLI では出ない entry", warn_body(proc))

    def test_c19_a_raising_cli_falls_back_to_the_default_root(self):
        state = os.path.join(self.fx.tmp, "raising-cli")
        self.clone(
            os.path.join(state, "claude-lessons-learned"), "alpha", "例外時の entry"
        )
        env = self.cli("raise RuntimeError('boom')\n")
        env["CLAUDE_MEMORY_ROOT"] = state
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx, "調査を終えました。" + TAIL, memory_root="", env_extra=env
        )
        self.assertWarnsFamily(proc, self.FAMILY)
        self.assertIn("例外時の entry", warn_body(proc))

    def test_c19_a_present_but_unreadable_config_scans_nothing(self):
        """既定 layout を推測すると public clone を private として読む経路が開く。"""
        state = os.path.join(self.fx.tmp, "unreadable-conf")
        self.clone(
            os.path.join(state, "claude-lessons-learned"), "alpha", "既定の entry"
        )
        os.makedirs(os.path.join(state, "clones.conf"), exist_ok=True)
        env = self.cli("def load_clones():\n    raise OSError('unreadable')\n")
        env["CLAUDE_MEMORY_ROOT"] = state
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx, "調査を終えました。" + TAIL, memory_root="", env_extra=env
        )
        self.assertNotWarned(proc, self.FAMILY)

    def test_c19_a_missing_cli_falls_back_to_the_default_root(self):
        state = os.path.join(self.fx.tmp, "no-cli")
        self.clone(
            os.path.join(state, "claude-lessons-learned"), "alpha", "CLI 不在の entry"
        )
        self.fx.turn(say("報告します"))
        proc = run_hook(
            self.fx,
            "調査を終えました。" + TAIL,
            memory_root="",
            env_extra={
                "CLAUDE_MEMORY_ROOT": state,
                "CLAUDE_MEMORY_SYNC_CLI": os.path.join(self.fx.tmp, "absent"),
            },
        )
        self.assertWarnsFamily(proc, self.FAMILY)
        self.assertIn("CLI 不在の entry", warn_body(proc))


class CorpusContinuationClaimTest(StopChecksTest):
    """C4 (corpus correction): future forms the old hook blocked in 74 real turns must block.

    The rewrite caught 0 of those 74 texts (drafts/replay-tools/replay_stop_fires.py, 2026-08-27),
    so the contract now names the roster verbatim instead of giving two examples.
    """

    FAMILY = "continuation-claim"
    CORPUS_BLOCKS = (
        "分析の完了通知が届き次第、輸入計画の確定 → 輸入実装 → 資料の統合、と進めます。",
        "compact 後は handoff の contingency どおり「裁定 8 点の要約提示」から再開します。",
        "この session は Bun が入り次第 SvelteKit skeleton 置換に着手します。",
        "それが済めば `/design-order` で稽古日程の mock 発注に進みます。",
        "結果が出次第 triage し、ACCEPT なら land → 実機確認へ進みます。",
        "ldfix の敵対レビューを走らせつつ、カレンダー High 案件の調査を並行で始めます。",
        "受け入れ工程へ進み、完成画面でご報告します。",
        "緑なら commit します。",
        "残りの 2 件は次の turn で修正します。",
        "配備が済んだら todos の項目を反映します。",
    )
    ROSTER = (
        "継続します",
        "再開します",
        "進めます",
        "進みます",
        "続けます",
        "着手します",
        "実施します",
        "実装します",
        "取り掛かります",
        "対応します",
        "調整します",
        "やります",
        "修正します",
        "削除します",
        "追加します",
        "作成します",
        "変更します",
        "反映します",
        "統合します",
        "置換します",
        "コミットします",
        "commit します",
        "デプロイします",
        "deploy します",
        "始めます",
        "報告します",
        "提示します",
        "直します",
    )

    def test_c4_corpus_forms_block(self):
        for text in self.CORPUS_BLOCKS:
            with self.subTest(text=text):
                self.fx.turn(say("整理しました"))
                self.assertBlocks(run_hook(self.fx, text + TAIL), self.FAMILY)

    def test_c4_roster_tail_blocks(self):
        for tail in self.ROSTER:
            with self.subTest(tail=tail):
                self.fx.turn(say("整理しました"))
                text = f"通知が届き次第、残りを{tail}。" + TAIL
                self.assertBlocks(run_hook(self.fx, text), self.FAMILY)

    def test_c4_polite_request_and_past_tense_pass(self):
        """A request to the user and a tool-backed past tense are not future claims."""
        for text in (
            "配備は sudo cp をお願いします。",
            "この設計で問題ないかご確認をお願いします。",
            "全 test を再実行しました。",
        ):
            with self.subTest(text=text):
                self.fx.turn(bash("python3 test.py"), say("実行しました"))
                self.assertNotBlocked(run_hook(self.fx, text + TAIL), self.FAMILY)

    def test_c4_list_and_table_labels_pass(self):
        """A roster word inside a bullet or table row is a plan item, not a claim."""
        self.fx.turn(say("整理しました"))
        text = (
            "計画:\n- 実装します\n| 手順 | 状態 |\n|---|---|\n| 反映します | 未 |"
            + TAIL
        )
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)


class CorpusMetaAnnounceTest(StopChecksTest):
    """C12 rule 1 (corpus correction): non-action announcements the old hook blocked in 15 real turns."""

    FAMILY = "self-report-honesty"
    CORPUS_BLOCKS = (
        "承認はそちらへお願いします（私は実行しません）。",
        "こちらからは実行しません。",
        "Task #9 に移しました (これ以上は催促しません)。",
        "seed には触りません。",
        "推測では書きません。",
        "判断は保留します。",
        "省略はしません。",
    )

    def test_c12_corpus_meta_announces_block(self):
        for text in self.CORPUS_BLOCKS:
            with self.subTest(text=text):
                self.fx.turn(say("整理しました"))
                self.assertBlocks(run_hook(self.fx, text + TAIL), self.FAMILY)

    def test_c12_negated_fact_about_the_tool_passes(self):
        """A statement about a tool's behaviour is not an announcement about the model's own inaction."""
        self.fx.turn(say("整理しました"))
        text = "この hook 自身は file を変更しません。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)


class CorpusRoutingQuestionTest(StopChecksTest):
    """C13 rule 2 (corpus correction): a closed choice handed to the user blocks without the skill."""

    FAMILY = "offload-to-user"

    def test_c13_which_one_question_blocks(self):
        for text in (
            "先に A の 10 件だけ適用して B は保留、という進め方でもよいです。どちらにしますか?",
            "(A) 今すぐ始める、(B) 取り込みまで待つ、のどちらにしますか？",
        ):
            with self.subTest(text=text):
                self.fx.turn(say("整理しました"))
                self.assertBlocks(run_hook(self.fx, text), self.FAMILY)

    def test_c13_which_one_question_after_the_skill_passes(self):
        self.fx.turn(call("Skill", skill="declare-and-proceed"), say("整理しました"))
        text = "(A) 今すぐ始める、(B) 取り込みまで待つ、のどちらにしますか？"
        self.assertNotBlocked(run_hook(self.fx, text), self.FAMILY)


class ReviewCorrectionTest(StopChecksTest):
    """Contract corrections from the first independent review (2026-08-27), one test per finding."""

    def test_c18_hook_is_executable(self):
        self.assertTrue(os.access(HOOK, os.X_OK), HOOK)
        with open(HOOK, encoding="utf-8") as stream:
            self.assertEqual(stream.readline().rstrip(), "#!/usr/bin/env python3")

    def test_c3_inline_code_is_stripped_before_block_and_warn(self):
        self.fx.turn(say("作業しました"))
        text = "検出語 `この後 実装を進めます` を regex に追加しました。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), "continuation-claim")
        text = "`該当なし` という語を pattern に追加しました。" + TAIL
        self.assertNotWarned(run_hook(self.fx, text), "claim-without-evidence")

    def test_c5_mentions_in_other_sentences_do_not_count(self):
        self.fx.turn(bash("git status"), say("報告します"))
        for text in (
            "レビュー報告書を 3 節にまとめ終わりました。lint は未実施のままです。",
            "Priority の整理が完了しました。所見は 3 件です。",
            "調査が完了しました。commit はまだ行っていません。",
        ):
            with self.subTest(text=text):
                self.assertNotBlocked(
                    run_hook(self.fx, text + TAIL), "done-state-ledger"
                )

    def test_c5_same_sentence_mention_still_blocks(self):
        self.fx.turn(bash("git status"), say("報告します"))
        proc = run_hook(self.fx, "ruff 0 件で lint まで完了しました。" + TAIL)
        self.assertBlocks(proc, "done-state-ledger")

    def test_c4_stop_declaration_across_a_period_passes(self):
        self.fx.turn(say("報告します"))
        text = "これから続きを進めますが、ここで停止します。再開条件は承認です。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), "continuation-claim")

    def test_c4_background_id_in_another_sentence_passes(self):
        self.fx.turn(
            bash("python3 long.py"),
            tool_result("Command running in background with ID: bg-77"),
            say("起動しました"),
        )
        text = "この後 解析を進めます。background task の id は bg-77 です。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), "continuation-claim")

    def test_c8_non_md_paths_are_tracked(self):
        report = tool_result("subagent report: 候補を 3 件見つけました")
        agent = call("Agent", subagent_type="general-purpose", prompt="調査")
        for path in (
            "files/claude_managed-hooks/stop_checks.py",
            "/var/lib/claude-rag-memory/claude-lessons-learned/org/alpha",
        ):
            with self.subTest(path=path):
                text = f"{path} の方針は妥当と判断しました。" + TAIL
                self.fx.turn(agent, report, say("報告します"))
                self.assertBlocks(run_hook(self.fx, text), "ruling-without-reading")
                self.fx.turn(agent, report, read(path), say("報告します"))
                self.assertNotBlocked(run_hook(self.fx, text), "ruling-without-reading")

    def test_c16_waste_latch_survives_a_blocked_stop(self):
        self.fx.write([prompt("この待ち時間は無駄では?"), say("報告します")])
        self.assertBlocks(
            run_hook(self.fx, "この後 実装を進めます。"), "continuation-claim"
        )
        self.assertIn("無駄", warn_body(run_hook(self.fx, "調査を終えました。" + TAIL)))

    def test_c12_unexpected_input_wording_passes(self):
        self.fx.turn(say("報告します"))
        text = "想定外の入力で fail-open することを確認しました。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), "self-report-honesty")

    def test_c13_declarative_self_decision_passes(self):
        self.fx.turn(say("報告します"))
        for text in (
            "どちらを先に読むかは自分で判断しました。",
            "実装するか調査するかは自分で決めて着手しました。",
        ):
            with self.subTest(text=text):
                self.assertNotBlocked(run_hook(self.fx, text + TAIL), "offload-to-user")

    def test_c13_inline_host_command_warns_despite_an_unrelated_fence(self):
        self.fx.turn(say("報告します"))
        text = (
            "お手元で `git push origin main` を実行してください。\n\n```\n# 参考\nls\n```"
            + TAIL
        )
        self.assertWarnsFamily(run_hook(self.fx, text), "host-command-format")

    def test_c2_window_holds_a_200kb_tool_result(self):
        self.fx.turn(
            read(self.fx.repo_file("big.txt")),
            tool_result("L" * 200_000),
            say("読みました"),
        )
        self.assertBlocks(
            run_hook(self.fx, "この後 実装を進めます。"), "continuation-claim"
        )

    def test_c2_final_text_and_state_families_survive_a_lost_boundary(self):
        self.fx.wind_down()
        self.fx.native_task("報告書を書く")
        self.fx.turn(
            read(self.fx.repo_file("big.txt")),
            tool_result("L" * 600_000),
            say("読みました"),
        )
        proc = run_hook(
            self.fx, "seed には触りません。commit まで完了しました。" + TAIL
        )
        self.assertBlocks(proc, "self-report-honesty")
        self.assertBlocks(proc, "wind-down-open-tasks")
        self.assertNotIn("done-state-ledger", blocked(proc))

    def test_c10_truncated_window_with_an_unreaped_launch_warns(self):
        self.fx.wind_down()
        filler = [say("x" * 900)] * 2_900
        self.fx.write(
            [
                prompt(),
                *filler,
                bash("python3 long.py"),
                tool_result("Command running in background with ID: bg-1"),
                say("片付けました"),
            ]
        )
        proc = run_hook(self.fx, "本日の作業をまとめました。" + TAIL)
        self.assertWarnsFamily(proc, "wind-down-background-unreaped")
        self.assertIn("窓外", warn_body(proc))

    def test_c16_non_utf8_entry_is_skipped(self):
        self.fx.memory_entry("alpha", "証跡を確認せよ")
        broken = os.path.join(self.fx.memory, "org", "broken.md")
        with open(broken, "wb") as stream:
            stream.write(
                b"---\nname: broken\nkeywords: \xe8\xaa\xbf\xe6\x9f\xbb\ncheck: \xff\xfe check\nwhen: stop\n---\n"
            )
        self.fx.turn(say("報告します"))
        proc = run_hook(self.fx, "調査を終えました。" + TAIL)
        self.assertWarnsFamily(proc, "memory-reminder")
        self.assertIn("証跡を確認せよ", warn_body(proc))

    def test_c17_marker_reads_the_statusline_cache(self):
        cache_dir = os.path.join(self.fx.cache, "claude-tui-statusline")
        os.makedirs(cache_dir, exist_ok=True)
        with open(
            os.path.join(cache_dir, SESSION + ".json"), "w", encoding="utf-8"
        ) as stream:
            json.dump(
                {
                    "stdin": {"context_window": {"used_percentage": 48}},
                    "session_started_epoch": 1000,
                },
                stream,
            )
        self.fx.turn(say("報告します"))
        self.assertIn(
            "Context 48%", marker(run_hook(self.fx, "調査を終えました。" + TAIL))
        )

    def test_c17_marker_without_a_cache_shows_a_dash(self):
        self.fx.turn(say("報告します"))
        self.assertIn(
            "Context -", marker(run_hook(self.fx, "調査を終えました。" + TAIL))
        )


class RecheckCorrectionTest(StopChecksTest):
    """Contract corrections from the final recheck (2026-08-27): decorations, path matching, question lines."""

    def test_c4_decorated_endings_still_block(self):
        for text in (
            "次に残りの family を検証します (約 10 分)。",
            "次に残りの family を検証します（約 10 分）。",
            "次に残りの family を検証します…",
            "次に残りの family を検証します 🔧",
            "次に実装します:",
            "（この後 実装を進めます）",
        ):
            with self.subTest(text=text):
                self.fx.turn(say("報告します"))
                self.assertBlocks(run_hook(self.fx, text + TAIL), "continuation-claim")

    def test_c8_relative_mention_of_an_absolutely_read_path_passes(self):
        agent = call("Agent", subagent_type="general-purpose", prompt="調査")
        report = tool_result("subagent report: 候補を 3 件見つけました")
        absolute = self.fx.repo_file("drafts/report.md")
        self.fx.turn(agent, report, read(absolute), say("読みました"))
        text = "drafts/report.md の指摘は妥当と判断しました。" + TAIL
        self.assertNotBlocked(run_hook(self.fx, text), "ruling-without-reading")

    def test_c8_urls_versions_and_ratios_are_not_paths(self):
        agent = call("Agent", subagent_type="general-purpose", prompt="調査")
        report = tool_result("subagent report: 候補を 3 件見つけました")
        for text in (
            "subagent が挙げた https://docs.python.org/3/library/re.html の記述は妥当と判断しました。",
            "python 3.11/3.12 の差は影響なしと判断しました。",
            "比率は 3/4.5 で妥当と判断しました。",
            "@anthropic-ai/sdk.js の採用は妥当と判断しました。",
        ):
            with self.subTest(text=text):
                self.fx.turn(agent, report, say("読みました"))
                self.assertNotBlocked(
                    run_hook(self.fx, text + TAIL), "ruling-without-reading"
                )

    def test_c13_topicalized_order_phrases_in_requests_pass(self):
        for text in (
            "どの順で実行したかは報告書に書いてありますのでご確認ください。",
            "どの順で実行するかは README を参照してください。",
        ):
            with self.subTest(text=text):
                self.fx.turn(say("報告します"))
                self.assertNotBlocked(run_hook(self.fx, text + TAIL), "offload-to-user")


if __name__ == "__main__":
    unittest.main()
