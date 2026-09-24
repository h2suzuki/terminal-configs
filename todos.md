# Todos

CAVEAT: 調査前の推論 (2026-08-29、ユーザーが court バグと同等の重大バグと認定)
調べる前に立てた推論を、 Claude が事実として出力する。 2026-08-28 18:04 〜 2026-08-29 04:48 の
session (inject_log.session_id = ff720c04) で、 確かめずに書いた断定 8 件のうち 7 件が実測に否定された。
残る 1 件「hook が存在しない」は結論だけ当たり、 根拠 (SubagentStop event の実在) を一度も
確かめていなかった — 当たった推論も、 なぜ当たったか言えないなら同じ欠陥。
**測って書いたものも外れる。** 「再発の上位 2 件で約 6 割」は推測でなく測定だった。 除外ゼロで
走査し、 件数表も貼った。 それでも 25 pt 外れた (正しくは 35%) — `grep -c '^### '` の数え方が
対象の形に合っておらず、 書式違いの事例を数え落とし、 2 位の entry を走査対象に入れていなかった。
**読んだ直後でも止まらない。** この CAVEAT を commit した 2 分後、 すぐ下の CAVEAT に「1 年分の
session に届かなくなり」と根拠なく書いた。 止めたのは読み返しではなく、 数字を 1 つ DB に
当てに行ったこと。
緩和策: 「無い」「そうなっている」と書く前に、 走査した空間を名指しで書く — 作業コピーか、
git 履歴か、 DB か、 動いているプロセスか。 除外ゼロで走査し、 出力を貼る。 貼った出力は、
数え方が対象の形 (見出し・箇条書き・複数書式) に合っているかを 1 件だけ目視で照合してから
件数を書く。 出力に自作 script が印字した結論文が混ざっていないか、 貼る前に見る。

CAVEAT: 調査前の推論 — 完了判断での再発 (同じバグの別場面)
完了の判断も推論なので、 調べる前に書けば同じように外れる。
2026-08-27 の要件は「surface hook が when: (prompt / stop / after-subagent) で振り分ける」。
`3b5d077` が「C16 family (`when:` に stop を含む entry だけ) として配備、 配備先で実発火を確認」
と書いて閉じた。 出したものは振り分けそのもので、 欠陥は **3 値のうち 1 値しか作らなかった**こと。
`when: after-subagent` の entry を 1 件置いて subagent を走らせれば済む確認をせず、 「stop だけ」と
自分で書いた文のまま閉じた。 `when:` を置いた 2026-08-27 11:16 から 2026-08-29 まで surface は 0 回。
なお私は、 この CAVEAT を最初に書いたとき閉じた当の commit (`3b5d077`) を開かず、 別 commit を
根拠に「出したのは gate の値域拒否で、 動詞が違う」と書いた。 偽である。 CAVEAT の中で
CAVEAT の言うバグをやった。 指摘を受けて commit を開いて訂正した。
緩和策: 走らせて出力を見ていないものを完了と書かない。 何を閉じたかは、 閉じた commit を開いて
確かめる。

CAVEAT: 要件の動詞と出荷物の動詞がずれたまま閉じた (2026-08-29 訂正)
要件 `8c504f1` は「surface hook がそれで振り分ける」。 出荷 `6451a19` が出したのは gate の値域拒否
だけで、 振り分けは書かれていない。 `2fb99ff` が項目を Close し、 `f91150f` が block ごと削除した。
その削除された本文自身が「`when:` に stop を含む entry だけ配備」と書いている — **半分だと認める
同じ文の中で、 完了として閉じた。**
実測 (2026-08-29): 失敗 session `ff720c04` の inject_log は emit 23 件・mismatch 12 件で、
`feedback_architecture_before_review` は 0 件。 ただし当時この entry は `when: prompt after-subagent`
で、 出荷済み hook は `when:` を読んでいない —— prompt の候補から外れてはおらず、 届かなかったのは
順位であって route の不在ではない。「route が無いから届かなかった」は私が書いた誤った因果で、
実測の前に因果まで書いた結果である。
緩和策: 閉じる前に、 要件の動詞 (振り分ける / 拒否する / 記録する) と出荷物の動詞を並べて書く。
原因を書くときは、 その原因が無ければ結果が変わったことを実測で示してから書く。

CAVEAT: Court bug
Claude Code 2.1.148 以降 "court" とうい文字列が混入し Tool Call が失敗するバグが頻発。
一度発生するとセッションが汚染され、まともに動作しなくなるため、直ちにセッションリセットするしかない。
緩和するには、英語で思考・発話する。
（セッションレジュームすると新しいセッションにも伝染する）

参考 https://github.com/anthropics/claude-code/issues/64108 (2026-08-06 時点 open)

session を跨いで引き継ぐ未完了作業の概要。詳細は last-session-handoff.md の同名節、経緯は git 履歴。

- Jev 文脈判定の誤判定改善とバックテスト — 再開点: jev に profile を足して検証用のキーを分け、試験版の gate で問いを作り直す (試験版は配備対象の外に置く)
- claude_md_lint の -p 化の実機確認 — 再開点: キャッシュが外れるプロジェクトで新しいセッションを起動して結果を見る
- codex_delegation_gate の SAFE_CLI に remote-control を足す件 — 再開点: 提案中、足すかをユーザーが決める
- close nudge の Codex 台帳対応 — 再開点: 実機で mytask の thread id と Codex hook の session_id が同じか測ってから、plan_first_nudge.py に codex 台帳を読ませる (小)
- agent_coord 入れ子表示と auto-mode skill の追随 — 再開点: SubagentStart 注記の Parent 表示と auto-mode-denial-recovery Skill を直す (小)
- memory surface 到達率の判定 — 再開点: 2026-09-25 に claude_memory_sync --reach を再実行
- 一次ソース確認 nudge の効果判定 — 再開点: 2026-10-10 に claude_unverified_claims を実行
- agent_coord の 2 環境疎通 — 再開点: session 間の send/catchup/ack と resource transfer→accept を Codex と試す (完了したかは未確認)
- lessons-learned repo の public / private 分離 — 再開点: 別マシンで branch wip/lessons-learned-split を探す (保留)
- report-in-plain-words skill の仕上げ — 再開点: 上と同じ branch 待ち (保留)
- 教訓「自分が回す loop の停止判断」の memory entry 化 — 再開点: 別マシンの transcript ff720c04 を読む (保留)
- 「先に形を決めて材料を当てはめる」を止める機構 — 再開点: 作るかをユーザーが判断 (要相談)
- 随伴エージェント待ちの 4 案件 — 再開点: 随伴エージェントが使えるまで触らない (凍結)
