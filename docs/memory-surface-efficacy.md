# memory surface の有効性 — transcript 実測 (2026-08-27)

計測日 2026-08-27。対象 = transcript 120 file (2026-07-01〜2026-08-27)、surface event の母数 1,459 (prompt 時 355 /
Stop 時 930 / 対照 174)、判定標本 508、反証対象 91、entry 87、判定 model = opus (judge 25 / refuter 16 / taxonomy 1)。
再計測は同じ script と rubric で行い、この段落の母数と日付を併記して差分を読む。

## 問い

2026-08-25 の 1 session 計測 (surface された 18 entry・本文 Read 0 回) から「advisory surface は効かない」と結論し、
Stop 時 surface を削除した (`11005b1`、2026-08-26)。効いた advise は本当にゼロか。効く advise と効かない advise を
カテゴリーで分けられるか。

## 方法

- 対象: 全 transcript 120 file (2026-07〜2026-08-27) の surface event **1,459 件** — prompt 時 (UserPromptSubmit) 355 /
  Stop 時 930 / 対照 174 (retrieval は当たったが model tag 不一致で表示されなかった event)。entry 87 (退役済み含む)
- 抽出: 決定的 script (`drafts/corpus-tools/extract.py`)。event ごとに reminder 文、直前の assistant 本文、直後の assistant
  本文と tool 呼び出し (次の user prompt まで) を window とする
- 判定 (ultracode、opus): 508 件 (entry ごとに prompt 時 4 / Stop 時 4 / 対照 3 を時系列の分位 (= 時系列を等分した位置) で抽出 + entry path を引数に
  含む tool 呼び出しがある 4 件 + 「教訓どおり / 教訓に従い / まさに効く」の句がある 21 件を全件同梱) を 25 agent が判定:
  適用可否 (0-2) / 順守 / 帰属 (explicit = 教訓を名指しして行動 / strong_implicit = prompt も規則も要求していない固有動作 /
  weak = prompt・規則・既定挙動で説明可 / none) / 軌道修正 / 定型文のみ (= 「教訓照合: 問題なし」等の定型応答だけ)
- 反証: 帰属 explicit・strong_implicit の 91 件を 16 agent が反証 (不確かなら refuted を既定)。生存 = 「教訓が行動を変えた」
- 分類: reminder 74 件を 1 agent が 6 種に分類 (T1 手順具体 / T2 環境診断 / T3 作業順序 / T4 文体 / T5 態度 / T6 domain 事実)
- 対照: 同じ entry で「reminder を見た時」と「見なかった時 (対照)」の順守率を比較

## 結果

### 1. ゼロではない — 生存 17 件 (11 entry)、すべて Stop 時 surface

| 形 | n | 適用あり | 順守 (適用のうち) | 帰属 explicit / strong (判定) | 反証を生存 | 軌道修正 (判定) | 定型文のみ |
|---|---|---|---|---|---|---|---|
| Stop 時 | 225 | 86% | 84% | 46 / 25 | **17** | 76 | 126 (56%) |
| prompt 時 | 164 | 84% | 77% | 11 / 9 | **0** | 8 | 6 |
| 対照 (非表示) | 119 | 71% | 69% | — | — | 0 | 1 |

prompt 時の陽性候補 20 件は全て反証された。理由は 3 型: prompt 自身がその動作を要求していた / CLAUDE.md・skill・hook が
既に要求する既定挙動 / 事前の本文が無いので「変わった」と言えない (比較すべき変更前の出力が無い)。

### 2. 対照比較 — reminder を見た方が順守率は高い

| 比較 (同じ entry のみ) | 見た時 | 見なかった時 |
|---|---|---|
| Stop 時 (29 entry) | 79/93 (85%) | 37/57 (65%) |
| prompt 時 (25 entry) | 55/66 (83%) | 39/52 (75%) |

prompt 時は個別 event では因果を立証できないが、集団では +8 pt。Stop 時は +20 pt。

### 3. 効いた advise の共通点

生存 11 entry の reminder はすべて「**自分の直前の出力に対して、今すぐ実行できる検査動作**」を 1 つ指定している:

| entry | 種別 | 動作 |
|---|---|---|
| grep_before_reading_search_space | T1 手順 | 除外ゼロで再走査、走査出力を示せない「網羅した」は書かない (3 件) |
| sandbox_excluded_commands_bare_name | T1 手順 | 除外 command は裸名・単独・先頭で再実行 (1) |
| try_host_ops_before_delegating | T2 環境 | sudo -n / cp / claude --bg を依頼前に自分で試す (3) |
| causal_claim_without_reading_source | T3 順序 | 因果を決める実装を開き行番号を出す (2) |
| control_before_mechanism_claim | T3 順序 | 主張に [仕様] [実測] [推測] を付ける、否定形の直接出典を確認 (1) |
| cjk_tool_arg_glyph_contamination | T3 順序 | commit 前に異文字混入を走査 (1) |
| constraint_asked_as_preference | T3 順序 | 選好として投げる前に技術的上限を確認 (1) |
| document_editor_fork_overwrite | T3 順序 | fork 産物を diff で両方向検証 (1) |
| reading_the_outside_world | T6 事実 | 判断が実際に読んだ対象を同じ粒度で読み直す (2) |
| test_oracle_must_be_spec_not_impl | T6 事実 | 期待値の出どころを spec に戻す (1) |
| no_upstream_bug_dependent_spec | T6 事実 | 上流バグ依存の記述を条件付きに直す (1) |

種別集計 (生存 / n): T1 4/103、T2 3/36、T3 6/142、T6 4/61、**T4 文体 0/64、T5 態度 0/73**。

### 4. 効かなかった advise

- **態度系 (T5)**: 順守率 90% と最高だが、生存 0 — 順守は既定挙動や CLAUDE.md で説明でき、reminder が変えたとは言えない
- **文体系 (T4)**: 生存 0、違反 7 (最多)。「〜と書くな」型は Stop 時に定型文を誘発する
- **否定形** (するな): 40 件中 生存 1、定型文 28
- **prompt 時 surface 全般**: 全種別で生存 0
- 「教訓どおり」等の句がある 21 件のうち生存 4、定型文 9 — 句があっても半数は実体が無い

### 5. model 差 — 定型文の主因は fable-5

| model | Stop 時 n | 定型文のみ | 軌道修正 (判定) | 生存 |
|---|---|---|---|---|
| opus-5 | 90 | 15 (17%) | 59 | 14 |
| fable-5 | 130 | 111 (85%) | 16 | 3 |

fable-5 は Stop 時 surface に「教訓照合: 問題なし」で応じる比率が 85%。opus-5 は 6 割で出力を変える。

### 6. 費用

Stop 時 225 件のうち 141 件は出力不変、126 件は定型文のみ。効果 17 件に対して定型文 126 件。

## 含意

- 2026-08-26 に削除した Stop 時 surface が、検証済みの有効経路そのものだった (生存 17/17)。ただし fable-5 では 85% が
  定型文で終わる
- 選択肢: (a) 削除のまま / (b) 効いた型 (検査動作を持つ T1 / T2 / T3 / T6) に限り、hook 文言を「抵触しないか確認し」から
  「抵触するなら修正してから完了、しなければ何も書かない」へ変えて再導入 / (c) opus 限定 (models tag) で再導入
- 08-25 の「本文 Read 0」は 1 session の観測で、全期間では entry path を引数に含む tool 呼び出しが 17 件ある

## 限界

- 判定・反証は LLM (opus)。反証は refuted 既定の保守側で、真の効果は 17 より多い可能性がある
- prompt 時は事前本文が無く strong_implicit を立てにくい (過小評価)。対照比較 (+8 pt) が補う
- 対照群は inject_log の期間 (2026-08-19〜) のみ
- 標本は entry ごとの分位抽出で全数ではない (1,459 → 508)

## 生存 17 件の証跡

| entry | session | 時刻 (UTC) | 引用 |
|---|---|---|---|
| grep_before_reading_search_space | 96c7898d | 08-11 14:49 | 「残骸ファイル名から逆引きした grep で済ませており、走査を完了していません。除外ゼロで実測し直します」→ find (除外なし) |
| grep_before_reading_search_space | 96c7898d | 08-11 15:04 | 「自分の測定 (49/59) ではなく監査の数字 (57/67) を実測として引用しており…白紙から走査し直します」 |
| grep_before_reading_search_space | 96c7898d | 08-11 21:37 | "I changed one getmtime to lstat — let me check every path-stat call" → grep 全件 |
| sandbox_excluded_commands_bare_name | c3ae0e92 | 07-31 23:50 | 「複合コマンド非先頭位置で実行しており除外パターン不一致…裸名・先頭・単独で再検証します」→ 再実行 |
| try_host_ops_before_delegating | a089b2ee | 08-03 17:51 | 「自分で試せるものを試さずに丸投げしていました。実行します」→ sudo -n true / vssadmin / dism |
| try_host_ops_before_delegating | a089b2ee | 08-03 18:33 | 「訂正します。手動実行が必要という framing が誤り…許可さえもらえれば私が実行できます」+ entry Read |
| try_host_ops_before_delegating | 7ec6a8f7 | 08-17 14:30 | 「Host 側の書き込みを自分で試さずに依頼していました」→ sudo -n tee、claude --bg |
| causal_claim_without_reading_source | 28aa752d | 08-14 11:40 | 実装を開かずに書いていた 3 箇所を検証、行番号を追記 (signals.rs:474) |
| causal_claim_without_reading_source | f291079a | 08-14 15:59 | 「2 件が未確認のまま断定形になっていました」→ 694 万行の主張を訂正 (engine.rs:207-212) |
| cjk_tool_arg_glyph_contamination | 884204e4 | 08-02 15:40 | commit 14 本 + 4 file を Cyrillic 混入で走査、検出ゼロ |
| constraint_asked_as_preference | c917831e | 08-23 21:32 | 「要件が消えるのか担い手が移るだけかを分けていませんでした」→ SKILL.md 修正 + commit |
| control_before_mechanism_claim | 68ddd1bf | 08-12 22:05 | 「permissions は新規 session から効きます は [推測] でした」と訂正 |
| document_editor_fork_overwrite | ab08a960 | 08-05 13:34 | 未通読の fork 産物 2 file を Read → 誤記を修正して commit --amend |
| no_upstream_bug_dependent_spec | a089b2ee | 08-03 21:01 | 「WSL 2.7.11.0 で観測した挙動であって恒久的な仕様ではありません」と条件付きに訂正 |
| reading_the_outside_world | f291079a | 08-14 11:18 | 「根拠は diffstat という proxy でした」→ spec 直読、真因を訂正、同型欠陥をもう 1 件検出 |
| reading_the_outside_world | a7526d44 | 08-25 11:05 | 中継した引用を自分で当たり、行番号ずれ 1 件 (117 → 119) と単位混同を訂正 |
| test_oracle_must_be_spec_not_impl | a7526d44 | 08-25 14:00 | 「真因は期待値の出どころが実装だったこと」→ 次巡の必須条件を書き換え |

## 教訓 (memory entry) を書く時の規準 — 本実測からの導出

1. reminder は「直前の自分の出力に今すぐ当てられる検査動作」を 1 つ指定する — 生存 17 件の 11 entry は全てこの型
2. 態度だけ・文体だけの entry は書かない。書くなら検査動作へ変換する — 態度 73 件・文体 64 件で生存 0
3. 否定形「〜するな」より肯定の動作形で書く — 否定形 40 件で生存 1
4. 教訓は出力が存在する時点 (Stop 時) で当てると効き、prompt 時は個別の効果を立証できない — Stop 時 17/225 vs
   prompt 時 0/164、対照比 +20 pt vs +8 pt
5. 「抵触しないか確認せよ」型の文言は定型文を誘う — fable-5 85% / opus-5 17%。「抵触するなら修正してから完了、
   しなければ何も書かない」と書く
6. 再計測は同じ script (`drafts/corpus-tools/` の extract / sample / aggregate) と同じ rubric で行い、母数と日付を併記する

## 素材

- event 全件 / 判定 / 分類: scratchpad `msurf/` (`events.jsonl` 1,459、`judged_rows.json` 508、`taxonomy.json` 74)
- script: `drafts/corpus-tools/extract.py` / `sample.py` / `aggregate.py`
- workflow: `wf_7c1fdf2e-eae` (42 agent、3.44M token、73 分、2026-08-27)
