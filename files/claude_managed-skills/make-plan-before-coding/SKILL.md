---
name: make-plan-before-coding
description: Align design space exploration, agreement, and documented rationale inheritance before entering implementation.
when_to_use: TRIGGER when about to propose a design / 方針, start substantive Edit / Write after research, or ask "X にしますか?" for already-documented choices. SKIP for mechanical changes or when user has approved the design.
---

# Make Plan Before Coding

coding に着手する前に plan を立てる discipline。 設計の option space を尽くし (investigate)、 概要を提示して user 合意を取り (agree)、 既 documented な rationale は再 litigate せず継承する (inherit) — 3 phase を 1 skill に統合。

## Why

設計 phase で頻発する 3 失敗 mode:

1. **Premature commit**: 既知範囲だけで設計が早期収束し、 productized 先行実装 / 他者解法を見落とす
2. **Silent assumption**: 調査が一段落した瞬間に user 合意を取らず実装に突入し、 手戻り = token 浪費
3. **Redundant litigation**: 既に documented な rationale を user 確認で再 litigate し、 合意済の判断を蒸し返す

共通 root cause = **着手 momentum**。 調査が進むほど 「もう分かった」 「早く書きたい」 という慣性が働き、 phase gate を skip しがちになる LLM calibration error。

## Process

### Phase 1: Investigate

設計案を verbalize する前に option space を能動列挙:

1. mechanism / API / library / framework は?
2. productized 先行実装 / 他者の公開解法 (blog / issue / repo) は?
3. 一次情報で mechanism 確認したか?
4. 「今知っている範囲」 で収束していないか self-rebut?
5. **Claude Code / Claude Developer Platform 機能** (hook event / skill frontmatter / `claude --bg` 等 hidden flag / settings.json schema / MCP / plugin / `ant` CLI 等の公式ツール) を含む planning なら、 `${XDG_CACHE_HOME:-~/.cache}/claude-code-feature-research/findings.md` を Read して cutoff 以降の delta を check。 最上位 `## v<X.Y.Z>` heading と `claude --version` を突き合わせ、 match していれば既知範囲は cache が cover、 不一致 / 不在なら `feature_findings_build.py` hook が version 変化時に決定的 rebuild する (高速) ので既知範囲で進めつつ negation / positive 断定は後追い verify

新事実が判明したら過去の設計判断を再評価して verbalize する (新事実発見後の古設計維持は calibration error)。

### Phase 2: Agree

調査が一段落 (probe 群が出揃った / blast radius が確定した / 複数の fork が見えた) したら、 自発的に **設計概要** を提示:

1. **ゴールの再述**
2. **中核原則**
3. **具体的変更点**
4. **合意が要る設計判断 fork**
5. **検証順序**
6. **制約ごとの目的と反証検査**: user が言葉で付けた制約 (「X 経由で」「Y を使って」「Z しない」) ごとに、目的を 1 行と、その制約を破ったら失敗する実行可能な検査を 1 つ書く。検査は文ではなく出した物 (process・呼び出し先・出力) を見る。実装前に置き、完了報告に結果を添える

最後に 「この設計で合意か」 を問う。 user 合意 phrase が明示されるまで substantive Edit / Write は hold する。 user の 「進めて良い」 が設計合意を含むか曖昧なら概要を先に出す。

### Phase 3: Inherit (skip when applicable)

設計案を提示しかけた瞬間に **停止** し、 関連 code comment / canonical doc / handoff / commit message を必要範囲で読む:

- rationale 発見 → 継承して実装に進む (user 再 litigate しない)
- rationale 不在 → 新規 design として Phase 2 へ
- 前提変化 / 新 trade-off / obsolete rationale → 再 litigate OK

## Rules

### Investigation 完成判定

「これ以上調べる事はない」 と感じたら 1 拍 self-rebut: 既知範囲だけで収束していないか? 一次情報 / productized 実装 / 他者解法を踏んだか? token を理由に一次情報確認を省略しない。

### Agreement form

概要は **合意可能な粒度** に絞る (冗長禁止、 詳細実装は合意後に展開)。 長時間調査後は user 側も lost track しやすいので概要再述で context を共有する。 改造が大きい / blast radius が広い 場合は特に厳守。

### Blocked front path

user の制約どおりの道が塞がって見えたら、取れる行動は 2 つだけ:

1. 塞いでいる物が自分たちの部品 (この repo・自分の設定) なら、拡張して道を開く
2. そうでなければ、代わりの案を実装する前に user に聞く

「代わりの案でも制約を満たす」と言い換えて進むのは禁止。推奨としても書かない。代わりの案を評価するときは次の順で見る:

1. 制約がもたらす性質を、言葉でなく中身で列挙する (例: 接続済みの同じプロセス、呼び出しをまたぐ状態、起動し直さない)
2. 案ごとに、各性質を保つか失うかを表にする
3. 制約に従わなかった場合と区別がつくか確かめる。区別がつかない案はすり替え
4. 手段の置き換え (性質を全部保つ) なら自分で決める。性質を失うなら user が決める
5. 案を平易な 1 文にし、失う性質を添えて示す

委任文にも「なければ代わりに…」の逃げ道を書かず、「塞がっていたら塞いでいる物を報告せよ」と書く。委任先の報告がこの言い換えをしていたら、採用前に制約の原文と目的に照らして検証する。

### Inheritance gate

過去 rejected 提案を再持出ししない:

1. 過去に止められた追加提案・marker・機能は **user が明示的に再要求した時のみ** 着手
2. user 拒否理由は **paraphrase せず** そのまま認識
3. **逆 framing 禁止**: 拒否理由 (例 「分かりにくい」) の逆方向 framing (例 「分かりやすさのため」) で再提案するのは LLM の典型 rationalization 癖

### Examples

- 悪い (Phase 1 skip): 「思いついた A 案を出します」 → option space 未列挙
- 悪い (Phase 2 skip): 「調査終わったので実装します」 → 概要提示なく substantive Edit
- 悪い (Phase 3 skip): 「`TTL_SECONDS` を 7 日にしますか? 30 日にしますか?」 (docstring に 「7 days because session usually completes within a week」 記載済)
- 悪い (Blocked front path): 「Jev は MCP 経由で」に対し、既存ツールでは足りないので hook が自分で `jev serve` を起動し「MCP で話すので満たす」とする → 接続済みの常駐サーバーを使う目的が消える。自分たちの `jev` に受付口のツールを足すのが正面の道
- 良い: 「A / B / C を比較した結果 B を提案、 概要は…、 この設計で合意か?」
- 良い: 「commit message に明記された通り fork 方式を採用、 実装に進みます」

## Output

適用後の典型 work flow:

```
research (option space 列挙)
  → 設計概要提示 (Goal / 中核原則 / 変更点 / fork / 検証順序)
  → user 合意 phrase 取得
  → implementation (substantive Edit / Write)
```

documented rationale 継承 case:

```
読む (comment / doc / handoff)
  → rationale 発見
  → 「documented 通り X 採用、 実装に進みます」 と verbalize
  → implementation
```

## Related

- `verify-before-claim` — 否定形断定前の primary source verify (Phase 1 「一次情報で mechanism 確認」 と family)
- `verbalize-before-action` — 判断 / 推奨を発話前に self-rebut (Phase 2 の verbalize 規律)
- `report-by-evidence` — 判定 / 推奨 / 影響評価の根拠提示
- `commit-discipline` — 実装後の commit 規律
