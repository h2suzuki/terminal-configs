---
name: code-conventions
description: コード新規作成・編集・リファクタリング時の汎用ルール集。改造 / 新規実装 の mode 分類、ハック → 優雅な解への昇格、一時変数の節度、convention 遵守、矛盾 pattern の扱い、汎用語コメント、LLM API 呼び出し制限、浪費 pattern (無限 loop / 過剰 polling / 重複計算 / 巨大 output / 高頻度実行) 回避、tool 呼び出し前の 1 拍確認。
when_to_use: TRIGGER when editing or creating Python / TypeScript / JavaScript / Go / Rust / Ruby / Java / Kotlin / Swift / C / C++ source files, when about to spawn subagents, or before running Bash commands whose output could be large. SKIP for bash scripts (use bash-writing-rules) and test files (use test-writing).
paths: "**/*.py, **/*.ts, **/*.tsx, **/*.js, **/*.jsx, **/*.mjs, **/*.cjs, **/*.go, **/*.rs, **/*.rb, **/*.java, **/*.kt, **/*.swift, **/*.c, **/*.cc, **/*.cpp, **/*.h, **/*.hpp"
---

# Code Conventions

実装時の汎用ルール集。 改造の手戻り・浪費 pattern・convention 衝突・LLM 呼び出しの flake を防ぐ。 各項目は CLAUDE.md (org / user) を補強する独立則。

## Mode classification

タスクは最初に **改造** か **新規実装** か分類し、 mode に合わせて進める。

- **改造**: 既存部分は fragile と仮定。 surgical 方針 (動物の手術と同じで、 殺さない・全体を作り変えない)。 触る前に対象ファイル / exports / 直接 callers / shared utilities を必要範囲で読む。 「orthogonal に見える」 は危険な signal。 依頼に直接トレースできる変更だけを加える
- **新規実装**: 想定すべき複数 case (境界条件 / エラー / 並行 / scale) を verbalize して整理してから書く。 simplicity 過剰だとナイーブ実装になり後で壊れる

## Universal rules

### ハック → 優雅な解への昇格

修正がハック的に感じられたら 「今知っているすべてを踏まえて、 優雅な解を実装せよ」。 ただし単純で自明な修正にはこの工程を飛ばす。

### 一時変数の節度

一時変数は値が複数回参照される時のみ作る。 一時変数を用いない関数型プログラミングのコードを見習う。

### convention 遵守

codebase / 既知 style / spec (CLAUDE.md / SKILL.md / hook 等) に最初から従う。 post-edit hook / commit deny で後から指摘されてやり直す手戻りは token 浪費。 convention が harmful と判断するなら silently fork せず surface する。

### 矛盾する pattern

codebase 内に矛盾する 2 つの pattern を見つけたら、 片方を選択して選択理由を述べ、 もう片方を cleanup flag として surface する (blend しない)。

### コメント / doc / エラーメッセージの汎用語

汎用語 (「base setup」「親スクリプト」 等) で意味が通るなら汎用語を使う。 他 script / file の固有名をハードコードすると rename / restructure 時に rot するため。

### LLM API を呼ぶ実装の制限

LLM 呼び出し (Anthropic Messages API など) は **judgment が要るもの限定** で使う:

- 良い: 分類 / 起草 / 要約 / 抽出
- 悪い: リトライ条件 / ルーティング / deterministic transform

動的 prompt で判定が確率的になり flake するため、 deterministic transform は LLM に投げない。

## Anti-waste

### tool 呼び出し前の 1 拍

各 tool 呼び出し前に 「この呼び出しは必要か」 を 1 拍考える。 token / rate limit を浪費しないため:

- 同じ file を session 内で何度も全体 Read しない (harness の file state tracking を信頼)
- Bash output が長くなる可能性があれば事前に `head` / `tail` / `wc -l` で size を確認してから本体を fetch
- 繰り返し処理は script 化を検討

### 浪費コード セルフチェック

生成するコードが浪費 pattern になっていないかチェックする (書く前と書いた後の両方):

- 無限 loop / 過剰 polling / 重複計算 / 巨大 output / 想定外の高頻度実行
- 並列化時は特に 「同じ前提で複数 worker が重複計算」 に陥っていないか確認

## Related

- **Legacy:** org CLAUDE.md §token 効率 (sub-bullets), §計画と遂行 (改造/新規実装 mode 詳細), §開発 a. コーディング (全体 6 項目) より
