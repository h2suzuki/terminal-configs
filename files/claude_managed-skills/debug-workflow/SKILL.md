---
name: debug-workflow
description: For inexplicable phenomena, form 2-3 hypotheses, back them with code / log, land on artifact-level fix; do not suggest manual respawn / session restart / re-cd workarounds.
when_to_use: TRIGGER when user reports or self-says "動かない" / "効かない" / "失敗した" / "うまくいかない" / "エラーが出る" / "期待と違う", when about to propose workarounds like "とりあえず手動で〜" / "session 再起動で〜", or when about to answer with "たぶん〜だと思う" without root-cause backing. SKIP for typos / syntax errors where the error message directly indicates the cause, when user explicitly requests "とりあえず動かして" workaround, or when root cause is agreed to be out of scope.
---

# Debug Workflow

不可解な現象に出会ったときに根本原因へ着地するための手順。

## Rules

- **バグは関連コードを読んでから論じる**: 常に想像を上回るバグが存在する。 推測で語らず、 まず実体を読む。

- **原因が不明なら、 不明と言う**: 当てずっぽうを書かない。 「たぶん〜」「おそらく〜」 系で埋めない。

- **「動かない」「効かない」「失敗した」 → 2-3 仮説 → 裏付け → artifact-level fix**: 現象に出会ったら、 まず原因仮説を 2-3 立てて、 コード / log で裏付けに行く → artifact-level の修正提案、 の順で根本に着地させる。 symptom 緩和の workaround として、 手動 spawn / session 再起動 / 再 cd 等を勧めない。

- **修正報告は一回で簡潔に**: 何を、 どこで見つけ、 どう直したのかを述べる。 一回で、 簡潔に。

- **発生条件は最小 AND 集合の箇条書きで述べる**: 必要となる条件の最小 AND 集合を、 箇条書きで述べる。

## Related

- **Legacy:** org CLAUDE.md 開発 § c. デバッグ より
