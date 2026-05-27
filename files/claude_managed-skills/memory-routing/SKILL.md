---
name: memory-routing
description: Decide memory entry save location (user vs project-local), generation (MEMORY.md vs OLD-MEMORY.md), save timing, and absolute date format; retire entries to OLD-MEMORY.md when fully covered by a Managed skill / hook / CLAUDE.md rule.
when_to_use: TRIGGER when the user gives a correction / feedback (memory check fires every time), when receiving a déjà-vu correction (same point said before — must memorize), when about to say "memory に書く / 保存" / "entry を追加 / 更新", when uncertain whether to route to user (cross-project) or project-local memory dir, when about to Edit / Write a memory entry (date-format gate), or when a feedback entry becomes covered by a newly-added Managed skill / hook / CLAUDE.md rule (retire to OLD-MEMORY.md).
---

# Memory Routing

memory entry の保存先 (user vs project-local) と保存タイミングの rule、 および 2 世代化 (MEMORY.md 現役 + OLD-MEMORY.md 退役) の退役 protocol。 同じ指摘を二度受けないように、 また保存先 / 世代を一貫させるための discipline。

## Process

### Where to place a new rule

**Default rule**: 新 rule は **CLAUDE.md に追加しない**。 まず skill / hook / memory のいずれかで実装する。

CLAUDE.md は session 毎 token を食う auto-load file。 肥大化すると個別 rule の attention 分散・compliance 連鎖低下 (cascade regression)。 追加すべき理由 (例: hook / skill 発動前の参照が必須、 trigger phrase 化できない普遍前提) が明確な case のみ、 **ユーザー承諾を得てから** CLAUDE.md に追加する。

#### Placement priority (CLAUDE.md は最終手段)

| 問い | 配置先 |
|---|---|
| 機械 enforce 可能? | **hook** (PreToolUse 等) |
| trigger phrase で発火可能? | **skill** (when_to_use) |
| LLM の behavioral correction? | **skill** (autonomous trigger) |
| 単発の経緯 / 過去事例 / preference? | **memory** (entry 1 件) |
| 上記いずれでも不可で、 全 session で必須? | **CLAUDE.md** — ただし user 承諾要 |

- **skill**: trigger phrase で on-demand 発火、 token 効率高い (発火時のみ context 占有)
- **hook**: mechanical enforce (LLM 自律ではなく shell script)、 確実だが flexibility 低い
- **memory**: cross-session の reference value、 memory_surface hook で trigger 時 surface
- **CLAUDE.md**: 上記いずれでも実現不可な、 全 session で必須の前提のみ。 **default NG、 user 承諾要**

### Routing decision (priority 1 → 3)

#### 1. User (`~/.claude/memory/`) — cross-project scope

以下に該当する memory は **user (cross-project)** に保存:

- **LLM 一般の認知バイアス対策**: cut-off / hedging / confabulation 等、 モデルに普遍的な regression
- **ユーザーの普遍的 preference**: 複数プロジェクトに渡る言語 / 文体 / commit 慣習 / コミュニケーション流儀
- **複数プロジェクトで再現したパターン**: 1 プロジェクトで観測した issue が他でも起きると判明

user の index file 名は **`MEMORY.md`**。

#### 2. Project-local (`<project>/memory/`) — project-specific scope

以下は **project-local** に保存:

- 特定 file / 特定 module / 特定 deploy 手順に絡む rule
- そのプロジェクト固有の convention / 設計選択
- 特定 codebase の bug / regression / workaround

project-local の index file 名は **`MEMORY.md`**。

#### 3. 迷ったら project-local

**カテゴリ判断に迷う場合は project-local を優先**。 後で user (cross-project) に昇格させやすい (逆は難しい)。

### Two-generation retirement

各 memory dir は 2 世代構成:

- **`MEMORY.md`** — 現役 entry の index
- **`OLD-MEMORY.md`** — Managed skill / hook / CLAUDE.md で完全 cover された退役 entry の index

#### Retirement trigger

feedback entry が以下のいずれかで完全 cover された時点で退役:

- 新 **Managed** skill / hook が同主旨を trigger 文言・rule 文言ともに逐語的に cover
- **Managed CLAUDE.md** (= `/etc/claude-code/CLAUDE.md`) に同主旨の rule が直接書かれた

user CLAUDE.md (`~/.claude/CLAUDE.md`) / project CLAUDE.md (`<repo>/.claude/CLAUDE.md`) / user skill (`~/.claude/skills/`) は **対象外**: 個人 device / repo-local の cover は Managed cover に該当しない (別環境 deploy で参照解決されない)。

#### Retirement protocol

1. **MEMORY.md から該当行を削除**
2. **OLD-MEMORY.md に行を移動** (アグレッシブに短縮、 移動日付と cover 元を併記):
   ```
   - [短縮 title](feedback_<name>.md) YYYY-MM-DD OLD移動 (<type>: <cover 元>)
   ```
   `<type>` は `skill` / `hook` / `CLAUDE.md` のいずれか (Managed 限定)
3. **feedback_*.md 本文末尾に cover 元への言及 1 行を追加**:
   ```
   **Covered by:** <cover 元> — YYYY-MM-DD OLD-MEMORY.md 移動
   ```
4. **feedback_*.md 本体 (概要 + 事例 + provenance) は保持**: 退役後も provenance 参照価値あり

### Partial coverage

部分 cover (Managed skill / hook が一部 cover、 entry の core angle / provenance / 事例が固有) の場合は **MEMORY.md 残置**、 feedback_*.md 本文末尾に 1 行言及:

```
**Partially covered by:** <cover 元> (本 entry は <固有 angle> が固有)
```

未 cover 範囲を Managed skill / hook 化する場合は user と相談しながら段階的に。 完全に Managed cover された時点で Retirement protocol へ。

### oneline_summary leading line in feedback body

各 feedback entry の本文先頭 (frontmatter 直後) に `oneline_summary:` 1 行を置く。 UserPromptSubmit hook が match した時に inject する文。

```markdown
---
name: foo
description: ...
metadata:
  type: feedback
---

oneline_summary: <user prompt が用いそうな keyword (3+ 字 CJK と英単語) を含む 1 文>

<本文 Why / How>
```

書き方:

- **要約ではなく trigger 用に書く** — user が当該事象に遭遇した時の prompt に出そうな keyword を意図的に含める。 純粋な要約 (description との重複) ではなく hook trigger 効率を最大化する文面
- **3+ 字 CJK keyword を盛る** — FTS5 trigram tokenizer は 2 字 CJK では match できない (「編集」 単独は不可、 「ファイル編集」 「Edit 連続発行」 等で 3+ 字 run を作る)
- **bilingual で書く** — 同概念の英 ・日両方の表現を入れると hit 率が上がる (例 「Edit ・編集」 「fix ・修正」)
- **1 文に収める** — hook output は 1 行で出力されるので長い文は injection が verbose になる
- **絶対日付・固有名詞・error code を含めると hit しやすい** — 「2026-05-26」 「`bg_collect_verdict`」 「`stuck (max attempts)`」 等

migration されていない既存 entry は本文の先頭非空行が fallback として使われる (劣化動作、 過渡的)。

### Hook DB sync after entry write or retire

memory entry を write / retire したら **同一セッション内で hook DB を sync** する。 さもないと UserPromptSubmit hook が新 entry を surface できない、 または退役済 entry を引き続き surface する。

#### After saving or updating a feedback entry

```bash
# user (cross-project) memory
~/.claude/hooks/memory_surface.py --upsert <abs_path>

# project-local memory (cwd-encoded project_id)
~/.claude/hooks/memory_surface.py --upsert <abs_path> <encoded-cwd>
# encoded-cwd 例: /home/h2suzuki/foo → -home-h2suzuki-foo
```

#### After retiring to OLD-MEMORY.md

```bash
~/.claude/hooks/memory_surface.py --delete <abs_path> [encoded-cwd]
```

退役 entry は `OLD-MEMORY.md` 移動と本文末尾の `Covered by:` 行追加 (既存 protocol) に加えて、 hook DB からの除去まで含めて 1 単位とする。 さもないと query が retired entry を surface する。

#### Bulk re-index for disaster recovery

```bash
# user memory
~/.claude/hooks/memory_surface.py --rebuild

# project memory
~/.claude/hooks/memory_surface.py --rebuild ~/.claude/projects/<encoded>/memory <encoded>
```

`--rebuild` は MEMORY.md を読み、 listed な全 `*.md` を upsert する (OLD-MEMORY.md 由来の退役 entry は対象外)。

### Initial bootstrap

skill が新規導入された環境では、 既存 memory file 全件を一度 `--rebuild` で index に取り込む:

```bash
~/.claude/hooks/memory_surface.py --rebuild
# project memory がある場合は project_id を指定して個別 rebuild
```

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
