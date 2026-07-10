# memory surface 精度分析 (UPS / Stop) — 2026-07-10

データ: `/var/lib/claude-rag-memory/memory_index.sqlite3` の `inject_log` 306 行 (2026-06-17〜07-10)。
L4 sentinel 6 行と transcript の無い合成 session 4 行を除く **296 event / 45 session** を、
session 単位の LLM judge (sonnet、transcript 全文照合) で判定した。判定は 1 event 1 judge
(多数決なし) のため個々の relevance には ±1 段のぶれがあり得るが、傾向把握には十分な規模。
判定 raw data: scratchpad `judgments.json`、集計スクリプトは inject_log.json / memory_catalog.json と併置。

## 1. Precision (出たものは適切だったか)

relevance: 2 = その場で actionable / 1 = 隣接トピックだが actionable でない / 0 = 無関係。

| | n | r2 (適切) | r1 (隣接) | r0 (noise) | strict precision |
|---|---|---|---|---|---|
| 全体 | 296 | 149 | 79 | 68 | **50%** |
| UPS (prompt 起点) | 43 | 17 | 15 | 11 | **40%** |
| Stop (出力起点) | 253 | 132 | 64 | 57 | **52%** |

- 可視の行動影響 (「抵触なし」応答や行動変化): Stop **86%** / UPS **23%**。Stop 側の
  「完了前に確認せよ」プロトコルは機能している。UPS は読み流されがち
- **score は relevance をほぼ分離しない**: r0 の score 平均 0.609 / r2 平均 0.645。
  HYBRID_FLOOR (0.45) を上げる調整は noise と正解を同率で削るだけで、precision 改善の主手段にならない

### noise の主犯は entry 単位で偏在

| entry | n | strict p | 症状 |
|---|---|---|---|
| document_editor_fork_overwrite | 42 | 0.26 | 「編集」全般で発火。最多量 × 最低精度で noise の最大源 |
| rebut_user_concern_with_inference | 13 | 0.31 | ユーザー発話があるだけで発火しがち |
| run_executable_after_edit | 12 | 0.33 | 編集文脈全般に発火 (実行が絡まない場面でも) |
| no_other_work_during_emergency | 5 | 0.00 | 緊急でない場面で発火。緊急トリガー語限定にすべき |
| rebase_autosquash_needs_interactive | 4 | 0.00 | git 語彙だけで発火 |
| pixel_perfect_computed_style_diff | 5 | 0.20 | ※recall 側では 5 miss — 「出るべき時に出ず、違う時に出る」典型 |

上位 3 entry だけで noise (r0) の 4 割。**keyword 設計の見直しで precision を局所的に直せる**。

## 2. Recall (出るべきものが出たか)

judge が「catalog entry が明白に適用可能なのに 900s throttle でも説明できない不発」と
認定した miss は **63 件** (session あたり上限 3 で打ち切りのため下限値)。
粗い推定: relevance-2 対比で recall ≈ 149/(149+63) ≈ **70% が上限**、実態はそれ以下。

### miss 上位と傾向

| entry | miss | 傾向 |
|---|---|---|
| declared_intent_vs_action | 8 | 「〜します」で turn を終える瞬間に出ない |
| run_executable_after_edit | 7 | 編集→完了報告の間に出ない |
| ui_change_requires_screenshot_check | 7 | UI 変更完了報告時に出ない |
| sandbox_server_unreachable_from_host | 6 | まさに躓いた瞬間に出ず、再発見に手間 |
| phase_close_cleanup / pixel_perfect | 各5 | phase close 報告・1px 系不一致の場面で不発 |

共通傾向: これらは **「特定の行動パターンの瞬間」を突く教訓**で、トリガー文面 (prompt /
assistant 出力) に entry の keyword が乗らないため語彙一致でも埋め込み類似でも掬えない。
検索精度の問題ではなく、**RAG という機構と教訓の型のミスマッチ**。

## 3. 構造的欠損: project entry の index 不在 (最重要・即修正可)

index (entries_fts) は 23 entry のみ: user 現役 21 (MEMORY.md 全件) + daily-stock-analyzer の 2。
**terminal-configs の project entry 3 件・genai-development-process の 15 件は index に無く、
仕組み上永遠に surface しない** (retrieval は DB のみ参照、filesystem fallback なし。
`--rebuild`/`--upsert` を該当 project で実行していないだけの population gap であることを
memory_surface.py のコード確認で確定済み — project_id は WHERE の hard filter で、
design 上の除外ではない)。

修正: 各 project の memory dir で `--rebuild <memory_dir> <encoded project_id>` を 1 回実行。
リスクなしで recall の底上げになる。

## 4. 改善候補 (優先順)

1. **[即効・低リスク] 未 index の project entry 18 件を --rebuild で登録** (§3)
2. **[高効果] noise 上位 entry の keyword を絞る**: document_editor_fork_overwrite /
   rebut_user_concern / run_executable_after_edit / no_other_work_during_emergency /
   rebase_autosquash の 5 件で発火条件を具体語 (fork skill 名、緊急語彙、rebase -i 等) に限定。
   noise の約 4 割がこの 5 件
3. **[高効果] miss 上位の「行動パターン型」教訓は RAG から deterministic 検出へ移管**:
   declared_intent (宣言止め regex は stop_checks に既にある — entry 側を退役)、
   run_executable_after_edit / ui_change_requires_screenshot_check / phase_close_cleanup は
   PostToolUse / Stop の regex 系 hook 化が RAG より適合
4. **[中効果] UPS の query を prompt 単文から「prompt + 直近 turn 要約」に拡張**: UPS の
   precision 40% / 影響 23% は query が痩せていることの帰結の可能性。要 A/B
5. **[非推奨] HYBRID_FLOOR の引き上げ**: score が relevance を分離しない (§1) ため効果薄

## 5. 測定上の注意

- 判定は単一 judge で adversarial verify なし。厳密比較 (改善前後の A/B) に使う場合は
  同一プロトコルで再測定すれば bias が相殺される
- miss は session あたり 3 件打ち切り + judge の見落としがあり、真の recall はさらに低い可能性
- throttle (900s) は補正済みだが、「throttle が正しかったか」自体は未評価
