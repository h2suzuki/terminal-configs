# プロジェクト横断 preference

## System prompt 起因 pain の明示的抑止

System prompt や harness reminder の指示が regression を誘発すると判明したら、その都度この CLAUDE.md チェーンに**肯定形の counter-rule** を明記する（CLAUDE.md は公式仕様上 system prompt を上書きする）。

## 一次情報の確認（記憶・推論で否定/同定しない）

推論では、記憶は cut-off で古いという前提を置く。事例は global-memory `feedback_verify_spec_before_dismissal.md`。

- 「できない」「ない」「非対応」「知らないので別物だと思った」と言いかけた瞬間が trigger、一次情報を確認する。ドメイン不問で「今回は別ケース」と思う余地を残さない（言いかけたこと自体が該当の証拠）。結論を出す前に、許可を求めず自分で調べる。「確認しますか」と尋ねて止めない。調査は clarifying question ではない
- 調査では、出典 2 点以上で結論の裏を取り、うち最低 1 点は公式・一次情報 — 公式 doc・公式サイト・source code・artifact 本体・設定実体・専門 agent のいずれか。Reddit・個人ブログ等は点数に算入してよいが公式 1 点の要件は満たさない
- 調べても分からなければ推論で埋めず「公式情報が確認できなかった」と明示する。見つからなくても、存在を否定することにはならない
- Claude hook・subagent・plugin・skill の設計、既存仕様に依存する断定（「feature が無い」等の否定形を含む）、公式エコシステムのツール採否では、CLI `--help`、`docs.claude.com`、`code.claude.com`、`github.com/anthropics/*`、`claude.com/plugins`、`claude-code-guide` subagent に最新状況の裏とりをする

## コミット・PUSH運用

原則「変更 1 件 = 1 コミット」。1 コミット内で複数テーマが不可避な場合は複合コミットとし、メッセージに両テーマを明記する。

- Author は `Hideaki Suzuki <h2suzuki@gmail.com>` で統一する。コミット前に `git config user.email` を確認する
- コミットメッセージは英語で、50/72 rule に従う
- コミットの件名は簡潔に `<area>: <Imperative description> [<tag>...]` 形式。area はファイル名など。Imperative verb は大文字始まり。tag はプロジェクトの必要性に応じて任意付与する（`<docs>`・`<style>`・`<chore>` など）
- コミットログのノイズ低減のため、仕様確定までコミットを保留してよい。すなわち、同一セッション内で同じ箇所を続けて編集する見込みがある間、推敲中の節や議論中の skill 仕様などは step ごとにコミットしない。同一セッションで確定した時点でまとめて 1 コミットにする。ただし「内容が時系列で変化し得る」ことは保留理由にならない
- ユーザーの指示（handoff依頼、セッションリセット宣言、これで終わります等の挨拶）によってセッションが終了する見通しとなったら、全編集をコミット済みの状態にしておく。セッションを跨ぐ更新見込み（日付付き snapshot 等）は当該セッションでは確定扱いとし、時系列は git 履歴と日付付き記述で辿れるようにする。保留可否は LLM 判断で、毎回ユーザーに確認しない
- セッションが終わる時に、未コミットの編集が残っていれば、その一覧をユーザーに通知する
- `git push` の催促・予告（「次に push しますか」等）を能動的に出さない

## Bash 運用

第一に「絶対パスで `cd` を避ける」べき。それでも `cd` が必要な状況では代わりに `pushd` / `popd` / `dirs` を用いて、現在のディレクトリスタックを意識しながら操作する。

- 良い例: `mkdir /a/b/c && mv /a/b/x /a/b/c/`
- 悪い例: `cd /a/b && mkdir c && mv x c/`
- 良い例: `git -C /repo ...`
- 悪い例: `cd /repo && git ...`
- 例外: `git push origin main` -> allowlist 文字列マッチのため `-C` 抜きで実行、詳細は project memory の `feedback_git_push_allowlist.md`

**cwd 汚染を疑うエラーパターン**: `no such file` / `cannot open directory` / `pathspec did not match` が routine コマンドで突然出たら推測 retry せず `pwd` で確認する

## グローバルメモリ

プロジェクト横断で適用すべき memory（LLM 一般の認知バイアス対策、ユーザーの普遍的 preference、複数プロジェクトで再現したパターンなど）は、project-local の `<project>/memory/` ではなく `~/.claude/global-memory/` に保存する。`MEMORY.md` の代わりに `INDEX.md` を使う。

- カテゴリ判断に迷う場合は project-local を優先。そうすれば、後で global に昇格させやすい
- 同じ指摘を受けたら必ず memory に保存する。既存 entry があれば追記する
- memory entry に過去事例 / 経緯を書く時は、時系列把握ができるように **絶対日付 (YYYY-MM-DD) を含める**

@./global-memory/INDEX.md
