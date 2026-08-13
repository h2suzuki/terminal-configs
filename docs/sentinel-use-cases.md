# codex_task_sentinel ユースケース正本

本書は `files/codex_task_sentinel` の**用途の正本**である。指摘・要求の妥当性は本書からの
逸脱度で判定する (裁定 60)。用途を広げる要求は欠陥報告ではなく目的外利用 (invalid) である —
普段使いの鋏に手術用の要件を課すことはできない。各ユースケースは本 repo の運用実績
(docs/sentinel-convergence-log.md) または module docstring に実例がある。

## 目的 (1 文)

発注側 (Claude Code session) が起動した codex background job 1 件を、plugin の state 配置を
観測して終局判定まで決定的に監視し、evidence 付き exit code で返す。

## ユースケース (これが用途の全て)

| # | ユースケース | 典型 |
|---|---|---|
| U-1 | 発注直後の監視: job 起動 → record 検証 → arm | `codex_task_sentinel <job> --artifact <報告書> --token REPORT_COMPLETE --estimate-seconds N [--stall-seconds N]` を run_in_background |
| U-2 | 再 arm: exit 14 / 11 / 12 の後に同じ job を張り直す (job 完了後の再 arm を含む) | 深い思考 phase の exit 14 後に `--stall-seconds` を上げて再 arm |
| U-3 | 完了受領: exit 0 / 3 → 成果物の受け入れへ進む | 報告書 path と末尾 token の確認 |
| U-4 | 異常検知: stall / hang / timeout / over-estimate の evidence 提示と cancel command 提示 | exit 4 / 7 / 12 と `--trust-log` の opt-in |
| U-5 | `--once` の単発評価 (呼び手が自前 cadence を持つ場合) | re-arm 前の状態確認 |
| U-6 | selftest / 外部 meta-test の実行 (開発・受け入れ) | `--selftest`・`codex_task_sentinel.test.py` |
| U-7 | `--state-root` override (test fixture・別配置の state) | selftest fixture・検証 script |
| U-8 | 出力先の多様性: terminal / pipe の部分読み (`\| head`) / file redirect (満杯・容量枯渇を含む) | 運用中の log 取り |

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

- 監視中の意図的な path 階層再構成 (走査 timing に合わせた symlink 付替え等)
- metadata 偽装による帰属の攪乱 (utime / chmod で他 run の成果物を騙す — 裁定 58)
- 無応答・異常 semantics の filesystem (hung NFS / FUSE・kernel 異常 — 裁定 59)
- 敵対的な資源絞り (例: RLIMIT_NOFILE を数個にして起動)
- state dir / log / artifact を procfs 等の擬似 filesystem に置く構成
- 監視対象 job を偽装・すり替えする敵対 actor

## 境界例の扱い

過去裁定 (docs/sentinel-rulings.md) と本書で決定できない境界例は、**人間に確認してよい**
(裁定 60)。用途内と判定された指摘だけが blocking である。

## 過剰実装もバグである

ユースケースの定義は双方向に効く。正本に無い状況のため**だけ**に存在する実装・複雑さ・
実行コストは、用途に対する cost 不整合 = 過剰実装であり、これも欠陥である (保守を重くする)。
円周率を 10 桁計算する道具と 1 万桁計算する道具はユースケースが違い、バグの定義も違う。
ただし削減の提案が既存裁定の担保 test と衝突する場合は裁定が優先で、裁定の変更は人間の
判断に委ねる。
