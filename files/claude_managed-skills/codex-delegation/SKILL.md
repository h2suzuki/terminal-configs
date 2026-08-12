---
name: codex-delegation
description: Lifecycle discipline for delegating implementation work to the Codex CLI plugin — ordering, isolated worktrees, launch registration, heartbeat-based stall detection, completion detection, review, and fix rounds.
when_to_use: TRIGGER when about to delegate implementation to codex ("codex に発注" / "codex に委譲" / invoking a codex rescue command), when waiting for a running codex task, or when about to review / commit codex-generated changes. SKIP when codex plugin is unavailable or the work is a trivial few-line edit Claude does directly.
---

# Codex Delegation

codex への実装委譲を「発注 → 走行監視 → 完了 / stall 判定 → 受け入れレビュー → fix round → セッション棚卸し」の lifecycle として規律化する。wrapper の報告と codex 本体の実行状態は一致しないため、判定と並行作業の規則を誤ると moving-target レビュー・ビルドロック競合・「未実装」誤判定が起きる。

## Process

1. **発注書を書く**: 依頼は chat 文でなく発注書 file（作業 dir の drafts/ 等）に固定する。含める: スコープ（触ってよい path / 触らない path）、仕様の優先順位（受け入れ修正節が本文に優先する等の明文）、完了条件（fmt / clippy / test の実行と **結果ログの file 保存**）、「コミットはしない（受け入れレビュー後に発注側が行う）」の明記
   - 対象 file kind の規約 skill（`writing-code` / `writing-bash` / `writing-skills` 等）を発注側で invoke し、その規約を発注書に転記する。skill gate は subagent と codex の書き込みには効かないため、規約は発注書経由でしか届かない
   - **「出力言語規約」節を必須で置く**: 納品物（code comment / CLI 出力 / log message / doc）の言語は対象 project / file の既存言語規約に従い、1 文書内で言語を混在させない。発注書自体の言語（日本語）を納品物へ持ち込まないことを明記する（日本語発注書からの leak で英語文書・CLI 出力に日本語が混入し、敵対レビューも素通しした実例。user 報告 2026-08-06）
   - `fuser -k` / `pkill` 等の kill-by-port を禁止し、port が塞がっていれば別 port を使い（この場合も excludedCommands 登録 launcher によるホスト側起動に限定する）、止められない process は放置して報告することも含める。subagent が port 5273 を `fuser -k` で掃除した直後にホスト側の vite が落ちた（2026-07-15）
   - **「適用される既存裁定」節を必須で置く**: 発注対象の scope を制約する user の既存決定（機能やデータ範囲の凍結・自動/手動の区別・スコープ境界等）を発注書へ転記する。裁定を運ばない発注は、実装者が裁定違反の default を選んでも止まらない（データ再同期の是正発注が過去データ取得凍結の裁定を欠き、空状態 fallback が無依頼の大規模バックフィルとして実装されレビュー 2 巡も通過した実例 2026-07-23）
   - **「作業量上限（worst-case bound）」節を必須で置く**: 外部取得・大量計算・一括変換など作業量が対象規模に比例する発注は、「初回・空状態で 1 実行が最大何を行うか」を上限として明文化し、上限をテストで pin させる。レビュー発注（受け入れ・cross-model・敵対レビュー等）にも同じ blast-radius 上限の観点を必須で含める（レビュー発注に空状態の upper bound が無く、無依頼の大規模データ取得がレビュー 2 巡を通過した実例 2026-07-23）
   - **所要見積もりバンドと調査発動しきい値（目安 = 見積もり 2 倍）を発注時に宣言する**: 規模 × build 状態（cold/warm）× テスト範囲から見積もる。見積もりを持たない監視は生存確認にとどまる（2026-07-23 の user 指摘）
   - **報告書の終端トークンを義務付ける**: 「報告書の最終行は `REPORT_COMPLETE` の 1 行で終える」を発注書に明記する。監視の完了判定が「report file の存在」だと書きかけと完成を機械的に区別できない（user 提案 2026-07-29）。「報告書を書いたら即座に最終出力して終了する（報告後の追加調査禁止）」も併記する
2. **起動**: codex rescue 系 command で発注書 path を渡す。**実装発注は `task --write` 必須（既定 = read-only sandbox）**。発注 prompt の第一動作に write probe file 作成を入れ、起動 1-2 分後に実在を確認する（数十分の空走を早期検知）。既存 thread の続き（fix round 等）は resume、新規作業は fresh。wrapper が「background job 起動」とだけ返すのは正常で、完了報告ではない
   - **報告書を成果物とする発注は read-only レビューでも `--write` で起動する**: 既定 sandbox では報告書 1 file すら書けず、レビュー本体が完走しても成果物ゼロで終わる（sol xhigh のレビューが分析完了後に apply_patch を拒否され全滅した実例 2026-08-13）。スコープの read-only 性は sandbox でなく発注書の禁止事項で担保し、起動後の record 検証では write flag が発注意図と一致することまで見る
   - **起動 command 行に長い日本語 prompt を直書きしない**: auto-mode classifier が長い日本語のコマンド行を確率的に deny する（別 project で 5 回中 3 回 deny の実測 2026-08-12〜13。短い機械的コマンド行は通過する対照実験済み）。prompt は「発注書 path + 第一動作 + 報告書 path + 終端 token 確認」程度の短文に留めるか、長くなるなら file に置いて `task "$(cat <prompt-file>)"` で渡す。companion 直接起動は既存 exclusion（`node *codex-companion.mjs*` 一致）でホスト実行されるので、専用 launcher を挟む必要はない（launcher 方式は plugin との版結合・exclusion 重複を理由に 2026-08-13 に不採用）
   - background 起動の出力 redirect 先は変数展開に頼らず、既知 writable な絶対 path に固定する
   - 実装委譲では、起動後は companion `status` の workspaceRoot が隔離 worktree を指すことを確認し、以降の probe 確認・静穏 find・`git diff`・成果物確認・受け入れレビュー・commit はこの workspaceRoot を唯一の作業 root とし、全 path をその絶対 path で扱う
3. **完了 / stall 判定**:
   - 正常完了（2 条件 AND。cancel した task や異常終了した task の running[] 消滅は含まない。完了は成果物で裏取りする）:
     - 作業ツリーの書き込み静穏 5-10 分。bfs 互換の ISO 時刻で判定し、stderr / exit code を確認する:
       `out=$(mktemp -p "${TMPDIR:-/var/tmp}"); cutoff=$(date -d '-8 minutes' +%Y-%m-%dT%H:%M:%S); find <dirs> -type f -newermt "$cutoff" > "$out" || exit 1; wc -l < "$out"`
     - codex plugin companion CLI の `status --json` で running[] から当該 task が消えた
   - stall 判定（heartbeat 凍結 7 分超、詳細は Rules）:
     - 監視は background script 内で 170 秒 × 3 回等で poll し、exit 時に re-arm して約 5-8.5 分 cadence を保つ。単発待機は bash tool の timeout 上限 600 秒以内にする
4. **走行中の並行作業規則**: 同一ツリーへの inline 編集をしない（moving-target）。同一 build dir を共有する build / test / lint を並行実行しない（ロック競合で双方が停滞）。別 path（例: backend 委譲中の frontend/、doc、発注書の次 round 準備）は並行してよい
5. **受け入れレビュー**: 完了判定後に開始。gates 結果は codex の自己申告でなくログ file / 再実行で確認する。仕様の根拠行（契約・実データの key 文字列等）はコードと突き合わせ、判断が乗る主張は spot-check する。高リスク変更（auth / data-loss / race / rollback）は独立 cross-model レビューを追加する
   - **表層品質 pass を別回で行う**: 内容の正誤と別に、読者体験で diff を見る — 英語文書内の日本語文 / CLI 出力・log 文字列の言語 / comment 言語と file 規約の一致 / tone・命名の一貫性。抽象的な「自然に見えるか」だけでは素通しするため、観点を列挙してレビューする。cross-model レビューを発注する場合も本観点を発注書に含める
   - **`claude_lang_lint` を worktree diff に必須実行する**: `claude_lang_lint --repo <workspaceRoot>` が ASCII baseline file への CJK 追加を機械検出する（日本語が正の file は baseline 判定で自動除外、新規の意図的日本語 file は `--allow` で指定）。fail は fix round 行き。LLM レビューの注意力に依存しない決定的 gate
   - server を抱えた run では、codex 側の残存検査 (Rules の hang-proof 節) と別に、司令塔側でも workspaceRoot で scope した `pgrep -af <workspaceRoot>` を打ち、残存 process ゼロを確認する（二重の網）
   - 通過後は隔離 worktree 側で commit して本線へ取り込む
6. **fix round**: 所見を番号付きで発注書または追記 file にまとめ、同一 thread の resume で発注する。発注側が既に直した箇所（trivial fix）は「re-add しない」と明記する
7. **セッション棚卸し**: 受け入れ・commit 完了後、companion `status --json` で当該委譲の codex session / thread の残存を確認し、残っていれば cancel で閉じる。発注文の指示では防げない codex session 自体の放置（1 日 10h 級の滞留要因）を lifecycle 終端で回収する

## Rules

- **effort は難易度推定で選び、過剰にしない**: 発注前に仕事の難易度を 1 拍推定して companion `task --effort` を決める。目安 = 機械的作業（定数 bump・rename・既存パターンの写経）は minimal/low、通常実装は未指定（config 既定に委ねる）、正しさクリティカル（golden 突合・並行性・migration）や設計判断を含む実装のみ high。xhigh は例外用途に留める
- **model は俗称でなく正式 id で渡す。`--effort` に `max` は無い**: 俗称（`luna` / `sol` 等）をそのまま `--model` に渡すと API が 400 (`The 'luna' model is not supported...`) で弾く。GPT-5.6 family の id は `gpt-5.6-sol`（品質優先・難コーディング）/ `gpt-5.6-terra`（バランス）/ `gpt-5.6-luna`（高スループット・低レイテンシ）で、alias `gpt-5.6` は Sol へ routing する。plugin が自動正規化するのは `spark` → `gpt-5.3-codex-spark` のみゆえ、他の俗称は発注側が id へ直す。`spark` は対話しながらその場で直す高速反復（リアルタイムコーディング）に特化した低遅延モデルで、text 専用・context 128K・ChatGPT Pro 限定という制約を持つ。長い context を要する発注や画像を伴う発注には選ばない。`--effort` の有効値は companion の `VALID_REASONING_EFFORTS` が定める `none` / `minimal` / `low` / `medium` / `high` / `xhigh` の 6 つ。**`max` は plugin の wrapper が起動前に弾く**（`Unsupported reasoning effort "max". Use one of: ...`、exit 1、task は起動しない）。codex CLI 単体や `~/.codex/config.toml` 経由の可否は別レイヤーで本 skill の管轄外ゆえ、**この経路で発注する限り上限は `xhigh`** と扱う。2026-08-08 実測: `--model gpt-5.6-luna --effort xhigh` は疎通確認 task が正常応答
- **resume は元 thread の sandbox を引き継ぐ**: read-only で始まった thread は `--write --resume-last` でも書けない。companion status の `write: True` 表示は起動意図であって実効権限ではない（表示でなく probe file で検証する）。write 化は fresh thread でやり直す（read-only 34 分空走 + resume 不達の実例 2026-07-11）
- **`--resume-last` は「自分の thread」でなく workspace 内で最後に走った thread に解決される**: write 実装 thread の fix round であっても、間に read-only のレビュー task を挟むと resume 先がそちらへすり替わり、read-only sandbox のまま起動して 1 file も書けずに完了する（fix round 1・2 は write を維持できたのに、read-only レビューを挟んだ fix round 3 で発生・2026-07-22）。resume で write 発注する前に、job state の直近 entry の `write` を確認する。read-only task を挟んだ後は `--fresh` を使う
- **`backgrounded pid N` は task の起動登録を証明しない**: shell が背景化しただけでも表示され、redirect が `/readme-launch.out: Permission denied` で失敗して task が未起動のまま `backgrounded pid 3905669` と表示された（2026-07-15）
- **完了 monitor は当該 task の起動登録確認後に張る**: probe file の出現または companion `status --json` の running[] に当該 task の新 id が現れるまで待つ。未登録のまま監視だけが成立した実例がある（2026-07-15）
- **running[]-empty 型 monitor を使わない**: 直前の task が終了済みで running[] が元から空だったため、起動前の空を完了と誤認して即時 false-fire した（2026-07-15）。当該 task id が running[] に現れてから消える遷移を待つ
- **監視は集合でなく当該 job の state file を id 直指定で poll する**: `status --json` の running[] は集合ゆえ、起動登録の前後で「空」が二度現れ、待機側からは完了と区別できない。plugin data の `state/<worktree>-<hash>/jobs/<job-id>.json` の `status` が `running` から変わるのを待てば集合の状態に依存しない。running[]-empty 型で 2026-08-08 に再度 false-fire し、実際は実行中の task を「成果物ゼロ = 非起動」と誤報告した
- **監視 loop を手書きせず `codex_task_sentinel <job-id> --artifact <path> --token <str> --estimate-seconds <見積もり>` を使う**: 判定を決定的に実装済で、job の state file を全 workspace から探すため隔離 worktree 起動でも見失わない。手書き loop は本節の rule を毎回書き直すことになり、2026-08-08 に 1 session 内で「id を JSON 全体から grep して latestFinished に永久 match」と「本線 workspace から status を引いて隔離 worktree の job を running 0 件と誤読」の 2 通りで壊れた (前者で 4 時間 24 分の空待ち)。全 exit code と test 件数は module docstring と `--help` が canonical。呼び分けは次の通り:

  | exit | 意味 | 呼び手の行動 |
  |---|---|---|
  | 0 | 完了 | 成果物を受け入れレビューへ |
  | 3 | 完了後 hang (`--trust-log` 時のみ) | 成果物を検証してから cancel |
  | 4 | stall (`--trust-log` 時のみ) | log を読み、cancel して fresh 再発注 |
  | 5 | 成果物なし完了 | log が何を報告したか読む |
  | 6 | 未登録 | 起動が成立していない。発注し直す |
  | 7 | timeout | 待ち続けるか判断する |
  | 8 | cancel / 失敗 | 結果ではない。fresh 再発注 |
  | 9 | id 重複 | どの job か特定してから信じる |
  | 10 | record 消失 | prune 済で outcome は読めない |
  | 11 | 生存 (`--once`) | re-arm するか調査に入る |
  | 12 | 見積もり 2 倍超 | log を発注書と突き合わせて調査 |
  | 13 | record 破損 | stall と読まない |
  | 14 | 検証不能 | ツリーを読めない、または既定で log もツリーも静穏。evidence を読んで人が決める |

  **既定は cancel を指示しない**: plugin が message 本文を無加工で append するため、log の同じ bytes が「本文が引用した偽 event」と「真正 event」の両方を表しうる。静穏 log から stall を断定できないので、既定は exit 14 で evidence（成果物 ready / 末尾複数行 / 未完了 command / cancel コマンド）を渡し、判断は呼び手が行う。`--trust-log` を明示した呼び手だけが exit 3 / 4 の断定へ落ちる。下の「3 分岐で exit する」rule の cancel 条件も、機械に委ねてよいのは opt-in した監視だけと読む
  `--once` は 1 cadence だけ評価して返すので、自分で cadence を持つ監視に使う。`--estimate-seconds` を渡すと見積もりの 2 倍で exit 12 に落ち、「乖離したら調査」が機械化される
- **wrapper が報告する task id を監視対象にしない**: 1 回の起動で task が複数登録されることがあり、wrapper 報告の id が即終了した短命 task で、実作業は別 id という実例がある（2026-07-21）。`status --json` で heartbeat が更新され続けている running task を監視対象にする
- **完了は成果物で裏取りする**: `git diff`、対象 file の mtime、companion `latestFinished` の id 変化のいずれかを確認する。`git diff README.md` が空で初めて非起動に気づいた実例があり、成果物ゼロは非起動または未着手と扱う（2026-07-15）。probe file は起動登録の確認に使い、完了の証拠にはしない
- **wrapper return / timeout ≠ 完了**: wrapper は起動直後 return または実行途中で切断する。codex 本体はサーバー側 thread として走り続け、切断報告後も 40 分以上書き続けた実例がある
- **ツリー静穏は必要条件であって十分条件ではない**: source 書き込みが止まっても検証フェーズ（build / check / test）は継続し得る（静穏 25 分後も cargo check 継続の実例）。task 終了は companion status で確認する
- **running[] 消滅や静穏の待機だけでは hang を捕捉できない**: high effort の敵対レビュー task は起動 2 分後に stall しても 73 分間 running[] に残り、完了イベント待ちでは検知できなかった（2026-07-15）
- **stall は heartbeat の鮮度で判定する**: companion `status --json` の running entry の `updatedAt` または job log file の mtime を定期 poll し、`now - updatedAt` が 7 分を超えた凍結を stall とする。73 分間 log 無音かつ updatedAt 凍結の実例がある（2026-07-15）。ただし作業ツリー / build dir の mtime が更新中、または job log 末尾が build / test 実行中を示す場合は生存として re-arm する
- **監視は生存確認に加えて見積もり乖離を検知する**: 再アーム時に累積 elapsed を発注時見積もりと突き合わせ、しきい値（目安 = 見積もり 2 倍）を超えたら re-arm を反射的に繰り返すのをやめ、job log の**実際の作業内容**を発注書のスコープと突き合わせて調査に入る（re-arm か cancel かの生存判定自体は「stall は heartbeat の鮮度で判定する」と「監視は完了・stall・生存の 3 分岐で exit する」の各 rule に従う）。発注していない規模・範囲の活動を見たら、正当化の前に「どの発注・どの既存裁定に基づくか」を裏取りする。委譲成果物の実行検証を含む長時間処理も、起動前に期待所要を宣言し乖離時は同様に調査へ入る（発注外の年次データ書込を目視しながら「正当な初回処理」と誤正当化し、user の障害報告まで検知が遅れた実例 2026-07-23）
- **監視は完了・stall・生存の 3 分岐で exit する**: 成果物出現または当該 id の running[] 消滅は完了候補にとどめ、静穏 5-10 分と running[] 消滅の 2 条件 AND を満たしてから成果物を裏取りして受け入れレビューへ進む。cancel した task や異常終了した task の running[] 消滅は完了ではなく、cancel / 異常終了後は必ず fresh thread で再発注する。heartbeat 凍結 7 分超・ツリー静穏・job log が build / test 実行中を示していない、の 3 条件 AND で cancel し、いずれか欠ければ生存として re-arm する（2026-07-15）
- **sandbox から codex プロセスは見えない**: PID namespace 隔離のため pgrep 不可。プロセス監視でなくツリー観測 + companion status を使う
- **stall 停止は kill でなく companion の cancel を使う**: sandbox から PID は見えないため codex plugin の `scripts/codex-companion.mjs` を `node` で起動して `cancel <job-id> --json` を渡し、`status: cancelled` を確認する。cancel 成功を実証済みで、resume は read-only sandbox を引き継ぐため fresh thread で再発注する（2026-07-15）
- **実装委譲は手動 git worktree で起動する**: `task --write` は発注側が `git worktree add`（repo 内 wt-*/ 等・`.git/info/exclude` 登録・ライフサイクルは発注側管理）で作成した worktree を cwd にして起動する。Agent `isolation: "worktree"` は使わない — harness の unchanged 自動掃除が走行中の codex の worktree を削除した実例（probe 書込先 drafts/ が gitignore 下で unchanged 判定・2026-07-21）。監視用 babysitter agent は非隔離で spawn し worktree へ cd して運用する。`--write` なしの read-only review task は隔離しなくてよい。main worktree への委譲で別 session の変更 14 file が堆積し、うち `main.rs` は行レベルで双方の追加行が混在した（2026-07-20）
- **worktree を作り直したら plugin state dir も掃除する**: 削除した worktree と同じ path で作り直すと、 plugin data の `state/<worktree>-<hash>/` が残ったまま再利用され、 app-server 起動が `failed to load configuration: No such file or directory (os error 2)` で即死する。 切り分けは `codex exec --cd <worktree>` の直接実行 — これが通るなら config も model も worktree も正常で、 companion 経由だけが壊れている。 当該 state dir を削除して再発注すれば復旧する（2026-08-08 実測）
- **sandbox で検証不能な gates はホスト側実行 + ログ保存を発注に含める**: network 遮断で依存 fetch やテストが sandbox で走らない場合、codex に「結果全文を file に tee」まで依頼し、そのログを受け入れ根拠にする
- **長寿命 listener の起動を codex task に委譲しない**: detached process は task 終了時に破棄され、`/var/tmp` も read-only である。`nohup ... &` が started を返しても listener と log が残らなかったため、検証 server は excludedCommands 登録 launcher でホスト側起動する（2026-07-07）。登録 launcher が無ければ、ユーザーに Claude Code の外の terminal での起動を依頼する（provide-user-instructions）。`!` プレフィックスは auto mode の実行許可を与えるだけで sandbox の外には出ないため、ホスト起動の手段にならない
- **workflow script 内に codex 生成ステップを入れない**: 静穏待ちができないため。生成は workflow 外、レビューのみ workflow 化する
- **静穏 find の exit を握り潰さない**: `2>/dev/null` + exit 非チェックは「常に 0 件 = 静穏」の偽陰性を生む（Invalid timestamp が不可視化された実例）

- **完了後 hang（DONE_HUNG_RUNNER）を成果物で検出する**: 報告書が終端トークンまで完成 ∧ job log 凍結 5 分超 ∧ ツリー静穏 は「作業完了・runner の deregister 失敗」であり stall と別分岐 — running[] 消滅を待たず成果物検証（gates ログ + 発注側の build/test 再実行 + ツリー照合）へ進み、runner は companion cancel で回収する。監視は完了・完了後 hang・stall・生存の 4 分岐になる（報告書完成後 31 分 running[] 残存の実例 2026-07-29）
- **監視 loop は登録確認直後に独立で張る**: forwarder subagent の Bash 完了通知に依存しない — hang した companion コマンドを待つ Bash からは通知が永遠に来ない（監視対象と通知チャネルが同一障害点を共有した実例 2026-07-29）
- **subagent 経由の委譲 (rescue 系の調査 task 含む) でも独立 monitor を張る**: subagent が「task を background へ移した。完了時に通知される」と報告したら、その報告を通知経路として信頼せず、その場で job id または成果物 / output path への独立 monitor（sentinel / until-loop）を張る。subagent が先に終了すると、その配下で background 化した task の完了通知は親 session に届かない（孤児化 — 調査 task の完了が 1.5 時間気づかれなかった実例 2026-08-13。結果は output file の直接確認で回収できた）
- **server を抱える run は hang-proof な実行レシピで発注する**: 長命 server（vite / dev server 等）を含む run の発注文には次の 3 点を必須で含める。(1) hang しうる step（テスト・probe）は `timeout <上限>` で有限化する — trap は crash 用で hang には無力、timeout が exit を保証し exit が trap を発火させる 2 段構え。(2) server 起動直後に `trap 'kill "$PID" 2>/dev/null' EXIT INT TERM` を張る（kill は起動 PID 個別。pkill / fuser / port 指定 kill は禁止のまま）。(3) run 終了後、worktree path で scope した `pgrep -af "$PWD"` の残存検査を行い、残存 PID を個別 kill してから完了報告する — task の完了条件に含める。cleanup trap が書かれていても hang した probe が EXIT への到達を阻み、session 放置と重なって vite を抱えた sandbox tree が 1 日以上滞留した（4 tree・port 5278-5282 占有の実測 2026-08-06）

## Related

- `tool-role-delegation` — 作業を codex へ「routing する」判断はこちら。本 skill は routing 後の lifecycle 規律
- `verify-before-claim` — gates 自己申告を鵜呑みにしない受け入れ姿勢の一般則
- `writing-code` — exit status 確認・convention 準拠などの実装汎用則
- `codex_task_sentinel` (`/usr/local/bin/codex_task_sentinel`) — 本 skill の完了 / stall / 完了後 hang 判定を決定的に実装した CLI。監視は手書きせずこれを使う
