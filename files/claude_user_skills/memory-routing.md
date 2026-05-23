---
name: memory-routing
description: Decide memory entry save location (global vs project-local) and save timing; past events / dates use absolute YYYY-MM-DD format.
when_to_use: TRIGGER when the user gives a correction / feedback (memory check fires every time), when receiving a déjà-vu correction (same point said before — must memorize), when about to say "memory に書く / 保存" / "entry を追加 / 更新", when uncertain whether to route to global or project-local memory dir, or when about to Edit / Write a memory entry (date-format gate).
---

# Memory Routing

memory entry の保存先 (global vs project-local) と保存タイミングのルール。 同じ指摘を二度受けないように、 また保存先を一貫させるための discipline。

## Process

### Routing decision (priority 1 → 3)

#### 1. Global (`~/.claude/global-memory/`) — cross-project scope

以下に該当する memory は **global** に保存:

- **LLM 一般の認知バイアス対策**: cut-off / hedging / confabulation 等、 モデルに普遍的な regression
- **ユーザーの普遍的 preference**: 複数プロジェクトに渡る言語 / 文体 / commit 慣習 / コミュニケーション流儀
- **複数プロジェクトで再現したパターン**: 1 プロジェクトで観測した issue が他でも起きると判明

global の index file 名は **`INDEX.md`** (project-local の `MEMORY.md` ではなく)。

#### 2. Project-local (`<project>/memory/`) — project-specific scope

以下は **project-local** に保存:

- 特定 file / 特定 module / 特定 deploy 手順に絡む rule
- そのプロジェクト固有の convention / 設計選択
- 特定 codebase の bug / regression / workaround

project-local の index file 名は **`MEMORY.md`**。

#### 3. 迷ったら project-local

**カテゴリ判断に迷う場合は project-local を優先**。 後で global に昇格させやすい (逆は難しい)。

## Rules

### Save timing

- **同じ指摘を受けたら必ず memory に保存する**: 既存 entry があれば追記、 なければ新規作成
- 1 回目で 「次は気をつける」 で済ませない (session 境界で失われる)

### Memory entry format

過去事例 / 経緯を書くときは、 時系列把握のために **絶対日付 (YYYY-MM-DD) を含める**:

- 良い: 「2026-05-23 のセッションで指摘を受け、 ...」
- 悪い: 「先日の指摘で...」「最近...」「前回のセッションで...」 (相対表現は session 境界で意味不明になる)

## Related

- **Legacy:** user CLAUDE.md「グローバルメモリ」 より
