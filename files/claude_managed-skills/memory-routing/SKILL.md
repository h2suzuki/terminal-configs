---
name: memory-routing
description: Decide memory entry save location (user vs project-local), generation (MEMORY.md vs OLD-MEMORY.md), save timing, and absolute date format; retire entries to OLD-MEMORY.md when fully covered by a Managed skill / hook / CLAUDE.md rule.
when_to_use: TRIGGER when user gives a correction / feedback, about to say "memory に書く / 保存" etc, uncertain about user vs project-local routing, or a feedback entry becomes covered by a new skill / hook / CLAUDE.md rule.
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
3. **feedback_*.md 本文末尾に cover 元への言及 1 行を追加** (entry 本体への追記も Edit 不可 → grant を mint してから full content を Write し直す。 step 1・2 の index file 編集は gate 対象外で Edit 可):
   ```
   **Covered by:** <cover 元> — YYYY-MM-DD OLD-MEMORY.md 移動
   ```
4. **feedback_*.md 本体 (概要 + 事例 + provenance) は保持**: 退役後も provenance 参照価値あり

### Partial coverage

部分 cover (Managed skill / hook が一部 cover、 entry の core angle / provenance / 事例が固有) の場合は **MEMORY.md 残置**、 feedback_*.md 本文末尾に 1 行言及 (同じく Edit 不可 → grant + full content Write):

```
**Partially covered by:** <cover 元> (本 entry は <固有 angle> が固有)
```

未 cover 範囲を Managed skill / hook 化する場合は user と相談しながら段階的に。 完全に Managed cover された時点で Retirement protocol へ。

### reminder + keywords lines in feedback body

各 feedback entry の本文先頭 (frontmatter 直後) に **2 行** を置く。 UserPromptSubmit の SQLite hook が、 prompt に **keywords** が match した entry の **reminder** 文を inject する。 reminder (表示) と keywords (match) を分離するのは、 表示文を keyword 詰めにして「要約」化させない (= 過去の drift) ため。

```markdown
---
name: foo
description: ...
metadata:
  type: feedback
---

reminder: <同じミスを二度としないための actionable な是正指示。 1 文>
keywords: <その状況が再発した時の prompt に出る選択的な match 語>

<本文 Why / How>
```

**reminder (surface 時に表示・inject される文)**:

**誰向けか**: model 自身。 prompt が keywords に match した時、 UserPromptSubmit hook が `reminder` + `詳細: <path>` を additionalContext に inject する (`<memory-surface>` で囲う)。 **body (Why/事例) は inject されない** — model は path を開かない限り body を読まない。 ゆえ reminder は**それ単体で行動を正せる self-sufficient な是正指示**にする。

- **要約でなく「是正指示」** — incident の叙述や description 再述でなく、 「X する前に Y せよ」 「Z するな (理由)」 等、 読んだ瞬間に再発を止める rule を先頭に置く
- **keyword を盛らない** — match は keywords 行が担うので reminder は自然文で読みやすく
- **事案名・jargon を入れない** — behavioral nudge は具体事案名や jargon を入れても効きにくい。 一般的な是正指示にする (個別事案・事例は entry 本文に書く)
- **1 文・150 字以内** — hook output は 1 行、 長文は verbose で無視される。 `memory_routing_gate` が 150 字超を deny する (hard 化)

良い例 / 悪い例:

- 良い: 「memory entry を書く前に、 引用 source が claim を直接支えるか 1 文で self-check せよ」 (単体で行動を正せる是正指示)
- 悪い: 「2026-05-28 に feedback_X で起きた件」 (事案の叙述で何をすべきか不明。 事案は body へ)
- 悪い: 「verify が大事」 (一般論で actionable でない)

**keywords (match 専用。 reminder とは別行)**:

keywords は **ranking ノブ** — entry は keywords 無しでも body だけで match しうるが、 keywords は「その状況の prompt で本 entry を top-1（or 強い 2 件目）に選ばれやすく + 弱 match 足切り (bm25 floor) を超えやすくする」選択的 boost (SEO で重要語を前方に置くのに近い)。 広い語を盛ると無関係 prompt に hit して逆効果なのは下記。

- **選択的に** — その状況が**本当に再発した時だけ** prompt に出る固有語 (tool 名 ・path ・error code ・固有名詞) を選ぶ。 過度に広い語 (する ・ファイル ・error 等) は無関係 prompt に hit して context を flood し、 結局無視される (CLAUDE.md ・skill が量で無視されたのと同じ失敗を hook で繰り返す)
- **3+ 字 CJK** — FTS5 trigram tokenizer は 2 字 CJK で match 不可 (「ファイル編集」 等で 3+ 字 run を作る)
- **bilingual** — 英 ・日両方 (例 「Edit ・編集」)
- **固有名詞 ・error code ・絶対日付を含める** — 「`bg_collect_verdict`」 「`stuck (max attempts)`」 等

reminder: 行が無い entry は本文先頭非空行が fallback (劣化、 必ず reminder: を置く)。 旧 `oneline_summary:` は廃止 (read されない)。

### Write gate: entry を書く前に grant を mint

memory entry (`~/.claude/memory/*.md` ・ `~/.claude/projects/<enc>/memory/*.md`) への書込は managed hook (`memory_routing_gate.py`) が gate する。 **この skill を経由せず直接 Write した entry は deny される** (Edit/MultiEdit も deny → 必ず full content で Write し直す)。 index file (MEMORY.md / OLD-MEMORY.md) は gate 対象外。

hook を通すには、 entry を Write する **直前に** grant ファイルを Write tool で作る:

1. grant path: `~/.claude/hooks/state/memory-routing/grants/<basename(entry)>`、 中身は entry の絶対パス。 例: entry `~/.claude/memory/feedback_foo.md` → grant `~/.claude/hooks/state/memory-routing/grants/feedback_foo.md`。
2. 直後に entry 本体を Write する (grant は hook が消費 = 1 回限り)。
3. 複数 entry を書くなら各 entry の直前にそれぞれ grant を作る。

内容も hook が検査し、 不備なら deny する (warn は無い → **一発で受理される内容を Write**): 非空の `reminder:` / `keywords:` 行が必須、 `oneline_summary:` 禁止、 keywords は FTS で match する固有語を含む (一般語のみ ・空は不可)。 書式は上記「reminder + keywords」に従う。

### Hook DB sync after entry write or retire

entry を **Write** すると PostToolUse の sync hook (`memory_routing_gate.py sync`) が自動で `memory_surface.py --upsert` を実行し FTS DB に反映する (project-local は path から project_id を導出)。 **保存・更新後の手動 `--upsert` は不要** (gate を通った Write は必ず sync される)。 `--upsert` / `--rebuild` は embed model DB がある環境では dense embedding (hybrid 検索用) も同時に維持する。

#### After retiring to OLD-MEMORY.md

退役は DB から **手動で `--delete`** する (auto-sync は upsert のみで delete しない):

```bash
~/.claude/hooks/memory_surface.py --delete <abs_path> [encoded-cwd]
```

順序注意: 退役 protocol の `Covered by:` footer 追記は (Edit 不可ゆえ) Write になり、 その Write で auto-upsert が走って DB に再登録される。 **`--delete` は footer Write の後に実行** する (逆順だと再登録が残り query が retired entry を surface する)。 退役は `OLD-MEMORY.md` 移動 + footer Write + `--delete` までで 1 単位。

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

hybrid 検索の embed model DB は installer (claude_extensions.sh) が deploy する単独 CLI `claude_memory_embed_build` (stdlib-only) で構築する。 未構築でも hook は BM25 単独に fail-open する。

## Rules

### Save timing

- **同じ指摘を受けたら必ず memory に保存する**: 既存 entry があれば追記、 なければ新規作成
- 1 回目で 「次は気をつける」 で済ませない (session 境界で失われる)

### Memory entry format

過去事例 / 経緯を書くときは、 時系列把握のために **絶対日付 (YYYY-MM-DD) を含める**:

- 良い: 「2026-05-23 のセッションで指摘を受け、 ...」
- 悪い: 「先日の指摘で...」「最近...」「前回のセッションで...」 (相対表現は session 境界で意味不明になる)

## Related

- `writing-code` — Rules「No dangling-prone references in persistent files」 (memory dir 外 file への path 引用禁止)
- `writing-skills` — skill SKILL.md の format / writing convention
