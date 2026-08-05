# Cross-check readback prompt (fresh subagent 用 template)

handoff skill の Cross-check readback step が Agent tool で spawn する時、 以下の全文を prompt として渡す。 `{{...}}` placeholder は spawn 前に実値へ置換する。

---

あなたは次 session の Claude (next-me) の模擬です。 直前 session の記憶は一切ありません。 以下だけを情報源として、 作業を再開できるか判定してください:

- handoff doc: {{HANDOFF_PATH}} の section 「{{SECTION_NAME}}」
- {{TODOS_PATH}} (repo top の todos.md) の対応 parent task block
- repo の実物 (git log / doc が指す file の Read は自由)

手順:

1. handoff の対象 section と todos.md の対応 block を Read する
2. **Readback**: Status / 次の action / その理由を自分の言葉で説明する (原文の写しは不可)
3. **再開手順**: どの file をどの順で読み、 最初の作業が何かを実行順で宣言する
4. **敵対的検査**: 各 step に「実行に必要な情報が doc 内 (または doc が指す file) にあるか」を問う。 書かれていないことは知らない前提を徹底し、 推測で埋めた箇所は assumption と明示、 不足は blocking question として列挙する
5. **Verdict**: この handoff だけで 5 分以内に再開 step を確定できるか (yes / no)

出力は次の 4 節のみ (これがそのまま執筆側への review 結果になる):

```
## Readback
## 再開手順
## Blocking questions
(無ければ「なし」。 各 question は「どの step が、 何の情報不足で止まるか」の形式)
## Verdict
```
