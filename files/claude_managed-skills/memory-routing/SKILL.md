---
name: memory-routing
description: Decide memory entry save location (org / user / project scope in the shared git clone), save timing, absolute date format, and per-model tags (models: line, cross-model search, tag propagation); retire entries via claude_memory_sync --retire when fully covered by a Managed skill / hook / CLAUDE.md rule.
when_to_use: TRIGGER when user gives a correction / feedback, about to say "memory に書く / 保存" etc, uncertain about org / user / project routing, a feedback entry becomes covered by a new skill / hook / CLAUDE.md rule, or about to conclude "できない" / "実行不能" / "環境の制約" or hitting a second failure on the same work (pull side, not write).
---

# Memory Routing

memory entry の保存先 (org / user / project-local) と保存タイミングの rule、 および退役 protocol (file 削除 = git 履歴が archive)。 同じ指摘を二度受けないように、 また保存先を一貫させるための discipline。

## Process

### Where to place a new rule

**Default rule**: 新 rule は **CLAUDE.md に追加しない**。 まず skill / hook / memory のいずれかで実装する。

CLAUDE.md は session 毎 token を食う auto-load file。 肥大化すると個別 rule の attention 分散・compliance 連鎖低下。 追加すべき理由 (例: hook / skill 発動前の参照が必須、 trigger phrase 化できない普遍前提) が明確な case のみ、 **ユーザー承諾を得てから** CLAUDE.md に追加する。

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

### Routing decision (priority 1 → 4)

entry の置き場は共有 clone `/var/lib/claude-rag-memory/claude-lessons-learned` 配下 (canonical は同名の private GitHub repo)。 index file は無い — **dir に file が存在する = 現役** (退役 = file 削除、 git 履歴が archive)。

#### 1. Org (`<clone>/org/`) — user-independent scope

ユーザー個人に依らない教訓は **org (全ユーザーに surface)** に保存する:

- **LLM 一般の認知バイアス対策**: cut-off / hedging / confabulation 等、 モデルに普遍的な regression
- **tool / 環境の一般教訓**: 使い方・落とし穴のうち、 特定ユーザーの好みに依らないもの
- **複数プロジェクトで再現したパターン**: 1 プロジェクトで観測した issue が他でも起きると判明し、 内容が user 非依存のもの

#### 2. User (`<clone>/user/<login>/`) — personal preference scope

そのユーザー本人に固有のものだけを **user** に保存 (判定基準: **個人情報を含むか** — 本人の呼称・好み・個人環境の事情が本文に入るなら user):

- **ユーザーの普遍的 preference**: 複数プロジェクトに渡る言語 / 文体 / commit 慣習 / コミュニケーション流儀
- 他のユーザーには当てはまらない working style の教訓

#### 3. Project-local (`<clone>/project/<project-id>/`) — project-specific scope

以下は **project-local** に保存。`<project-id>` は
`~/.claude/hooks/memory_surface.py --project-id` で取得する (origin remote URL の正規化形
`github.com-<owner>-<repo>`。remote 無し repo・非 git dir は cwd の `/`→`-` encode に
fallback。ユーザーや checkout path に依存しない。暗算で導出しない):

- 特定 file / 特定 module / 特定 deploy 手順に絡む rule
- そのプロジェクト固有の convention / 設計選択
- 特定 codebase の bug / regression / workaround

#### 4. 迷ったら狭い scope

**カテゴリ判断に迷う場合は狭い scope (project > user > org の順) を優先**。 後で広い scope へ昇格させやすい (逆は難しい)。 org か user かで迷ったら user。

### Retirement (git history is the archive)

feedback entry が以下のいずれかで完全 cover された時点で退役:

- 新 **Managed** skill / hook が同主旨を trigger 文言・rule 文言ともに逐語的に cover
- **Managed CLAUDE.md** (= `/etc/claude-code/CLAUDE.md`) に同主旨の rule が直接書かれた

user CLAUDE.md (`~/.claude/CLAUDE.md`) / project CLAUDE.md (`<repo>/.claude/CLAUDE.md`) / user skill (`~/.claude/skills/`) は **対象外**: 個人 device / repo-local の cover は Managed cover に該当しない (別環境 deploy で参照解決されない)。

#### Retirement protocol

```bash
claude_memory_sync --retire <entry の絶対パス>
```

1 コマンドが git rm → commit → detached push → index --delete を正しい順序で実行する。 provenance は git 履歴が永続保存するので footer 追記は不要 — 退役 entry を読み返す時は clone で `git log --diff-filter=D --summary` / `git show <rev>:<path>` を使う。

### Partial coverage

部分 cover (Managed skill / hook が一部 cover、 entry の core angle / provenance / 事例が固有) の場合は **現役のまま残し** (file は削除しない)、 feedback_*.md 本文末尾に 1 行言及 (Edit 不可 → grant + full content Write):

```
**Partially covered by:** <cover 元> (本 entry は <固有 angle> が固有)
```

未 cover 範囲を Managed skill / hook 化する場合は user と相談しながら段階的に。 完全に Managed cover された時点で Retirement protocol へ。

### Entry types (file 名 prefix)

entry の種別は file 名 prefix で表す (gate が検証し、 他 prefix は deny)。 frontmatter の `metadata.type` も prefix と揃える:

| Prefix | 種別 | 本文の必須要素 |
|---|---|---|
| `feedback_*` | 行動是正の教訓 | h2 は `理由` → `対処` (任意) → `事例` → `関連` (任意) の固定語彙 ・固定順 ・各 1 回。 `## 理由` と `## 事例` (絶対日付 YYYY-MM-DD を含む) は必須 |
| `reference_*` | 外部仕様の調査 snapshot | 確認日 (YYYY-MM-DD)。 見出しは自由 |

**2 層契約**: h2 = 固定の役割語彙、 h3 = 自由。 深掘り分析 (`### 技術的真相` 等) は `## 理由` の下、 再発 ・追記は `## 事例` の下に `### YYYY-MM-DD — <要旨>` を積む (日付先頭 = 時系列 log として append)。 旧 prefix (project_* 等) の entry は再 Write する機会に feedback_* へ rename する。

### reminder + keywords + models lines in frontmatter

各 entry の frontmatter 内 (metadata の後) に **3 行** を置く。 UserPromptSubmit の SQLite hook が、 prompt に **keywords** が match した entry の **reminder** 文を inject する。 reminder (表示) と keywords (match) を分離するのは、 表示文を keyword 詰めにして「要約」化させないため。 **models** はその教訓を観測したモデルの tag で、 surface を model-scope 化する。

```markdown
---
name: foo
description: ...
metadata:
  type: feedback
reminder: <同じミスを二度としないための actionable な是正指示。 1 文>
keywords: <その状況が再発した時の prompt に出る選択的な match 語>
models: <観測モデルの短形式 tag (例 fable-5)。 複数は space 区切り>
---

## 理由

<原因 ・機序>

## 対処

<是正手順 (任意)>

## 事例

- YYYY-MM-DD: <発生事例>

## 関連

<隣接 entry / skill (任意)>
```

parser (memory_surface.py) は **dual-read** — frontmatter (正書式) と本文 (旧形式) の両位置を読むため、 旧形式の既存 entry はそのまま surface され続ける。 ただし再 Write 時は gate が新書式を要求するので、 その機会に frontmatter へ移す。

**reminder (surface 時に表示・inject される文)**:

**誰向けか**: model 自身。 prompt が keywords に match した時、 UserPromptSubmit hook が `reminder` + `詳細: <path>` を additionalContext に inject する (`<memory-surface>` で囲う)。 **body (Why/事例) は inject されない** — model は path を開かない限り body を読まない。 ゆえ reminder は**それ単体で行動を正せる self-sufficient な是正指示**にする。

- **要約でなく「是正指示」** — incident の叙述や description 再述でなく、 「X する前に Y せよ」 「Z するな (理由)」 等、 読んだ瞬間に再発を止める rule を先頭に置く
- **keyword を盛らない** — match は keywords 行が担うので reminder は自然文で読みやすく
- **事案名・jargon を入れない** — behavioral nudge は具体事案名や jargon を入れても効きにくい。 一般的な是正指示にする (個別事案・事例は entry 本文に書く)
- **1 文・150 字以内** — hook output は 1 行、 長文は verbose で無視される。 `memory_routing_gate` が 150 字超を deny する

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

reminder: 行が無い entry は本文先頭非空行が fallback (劣化、 必ず reminder: を置く)。 `oneline_summary:` 行は書かない (read されず、 gate が deny する)。

**models (model-scope tag。 reminder / keywords とは別行)**:

surface hook (UserPromptSubmit / Stop) は **実行中モデルの tag を持つ entry だけ** を inject する (実行中モデルは statusline cache → transcript から自動判別)。 `models:` 行が無い entry は `opus-4.8` とみなす (tag 導入前世代の既定 = モデル世代交代でいったん mute する意図的 reset)。

- **自分のモデルを書く**: system prompt の model id (例 `claude-fable-5`) の短形式 (`fable-5`) を書く。 フル ID でも可 (index 時に正規化)
- **複数可**: 同じ教訓を複数モデルで観測したら space 区切りで並べる (例 `models: opus-4.8 fable-5`)
- **観測ベース**: 「効きそうだから」で tag を盛らない。 そのモデルで実際に観測・再発した時に下記 Tag propagation で追記する

### Tag propagation (新しい学びを得た時 / 壁と結論する前)

**引く側の trigger**: 「できない」 「実行不能」 「権限がない」 「環境の制約」 と結論しかけた時と、 同じ作業で 2 回失敗した時は、 entry を書く予定が無くても下記 1. の横断検索を先に実行する。 `--search` は model filter を通さないので、 **自分の tag が無くて mute されていた過去の教訓がここで初めて見える**。 今の状況にも当てはまれば 2. で tag を追記し、 当てはまらなければ何もしない (「効きそうだから」 で tag を盛らない)。

新しい教訓を entry 化する前に、 モデル横断で過去の教訓を検索し、 同じ教訓なら tag 追記・無ければ新規作成する:

1. **横断検索**: `~/.claude/hooks/memory_surface.py --search "<学びの要旨>" [project-id]` — model filter / throttle / 記録なしで全 entry を対象に `score<TAB>models<TAB>path<TAB>reminder` を返す。 同じ教訓かは LLM が判断する
2. **hit (既存 entry が同じ教訓)** → その entry の `models:` に自分のモデル tag を追記し、 grant → full content Write → auto-upsert の通常手順で保存する
3. **miss** → 新規 entry を作成し `models:` に自分のモデル tag を書く
4. **mismatch 統計**: model 不一致で mute された would-be hit は inject_log に `kind='mismatch'` で記録される。 集計すると「他モデルの教訓で自モデルにも刺さりそうなもの」が見える (tag 追記候補の定量材料):

   ```bash
   sqlite3 /var/lib/claude-rag-memory/memory_index.sqlite3 \
     "SELECT file_path, model, COUNT(*) FROM inject_log \
      WHERE kind='mismatch' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10"
   ```

### Write gate: entry を書く前に grant を mint

memory entry (`<clone>/org/*.md` ・ `<clone>/user/<login>/*.md` ・ `<clone>/project/<enc>/*.md`; clone = `/var/lib/claude-rag-memory/claude-lessons-learned`) への書込は managed hook (`memory_routing_gate.py`) が gate する。 **この skill を経由せず直接 Write した entry は deny される** (Edit/MultiEdit も deny → 必ず full content で Write し直す)。 README.md 等の非 entry file は gate 対象外。 旧 location (`~/.claude/memory` / `~/.claude/projects/<enc>/memory`) への書込は clone への redirect deny、 clone 不在/破損時は閉塞 deny (install_claude_extensions 再実行で復旧)。

hook を通すには、 entry を Write する **直前に** grant ファイルを Write tool で作る:

1. grant path: `~/.claude/hooks/state/memory-routing/grants/<basename(entry)>`、 中身は entry の絶対パス。 例: entry `<clone>/user/<login>/feedback_foo.md` → grant `~/.claude/hooks/state/memory-routing/grants/feedback_foo.md`。
2. 直後に entry 本体を Write する (grant は hook が消費 = 1 回限り)。
3. 複数 entry を書くなら各 entry の直前にそれぞれ grant を作る。

内容も hook が検査し、 不備なら deny する (warn は無い → **一発で受理される内容を Write**): 非空の `reminder:` / `keywords:` / `models:` 行が **frontmatter 内** に必須、 file 名 prefix は feedback_ / reference_ のみ、 feedback は本文 h2 が固定語彙 ・固定順 (`## 理由` ・`## 事例` 必須、 自由見出しは h3)、 本文に絶対日付 (YYYY-MM-DD) 必須、 `oneline_summary:` 禁止、 keywords は FTS で match する固有語を含む (一般語のみ ・空は不可)、 models は小文字短形式 tag (フル ID も可)。 書式は上記「reminder + keywords + models」に従う。

### Hook sync after entry write

entry を **Write** すると PostToolUse の sync hook (`memory_routing_gate.py sync`) が自動で `claude_memory_sync --commit` を実行し、 FTS DB 反映 (scope は path から導出) + git commit + detached push まで行う。 **保存・更新後の手動 upsert / commit / push は不要** (gate を通った Write は必ず sync される)。 index 更新は embed model DB がある環境では dense embedding (hybrid 検索用) も同時に維持する。

退役の DB 削除は `claude_memory_sync --retire` に内蔵 (Retirement protocol 参照) なので手動 `--delete` は不要。

#### Bulk re-index for disaster recovery

```bash
claude_memory_sync --full
```

clone に存在する全 scope (org / user / project) を wipe + 再 upsert する。 pull / push / sync 状態の確認は `/memory-sync` (`claude_memory_sync --status`)。

### Initial bootstrap

新環境では installer (install_claude_extensions) が clone 作成と `claude_memory_sync --full` まで実行する。 hybrid 検索の embed model DB は base installer が deploy する単独 CLI `claude_memory_rag_builder` (stdlib-only) で構築する。 未構築でも hook は BM25 単独に fail-open する。

## Rules

### Save timing

- **同じ指摘を受けたら必ず memory に保存する**: 既存 entry があれば追記、 なければ新規作成
- 1 回目で 「次は気をつける」 で済ませない (session 境界で失われる)

### Memory entry format

過去事例 / 経緯を書くときは、 時系列把握のために **絶対日付 (YYYY-MM-DD) を含める**:

- 良い: 「2026-05-23 のセッションで指摘を受け、 ...」
- 悪い: 「先日の指摘で...」「最近...」「前回のセッションで...」 (相対表現は session 境界で意味不明になる)

## Related

- `memory-sync` — clone の sync 状態確認 / 手動 pull / 退役 / 全再 index (git transport 側)
- `writing-code` — Rules「No dangling-prone references in persistent files」 (memory dir 外 file への path 引用禁止)
- `writing-skills` — skill SKILL.md の format / writing convention
