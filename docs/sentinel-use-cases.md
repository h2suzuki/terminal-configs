# codex_task_sentinel ユースケース正本 (v2 — codex delegation の実運用から導出)

本書は `files/codex_task_sentinel` の**用途の正本**である。指摘・要求の妥当性は本書からの
逸脱度で判定する (裁定 60)。「codex task を delegation する」という抽象要件は無限に広がる —
本書は**我々自身の使い方** (docs/sentinel-convergence-log.md に 70 巡超の実績) に根ざして
用途を絞る。一般化はユースケースを増やし実装を高度化させる = 過剰実装まっしぐらである。

## 目的 (1 文)

発注側 (Claude Code session) が起動した codex background job 1 件を、plugin の state 配置を
観測して終局判定まで決定的に監視し、evidence 付き exit code で返す。

## 導出: codex delegation の機能 → 我々の使い方 → sentinel への要求

| delegation 機能 | 我々の使い方 (実績) | sentinel への要求 |
|---|---|---|
| 発注 (発注書 + lint + worktree cp) | drafts/ の発注書を lint し worktree へ複写 | 関与なし |
| 起動 (`task --write`・fresh) | **1 worktree に 1 job** を起動し、直後に record の model / effort / write / fresh を検証 | 起動登録の確認 = record の存在と内容 (U-1) |
| resume (fix round) | 同 worktree の直近 write thread を**直列で** resume。間に read-only を挟まない | 再 arm と同型 (U-2)。旧成果物の帰属は ctime gate |
| 走行監視 | sentinel **1 本**を run_in_background。xhigh の思考 phase では `--stall-seconds` を上げて再 arm | U-1 / U-2 / U-4 |
| 完了受領 | exit 0 / 3 → 成果物 (token 終端の報告書) の受け入れへ | U-3 |
| stall / hang 判断 | exit 14 の evidence を発注側が読み判断 (裁定 1)。cancel command を copy-paste | U-4 |
| 棚卸し / cleanup | worktree remove + branch 削除 + exclude 掃除。plugin state の prune は plugin 任せ | 残 record の後日判定 (exit 10 / U-2) |
| 再起動・session 断 | 方針 = C-3 (下記)。復旧 orchestration は sentinel の役割でない | U-2 の再 arm のみ |

## 運用規約 (commitment — 用途を意図的に絞る決定)

- **C-1**: write mode の delegation は **1 worktree につき同時 1 本** (直列)。並列は worktree を
  分ける — worktree はチープである。同一 worktree への並列 write は目的外
- **C-2**: 同一 job に同時に張る sentinel は **1 本**。再 arm は直列 (前の監視の exit 後)
- **C-3**: マシン再起動・session 断の回収は「sentinel で残 record を判定 → worktree 内の
  成果物を拾う → worktree ごと削除」まで。sentinel は判定を返すのが役割で、復旧の
  orchestration・再開はしない
- **C-4**: state root は plugin 既定の配置。`--state-root` override は test fixture 用
- **C-5**: 報告書 deliverable は終端 token (`REPORT_COMPLETE` 等) で完成を宣言する

## ユースケース (これが用途の全て)

| # | ユースケース | 典型 |
|---|---|---|
| U-1 | 発注直後の監視: job 起動 → record 検証 → arm | `codex_task_sentinel <job> --artifact <報告書> --token REPORT_COMPLETE --estimate-seconds N [--stall-seconds N]` を run_in_background |
| U-2 | 再 arm: exit 14 / 11 / 12 の後、または再起動・session 断の後に同じ job を張り直す (job 完了後の再 arm を含む) | 深い思考 phase の exit 14 後に `--stall-seconds` を上げて再 arm |
| U-3 | 完了受領: exit 0 / 3 → 成果物の受け入れへ進む | 報告書 path と末尾 token の確認 |
| U-4 | 異常検知: stall / hang / timeout / over-estimate の evidence 提示と cancel command 提示 | exit 4 / 7 / 12 と `--trust-log` の opt-in |
| U-5 | `--once` の単発評価 (呼び手が自前 cadence を持つ場合) | re-arm 前の状態確認 |
| U-6 | selftest / 外部 meta-test の実行 (開発・受け入れ) | `--selftest`・`codex_task_sentinel.test.py` |
| U-7 | `--state-root` override (test fixture) — C-4 | selftest fixture・検証 script |
| U-8 | 出力先の多様性: terminal / pipe の部分読み (`\| head`) / file redirect (容量枯渇を含む) | 運用中の log 取り |

## 環境前提 (ユースケースが成立する土台)

- Linux local filesystem (WSL2 含む)。fs は有限時間で応答する (裁定 59)
- state 配置は plugin (codex-companion) 管理: `<root>/<workspace>/jobs/<id>.json` + `.log`
- record 更新は plugin の writeFileSync 相当 (同 inode の truncate+write) — この race 窓は
  用途内の実在 (67 巡 fix が対応)
- **静的な** symlink / alias 構成 (data dir の移設・別名) は正当な環境設定として扱う
  (71/73/74 巡 fix が対応)
- 資源は通常の user session 相当。ただし**自己誘発**の資源消費 (候補数・入力規模に比例した
  fd / memory の保持) は実装欠陥として用途内 (62/65 巡 fix が対応)
- 呼び手は発注側自身 (job を起動した session / operator)。敵対的 local actor はいない
  (裁定 58)

## 目的外利用 (invalid — バグではない)

- 同一 worktree への並列 write delegation とその競合の調停 (C-1 違反)
- 同一 job への並列 sentinel とその相互作用 (C-2 違反)
- 再起動後の復旧 orchestration・job の再開制御 (C-3 の範囲外)
- 監視中の意図的な path 階層再構成 (走査 timing に合わせた symlink 付替え等)
- metadata 偽装による帰属の攪乱 (utime / chmod — 裁定 58)
- 無応答・異常 semantics の filesystem (hung NFS / FUSE — 裁定 59)
- 敵対的な資源絞り (例: RLIMIT_NOFILE を数個にして起動)
- state dir / log / artifact を procfs 等の擬似 filesystem に置く構成
- 他 session の job の奪取・偽装・すり替え

## 境界例の扱い

過去裁定 (docs/sentinel-rulings.md) と本書で決定できない境界例は、**人間に確認してよい**
(裁定 60)。用途内と判定された指摘だけが blocking である。

## 過剰実装もバグである

ユースケースの定義は双方向に効く。正本に無い状況のため**だけ**に存在する実装・複雑さ・
実行コストは、用途に対する cost 不整合 = 過剰実装であり、これも欠陥である (保守を重くする)。
円周率を 10 桁計算する道具と 1 万桁計算する道具はユースケースが違い、バグの定義も違う。
ただし削減の提案が既存裁定の担保 test と衝突する場合は裁定が優先で、裁定の変更は人間の
判断に委ねる。
