---
name: codex-delegation
description: Lifecycle discipline for delegating implementation work to the Codex CLI plugin — ordering, isolated worktrees, launch registration, heartbeat-based stall detection, completion detection, review, and fix rounds.
when_to_use: TRIGGER when about to delegate implementation to codex ("codex に発注" / "codex に委譲" / invoking a codex rescue command), when waiting for a running codex task, or when about to review / commit codex-generated changes. SKIP when codex plugin is unavailable or the work is a trivial few-line edit Claude does directly.
---

# Codex Delegation

codex への実装委譲を「発注 → 走行監視 → 完了 / stall 判定 → 受け入れレビュー → fix round」の lifecycle として規律化する。wrapper の報告と codex 本体の実行状態は一致しないため、判定と並行作業の規則を誤ると moving-target レビュー・ビルドロック競合・「未実装」誤判定が起きる。

## Process

1. **発注書を書く**: 依頼は chat 文でなく発注書 file（作業 dir の drafts/ 等）に固定する。含める: スコープ（触ってよい path / 触らない path）、仕様の優先順位（受け入れ修正節が本文に優先する等の明文）、完了条件（fmt / clippy / test の実行と **結果ログの file 保存**）、「コミットはしない（受け入れレビュー後に発注側が行う）」の明記
   - `fuser -k` / `pkill` 等の kill-by-port を禁止し、port が塞がっていれば別 port を使い（この場合も excludedCommands 登録 launcher または `!` によるホスト側起動に限定する）、止められない process は放置して報告することも含める。subagent が port 5273 を `fuser -k` で掃除した直後にホスト側の vite が落ちた（2026-07-15）
2. **起動**: codex rescue 系 command で発注書 path を渡す。**実装発注は `task --write` 必須（既定 = read-only sandbox）**。発注 prompt の第一動作に write probe file 作成を入れ、起動 1-2 分後に実在を確認する（数十分の空走を早期検知）。既存 thread の続き（fix round 等）は resume、新規作業は fresh。wrapper が「background job 起動」とだけ返すのは正常で、完了報告ではない
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
   - 通過後は隔離 worktree 側で commit して本線へ取り込む
6. **fix round**: 所見を番号付きで発注書または追記 file にまとめ、同一 thread の resume で発注する。発注側が既に直した箇所（trivial fix）は「re-add しない」と明記する

## Rules

- **effort は難易度推定で選び、過剰にしない**: 発注前に仕事の難易度を 1 拍推定して companion `task --effort` を決める。目安 = 機械的作業（定数 bump・rename・既存パターンの写経）は minimal/low、通常実装は未指定（config 既定に委ねる）、正しさクリティカル（golden 突合・並行性・migration）や設計判断を含む実装のみ high。xhigh は例外用途に留める
- **resume は元 thread の sandbox を引き継ぐ**: read-only で始まった thread は `--write --resume-last` でも書けない。companion status の `write: True` 表示は起動意図であって実効権限ではない（表示でなく probe file で検証する）。write 化は fresh thread でやり直す（read-only 34 分空走 + resume 不達の実例 2026-07-11）
- **`backgrounded pid N` は task の起動登録を証明しない**: shell が背景化しただけでも表示され、redirect が `/readme-launch.out: Permission denied` で失敗して task が未起動のまま `backgrounded pid 3905669` と表示された（2026-07-15）
- **完了 monitor は当該 task の起動登録確認後に張る**: probe file の出現または companion `status --json` の running[] に当該 task の新 id が現れるまで待つ。未登録のまま監視だけが成立した実例がある（2026-07-15）
- **running[]-empty 型 monitor を使わない**: 直前の task が終了済みで running[] が元から空だったため、起動前の空を完了と誤認して即時 false-fire した（2026-07-15）。当該 task id が running[] に現れてから消える遷移を待つ
- **完了は成果物で裏取りする**: `git diff`、対象 file の mtime、companion `latestFinished` の id 変化のいずれかを確認する。`git diff README.md` が空で初めて非起動に気づいた実例があり、成果物ゼロは非起動または未着手と扱う（2026-07-15）。probe file は起動登録の確認に使い、完了の証拠にはしない
- **wrapper return / timeout ≠ 完了**: wrapper は起動直後 return または実行途中で切断する。codex 本体はサーバー側 thread として走り続け、切断報告後も 40 分以上書き続けた実例がある
- **ツリー静穏は必要条件であって十分条件ではない**: source 書き込みが止まっても検証フェーズ（build / check / test）は継続し得る（静穏 25 分後も cargo check 継続の実例）。task 終了は companion status で確認する
- **running[] 消滅や静穏の待機だけでは hang を捕捉できない**: high effort の敵対レビュー task は起動 2 分後に stall しても 73 分間 running[] に残り、完了イベント待ちでは検知できなかった（2026-07-15）
- **stall は heartbeat の鮮度で判定する**: companion `status --json` の running entry の `updatedAt` または job log file の mtime を定期 poll し、`now - updatedAt` が 7 分を超えた凍結を stall とする。73 分間 log 無音かつ updatedAt 凍結の実例がある（2026-07-15）。ただし作業ツリー / build dir の mtime が更新中、または job log 末尾が build / test 実行中を示す場合は生存として re-arm する
- **監視は完了・stall・生存の 3 分岐で exit する**: 成果物出現または当該 id の running[] 消滅は完了候補にとどめ、静穏 5-10 分と running[] 消滅の 2 条件 AND を満たしてから成果物を裏取りして受け入れレビューへ進む。cancel した task や異常終了した task の running[] 消滅は完了ではなく、cancel / 異常終了後は必ず fresh thread で再発注する。heartbeat 凍結 7 分超・ツリー静穏・job log が build / test 実行中を示していない、の 3 条件 AND で cancel し、いずれか欠ければ生存として re-arm する（2026-07-15）
- **sandbox から codex プロセスは見えない**: PID namespace 隔離のため pgrep 不可。プロセス監視でなくツリー観測 + companion status を使う
- **stall 停止は kill でなく companion の cancel を使う**: sandbox から PID は見えないため codex plugin の `scripts/codex-companion.mjs` を `node` で起動して `cancel <job-id> --json` を渡し、`status: cancelled` を確認する。cancel 成功を実証済みで、resume は read-only sandbox を引き継ぐため fresh thread で再発注する（2026-07-15）
- **実装委譲は隔離 worktree で起動する**: `task --write` は Agent `isolation: "worktree"` 下で起動して書き込みを閉じ、`--write` なしの read-only review task は隔離しなくてよい。main worktree への委譲で別 session の変更 14 file が堆積し、うち `main.rs` は行レベルで双方の追加行が混在した（2026-07-20）
- **sandbox で検証不能な gates はホスト側実行 + ログ保存を発注に含める**: network 遮断で依存 fetch やテストが sandbox で走らない場合、codex に「結果全文を file に tee」まで依頼し、そのログを受け入れ根拠にする
- **長寿命 listener の起動を codex task に委譲しない**: detached process は task 終了時に破棄され、`/var/tmp` も read-only である。`nohup ... &` が started を返しても listener と log が残らなかったため、検証 server は excludedCommands 登録 launcher でホスト側起動する（2026-07-07）。登録 launcher が無ければユーザーに `!` プレフィックスでのホスト起動を依頼する（provide-user-instructions）
- **workflow script 内に codex 生成ステップを入れない**: 静穏待ちができないため。生成は workflow 外、レビューのみ workflow 化する
- **静穏 find の exit を握り潰さない**: `2>/dev/null` + exit 非チェックは「常に 0 件 = 静穏」の偽陰性を生む（Invalid timestamp が不可視化された実例）

## Related

- `tool-role-delegation` — 作業を codex へ「routing する」判断はこちら。本 skill は routing 後の lifecycle 規律
- `verify-before-claim` — gates 自己申告を鵜呑みにしない受け入れ姿勢の一般則
- `writing-code` — exit status 確認・convention 準拠などの実装汎用則
