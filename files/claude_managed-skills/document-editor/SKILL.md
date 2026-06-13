---
name: document-editor
description: Edit persistent artifacts (README / public doc / tutorial / spec / canonical guide / design doc / library API doc / 5+ line code comments / housekeeping prose) in a fork with verbalize-before-edit discipline; write the file back inside the fork and return only a change-summary to main (context bloat protection).
when_to_use: TRIGGER when about to Edit / Write a persistent artifact, or write red-flag phrases ("旧 X との差分" / "執筆経緯" / "〜は含みません" — meta-notes addressed to the author / reviewer, not the reader) into the body. SKIP for ephemeral text (chat / todos.md / drafts/*) or code comments of 4 lines or fewer.
argument-hint: <file-path> <edit-intent>
arguments: file edit_intent
context: fork
agent: general-purpose
---

# Document Editor

fork 内 (general-purpose subagent) で動く。 main session の context は持たない。 SKILL.md と invocation 引数 (`$file` / `$edit_intent`) のみを参照して動く。

## Input

- **`$file`** — 編集対象 artifact の path
- **`$edit_intent`** — 編集意図の 1-2 文要約 (例: 「新規 API 追加に伴う section 追記」「stale 節を整理」)
- (optional) 参考用の補助情報 (関連 commit / 上流 issue 等)

current content は `$file` を Read して subagent が取得する。

## Process

- **分類・読者・節目的・jargon 妥当性を verbalize**: 分類 (README / 公開 doc / 教材 / spec / canonical ガイドライン / 設計書 / ライブラリ API / 5 行以上のコードコメント / ハウスキーピング)、 想定読者 (初心者 / 社外 / 旧版も本対話も知らない将来の自分)、 各節の目的、 jargon 妥当性 を 1 文ずつ言葉にする。 言葉にできなければ source / 周辺ファイルを Read してから戻る。 さらに各文に **想定読者テスト** を当てる: 「この文は誰に向けて書くか」 を問い、 想定読者の task を進める文だけ残す。 執筆者・査読者 (本対話の自分や指示者) にしか意味を持たない弁明・不在の断り・経緯注記は読者宛でないため除去する — これが下記赤信号フレーズ群の上位原則。

- **赤信号フレーズの削除**: 次のいずれかで始まる / 含む節・文・コメントを artifact 本文から除去する (本来は commit message / todos / handoff に書くべき内容): 「このドキュメントが解決した / 修正した / 書き直した」「旧 X との差分」「以前は…だった」「従来は」「矛盾していたので一本化」「reconcile / reconciliation」「執筆経緯」「旧版 changelog」「今回直した点」「今回の修正で」、 不在の断り「〜は含みません / 含まない」「ここでは扱わない」「対象外」 (ある要素が無いことをわざわざ説明する、 読者の task を進めない執筆者・査読者向けの注記)、「検証証跡」「動作確認した」「テストした」 (設計理由でなく検証ログを書いている場合)、「台帳参照 C##/H##/M##」、 対話接続表現「ご指摘の通り」「お答えします」「本書の論点は」 等の自己言及。 **例外**: バグ教訓 guardrail (「ここを Z にすると再帰発火するので必ず W」 等、 将来の改変者の事故防止) は赤信号文言を含んでも削除しない (現在の制約として正当)。

- **discussion label を descriptive name に置換**: Plan C / Phase γ / 案 2 / Option B / Approach 3 等の discussion ラベルを、 確定済みの永続 doc では descriptive name (機能や目的を示す名前) に書き換える。 例: 「Plan C」 → 「retry-with-backoff 方式」、「Phase γ」 → 「bundle protocol」。 選択肢が現存し live に分岐する文脈でのみ discussion label を残す。

- **jargon の平易化または定義補強**: 想定読者 level に合わない jargon を、 平易な言い換え (例: 「cascade」 → 「依存先に連鎖伝播する」) または初出での定義補強 (例: 「cascade (= 変更が依存先に連鎖伝播する仕組み)」) で処理する。 頻出語は定義補強で残し、 1 度しか出ない jargon は平易化する。

<!-- dangling-ref-check: allow (next bullet は rule 説明として ephemeral label を例示) -->
- **family-sweep 義務 (reader-hostile-artifact のクラス対応)**: 1 件でも flag された応答内で、 同 family の他箇所も網羅 sweep する。 family = letter/option/ledger ラベル (Plan C / Phase γ / Option B 等) / `M##` `H##` `C##` 等 ephemeral 台帳 ID / 旧/以前/従来/observed 等 changelog narration triggers / `Phase` 文字。 stated scope だけ忠実にこなして全掃を出さないと、 scope 拡大を user に N 回 driving させる regression (partial-fix の過小一般化より上位の受け身さ)。 (a) pattern family を認識して全 canonical artifact を grep-sweep し、 (b) 名指し increment だけでなく family 全体の網羅修正を proactively 提案 or (bounded・低リスクなら) 実行する。 AskUserQuestion で scope を問う場合も、 選択肢に必ず「family 全体・全 canonical file」 案を含める。

- **established terminology の保存**: skill SKILL.md / canonical doc で繰り返し参照される用語 (= bold-labeled 項目 / frontmatter 繰返し term / section heading) は doc 構造の anchor。 説明文が外部事実と矛盾しているように見えても、 **label 自体を rename / 削除しない** (cross-link dangling 化 / mental model disrupt / API-level breaking change 相当)。 説明文 (描写) だけを事実整合に修正する。 例外: 用語自体が誤りと user / handoff で agreed の場合のみ rename / 削除 OK。

## Output

fork 内で **対象 file を直接 Edit/Write** して書き戻す。 main session への返却は **主な変更の 1 行要約 list のみ** (artifact 本文は file に書き戻し済みなので main の context に再 load しない — これが fork による context 肥大対策の本質)。

要約 list の形式は `<行範囲 or 節> <変更の種類> (<補足>)`。 例:

- `L42-48 赤信号 「このドキュメントが解決した不整合」 節を削除 (commit message へ migrate 推奨)`
- `L88 discussion label 「Plan C」 → 「retry-with-backoff 方式」 に rename`
- `L120 jargon 「cascade」 を 「変更が依存先に連鎖伝播する仕組み」 に置換`
- `L155 対話接続表現 「ご指摘の通り」 を削除`

## What to leave out

- **syntactic style**: paren-density / enumeration-separator / 句読点 / 改行・空行 ルール 等。 別途 syntactic style checker を持つプロジェクトに任せる前提。
- **factual rewrite**: 設計変更や API 仕様変更を伴う書き換え。 本 skill は「読者基準で整える」 だけ。
- **ephemeral 文章**: chat 応答 / drafts/* など fork overhead に見合わない短命な文章。 todos.md は session 越しに残る永続 sink だが、 短い checklist として in-place 編集で十分なため同じく対象外。
- **intent change**: 元の意図を変える書き換え (intent-preserving edit のみ)。
- **短いコードコメント (4 行以下)**: fork overhead に見合わない。 inline で Claude が direct 適用。

## Related

- **inline (fork なし) 適用**: 小さい edit、 1-4 行コードコメント、 1-2 行修正は、 main session の Claude が本 skill の 4-step discipline を verbalize して direct に適用する。 fork の overhead に見合わない場合の fallback。
- **Legacy:** org CLAUDE.md 文章執筆の自己レビュー より
