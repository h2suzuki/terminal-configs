# codex 利用規定 — 置換対象の anchor 一覧

外から来る発注ポリシーを当てるための、**行番号に依存しない**対象一覧。
各 anchor は本 file 生成時に grep で 1 件だけ当たることを実測している。
生成 2026-08-25。

| # | 対象 file | anchor (逐語・この文字列で当てる) | 命中 |
|---|---|---|---|
| 1 | `files/claude_managed-skills/tool-role-delegation/SKILL.md` | `description: Route work to the right executor when codegraph` | 1 |
| 2 | `files/claude_managed-skills/tool-role-delegation/SKILL.md` | `3. **実装は codex へ委譲**: `/codex:rescue <spec>` で codex に渡す (長時` | 1 |
| 3 | `files/claude_managed-skills/tool-role-delegation/SKILL.md` | `- **codex 未認証 / 利用不可時は Claude が直接**: 委譲できないので degrade して Cla` | 1 |
| 4 | `files/claude_managed-skills/tool-role-delegation/SKILL.md` | `- **役割境界を守る**: 実装は codex、 仕様・指示・バグ出し・レビューは Claude。 patch 反映や` | 1 |
| 5 | `files/claude_managed-skills/tool-role-delegation/SKILL.md` | `- **trivial の数値境界 (2026-08-21 ユーザー決裁)**: Claude が直接編集してよい so` | 1 |
| 6 | `files/claude_managed-skills/tool-role-delegation/SKILL.md` | `4. **Claude がレビュー**: codex が返したコードを敵対的 / 受け入れレビューし、 バグ・仕様逸脱・` | 1 |
| 7 | `files/claude_managed-skills/tool-role-delegation/SKILL.md` | `検索は codegraph の適切なツール、 実装は `/codex:rescue` 委譲 → Claude レビュー、` | 1 |
| 8 | `files/claude_managed-skills/codex-delegation/SKILL.md` | `SKIP when codex plugin is unavailable or the work is a trivi` | 1 |
| 9 | `docs/adversarial-review-methodology.md` | `- **G0. 構造審査 (巡 0) — 実装前に「この構造で本当によいのか」を 1 巡だけ問う**:` | 1 |
| 10 | `docs/adversarial-review-methodology.md` | `成果物は構造承認 or 作り直し案の判定のみ。判定` | 1 |
| 11 | `docs/adversarial-review-methodology.md` | `- **L1. 認定基準を事前に固定する**: 「最強レビューアの K 巡連続・` | 1 |
| 12 | `docs/adversarial-review-methodology.md` | `- **R2. レビュー戦力は非対称に配る**: 巡内レビューは実装と別系のモデ` | 1 |
| 13 | `docs/adversarial-review-methodology.md` | `1. **write path は codex を既定とする** (現に収束実績がある側)。opus を write に` | 1 |
| 14 | `docs/adversarial-review-methodology.md` | `2. **review path の opus xhigh は維持する**。実装 (codex) と別系のモデルであるこ` | 1 |
| 15 | `docs/adversarial-review-methodology.md` | `**fix 受け入れの回帰 filter (2026-08-22 ユーザー採用)**: fix 納品の受け入れは「決定的` | 1 |
| 16 | `docs/sentinel-convergence-log.md` | `4. **実装・レビュー体制** — 実装 = codex (refactor は sol xhigh 推奨・通常巡は ` | 1 |
| 17 | `files/claude_managed-hooks/codex_delegation_surface.py` | `PreToolUse ExitPlanMode : plan -> 実装の境界。 実装を /codex:rescue へ` | 1 |
| 18 | `files/claude_managed-hooks/codex_delegation_surface.py` | `"[codex-delegation] plan を終え実装に入ります。 tool-role-delegation: 実` | 1 |
| 19 | `files/claude_managed-hooks/codex_delegation_surface.py` | `"--effort。 Claude は仕様明文化・レビュー・バグ出しを担い、 c` | 1 |
| 20 | `files/claude_managed-hooks/codex_delegation_surface.py` | `"`codex-delegation` skill を invoke。 triv` | 1 |
| 21 | `files/claude_managed-hooks/codex_delegation_surface.py` | `"レビューを回避)。 tool-role-delegation step4: コ` | 1 |
| 22 | `/var/lib/claude-rag-memory/claude-lessons-learned/org/feedback_self_build_impulse.md` *(帰属を訂正)* | `reminder: コードを書き始める前に委譲判定を先に置け — 実装 token は本当に価値ある部分だけに使い、既存` | 1 |
| 23 | `/var/lib/claude-rag-memory/claude-lessons-learned/org/feedback_self_build_impulse.md` *(帰属を訂正)* | `2. **trivial の数値境界**: 単一 file・追加 10 行以内・test 追加なし。1 つでも超えたら ` | 1 |
| 24 | `/var/lib/claude-rag-memory/claude-lessons-learned/org/feedback_self_build_impulse.md` *(帰属を訂正)* | `3. **境界超過の自作には、委譲不採用の理由 1 行の記録と敵対レビューを必須とする** (「Claude が書いた ` | 1 |
| 25 | `/var/lib/claude-rag-memory/claude-lessons-learned/org/feedback_delegation_failure_no_self_impl.md` *(帰属を訂正)* | `1 回の raw error で自前実装へ切り替えると、委譲方針 (永続コードは委譲先に書かせる) が失敗のたびに崩れ、` | 1 |
| 26 | `todos.md` | **未確定** — 行跨ぎ。適用時に手で当てる | 0 |

**一意に当たる 25 / 26**。

## 統合レポート側の誤り (実測で判明)

- **file の帰属が 4 件ずれていた** — `codex_delegation_surface.py` の節に置かれていた 4 つの引用は、
  実際には memory entry (`org/feedback_self_build_impulse.md` 3 件 /
  `org/feedback_delegation_failure_no_self_impl.md` 1 件) の文言だった
- **行番号が 1 件ずれていた** — 「5 巡以内の決定保証」は 117 行と書かれていたが実際は 119 行

ゆえに適用時は行番号でなく本表の anchor で当てる。

## 反映 (2026-08-27)

正本 `docs/codex-delegation-policy.md` を anchor 経由で反映した後の再実測:

- 書き換えで消えた anchor = #2・#4〜#8・#17〜#21 (12 件、命中 0)。#1 と #3 は文言を保った (命中 1)
- #9〜#15 は凍結 doc への置換で 2026-08-26 に消滅、#22〜#25 は entry 退役で消滅 (後継 `org/feedback_self_build_over_delegation.md` は同日改訂済み)
- #16 は凍結済み履歴 doc のため反映先から外した (命中 1 のまま)
