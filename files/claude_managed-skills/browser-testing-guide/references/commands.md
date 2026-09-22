# Browser Testing Guide Commands

選択した道具の節だけ読む。Google の例は導入・実行経路の smoke test であり、自作アプリの検証の代わりにはならない。通常は依頼された URL・locator・期待結果へ置き換える。Google に同意画面や CAPTCHA が出た場合は観測結果として扱い、回避せず確認できなかった範囲を報告する。

## Storage and sandbox

- 小さく短命な出力は、セッション専用 scratch を `TMPDIR` に設定して作る。Claude Code の既定運用は `/tmp/claude-scratch-$CLAUDE_CODE_SESSION_ID`。Codex では自身のセッション ID で区別し、Claude Code の終了フックによる削除を期待せず自分で片付ける。
- レビューや次のセッションでも使う画像・テストコード・結果は、既存の `drafts/` のセッション／スレッド別ディレクトリを使う。継続検証に必要なキャッシュ・runtime も同じ作業ディレクトリ内で分離できる。日付・PID だけで `drafts/` 直下に別系統の置き場を作らない。
- `/var/tmp` は大容量・mmap 用の一時領域などで必要な場合の選択肢であり、キャッシュすべての必須配置先ではない。正常な既存キャッシュを理由なく変更しない。容量と権限を確認し、不要な依存関係・キャッシュ・runtime は終了後に削除する。
- 保存先の変更は、許可された作業領域を選ぶために行う。プロセス実行・ネットワーク・MCP の拒否を迂回する手段にしない。

以下の例は、リポジトリ内で作業用変数を設定した同じシェル内から実行する。既存のセッション作業ディレクトリがある場合はその配下を使う。セッション ID の環境変数がなければ、実際の ID を確認して指定する。空文字や PID で代用しない。

```bash
browser_scope="${CLAUDE_CODE_SESSION_ID:-${CODEX_THREAD_ID:?session ID is required}}"
browser_work_dir="$(git rev-parse --show-toplevel)/drafts/$browser_scope/browser-testing-guide"
export TMPDIR="/tmp/claude-scratch-$browser_scope"
mkdir -p "$browser_work_dir" "$TMPDIR"
```

Playwright CLI の smoke test では、シェル実行ツールの作業ディレクトリもこの `browser_work_dir` にする。自動生成される `.playwright-cli/` をリポジトリ直下に散らさない。別のシェル実行では上の変数を設定し直す。

`TMPDIR` は短いセッション専用 scratch にする。深い `drafts/` 配下をそのまま指定すると、Chrome が作る Unix ソケットで `Socket path too long` になる場合がある。継続用キャッシュの `XDG_CACHE_HOME` と短命な runtime の `TMPDIR` は分ける。終了後は、自分のプロセスが終わったことを確かめてから作成した一時物を削除する。

## agent-browser

導入版に対応する操作説明を最初に取得する。

```bash
agent-browser --version
agent-browser skills get core
```

既定のソケット保存先（例: `/run/user/1000/agent-browser`）が書き込み不可の場合は、起動前に次を設定する。同じセッションの各コマンドで同じ値を維持する。[導入版での保存先選択](https://github.com/vercel-labs/agent-browser/blob/v0.38.1/cli/src/connection.rs)

```bash
export AGENT_BROWSER_SOCKET_DIR="$TMPDIR/ab"
```

同じシェル実行内で、専用セッションの起動・観察・画像保存・終了まで行う例。通常のキャッシュ設定を使う。

```bash
set -e
browser_artifacts="$browser_work_dir/agent-browser"
mkdir -p "$browser_artifacts"
browser_session="fe-check-$$"
trap 'agent-browser --session "$browser_session" close' EXIT
agent-browser --session "$browser_session" open https://www.google.com/
agent-browser --session "$browser_session" snapshot -i
agent-browser --session "$browser_session" get title
agent-browser --session "$browser_session" screenshot "$browser_artifacts/page.png"
```

対話的に調べるときは、snapshot の実際の ref を使う。以下の `@e14` は例であり、直前の出力で対象を確認して置き換える。操作後は値と新しい画面を確認する。

```bash
agent-browser --session "$browser_session" fill @e14 'browser verification'
agent-browser --session "$browser_session" get value @e14
agent-browser --session "$browser_session" snapshot -i
agent-browser --session "$browser_session" screenshot "$browser_artifacts/after.png"
agent-browser --session "$browser_session" close
```

後半の操作はセッションが開いている間に行う。上の完結例を実行済みなら新しく開いて snapshot を取り直す。画面幅を確認する場合は `agent-browser --session "$browser_session" set viewport 390 844` などで変更する。保存された画像は実際に開いて確認する。

## Playwright CLI

```bash
playwright-cli --version
playwright-cli --help
```

Google の検索欄が combobox 1個であることを snapshot で確認した場合の例。送信せず、入力値まで確認する。別の画面では locator を実際の対象に合わせる。

```bash
set -e
browser_artifacts="$browser_work_dir/playwright-cli"
mkdir -p "$browser_artifacts"
browser_session="fe-test-$$"
trap 'playwright-cli -s="$browser_session" close' EXIT
playwright-cli -s="$browser_session" open https://www.google.com/ --browser=chrome
playwright-cli -s="$browser_session" snapshot
playwright-cli -s="$browser_session" generate-locator "getByRole('combobox')"
playwright-cli -s="$browser_session" fill "getByRole('combobox')" 'browser verification'
playwright-cli -s="$browser_session" eval 'el => el.value' "getByRole('combobox')"
playwright-cli -s="$browser_session" screenshot --filename="$browser_artifacts/page.png"
```

`eval` の結果が入力値と一致することを確認する。保存するテストへ期待結果を追加し、Playwright Test で実行する。CLI が生成する snapshot などは作業ディレクトリの `.playwright-cli/` にも保存されるので、書き込み可能な場所から実行する。

ホーム配下のキャッシュ作成で失敗する場合は、上の `open` の前に次を加え、継続検証の作業ディレクトリに分離する。ブラウザー終了後に専用キャッシュも削除する。`set -e` により保存先の作成に失敗したら、その時点で停止する。

```bash
browser_cache="$browser_work_dir/$browser_session-runtime"
mkdir -p "$browser_cache"
export XDG_CACHE_HOME="$browser_cache/cache"
```

終了時は先の `trap` でセッションを閉じる。終了を確認してから、自分で作った `browser_cache` の実パスだけを対象に、環境が許可する削除方法で片付ける。成果物や他のセッションの作業領域は削除しない。

同じセッションのすべてのコマンドで同じキャッシュ指定を使う。別シェルでは変数が失われる場合がある。`Browser ... is not open` が出たらキャッシュ指定・作業場所・プロセス寿命を確認し、セッションをまたげない環境では同じシェル実行にまとめる。出力を解析して操作を決める場合も、利用可能なら同じ実行セッションを維持する。

root で Chrome の sandbox エラーになった場合は、共通セットアップが root の `~/.playwright/cli.config.json` に `browser.launchOptions.chromiumSandbox: false` を配置しているか確認する。これはブラウザー側の設定であり、エージェントの sandbox 権限を変更するものではない。一般ユーザーへ一律に適用しない。

## Playwright Test

まず対象アプリの `package.json`・lockfile・Playwright 設定・起動方法を確認する。検証に必要で未導入なら、[公式のインストール手順](https://playwright.dev/docs/intro#installing-playwright)を参照し、そのプロジェクトの開発用依存関係として追加する。ブラウザーの準備は[公式のブラウザー導入手順](https://playwright.dev/docs/browsers#install-browsers)を参照する。以下は npm で Chromium を使う場合の例であり、実際のパッケージマネージャー・対象ブラウザー・導入版に合わせる。実行場所は対象アプリのディレクトリとする。

```bash
npm install --save-dev @playwright/test
npx --no-install playwright install --with-deps chromium
```

必要なブラウザーだけを導入し、設定・テスト・変更された package.json と lockfile をアプリ側で管理する。新しく設定を作る場合は `use.baseURL`、対象ブラウザー、必要なら `webServer` をアプリに合わせる。初期化から始める未設定プロジェクトでは `npm init playwright@latest` も選べるが、既存設定へ重ねて実行しない。グローバルインストールや一時的な `npx` の自動取得でプロジェクトの依存関係を代用しない。

導入済みなら既存環境をそのまま使い、対象テストを実行する。

```bash
npx --no-install playwright --version
npx --no-install playwright test tests/example.spec.ts
```

導入確認用の Google のテスト例。アプリの回帰テストとして追加せず、必要なら一時プロジェクトで使う。`@playwright/test` はそのプロジェクトの開発用依存関係として必要。CLI を入れただけでは揃わない。

```typescript
import { test, expect } from '@playwright/test';

test('Google search field accepts input', async ({ page }) => {
  await page.goto('https://www.google.com/');
  await expect(page).toHaveTitle('Google');
  const search = page.getByRole('combobox');
  await expect(search).toBeVisible();
  await search.fill('browser verification');
  await expect(search).toHaveValue('browser verification');
});
```

インストール済み Linux Chrome を使う smoke test なら、テスト設定の `use` で `channel: 'chrome'` と `headless: true` を指定できる。失敗の記録には `trace: 'retain-on-failure'` を使う。既存アプリの対象ブラウザーを、手元で通しやすい Chrome に勝手に変更しない。

ブラウザー未導入なら、許可された導入作業で `npx --no-install playwright install --with-deps` を使う。OS 依存関係の追加には権限が必要になる場合がある。テストが失敗したら trace・画像・assertion を確認し、未実行とテスト不合格を区別する。

## Chrome DevTools MCP

ここだけは CLI 操作ではなく、接続済み MCP のツールを呼ぶ。登録コマンドを再実行しても性能計測にはならない。実際のツール定義を確認し、次の順で使う。

1. `new_page` に `url` と作業専用の `isolatedContext` を渡し、返されたページ ID を使う。
2. 読み込みの計測は `performance_start_trace` に `pageId`、`reload: true`、`autoStop: true`、書き込み可能な `filePath` を指定する。
3. 結果に出た `insightSetId` と `insightName` を `performance_analyze_insight` に渡す。任意の操作区間を測る場合は自動停止を使わず、操作後に `performance_stop_trace` を呼ぶ。
4. メモリー調査なら `take_heapsnapshot` で操作前後を保存し、`compare_heapsnapshots` で比較する。各引数は接続中のツール定義に従う。
5. 作成したページを `close_page` で閉じる。既存の他のページは閉じない。

MCP が承認・権限で拒否された場合は、その拒否を別プロセスや別接続で迂回しない。計測未実施と理由を報告する。CLI で画面が開けたことを MCP の接続・診断成功として扱わない。
