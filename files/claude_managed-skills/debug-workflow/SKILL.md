---
name: debug-workflow
description: For inexplicable phenomena, form 2-3 hypotheses, back them with code / log, land on artifact-level fix; verify fix is not algebraically identical to the bug before locking.
when_to_use: TRIGGER when user reports or self-says "動かない" / "効かない" / "失敗した" / "うまくいかない" / "エラーが出る" / "期待と違う", when about to propose workarounds like "とりあえず手動で〜" / "session 再起動で〜", when about to answer with "たぶん〜だと思う" without root-cause backing, or when about to write fix-locking statements like 「これで直る」 / 「これで fix」 / 「X が governing」 before verifying fix vs bug equivalence (fix-lock gate). SKIP for typos / syntax errors where the error message directly indicates the cause, when user explicitly requests "とりあえず動かして" workaround, when root cause is agreed to be out of scope, or for trivial 1-character fixes.
---

# Debug Workflow

不可解な現象に出会ったときに根本原因へ着地するための手順。 仮説 → 裏付け → fix lock 直前の equivalence verify までを一貫した規律として扱う。

## Rules

- **バグは関連コードを読んでから論じる**: 常に想像を上回るバグが存在する。 推測で語らず、 まず実体を読む。

- **原因が不明なら、 不明と言う**: 当てずっぽうを書かない。 「たぶん〜」「おそらく〜」 系で埋めない。

- **「動かない」「効かない」「失敗した」 → 2-3 仮説 → 裏付け → artifact-level fix**: 現象に出会ったら、 まず原因仮説を 2-3 立てて、 コード / log で裏付けに行く → artifact-level の修正提案、 の順で根本に着地させる。 symptom 緩和の workaround として、 手動 spawn / session 再起動 / 再 cd 等を勧めない。

- **修正報告は一回で簡潔に**: 何を、 どこで見つけ、 どう直したのかを述べる。 一回で、 簡潔に。

- **発生条件は最小 AND 集合の箇条書きで述べる**: 必要となる条件の最小 AND 集合を、 箇条書きで述べる。

## Verifying the fix

fix を lock / 合意 / 提案する直前に、 提案 fix と元 bug が **代数的・挙動的に同一でない** ことを必ず通す。 別名で同じ量を再計算しているだけなら、 それは fix ではなく bug の再実装。 「これで直る」 「これで fix」 「pass cache が governing」 「optimization が統括」 等の lock 表現を発する手前で gate がかかる。

### Lock 前 3-step verify

1. **新しい式 / 述語を 1 文で verbalize**
2. **旧 (バグ) の式と並べて diff**: 入力集合 ・停止条件 ・参照するデータ源 が違うことを明示
3. **Governing source の実 read を grep 確認**: 「この cache / optimization が governing」 と言うなら、 新コードの該当行で実際にその cache / source を read しているか grep で確認。 別名で再計算は不可

### Why this gate

LLM は 「fix した」 感覚が先行し、 新旧の量が同値であることを verbalize せずに見落とす calibration error を起こす。 設計上 governing なはずの cache / source を新コードが実際には read していない事故も同じ class。 lock 前に 「同値でない」 + 「governing source を実 read」 を明示することで artifact-level fix の質を担保する。

## Related

- `verify-before-claim` — positive self-verification claim の exhaustiveness。 fix correctness verify は specific instance
- `evidence-reporting` — 判定 / 推奨 を発話する前に根拠を示す
- **Legacy:** org CLAUDE.md 開発 § c. デバッグ より
