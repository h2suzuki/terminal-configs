---
name: memory-surface-analyzer
description: Qualitatively evaluates memory-surface backtests while keeping human judgments separate from deterministic measurements.
when_to_use: TRIGGER when asked to remeasure memory-surface precision, backtest keyword edits, or confirm their improvement effect. SKIP for ordinary memory lookup, analyzer implementation or debugging, and memory edits without comparative evaluation.
---

# Memory Surface Analyzer

inject_log から復元した query を再スコアし、既存 relevance label と発火変化の組み合わせで precision 変化を機械計算する。LLM は機械集計を再計算せず、個別 event の質的判定と改善案の起草だけを担う。

## Process

1. `claude_memory_surface_analyzer --help` と各 subcommand の `--help` を読み、引数を実機確認する。
2. dataset を作り、候補変更なしの strict control を通す。

   ```bash
   claude_memory_surface_analyzer dataset --out "$CONTROL" --since "$SINCE" --labels "$LABELS"
   claude_memory_surface_analyzer rescore --run "$CONTROL"
   claude_memory_surface_analyzer report --run "$CONTROL"
   ```

3. shared corpus と keyword edit の二段 run を実行する。`$SHARED_DIRS` は両側に共通の entry、`$EDIT_DIR` は keyword edit のみを含める。

   ```bash
   claude_memory_surface_analyzer dataset --out "$RUN1" --since "$SINCE" --labels "$LABELS"
   claude_memory_surface_analyzer rescore --run "$RUN1" --candidate-memory "$SHARED_DIRS"
   claude_memory_surface_analyzer dataset --out "$RUN2" --since "$SINCE" --labels "$LABELS"
   claude_memory_surface_analyzer rescore --run "$RUN2" --baseline-db "$RUN1/candidate.sqlite3" --candidate-memory "$EDIT_DIR"
   claude_memory_surface_analyzer misses --run "$RUN2" --judgments "$JUDGMENTS"
   claude_memory_surface_analyzer report --run "$RUN2" --gate-entries "$MODIFIED_ENTRIES"
   ```

4. `report.json` を読み、health gate を先に判定してから `events.jsonl` と `rescored.jsonl` を `id` で join し、`misses.jsonl`、生成された場合は `unlabeled.jsonl` と合わせて個別 event を読む。
5. 機械値と LLM 判定を分離した report を作る。

## Rules

- **Health gate**: `reconstruction_rate_existing >= 0.90`、`baseline_refire_rate >= 0.85`、strict control の `killed_all` 全 category・`n_new_fire_pairs`・`n_pick_changes` がすべて 0 の時だけ判定に使う。0.85 は field 固有の根拠から導出された値ではなく guidance threshold として扱う。1 つでも下回れば run を棄却し、原因と再実行条件だけを報告する。raw `reconstruction_rate` は削除済み transcript event も分母に残るため、`n_transcript_missing` と併読し慎重に解釈する。
- **Event ownership**: kill / retained / gate の集計単位は「その event を元々発火させた entry」(`rescored.jsonl` の `file_path` 列) である。他 entry 所有 event の `picks_base` / `picks_cand` への同乗・離脱は pick change であり killed に数えない。picks を目視 join した手集計で gate を代替しない (2026-07-11 に所有権無視の手集計で killed_r2 を過大評価した実例あり)。
- **Killed R2 review**: `relevance == 2` かつ baseline 発火・candidate 非発火の event を全件目視する。query、picks、`score_base` / `score_cand` とその差を根拠に、真の actionable loss か、僅少 delta の borderline かを個別に判定する。固定閾値を捏造しない。
- **Unlabeled queue**: 新規発火 event を全件判定し、`2=actionable`、`1=adjacent`、`0=noise` を付け、短い根拠を残す。既存 label や機械集計を上書きしない。
- **Recommendations**: `per_entry`、`killed_all`、`new_fires_by_entry`、`strata`、miss recovery、gate と個別判定を結び、keyword 修正案、entry 退役、または deterministic hook への移管案を起草する。数値だけで因果を断定しない。
- **Evidence discipline**: 合否は `report.json` の field 名と値を引用する。機械集計を「LLM 判定」、LLM rubric を「測定結果」と表現しない。

## Output

1. **Machine results** — run、health gate、gate、主要 metric を field 名・値付きで記載する。
2. **LLM judgments** — killed R2 の event 別判定と unlabeled queue の rubric・根拠を記載する。
3. **Recommendations** — keyword 修正、entry 退役、hook 移管を evidence と risk 付きで優先順位化する。

## Related

- `writing-code` — deterministic 処理と LLM judgment の境界、および永続 artifact の参照規律。
- `verify-before-claim` — 合否と改善 claim の根拠確認。
