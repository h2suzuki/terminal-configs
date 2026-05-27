---
name: memory-routing
description: Decide memory entry save location (global vs project-local), generation (MEMORY.md vs OLD-MEMORY.md), save timing, and absolute date format; retire entries to OLD-MEMORY.md when fully covered by a skill / hook / CLAUDE.md rule.
when_to_use: TRIGGER when the user gives a correction / feedback (memory check fires every time), when receiving a déjà-vu correction (same point said before — must memorize), when about to say "memory に書く / 保存" / "entry を追加 / 更新", when uncertain whether to route to global or project-local memory dir, when about to Edit / Write a memory entry (date-format gate), or when a feedback entry becomes covered by a newly-added skill / hook / CLAUDE.md rule (retire to OLD-MEMORY.md).
---

# Memory Routing

memory entry の保存先 (global vs project-local) と保存タイミングの rule、 および 2 世代化 (MEMORY.md 現役 + OLD-MEMORY.md 退役) の退役 protocol。 同じ指摘を二度受けないように、 また保存先 / 世代を一貫させるための discipline。

## Process

### Routing decision (priority 1 → 3)

#### 1. Global (`~/.claude/memory/`) — cross-project scope

以下に該当する memory は **global** に保存:

- **LLM 一般の認知バイアス対策**: cut-off / hedging / confabulation 等、 モデルに普遍的な regression
- **ユーザーの普遍的 preference**: 複数プロジェクトに渡る言語 / 文体 / commit 慣習 / コミュニケーション流儀
- **複数プロジェクトで再現したパターン**: 1 プロジェクトで観測した issue が他でも起きると判明

global の index file 名は **`MEMORY.md`**。

#### 2. Project-local (`<project>/memory/`) — project-specific scope

以下は **project-local** に保存:

- 特定 file / 特定 module / 特定 deploy 手順に絡む rule
- そのプロジェクト固有の convention / 設計選択
- 特定 codebase の bug / regression / workaround

project-local の index file 名は **`MEMORY.md`**。

#### 3. 迷ったら project-local

**カテゴリ判断に迷う場合は project-local を優先**。 後で global に昇格させやすい (逆は難しい)。

### Two-generation retirement

各 memory dir は 2 世代構成:

- **`MEMORY.md`** — 現役 entry の index
- **`OLD-MEMORY.md`** — skill / hook / CLAUDE.md で完全 cover された退役 entry の index

#### Retirement trigger

feedback entry が以下のいずれかで完全 cover された時点で退役:

- 新 skill / hook が同主旨を trigger 文言・rule 文言ともに逐語的に cover
- CLAUDE.md (org / user / project) に同主旨の rule が直接書かれた

#### Retirement protocol

1. **MEMORY.md から該当行を削除**
2. **OLD-MEMORY.md に行を移動** (アグレッシブに短縮、 移動日付と cover 元を併記):
   ```
   - [短縮 title](feedback_<name>.md) YYYY-MM-DD OLD移動 (<type>: <cover 元>)
   ```
   `<type>` は `skill` / `hook` / `CLAUDE.md` のいずれか
3. **feedback_*.md 本文末尾に cover 元への言及 1 行を追加**:
   ```
   **Covered by:** <cover 元> — YYYY-MM-DD OLD-MEMORY.md 移動
   ```
4. **feedback_*.md 本体 (概要 + 事例 + provenance) は保持**: 退役後も provenance 参照価値あり

### Partial coverage

部分 cover (skill / hook が一部 cover、 entry の core angle / provenance / 事例が固有) の場合は **MEMORY.md 残置**、 feedback_*.md 本文末尾に 1 行言及:

```
**Partially covered by:** <cover 元> (本 entry は <固有 angle> が固有)
```

未 cover 範囲を skill / hook 化する場合は user と相談しながら段階的に。 完全に skill / hook 化された時点で Retirement protocol へ。

## Rules

### Save timing

- **同じ指摘を受けたら必ず memory に保存する**: 既存 entry があれば追記、 なければ新規作成
- 1 回目で 「次は気をつける」 で済ませない (session 境界で失われる)

### Memory entry format

過去事例 / 経緯を書くときは、 時系列把握のために **絶対日付 (YYYY-MM-DD) を含める**:

- 良い: 「2026-05-23 のセッションで指摘を受け、 ...」
- 悪い: 「先日の指摘で...」「最近...」「前回のセッションで...」 (相対表現は session 境界で意味不明になる)

## Related

- `code-writing` — Rules「No dangling-prone references in persistent files」 (memory dir 外 file への path 引用禁止)
- `skill-writing` — skill SKILL.md の format / writing convention
