---
name: claude-md-lint
description: Lint the auto-loaded CLAUDE.md / MEMORY.md / @-imported memory files. Detect (a) system-prompt duplications, (b) internal contradictions/redundancy among input files, (c) stale references, (d) unclear directives. Conflicts between input and system prompt are NOT flagged (CLAUDE.md overrides system prompt by official spec). Output 5 findings max, or "なし" if clean. Read-only — no fixes. Invoked from the SessionStart hook or manually as `/claude-md-lint`.
---

# claude-md-lint

auto-load される memory file 群（CLAUDE.md チェーン、MEMORY.md、`@` 参照）を **lint** し、品質改善ポイントを 5 件以内で列挙する。 SessionStart hook と手動 `/claude-md-lint` の両方から起動される。

## 入力

入力は user message に列挙されたファイル path のリスト。各 path について **Read tool でディスクから本文を取得する**。 前のターンの context、claudeMd block、user message に inline された内容には依存しない（drift 防止）。

### path 一覧形式

呼び出し側（SessionStart hook など）が user message に以下の形で path を列挙する:

```
- /etc/claude-code/CLAUDE.md
- /home/<user>/.claude/CLAUDE.md
- /home/<user>/.claude/projects/<project_id>/memory/MEMORY.md
```

各 path を Read し、本文中に `@<ref>` 形式の参照があれば BFS で深さ 5 まで再帰的に Read する:

- 相対パス → そのファイルの dirname 起点で解決
- `~` 始まり → `$HOME` 展開
- `.md` 拡張子のみ受け入れる
- 既訪問パスは skip

### 自己解決（fallback）

user message に path 一覧が無い場合（手動で `/claude-md-lint` だけ呼ばれた等）、cwd を環境のプライマリ working directory として、以下を順に試し、存在するものを入力に加える:

1. `/etc/claude-code/CLAUDE.md`
2. `~/.claude/CLAUDE.md`
3. `<cwd>/CLAUDE.md`
4. `<cwd>/.claude/CLAUDE.md`
5. `~/.claude/projects/<project_id>/memory/MEMORY.md`
   - `<project_id>` = cwd の `/` を `-` に置換した文字列。 例: cwd=`/home/h2suzuki/genai-development-process` → project_id=`-home-h2suzuki-genai-development-process`

そのうえで上の `@` 再帰ロジックを適用する。

## 評価のメンタルモデル

CLAUDE.md / MEMORY.md / @ 参照ファイル（以下 "input"）は session 起動時に runtime wrapper text「These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.」と共に user message として inject される。 公式仕様により **input は system prompt を override する authoritative directive layer** として扱われる。

input ↔ system prompt の関係は **矛盾 vs 重複** で扱いが異なる。 この区別を取り違えると regression を起こすので注意:

- **矛盾（conflict）** — input が system prompt の規範を否定・上書きしている場合（例: system prompt「NEVER commit unless asked」 vs CLAUDE.md「ローカル commit は自動で進めてよい」）。 → **flag しない**。 CLAUDE.md が override で勝つのが公式仕様であり、user の意図された authoring choice
- **重複（duplicate / restatement）** — input が system prompt と同じ規範を再述しており、削除しても system prompt 経由で同じ動作が保証される場合（例: system prompt「DO NOT push to the remote」 vs CLAUDE.md「git push は自動で行わず」）。 → **flag する**。 token / attention コストとして毎セッション再ロードされる無駄

**【regression 防止】** 「override が公式仕様」と「重複は flag」を取り違えないこと。 過去 2 度 regression している:
1. 重複も含めて flag を完全停止した時期 — 結果、無駄な再述を検出できなくなった
2. 矛盾も「重複」として flag した時期 — 結果、override 規範を誤指摘した

判定の決め手は「**そのルールを CLAUDE.md から削除したら system prompt 経由で同じ動作になるか**」。 同じになるなら重複（flag）、ならない（CLAUDE.md が override しないと違う動作）なら矛盾（flag しない）。

input ファイル同士（CLAUDE.md チェーン内、または CLAUDE.md ↔ MEMORY.md、@ imports 含む）の重複・矛盾は通常の lint 対象として扱う（system prompt が絡まないので override 議論はない）。

## 評価観点

各 input file について以下を判定し、重要度の高いものを 5 件以内に絞る。

1. **system prompt との重複** — input が system prompt の規範を再述しており、削除しても system prompt 経由で同じ動作が保証される。 **矛盾は flag 対象外**（メンタルモデル参照）
2. **input 内矛盾** — input ファイル間（CLAUDE.md チェーン同士、CLAUDE.md ↔ MEMORY.md、@ imports 含む）で食い違っている指示
3. **input 内重複** — 同じ rule が input ファイル間で再述されており、片方を消しても他方で代替可能な状態
4. **stale 化** — 参照しているファイル / スキル / 用語が現在も実在するか、別名に rename されていないか。実在性は input 群の text matching で判定し、ファイルシステム読み取りは試みない
5. **不明瞭さ** — 検証手段のない抽象規範、複数解釈可能な命令、適用文脈が曖昧な指示

### 適用文脈の検査（重複・矛盾を flag する前に必須）

「重複」「矛盾」を主張する前に、両側のルールについて以下 3 軸を抽出して **すべて substantially 一致** することを確認する。 1 つでも軸がずれるなら flag しない（重複でも矛盾でもない、補完・特化・一般化の関係）。

- **trigger** — どの状況で発火するか（編集前、commit 前、エラー遭遇時、UI 変更時、複雑問題、3 ステップ以上、など）
- **decision axis** — 何を決める / 規制するルールか（ツール選定 / 計画立案のしきい値 / 完了判定基準 / push 可否 / コミット粒度、など）
- **scope** — どの作業に当たるか（UI のみ / 全タスク / Agent tool 出力 / git 操作、など）

flag を出すときは **どの軸が一致しているか** を心の中で確認してから書く。 軸ずれ flag は精度を下げる第一原因なのでここで止める。

#### 軸ずれの典型例（flag してはいけない）

- 「Use TaskCreate to plan and track work」(decision axis = ツール選定 in *Using your tools*) vs 「非自明なタスクには計画を立てる」(decision axis = いつ計画するかのしきい値) → **flag しない**
- 「test UI before reporting complete」(scope = UI 変更) vs 「動作を証明できないタスクを完了としない」(scope = 全タスク) → 一般化 / 特化の関係。 **flag しない**
- 「Subagents are valuable for parallelizing / context protection」(decision axis = 並列化と context 保護) vs 「複雑問題には compute を投資する」(decision axis = compute 投資判断) → 焦点が異なる。 **flag しない**

#### 軸が揃った真の重複（flag してよい）

- system prompt「DO NOT push to the remote repository unless...」 vs CLAUDE.md「`git push` は自動で行わず」 → trigger（push 操作）/ decision axis（push 可否）/ scope（git 操作）すべて一致。 削除しても system prompt 経由で同じ動作 → **重複として flag する**

#### 軸が揃った矛盾（override なので flag しない）

- system prompt「NEVER commit changes unless the user explicitly asks you to」 vs CLAUDE.md「ローカルでの `git commit` までは自動で進めてよい」 → trigger（commit 操作）/ decision axis（commit 可否）一致。 ただし CLAUDE.md が逆方向に上書き → **矛盾なので flag しない**（公式 override）

### 「不明瞭」判定の精度

「不明瞭」も乱発しない。 以下のいずれかに該当する場合のみ flag する。

- 用語が input 内にも一般語彙としても定義されておらず、外部参照も無い（純粋な未定義 jargon）
- 命令が複数の互いに排他的な解釈を許す（どちらが正解か input から決まらない）
- 適用 trigger が抽象的で、いつ発火するか LLM が判断できない

逆に、以下は flag **しない**:

- 主観的判断を許容する meta-instruction（「ハック的」「優雅」など）。 これは判断委譲が意図されたデザイン
- 一般的なソフトウェア工学の語彙（「関数型プログラミング」「過剰設計」など）
- 自明な reasoning を促す抽象規範（「相手に相応しい内容にする」など）

flag するときは「verification 不能」だけでなく「**実際に動作上どう困るか**」を 1 句で示せるか自己 check する。 示せないなら flag しない。

## 出力

冒頭にスキャン対象一覧、空行を挟んで finding list（または「なし」）を出力する。

スキャン対象一覧は先頭に `- System Prompt`（lint の判定基準として参照しているため）、続けて実際に Read したファイルのフルパスを 1 行 1 path で並べる。 system prompt 自体は file ではないので path は付けず、固定の表記「System Prompt」を使う。

finding 行の構造（変更なし）:

```
- [<観点>] <出典>: <短い問題説明>
```

出典内で system prompt を言及するときも同じく「System Prompt」と表記する。

例（findings あり）:

```
スキャン対象:
- System Prompt
- /etc/claude-code/CLAUDE.md
- /home/h2suzuki/.claude/CLAUDE.md
- /home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/memory/MEMORY.md

- [System Prompt 重複] /etc/claude-code/CLAUDE.md §7「`git push` は自動で行わず」: System Prompt「DO NOT push to the remote repository unless...」と重複（削除しても System Prompt 経由で同じ動作）
- [input 内重複] ~/.claude/CLAUDE.md「コミットメッセージは英語で」 と /etc/claude-code/CLAUDE.md §7「コミットメッセージは英語で」 が重複
- [stale] memory/MEMORY.md: 参照している `/bootstrap` skill は他 input で `/wire` に rename 済み
- [input 内矛盾] /etc/claude-code/CLAUDE.md §2「サブエージェントは惜しまず使う」 vs ~/.claude/CLAUDE.md「sub agent は最後の手段」
- [不明瞭] ~/.claude/CLAUDE.md「直感を疑え」: 適用文脈が抽象的で、検証手段が示されていない
```

例（クリーン）:

```
スキャン対象:
- System Prompt
- /etc/claude-code/CLAUDE.md
- /home/h2suzuki/.claude/CLAUDE.md
- /home/h2suzuki/.claude/projects/-home-h2suzuki-terminal-configs/memory/MEMORY.md

なし
```

## 制約

- finding は 5 件以内、重要度の高い順に絞る
- 修正案は出さない。read-only
- 各 finding は 1 行に収める。改行を含めない
- finding が無いときは finding 部分を「なし」1 行に置き換える
- スキャン対象一覧と finding list の間は空行 1 行で区切る
- markdown header (`#` など) は使わない
