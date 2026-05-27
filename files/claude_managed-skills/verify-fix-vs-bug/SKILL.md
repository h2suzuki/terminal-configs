---
name: verify-fix-vs-bug
description: 提案する fix が直そうとしているバグと代数的・挙動的に同一でないか、 governing なはずの cache / source を新コードが実際に read しているか、 lock 前に verify する。 新旧式を 1 文 verbalize + 並べて diff + grep で実 read 確認
when_to_use: TRIGGER when about to lock / 合意 / 提案 a fix design for a bug, when about to write fix-locking statements like 「これで直る」 / 「これで fix」 / 「pass cache が governing」 / 「optimization が統括」, or when noticing the fix proposal cites a cache / optimization / source as governing without verifying the new code actually reads it. SKIP for trivial syntactic fixes (typo / 1 character) or when the user explicitly waives verify.
---

# Verify Fix vs Bug

提案する fix が、 直そうとしているバグと **代数的・挙動的に同一** になっていないかを、 設計 lock 前に必ず検証する。 別名で同じ量を再計算しているだけなら、 それはバグの再実装。

## Process

### Lock 前 3-step verify

1. **新しい式 / 述語を 1 文で verbalize**
2. **旧 (バグ) の式と並べて diff**: 入力集合 ・停止条件 ・参照するデータ源 が違うことを明示
3. **Governing source の実 read を grep 確認**: 「この optimization が governing」 と言うなら、 新コードの該当行で実際にその cache / source を read しているか grep で確認

## Rules

### 同値なら fix ではない

新旧の量が同値なら fix ではなくバグ再実装。 lock 前に 「同値でない」 を明示する。 LLM は 「fix した」 感覚が先行し、 新旧の量が同値であることを verbalize せずに見落とす calibration error を起こす。

### Governing source は read を確認

「pass cache が tag 前進を統括」 等、 ある cache / optimization が挙動を *統括* するはず の設計では、 新コードが実際にその情報を **read しているか確認**。 別名で再計算は不可。

## Why

2026-05-18 checking-style tag-advance 改修で fix を `min over dirty of parent(oldest_touch)` と 2 回定式化したが、 現行バグの `compute_forward_sweep_target` (違反 file の最古 touch の親で STOP) と代数的に同一だった経験から起票。 pass cache が tag 前進を統括する設計なのに、 提案コードは cache を参照していなかった。 ユーザーが 「Opt 1 batch ≒ 現行バグ」 「サボってこのバグを実装したのでは」 と 2 度指摘して初めて気付いた。

## Related

- `debug-workflow`: 不可解現象 → 2-3 仮説 → 裏付け → artifact-level fix。 本 skill は debug-workflow の 「fix lock 直前」 stage の追加 verify discipline
- `verify-before-asserting`: positive self-verification claim の exhaustiveness。 本 skill は specific instance (fix correctness)
- `evidence-reporting`: 判定 / 推奨 を発話する前に根拠を示す
- **Legacy:** user memory `feedback_fix_must_differ_from_bug.md` (2026-05-18 checking-style 起票) より昇格
