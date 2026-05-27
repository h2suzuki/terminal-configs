---
name: verify-before-claim
description: Verify supporting evidence (primary source / actual code / exhaustively traversed pointers) before uttering a positive or negative claim.
when_to_use: TRIGGER when about to make a positive claim ("網羅した" / "reasonable default" etc) or negative claim ("できない" / "非対応" etc). SKIP when basing on a primary source you directly verified with citation.
---

# Verify Before Claim

claim を発する前に根拠 (primary source / 実体 code / 参照ポインタ先) を verify する。 positive form (「網羅した」「確認済」 等の自己 verify claim) と negative form (「できない」「ない」「非対応」 等の否定断定) は polarity が違うだけで、 LLM の calibration error (cut-off で古い記憶・入口だけ読んで網羅と framing) という共通 root cause を持つ。 根拠なき claim は durable artifact に書くと自己強化されて未来の自分を誤誘導する。

## Process

1. claim を発しかけた瞬間に **停止**
2. **許可を求めず自分で調べる** — 「確認しますか?」 と尋ねて止めない、 調査は clarifying question ではない
3. 公式一次情報 / 実体 code / 参照ポインタ先で裏とり (下記 Sources の優先順)
4. 確認できた → 根拠を本文に示して claim を出す
5. 確認できなかった → 「未確認」「公式 doc では未記載」「観測値のみ」 を明示。 見つからなくても存在を否定したことにはならない

## Rules

### Positive claim: exhaustive traversal verify

「詳しく見た」「確認済み」「網羅した」 等の self-verification claim は、 入口 file 1 本だけ読んで 「網羅」 と framing する LLM regression の典型。 claim する前に参照ポインタ先を実体まで網羅したか self-check する:

- **handoff の primary entry / provenance**: 入口 file 1 本だけでなく、 そこが参照する provenance file 群すべて
- **INDEX が指す全 file**: 上位 INDEX 1 行だけでなく、 各 entry の body file 本体
- **目次の named section 全部**: 1 セクションだけでなく、 named されている全 section
- **todos.md の `参照保持` 節**: 列挙された複数 file 全部

positive 断定形 (「reasonable default」 等) の場合は、 何を根拠にその claim を出しているかを 1 文 verbalize する。 根拠なしなら 「観測値のみ」「単一サンプル」「公式 doc では未記載」「未確認」 を明示する。

### Negative claim: primary source 直読

否定形断定は、 LLM の cut-off で古い記憶に基づいて間違える代表 pattern。 推論では、 記憶は cut-off で古いという前提を置く。 否定主張 ("X はない") に倒す前は、 SKIP 条件の 「primary source を直接読んで cite」 は **自分が直接 fetch / 実行する** ことを意味し、 他者経由の引用は該当しない。 subagent が primary source URL 引用付きで出した bonus claim も 「hallucinate 可能性」 と推定して verify せず dismiss しない。 URL fetch / command 実行 (`--help` 等) で primary verify した上で accept / reject する。

### Emphasis-marker reverse implication avoidance

「(公式明記)」「実機確認済」 を一部 fact に付けると、 付けなかった箇所を 「公式でない / 未確認」 と読者に imply させる。 certainty に差を付けたいなら **弱い側** に 「未確認」「公式 doc 未記載」 を明示する (強い側に 「公式」 を付けない)。

### Token efficiency exception

verify のための一次情報 Read (公式 doc / source / 設定実体 / artifact 本体) と専門 agent の spawn は **token 効率則・簡潔さ・anti-overreach の例外**。 token / コスト / scope を理由に確認を 「冗長・過剰・scope 外」 と自己抑制しない。 **誤判断によるやり直しで消費するコストは、 read や spawn コストより遥かに甚大** (局所最適に陥らない)。

### Stronger application to durable artifacts

memory / doc / commit message / todos / handoff 等の **durable artifact** に concrete claim (過去事実・日付・自分の行動・file:line・「X は Y で cover」 等) を書く瞬間が trigger。 ephemeral chat 主張より **一段強く** 一次情報照合する:

- 一次ソース (git log / git show / 会話 / 当該 file 実体) で claim を verify
- 「具体 = 親切」 の圧で confabulate しない (plausible specifics を検証の代わりに生成しない)
- 照合できなければ confident-specific に書かず、 曖昧化するか省く
- 誤 memory は無いより有害 (durable かつ自己強化、 未来の自分を誤誘導)

## Sources

特に Claude hook / subagent / plugin / skill / Anthropic API / 公式エコシステムのツール採否では、 以下を裏とりする:

- **CLI `--help` 出力** — 実機で確認できる最新 spec
- **`docs.claude.com`** — Anthropic 公式 docs
- **`code.claude.com`** — Claude Code 公式 docs
- **`github.com/anthropics/*`** — Anthropic OSS repos (source code 本体)
- **`claude.com/plugins`** — plugin marketplace
- **`${XDG_CACHE_HOME:-~/.cache}/claude-code-feature-cache/findings.md`** — `claude-code-feature-cache` SessionStart hook が cutoff 以降の delta を bg research して累積。 不明 spec 点に当たった時 Read で参照 (最上位 `## v<X.Y.Z>` heading と `claude --version` を突き合わせ、 cover 状況を確認)

出典 **2 点以上** で結論の裏を取り、 うち **最低 1 点は公式・一次情報** (公式 doc / 公式サイト / source code / artifact 本体 / 設定実体 / cache file のいずれか)。 Reddit / 個人ブログ等は点数に算入してよいが公式 1 点の要件は満たさない。

## Output

verify 結果を引用しつつ claim する。 網羅していない / 確認できていない部分は scope を明示する。

例:

- 良い: 「`handoff.md` のみ確認、 `synthesis.md` `research.md` は未読」
- 良い: 「INDEX の上位 3 entry を確認、 残り 8 entry は未読」
- 良い: 「`claude --help` 実行で `agents` mode 実存を確認」
- 良い: 「観測値のみ — 公式 doc では未記載」
- 悪い: 「全部読んだ」 (実際は 1 file だけ)
- 悪い: 「網羅した」 (実際は INDEX line のみ、 body 未読)
- 悪い: 「X はない」 (公式 doc 未確認)
- 悪い: 「reasonable default」 (出典なし、 直感のみ)

scope / 根拠 を明示すれば、 reader は何が確認済み / 何が未確認か把握できる。 主張の信頼性も上がる。

## Related

- `writing-code` — durable artifact での「No dangling-prone references」
- `report-by-evidence` — 判定・推奨・結論を発する前の根拠提示 rule (隣接 scope)
- `debug-guardrail` — hypothesis を code / log で裏付ける workflow
