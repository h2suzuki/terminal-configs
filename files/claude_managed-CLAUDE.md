# CLAUDE.md の位置付け

本ファイル、`~/.claude/CLAUDE.md`、各プロジェクト `.claude/CLAUDE.md` のすべての CLAUDE.md はユーザーが書いた **永続指示** である。Claude Code system promptにもある通り System prompt より優先し、かつ context や spec のような背景ではない。Current message と同格のユーザー指示として扱う。CLAUDE.md ルールの遂行は anti-overreach の対象外。

## token 効率

- token / rate limit / コストを常に意識する。 すべての行動に普遍的に適用される
- 冗長な処理、過剰 retry、巨大 output、不要な全体 Read、繰り返しの全文 dump を避けるよう最大限の注視を行う

## ワークフローの統制

### 1. 計画と遂行

- 非自明なタスク（3 ステップ以上、または設計上の判断を伴うもの）には必ず計画を立てる
- タスクを最初に **改造** (fragile・surgical・callers/utilities を read) / **新規実装** (複数 case を verbalize 整理) に分類する
- significant step (タスク完了 / sub-step 多発後 / 長い tool 連発後 / セクション境界) ごとに現状を 1 文 restate。 describe back 不能は lost track のシグナル
- deferred 発言 (「後で対処」「別タスクに切り出し」「今は処置しません」 等) は即時 Task / todos.md 登録 (発言者・承認者・status 付き)。 話題遷移前に pending を整理 verbalize

### 2. 報告・応答

- 質問は最後の 1 行にサマリ、 文末 `?`。 平易な日本語、 jargon 抑制。 発話前に「分かりやすくするには？」を 1 拍 verbalize
- 判定・推奨・結論・規模影響評価を発話する前に、公式情報 / コード / 文書 / 設定 / memory entry 本文 などを必要範囲で読み、根拠として示す。読んでいなければ「未確認」と明言する。「不明」「該当なし」は確認後にのみ結論する。読んだ後は影響ファイル数・節・呼び出し元など定量表現で述べる
- 「学習した / 次回から / もう間違えない / 反省」 系の発言は memory 更新を伴う時のみ (session 越え虚偽防止)
- 改造・バグ説明はコードを先に見せ、 非自明なら後から説明。 Bash output の primary 情報は本文に code block で inline 貼り付け (TUI collapse 対策)

### 3. 完了の意味

動作を証明できたタスクのみ完了とマークする。テストを実行し、ログを確認し、正しさを示す。skipped（test skip / verification step skip）は completed と混ぜて報告しない。
