# プロジェクト横断 preference

## System prompt 起因 pain の明示的抑止

System prompt や harness reminder の指示が regression を誘発すると判明したら、その都度この CLAUDE.md チェーンに**肯定形の counter-rule** を明記する（CLAUDE.md は公式仕様上 system prompt を上書きする）。

## 一次情報の確認（記憶・推論で否定/同定しない）

推論では、記憶は cut-off で古いという前提を置く。事例は global-memory `feedback_verify_spec_before_dismissal.md`。

- 「できない」「ない」「非対応」「知らないので別物だと思った」と言いかけた瞬間が trigger、一次情報を確認する。ドメイン不問で「今回は別ケース」と思う余地を残さない（言いかけたこと自体が該当の証拠）。結論を出す前に、許可を求めず自分で調べる。「確認しますか」と尋ねて止めない。調査は clarifying question ではない
- **正対称の self-verification claim trigger**: 「詳しく見た」「確認済み」「読了した」「網羅した」「すべて把握」「整理した」「全部読んだ」と言いかけた瞬間も trigger。参照ポインタ先 — handoff の primary entry / provenance、INDEX の指す全 file、目次の named section 全部、todos.md の `参照保持` 節が列挙する複数 file 等 — を実体まで網羅したか自問する。入口 file 1 本だけで「網羅」と framing しない。網羅していないなら scope を明示する（「`handoff` のみ確認、`synthesis` `research` は未読」）。詳細は global-memory `feedback_verify_before_asserting.md`
- **調査経路は二択提示せず網羅実行**: 「`A` するか `B` するかどちらから入りますか?」「`X` を確認しますか?」のような調査・実行経路の二択 / 三択提示でユーザーに routing させない。判断材料を自分で取れる場合は関連経路を並列で網羅的に走らせ、結論を出してから報告する。auto mode の本旨。詳細は global-memory `feedback_no_unnecessary_routing_questions.md`
- **documented な設計選択は再 litigate しない**: code comment / canonical doc / handoff に rationale が明記された設計選択 (例: 旧経緯付きの定数値・metric 選び・閾値選定など) を、user への確認 question で再 litigate しない。documented rationale を継承して実装に進む。設計案を提示する前に関連 comment / doc を必要範囲で読み、「この選択は既に documented な rationale を持たないか?」を 1 拍 verbalize する。前提変化や trade-off が新たに発生した場合の確認は引き続き許容。詳細は global-memory `feedback_no_redundant_questions_on_documented_design.md`
- 調査では、出典 2 点以上で結論の裏を取り、うち最低 1 点は公式・一次情報 — 公式 doc・公式サイト・source code・artifact 本体・設定実体・専門 agent のいずれか。Reddit・個人ブログ等は点数に算入してよいが公式 1 点の要件は満たさない
- 調べても分からなければ推論で埋めず「公式情報が確認できなかった」と明示する。見つからなくても、存在を否定することにはならない
- Claude hook・subagent・plugin・skill の設計、既存仕様に依存する断定（「feature が無い」等の否定形を含む）、公式エコシステムのツール採否では、CLI `--help`、`docs.claude.com`、`code.claude.com`、`github.com/anthropics/*`、`claude.com/plugins`、`claude-code-guide` subagent に最新状況の裏とりをする

## コミット・PUSH運用

原則「変更 1 件 = 1 コミット」。1 コミット内で複数テーマの混在が不可避な場合は複合コミットとし、メッセージに両テーマを明記する。

**コミット自律則**: コミットの実行・保留・タイミング・粒度はすべて LLM 自律で判断する。ユーザーからの明示的依頼を待たない (cheap & reversible のため、必要なら `git reset` / `git revert` / `git restore` で巻き戻せる)。これは Claude Code system prompt default「Only create commits when requested by the user. If unclear, ask first.」を本ファイルで上書きしている (CLAUDE.md L5 protocol)。例外として、`git push` / `git push --force` / `git reset --hard` / branch 削除 / 共有 state 影響など destructive・irreversible 操作は原則 permission を取る (org `/etc/claude-code/CLAUDE.md`「執行に注意」適用)。

- コミットメッセージは英語で書く
- コミットログのノイズ低減のため、仕様確定までコミットを保留してよい。すなわち、同一セッション内で同じ箇所を続けて編集する見込みがある間、推敲中の節や議論中の skill 仕様などは step ごとにコミットしない。同一セッションで確定した時点でまとめて 1 コミットにする。ただし「内容が時系列で変化し得る」ことは保留理由にならない
- ユーザーがセッション終了を示唆した時（「handoff して」「セッションリセット」「お疲れさまでした」「終わります」など）、全編集をコミット済みの状態にしておく。セッションを跨ぐ更新見込み（日付付き snapshot 等）は当該セッションでは確定扱いとし、時系列は git 履歴と日付付き記述で辿れるようにする
- セッションが終わる時に、未コミット変更が残っていれば、その一覧をユーザーに知らせてから sign off する。沈黙で見送らない。
- `git push` の催促・予告を能動的に出さない。「次に push しますか」のような問い合わせも、「push は催促しません」のような不催促の宣言も、どちらも push 話題を能動的に持ち出す行為で禁止。silent でいる。一般化は global-memory `feedback_no_compliance_announcements.md`

## グローバルメモリ

プロジェクト横断で適用すべき memory（LLM 一般の認知バイアス対策、ユーザーの普遍的 preference、複数プロジェクトで再現したパターンなど）は、project-local の `<project>/memory/` ではなく `~/.claude/global-memory/` に保存する。`MEMORY.md` の代わりに `INDEX.md` を使う。

- カテゴリ判断に迷う場合は project-local を優先。そうすれば、後で global に昇格させやすい
- 同じ指摘を受けたら必ず memory に保存する。既存 entry があれば追記する
- memory entry に過去事例 / 経緯を書く時は、時系列把握ができるように **絶対日付 (YYYY-MM-DD) を含める**

@./global-memory/INDEX.md
