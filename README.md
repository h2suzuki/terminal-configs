[[en]](README.en.md) [jp]

# Terminal Configs

ターミナル環境を素早くセットアップするための設定ファイルとスクリプトです。


## 使い方

環境に合うスクリプトを root で実行してください。

    # ./debian12.sh

以下のセットアップを行っています。


## 1. Bash 環境の設定（root, ログインユーザー）

- プロンプト色の調整（ログインユーザーの緑 → 紫）
- Bash エイリアスの調整・追加（`ls`, `tree`, `diffy`, `grip` など）
- Git エイリアスの調整（`git st`, `git diffc`, `git log1`, `git graph` など）
- Terminal bell の抑止（`inputrc`）
- ログインユーザーへの sudo NOPASSWD 権限付与
- 標準エディタを Neovim に
- 標準ブラウザを `powershell.exe start` に [WSL2のみ]


## 2. X ディスプレイ・サーバーの共有

- ログインユーザーの X 接続を root にも継承（`.bashrc` で `DISPLAY` と `.Xauthority` を引き継ぎ）
  - `sudo -i` 後、root から `xeyes` を起動するとログインユーザーの画面に転送される


## 3. SSH 調整

- SSH ログイン後の音声出力を Windows ホストへ転送
  - PulseAudio 接続を 24713/tcp で待ち受け（ローカルプロキシ → WSLg）[WSL2のみ]
  - ログイン時に `PULSE_SERVER=tcp:localhost:24713` を自動設定 [WSL2以外]
- `sudo -i` 時に `PULSE_SERVER` 環境変数を引き継ぎ


## 4. Claude Code 設定

- Spinner Verbs の日本語訳表示
- Status Line にプロジェクト名 / モデル名 / Context 消費 / レートリミット / 現在時刻を表示


## 5. Claude Code 向け MCP / CLI

(TODO)


## 6. Claude Code 通知フック

Claude Code のイベントを Voicevox で読み上げる通知スクリプト
`voicevox_claude_alerts` を `/usr/local/bin/` にインストールします。
アイドル警告、許可プロンプト、応答完了時の要約読み上げなどに対応します。

CLI として以下のサブコマンドが利用できます:

- `voicevox_claude_alerts help` — サブコマンド一覧
- `voicevox_claude_alerts events` — 対応フックの一覧
- `voicevox_claude_alerts log` — 直近の発話履歴
- `voicevox_claude_alerts say TEXT` — 任意のテキストを読み上げ

### デバッグログ

`CLAUDE_NOTIFY_DEBUG=1` を設定すると、フック payload と発話内容が
`$XDG_STATE_HOME/voicevox_claude_alerts/`（既定では
`~/.local/state/voicevox_claude_alerts/`）配下の `dump.jsonl` と
`spoken.log` に追記されます。常時有効にしたい場合は
`~/.claude/settings.json` に以下を追加してください:

    {
      "env": {
        "CLAUDE_NOTIFY_DEBUG": "1"
      }
    }

ログは無制限に増えるので、不要になったら削除してください。


## 7. WSL2 調整 [WSL2のみ]

- DNS 名前解決を Windows ホスト側にデリゲート
  - NAT モードの WSL2 上でも mDNS（`.local`）を利用可能
- systemd の有効化

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
