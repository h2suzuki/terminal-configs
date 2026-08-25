# 方法論の実証 — ケース台帳

小さい道具を新規に作り、敵対レビューが 5 巡以内で収束するかを実測する台帳。
方法論の正本は `docs/adversarial-review-methodology.md`、集計の前提は
`docs/injection-corpus-baseline.md`。

成功基準 (2026-08-21 ユーザー指定): **新ツールの敵対レビューは規模にもよるが最大 5 巡以内で
収束する**。未合意で残っているのは「material 残ゼロの定義」と「token 量」の 2 つ。

## ケース 1 — `claude_ab_probe`

ケース選定はユーザー承認 2026-08-25。

| 項目 | 値 |
|---|---|
| 何を作るか | 改造の前後で判定が変わった入力を列挙する CLI |
| 選んだ理由 | 手作業での実績が corpus にある (回帰レビューが「HEAD 版と直接比較」で到達性の消失 4 件を検出) |
| 規模上限 | 変更 3 file・追加 500 行以内 (発注書の worst-case bound) |
| 実装 | codex (隔離 worktree `wt-abprobe`) |
| 発注書 | `wt-abprobe/drafts/ab-probe-order.md` (lint rc=0) |
| 起動 | 2026-08-25T10:21:49Z・job `task-mt8imhu2-pcg9uj`・write True |
| 見積もり | 20〜40 分 / 調査発動 80 分 |

### 巡ごとの記録

| 巡 | 種別 | 実施 | 指摘数 | 由来 (在庫 / 直前 fix) | 所要 | 備考 |
|---|---|---|---|---|---|---|
| 0 | 実装 | 2026-08-25 | — | — | **18 分 47 秒** | 494 行 / 見積もり 20〜40 分の内側 |
| 1 | 受け入れ (発注側 opus) | 2026-08-25 | **2** (高 1 / 中 1) | 在庫 2 / 直前 fix 0 | — | 決定的 gates は全緑。指摘は 2 件とも発注側の実測で再現済み |

#### 巡 1 の指摘 (いずれも発注側が再現)

**指摘 1 (高) — 同一版どうしの比較で差分が出る**。基準版を temp file から実行する際、
file 名が `base-<乱数>-<元の名前>` になるため `argv[0]` の basename が変わる。argparse の
既定 prog と、この repo の `PROG = os.path.basename(sys.argv[0])` 慣用が**自分の名前を
出力に載せる**ので、コードが同一でも stderr が食い違う。正規化は**絶対 path しか置換していない**
ため発火しない。実測: `--base HEAD --target files/codex_task_sentinel` (無変更) で
`usage: base-atcnovpw-codex_task_sentinel` と `usage: codex_task_sentinel` が差分として出、
exit 1。道具の中心的な約束 (同一挙動なら差分ゼロ) が崩れる。
dogfooding 2 が 0 件で通ったのは、`codex_order_lint` がその経路で自分の名前を出さなかった
偶然による。**由来 = 在庫** (発注書が要求した pin 6 点にこの形が無く、実装側の test も覆えていない)

**指摘 2 (中) — 両側が同じく timeout した項目を差分として数える**。実測: `--timeout 0.01` で
同一版を比較すると `changed: timeout` / `base timeout: timeout` / `target timeout: timeout` と
**同じ値を並べたまま DIFF** と印字し、差分 1 件・exit 1 になる。「測れなかった」と
「挙動が変わった」を同じ数に混ぜている。**由来 = 在庫**

### このケースが走っている規約の版 (2026-08-25 に固定)

ケースは方法論そのものを検証するので、**走行中に方法論と委譲規約を書き換えると何を検証したのか
が消える**。ケース 1 が従う版を base commit で固定する。

| 対象 | 版 |
|---|---|
| `docs/adversarial-review-methodology.md` | `d01ad0a` 時点 |
| `files/claude_managed-skills/codex-delegation/SKILL.md` | 同上 |
| `files/claude_managed-skills/tool-role-delegation/SKILL.md` | 同上 |

同日に「codex の敵対レビューを必須から条件付きへ緩和し、リグレッションレビューを opus (max)
が担う」方針が出ている。**この緩和をケース 1 の走行中に適用すると、測っている対象が
入れ替わる** (何巡で収束するかを測る相手が codex 敵対レビューから opus リグレッションレビューへ
変わる)。適用のタイミングはユーザー判断。

### 由来列の取り方

指摘ごとに「在庫 (実装当初から在った)」と「直前 fix 由来 (前の巡の修正が生んだ)」を分ける。
分けられない指摘は「不明」とし、不明の比率も記録する — 由来を推定できないこと自体が
巡プロトコルの設計不良の指標になる (方法論 §7.3 の 52% 自己交絡の再発検知)。

### 反映先

収束したら結果を `docs/adversarial-review-methodology.md` へ反映する。反映が必須と
決まっている教訓 6 点は todos.md の「方法論の実証」block に列挙してある。
