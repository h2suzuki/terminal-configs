# Jev

Claude Code と Codex には公式の `typesafe@typesafe-ai` プラグインと、このリポジトリの
Jev MCP サーバーを導入します。Antigravity には公式 `typesafe-ai` スキルを導入します。
公式プラグインはスキルを提供するもので、MCP サーバーや認証 CLI は含みません。

## API キーと動作確認

セットアップ後、利用するユーザーの通常のターミナルで実行します。

```bash
jev api-key set   # キーを非表示入力し、API で確認してから保存・更新
jev hello         # テストクエリーを 1 回送り、認証・通信・応答を診断
jev api-key status # 保存状態を確認し、登録済みならテストクエリーで利用可否を診断
jev api-key clear # 保存済みキーを削除するとき
```

`set` の入力は端末に表示されません。空入力はキャンセルとして何も表示せず終了し、保存済みキーは変更しません。保存成功時は `API is set` と表示します。非表示入力ができない端末では中止します。
保存先は OS ユーザーの `~/.config/typesafe/credentials.json` です。
ファイル権限は `600`、ディレクトリは `700` とし、シンボリックリンクは受け付けません。
この保存先は本リポジトリの規約で、TypeSafe 公式 CLI の保存先ではありません。

`.env`、`.bashrc`、MCP 設定へのキーの記載や `TYPESAFE_API_KEY` の export は不要です。
`set` は入力したキーでテストクエリーを 1 回送り、正常な応答を確認してから保存します（API 利用が発生します）。認証・通信・応答の診断に失敗した場合は保存せず、既存のキーも変更しません。OAuth 認証は行いません。
TypeSafe の公開 API は API キーによる Bearer 認証です。

`jev hello` と登録済みキーに対する `jev api-key status` は公式 Python SDK で小さな Jev クエリーを送信するため、API 利用が発生します。
`jev hello` は送信クエリーとレスポンスを JSON で表示し、成功時は最後に `Hello! Jev is ready.` と表示します。失敗時は診断メッセージと終了コード `1` を返します。

| 診断 | 対処 |
| --- | --- |
| 保存キーなし・形式や権限の不備 | `jev api-key set` で登録し、保存先の権限を確認 |
| HTTP 401 | 無効・失効・期限切れなどの認証拒否。現在有効なキーで再登録 |
| HTTP 403 | キーの権限とアカウントのアクセス権を確認 |
| HTTP 429 | 利用枠・レート制限を確認し、時間を置いて再試行 |
| HTTP 5xx | TypeSafe 側の障害として時間を置いて再試行 |
| 通信・TLS・タイムアウト | ネットワーク接続を確認 |

`status` は未登録・削除済みならキー未設定と表示し、API を呼びません。登録済みなら API で利用可否を確認し、成功時は `API key is valid.` と表示します。未設定や診断失敗時の終了コードは `1`、利用可能なら `0` です。

API のエラー本文やキーは表示しません。[公式のエラー仕様](https://docs.typesafe.ai/api#errors)では期限切れ専用の応答が定義されていないため、401 は `invalid` と表示し、`expired` とは推測しません。通信障害・利用制限・サービス障害は別の診断を表示します。
キーを更新・削除した後は、接続中のエージェントを再起動して MCP 内のキャッシュも破棄してください。
ローカルの削除は TypeSafe 側のキー失効操作ではありません。

## エージェントからの利用

Claude Code と Codex の MCP 登録名は `jev`、公開ツールは `evaluate` です。
「TypeSafe スキルで質問を設計し、Jev MCP の evaluate で呼び出す」と指示できます。
ツールには次のような引数を渡します。

```json
{
  "state": "注文した商品がまだ届きません。配送状況を確認してください。",
  "questions": {
    "delivery": {
      "type": "noul",
      "instructions": "配送についての問い合わせか"
    }
  }
}
```

`model` の省略時は `jev-latest` を使います。質問形式は公式スキル・ドキュメントを参照してください。
MCP は `state`、`questions`、任意の `model` だけを受け取り、型付き回答と利用量を返します。
キーや送信先を指定する引数、キーを読み出すツールはありません。

エージェントが `jev serve` を stdio MCP として起動し、接続終了まで維持します。
公式 Python SDK の `AsyncTypeSafeClient` と HTTP 接続プールを再利用するので、
リクエストごとのプロセス起動はありません。エージェントの接続ごとに別プロセスとなり、
systemd などによる独立した daemon の管理は不要です。`jev hello` は単発の診断コマンドです。

## Sandbox と資格情報

- Claude Code：資格情報ディレクトリの Read と sandbox 内からの読み取りを拒否し、
  `TYPESAFE_API_KEY` も sandbox 環境から除去します。
- Codex：`terminal-configs` permission profile が資格情報ディレクトリを deny し、
  `TYPESAFE_API_KEY` をシェル環境から除去します。
- Antigravity：公式スキルのみで、MCP 登録や同等の credential deny は設定していません。

MCP プロセスがホスト側で資格情報を読みます。`jev` の sandbox 除外コマンド設定は不要です。
送信先は `https://api.typesafe.ai/v1/systemone` 固定です。リダイレクトと環境変数による
プロキシ・CA・送信先の変更を使わず、OS の CA 証明書で HTTPS を検証します。

Codex の permission profile は旧 `sandbox_mode` / `sandbox_workspace_write` と併用できません。
ユーザー設定やプロジェクト設定に旧形式が残っていたり、`--sandbox` で起動したりすると、
この profile の deny は適用されません。該当設定を取り除き、再起動後に `/permissions` で
`terminal-configs` が選ばれていることを確認してください。

ここでの deny は通常の sandbox 実行に対する制限です。ホスト実行を許可した他のコマンドや
同じ OS ユーザーのプロセス全体を隔離するものではありません。

## 配備・更新

CLI だけの変更なら `sudo cp files/jev /usr/local/bin/jev` で反映できます。

CLI、SDK、sandbox 設定をまとめて反映するには、リポジトリのルートから対象 OS の基本セットアップを実行します。

```bash
sudo ./debian12.sh
# Ubuntu 24.04 on WSL2 の場合
sudo ./ubuntu2404-wsl.sh
```

SDK の実行環境は `/usr/local/lib/jev` にインストールします。
プラグイン・スキルの更新とユーザーの MCP 再登録は `install_typesafe_extensions` で行えます。
エージェントを再起動し、対象ユーザーで `jev api-key set` と `jev hello` を実行してください。

## 公式資料

- [TypeSafe Agent skill](https://docs.typesafe.ai/agent-skill)
- [TypeSafe Python SDK](https://docs.typesafe.ai/sdk/python/api/clients/async)
- [TypeSafe API](https://docs.typesafe.ai/api)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Code credential protection](https://code.claude.com/docs/en/sandboxing#protect-credentials)
- [Codex permission profiles](https://learn.chatgpt.com/docs/permissions)
