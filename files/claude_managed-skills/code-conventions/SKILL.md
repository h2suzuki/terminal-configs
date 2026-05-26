---
name: code-conventions
description: Universal source code rules (mode classification, convention compliance, wasteful pattern avoidance, LLM API restrictions). Applies to any language; language-specific add-ons (bash-writing-rules, test-writing) layer on top.
when_to_use: TRIGGER when editing source code in any language (including bash, tests). Stacks additively with language-specific add-on skills — do not treat add-ons as replacements.
---

# Code Conventions

実装時の汎用ルール集。 改造の手戻り・浪費 pattern・convention 衝突・LLM 呼び出しの flake を防ぐ。

## Process

### Task mode classification

タスクは最初に **改造** か **新規実装** か分類し、 mode に合わせて進める。

- **改造**: 既存部分は fragile と仮定。 surgical 方針 (動物の手術と同じで、 殺さない・全体を作り変えない)。 触る前に対象ファイル / exports / 直接 callers / shared utilities を必要範囲で読む。 「orthogonal に見える」 は危険な signal。 依頼に直接トレースできる変更だけを加える
- **新規実装**: 想定すべき複数 use cases (境界条件 / エラー / 並行 / scale) を verbalize して整理してから書く。 simplicity 過剰だとナイーブ実装になり後で壊れる

## Rules

### Promote hacks to elegant solutions

ハック的な修正は 「今知っているすべてを踏まえての優雅な解」に書き換えよ。
ただし単純で自明な修正にはこの工程を飛ばす。

### Restrain temporary variables

一時変数は値が複数回参照される時のみ作る。
一時変数を用いない関数型プログラミングのコードを見習う。

### Comply with conventions

codebase / 既知 style / spec (CLAUDE.md / SKILL.md / hook 等) に最初から従う。
post-edit hook / commit deny で後から指摘されてやり直す手戻りは token 浪費。
convention が harmful と判断するなら silently fork せず surface する。

### Handle conflicting patterns explicitly

codebase 内に矛盾する 2 つの pattern を見つけたら、片方を選択して選択理由を述べ、もう片方を cleanup flag として surface する (blend しない)。

### Prefer generic terms in comments / doc / error messages

汎用語 (「base setup」「親スクリプト」 等) で意味が通るなら汎用語を使う。
他 script / file の固有名をハードコードすると rename / restructure 時に rot するため。

### Restrict comment length

コメントは 1 行 max を default とする。 system prompt の "Never write multi-paragraph docstrings or multi-line comment blocks — one short line max" を踏襲。

- WHY が非自明な部分だけ書く。 WHAT (well-named identifier で明らか) は書かない
- 関数の docstring も 1 行。 仕組み詳細は code を読めば分かるので不要
- task / fix / 経緯への言及 ("X 機能を追加" / "issue #N 対応") は PR description / commit message に書き、 ファイルに残さない
- 多段落の WHY が必要なら commit message / external docs に書く

### Restrict LLM API call use cases

LLM 呼び出し (Anthropic Messages API など) は **judgment が要るもの限定** で使う:

- 良い: 分類 / 起草 / 要約 / 抽出
- 悪い: リトライ条件 / ルーティング / deterministic transform

動的 prompt で判定が確率的になり flake するため、 deterministic transform は LLM に投げない。
deterministic ならコードを書いて、毎回それを呼び出す。

### Pause before tool calls

各 tool 呼び出し前に 「この呼び出しは必要か」 を 1 拍考える。 token / rate limit を浪費しないため:

- 同じ file を session 内で何度も全体 Read しない (harness の file state tracking を信頼)
- Bash output が長くなる可能性があれば事前に `head` / `tail` / `wc -l` で size を確認してから本体を fetch
- 繰り返し処理は script 化を検討

### Self-check for wasteful code patterns

生成するコードが浪費 pattern になっていないかチェックする (書く前と書いた後の両方):

- 無限 loop / 過剰 polling / 重複計算 / 巨大 output / 想定外の高頻度実行
- 並列化時は特に 「同じ前提で複数 worker が重複計算」 に陥っていないか確認

### No global-memory references in persistent files

永続ファイル (repo に commit される source / doc / SKILL.md / hook script / template / コメント / commit message 等) から `~/.claude/global-memory/` 配下の memory entry を citation してはならない。

**Why:** global memory は端末固有 (個人 device の personal memory) で repo に含まれない。 他環境で当該 file が deploy された時に dangling reference になり、 reader が参照先を fetch できない。 同じ理由で ephemeral tag (Action Item 番号 / Plan C / Phase γ 等の一時的ラベル) も永続 file 本文に残さない。

**代替:**

- 内容が project 全体で必要 → 該当 file の body に inline で明文化、 または project 内別 file (`files/...`) に切り出して file path で reference
- 個人 device 固有 → 永続化せず、 chat 内の会話だけで使う

**例外 (許容される機械 reference):**

`stop_checks.py` / `claude-md-lint.sh` 等が `~/.claude/global-memory/` を path-matching の対象として扱う用途は機械 reference であり citation ではない (他環境で空 match で動作)。 同様に `memory-routing` skill が global memory dir 自体の routing を define する path 言及も許容。

## Related

- **Legacy:** org CLAUDE.md §token 効率 (sub-bullets), §計画と遂行 (改造/新規実装 mode 詳細), §開発 a. コーディング (全体 6 項目) より
