---
name: browser-testing-guide
description: Choose browser verification tools for frontend work in Claude Code and Codex. Use for checking page appearance and interactions, reproducing browser bugs, planning browser tests, or investigating frontend performance and memory. Excludes unit tests and tasks without browser verification.
---

# Browser Testing Guide

画面の観察、繰り返す検証、テスト作成の調査、性能の原因調査を分け、目的に必要な道具だけを使う。Svelte / React などのフレームワークによらず適用する。ユーザーが指定した道具と既存のテスト環境を優先する。

## Tool selection

| 目的 | 道具 | 残すもの |
|---|---|---|
| 新しい画面の表示・操作、画面幅による崩れ、入力エラー、通信失敗の一次確認 | agent-browser CLI | 対象 URL、画面幅、操作手順、実際の結果、画面画像 |
| 決めた操作・期待結果の繰り返し検証、複数ブラウザーでの回帰テスト、承認済み基準画像との比較 | Playwright Test | テストコード、実行結果、失敗時の trace・差分画像など |
| テスト用の操作順・locator を実画面で調べる、失敗した Playwright 操作を対話的に再現する | Playwright CLI | 確認した操作・locator と、それを反映したテストの実行結果 |
| 表示や操作の遅さ、増え続けるメモリーの原因を掘り下げる | Chrome DevTools MCP | 再現条件、性能・メモリーの記録、原因の根拠、修正前後の比較 |

既存テストの入力値や期待結果を追加するだけなら、テストを編集して実行する。Playwright CLI や agent-browser での探索を必須工程にしない。Firefox / WebKit の合否は Playwright Test で確認し、対話的な調査が必要なときだけ Playwright CLI を使う。

## Execution

選んだ道具の実行前に [実行形式と sandbox 内の手順](references/commands.md) の該当節を読む。agent-browser は `--session`、Playwright CLI は `-s=` で自分のセッションを指定し、Playwright Test はアプリのローカル依存関係で実行する。Chrome DevTools は MCP ツールを呼び出す。

CLI のブラウザープロセスがシェル実行をまたげない環境では、起動・操作・検証・終了を同じシェル実行内にまとめる。保存先は既存の一時ファイル運用に従う。継続検証の作業物は `drafts/` のセッション／スレッド別ディレクトリにまとめ、必要な作業用キャッシュもそこで分離する。キャッシュという名前だけで `/var/tmp` を必須にせず、内容・サイズ・寿命・書き込み権限で選ぶ。`/tmp` 直下には散らさない。必要な保存先やプロセス実行、MCP 呼び出しを拒否された場合は、その制約と未検証の範囲を報告する。

## Process

1. 対象 URL、操作、期待結果、必要な画面幅・ブラウザーを特定し、上の表から道具を選ぶ。既存の起動方法・テスト設定を確認する。
2. 表示・操作の調査なら agent-browser で再現し、変更後も同じ条件で確認する。要素一覧だけで外観を合格にせず、スクリーンショットも見る。操作で画面が変わったら要素一覧を取り直す。
3. 今後も守るべき動作は、依頼範囲に応じて Playwright Test に残す。操作・locator が不明な部分だけ Playwright CLI で調べ、修正したテストを実行する。
4. 性能・メモリーの原因が説明できない場合は Chrome DevTools MCP に切り替える。同じ URL・データ・画面幅・操作で修正前後を測る。メモリーが一度増えただけでリークと断定しない。
5. 自分が開始したブラウザーセッションを閉じ、実行した範囲と結果を報告する。他の作業のセッションまで閉じない。

## Rules

- **目的が変わるときだけ切り替える** — 同じ確認を複数の道具でやり直さない。切り替え先へ URL、画面幅、データ、ログイン条件、再現手順、期待結果を渡す。ブラウザー状態が自動で共有されるとは扱わない。並行作業ではセッション名を分ける。
- **結果を検証する** — クリックできたことだけでなく、保存後の値や入力エラーからの回復などを確認する。固定秒数や通信停止だけに頼らず、必要な要素・状態を待つ。保存するテストには、その場限りの要素番号ではなく role・label などの安定した locator を使う。
- **基準を勝手に緩めない** — テストを通すためだけに期待値や基準画像を更新しない。画像比較は OS・ブラウザー・フォント・データを揃える。Playwright の WebKit は実機 Safari / iPhone の確認を代替しきらない。
- **確認範囲を混同しない** — 通信を mock した検証は実際の接続先との疎通確認ではない。Chrome の計測は Firefox / WebKit の結果ではない。JavaScript のメモリー記録だけでブラウザー全体や GPU の使用量を説明しない。
- **既存環境を使う** — agent-browser / Playwright CLI は共通 CLI、Playwright Test はアプリの開発用依存関係。検証に必要で未導入なら、対象プロジェクトのパッケージマネージャーで `@playwright/test` と必要なブラウザーを導入し、設定・テスト・lockfile をそのプロジェクトで管理する。グローバル導入で代用しない。`playwright-cli`、`npx playwright test`、ブラウザー準備の `npx playwright install` を区別する。単体・部品テストは既存の仕組みを継続し、既存設定の再初期化や無関係な依存関係の更新をしない。
- **操作方法は導入版で確認する** — 利用可能な agent-browser / playwright-cli の公式 Skill、CLI の help、MCP のツール定義を参照する。Skill があるだけで本体やブラウザーも導入済みとは扱わない。利用できない道具は明記し、代替で確認できる範囲を示す。
- **操作経路を増やさない** — 通常のブラウザー操作は CLI を使い、Playwright MCP や agent-browser の MCP を重ねて導入しない。Chrome DevTools MCP は詳細診断用で、日常の画面確認には持ち込まない。他のブラウザーツールやアプリへの計測用依存関係の追加は、具体的な必要性と依頼範囲で判断する。
- **作業用の状態を使う** — 試験用アカウント・データを使い、普段使いのブラウザーを無条件に共有しない。購入・外部送信・削除は既存の承認範囲を確認する。画像・trace・通信記録に含まれる機密情報にも注意する。

## Output

対象と条件、使った道具、実行した操作・テスト、期待結果と実際の結果、画像・記録の保存先、未確認事項を報告する。画面を開けただけ、MCP が登録一覧に出ただけで検証完了としない。未実行・起動失敗・権限不足を成功として報告しない。

## Sources

2026-09-18 の提供資料「エージェントでの FE 開発でのツール利用ベストプラクティス」2版の役割分担と運用方針を統合したもの。PDF が手元になくても、このスキルだけで道具を選択できる。

- [agent-browser](https://agent-browser.dev/)
- [Playwright Test](https://playwright.dev/docs/intro)
- [Playwright CLI](https://github.com/microsoft/playwright-cli)
- [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)
