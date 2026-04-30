[[en]](README.en.md) [jp]

# Terminal Configs

ターミナル環境を素早くセットアップするための設定ファイルとスクリプトです。


## 使い方

環境に合うスクリプトを root で実行してください。

    # ./debian12.sh


## Claude Code 通知フック

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

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
