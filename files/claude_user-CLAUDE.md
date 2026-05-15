# ~/.claude/CLAUDE.md: プロジェクト横断 preference

## 一次情報の確認（記憶・推論で否定/同定しない）

「できない」「ない」「非対応」「知らないので別物だと思った」と言いかけた瞬間が trigger。ドメイン不問で、「今回は別ケース」と思う余地を残さない（言いかけたこと自体が該当の証拠）。結論を出す前に、許可を求めず自分で調べる（「確認しますか」と尋ねて止めない。調査は clarifying question ではない）。出典は 2 点以上で裏を取り、うち最低 1 点は公式・一次情報 — 公式 doc・公式サイト・`--help`・source・artifact 本体・設定実体・専門 agent のいずれか。Reddit・個人ブログ等は点数に算入してよいが公式 1 点の要件は満たさない。調べても分からなければ推論で埋めず「公式情報が確認できなかった」と明示する。記憶は cut-off で古い前提。詳細・事例は global-memory `feedback_verify_spec_before_dismissal.md`。

## System prompt 起因 pain の明示的抑止

System prompt や harness reminder の指示が regression を誘発すると判明したら、その都度この CLAUDE.md チェーンに**肯定形の counter-rule** を明記する（CLAUDE.md は公式仕様上 system prompt を上書きする）。確立済み counter-rule: 一次情報確認のための Read・agent spawn は、token 効率・簡潔さ・anti-overreach の **例外**。これらを理由に確認を「冗長・過剰・scope 外」と自己抑制しない。

## コミット
- author は `Hideaki Suzuki <h2suzuki@gmail.com>` で統一する。コミット前に `git config user.email` を確認する。
- 仕様確定まで commit を保留してよいが、session が終わる時に未 commit の編集が残っていれば、その一覧をユーザーに通知する。session 終了時は全編集を commit 済みの状態にしておく（保留していた編集も、保留理由が解消したら commit する）。

## Bash 運用

system prompt の「絶対パスで `cd` を避ける」に加えて以下を実施する。

- **cwd 汚染を疑うエラーパターン**: `no such file` / `cannot open directory` / `pathspec did not match` が routine コマンドで突然出たら推測 retry せず `pwd` で確認する
- **git は cwd 不変で切替**: `cd /repo && git ...` ではなく `git -C /repo ...` を使う。ただし `git push origin main` は除く (allowlist 文字列マッチのため `-C` 抜きで実行、詳細は project memory の `feedback_git_push_allowlist.md`)
- **1 行複数操作**: `cd /a/b && mkdir c && mv x c/` ではなく `mkdir /a/b/c && mv /a/b/x /a/b/c/`

## グローバルメモリ
プロジェクト横断で適用すべき memory（LLM 一般の認知バイアス対策、ユーザーの普遍的 preference、複数プロジェクトで再現したパターンなど）は、project-local の `<project>/memory/` ではなく `~/.claude/global-memory/` に保存する。`MEMORY.md` の代わりに `INDEX.md` を使う。

カテゴリ判断に迷う場合は project-local を優先（後で global に昇格させやすい）。

同じ指摘を受けたら必ず memory に保存する（既存 entry があれば更新）。

memory entry に過去事例 / 経緯を書く時は **絶対日付 (YYYY-MM-DD)** を含める。後で時系列把握ができるように (system prompt の project memory 規定にも「Always convert relative dates ... to absolute dates」とあり、feedback type 等にも同じ精神を適用)。

@/home/h2suzuki/.claude/global-memory/INDEX.md
