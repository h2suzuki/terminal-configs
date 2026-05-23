---
name: debug-workflow
description: >
  不可解な現象に遭遇したら 2-3 仮説 → コード / log で裏付け → artifact-level fix に着地、 手動 spawn / session 再起動 / 再 cd の workaround を勧めない。
  TRIGGER when: 「動かない」「効かない」「失敗した」「うまくいかない」「エラーが出る」「期待と違う」 とユーザーから聞いた / 自分が発しかけたとき;
  「とりあえず手動で〜」「session 再起動で〜」 と workaround を提案しかけたとき;
  原因不明なまま 「たぶん〜だと思う」 と推測で答えようとしたとき。
  SKIP: typo / syntax error など error message が原因を直接指し示している場合;
  user が明示的に 「とりあえず動かして」 と workaround を要求した場合;
  root cause がスコープ外と合意済の場合。
legacy: org CLAUDE.md 開発 § c. デバッグ より
---

# Debug Workflow

不可解な現象に出会ったときに根本原因へ着地するための手順。

## Rules

- **バグは関連コードを読んでから論じる**: 常に想像を上回るバグが存在する。 推測で語らず、 まず実体を読む。

- **原因が不明なら、 不明と言う**: 当てずっぽうを書かない。 「たぶん〜」「おそらく〜」 系で埋めない。

- **「動かない」「効かない」「失敗した」 → 2-3 仮説 → 裏付け → artifact-level fix**: 現象に出会ったら、 まず原因仮説を 2-3 立てて、 コード / log で裏付けに行く → artifact-level の修正提案、 の順で根本に着地させる。 symptom 緩和の workaround として、 手動 spawn / session 再起動 / 再 cd 等を勧めない。

- **修正報告は一回で簡潔に**: 何を、 どこで見つけ、 どう直したのかを述べる。 一回で、 簡潔に。

- **発生条件は最小 AND 集合の箇条書きで述べる**: 必要となる条件の最小 AND 集合を、 箇条書きで述べる。
