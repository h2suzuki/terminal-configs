---
name: code-writing
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

### Universal vs add-on skill layering

複数 skill が同じ file kind を対象にする時、 役割が **universal** か **add-on** かで設計が変わる:

| Role | 例 | 適用範囲 |
|---|---|---|
| Universal | `code-writing` | 全 source code (any language) |
| Language-specific add-on | `bash-writing-rules` | bash 固有の追加 rule |
| File-kind add-on | `test-writing` | test file 固有の追加 rule |

これらは **layered (additive)**: bash test script を編集する時は code-writing + bash-writing-rules + test-writing の 3 つすべて fire する。 add-on は universal を replace するのではなく、 上に積む。

**Wrong design (replacement model 誤解を生む)**:

- 悪い: universal の when_to_use に `SKIP for bash (use bash-writing-rules) and tests (use test-writing)` — 「bash は別 skill が代替するから universal は skip」 と読める。 実際は両方 fire してほしい
- 悪い: universal の paths が language-specific add-on の対象 extension (例 `.sh`) を含まない — paths で auto-trigger が切られると universal の rule が bash file 編集時に発火しない

**Right design (layered model)**:

- 良い: universal の when_to_use は broad に書く: `TRIGGER when editing source code (any language; stacks with language-specific add-ons).`
- 良い: universal の paths は全 source extension を網羅: `.py, .ts, .go, .rb, ..., .sh, .bash, .zsh, .fish`
- 良い: add-on の when_to_use では `SKIP for non-{kind} files (handled elsewhere)` のように自 skill の適用外を明示。 universal は SKIP に書かない (universal を SKIP リストに入れると逆方向の競合宣言になる)
- 良い: universal の description に `Universal` prefix を付けて role を明示

新規 universal / add-on skill 作成・編集時は本節を参照。 詳細な skill format は `skill-writing` skill 参照。

### No dangling-prone references in persistent files

<!-- dangling-ref-check: allow (本 section は rule 説明として dangling pattern を例示する) -->

判定基準は「**この repo を新規環境に deploy したとき、 参照解決できなくなる reference か**」。 同じ repo install で作られる path (`/etc/claude-code/...` / `~/.claude/skills/<name>/...` / `~/.claude/CLAUDE.md` / `~/.claude/hooks/<name>` 等) への reference は新規環境でも生成されるので OK。

永続ファイル (repo に commit される source / doc / SKILL.md / hook script / template / コメント / commit message 等) に含まれてはならない pattern:

- **repo deploy 範囲外の path**: 個人 device 固有 / Claude Code runtime 生成 dir (`~/.claude/global-memory/`、 `~/.claude/projects/.../memory/` 等)。 repo install script で作られないため、 新規環境では存在しない
- **skill dir 外 file への file path 参照**: skill SKILL.md は同 skill dir 内の supporting file (template / data / sub-doc) のみ確証してアクセスできる。 dir 外の任意 path (project CLAUDE.md / `files/...` の repo path 等) への file path citation は deploy 順序 / dir 構造に依存し dangling 可能
- **ephemeral tag**: Action Item 番号 (`AI-12` 等) / Plan C / Phase γ / sprint label など、 議論 / sprint / review 中の一時的ラベル。 永続化すると context が失われた reader に意味不明 (例外: GitHub Issue / PR 番号 `#NNN` は発行で永続化されるので OK) <!-- dangling-ref-check: allow -->
- **会話文脈依存 reference**: 「先ほどの議論で」「前回のセッションで」「上の例で」 など、 当該 file 単独で解決できない indexical な参照

**Why:** dangling reference は永続 file の自己完結性 (standalone readability) を損なう。 新規環境 deploy 時 / 時間経過後 / 別 reader が読むときに参照先を fetch できず、 文章の主張が verify 不能になる。

**代替:**

- 内容を該当 file の body に **inline で明文化** する (rationale を doc 内で完結)
- 必要な context を文章で説明: 「個人 device の memory に X という rule あり」 ではなく「X という rule に従う」 と直接書く
- 他 skill 間 reference は **skill 名 symbolic** (例: `code-writing`) で。 Claude Code が auto-discover する spec に依存する OK pattern (skill 名は file path ではない)

**例外 (許容される機械 reference):**

skill 機能上 path-matching の対象として扱う path 言及は citation ではなく機械 reference (他環境で空 match で動作する設計):

- `claude-md-lint` が `/etc/claude-code/CLAUDE.md`, `~/.claude/CLAUDE.md`, `<cwd>/.claude/CLAUDE.md` を scan target として listing
- `stop_checks.py` / `claude-md-lint.sh` が `~/.claude/global-memory/` を path-matching 対象として参照
- `memory-routing` skill が memory dir 自体の routing を define

## Related

- **Legacy:** org CLAUDE.md §token 効率 (sub-bullets), §計画と遂行 (改造/新規実装 mode 詳細), §開発 a. コーディング (全体 6 項目) より
