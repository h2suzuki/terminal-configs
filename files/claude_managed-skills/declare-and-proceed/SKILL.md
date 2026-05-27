---
name: declare-and-proceed
description: batch / iterative 作業 (memory entry draft / 多数 file 一括 Edit / mechanical sweep / 同種 review pass 等) では per-entry / per-batch で user に採否や style calibration を聞かず、 verbalize で方針を 1 度宣言して proceed する。 review は user が事後 chat log を見て指摘する流れに任せる
when_to_use: TRIGGER when about to ask user 「この style で良い?」 / 「この draft で進める?」 / 「OK ですか?」 / 「次に進んで良い?」 per entry / per batch during iterative work (memory entry migration / 多数 file 一括 Edit / mechanical sweep / 同種 review pass / migration / promotion), or when about to use AskUserQuestion to seek per-batch approval during such work. SKIP for design-level choices (アーキ / 命名 / 優先度 / scope 境界) which still need user agreement, for pre-approval of destructive ops (push --force / reset --hard / branch 削除), or for the first 1 unit where style 方針 has not been verbalize-declared yet.
---

# Declare and Proceed

batch / iterative な作業で per-entry / per-batch に user 確認を求めない。 一度方針を verbalize 宣言したら proceed、 user は事後 chat log で review して指摘する流れに任せる。

## Rules

### 適用範囲

batch / iterative work:

- memory entry の oneline_summary draft
- 多数 file の一括 Edit / sweep
- mechanical bulk transform (rename / format 統一 等)
- 同種 review pass
- migration / promotion / retirement の batch 化

### 1 unit 目で verbalize 宣言

最初の 1 unit (entry / batch) で **style 方針を verbalize 宣言** する:

- どんな draft style か (例: 「3+字 CJK keyword + 絶対日付 + bilingual の 1 文」)
- どの scope か (例: 「user memory 11 entry」)
- 件数 / 完了基準

### 以降は proceed、 per-unit の確認は不要

宣言後は per-unit の 「これで良い?」 を user に聞かない。 chat log review に任せる。

### User が tone / depth / 用語を変えたい時は事後指摘で

chat log を遡って user が指摘する流れ。 私から逐一伺いを立てない。

## 例外 (依然 user 合意を取る case)

- **設計レベル選択** (アーキ / 命名 / 優先度 / scope 境界) は no-redundant-design-litigation の例外条件 = taste / priority に該当するので通常通り ask
- **破壊的 op の pre-approval** (push --force / reset --hard / branch 削除 等) は commit-discipline の通り
- **1 unit 目で style 宣言を verbalize していない時**: 最初の 1 件で宣言を行う (skip しない)

## Why

chat log は cheap & reversible な review channel。 per-batch 確認は overhead が高く fast iteration を妨げる。 user の judgment は事後でも cost が低い (log scan + 1 wording 指摘)。 inverse: 私が per-entry に聞くと、 user は同じ judgment を 5 回繰り返すことになる。

2026-05-27 セッションで memory oneline_summary migration の sample draft を 1 entry 提示した後、 user が 「私に聞かないでも、 やることを宣言してくれたらよいです。 変えてほしかったら、 チャットログをみて後ほど指摘します。」 と明示。

## Related

- `no-routing-questions`: 投資路選択を user に丸投げしない。 本 skill は逆方向 (per-batch 確認を user に振らない) の同根則
- `design-agreement-checkpoint`: 設計レベルは依然 user 合意。 本 skill は batch execution 局面の振る舞いに限定
- `verbalize-before-action`: 1 度の verbalize 宣言は本 skill でも必須
- **Legacy:** user memory `feedback_declare_and_proceed.md` (2026-05-27 起票) より昇格
