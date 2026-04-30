[[en]](README.en.md) [jp]

# Terminal Configs

ターミナル環境を素早くセットアップするための設定ファイルとスクリプトです。


## 使い方

環境に合うスクリプトを root で実行してください。

    # ./ubuntu2404-wsl.sh

もしくは

    # ./debian12.sh

## 主な環境設定

主な内容は、以下のとおりです。

### 1. Bash 環境の設定（root, ログインユーザー）

- プロンプト色の調整（ログインユーザーの緑 → 紫）
- Bash エイリアスの調整・追加（`ls`, `tree`, `diffy`, `grip` など）
- Git エイリアスの調整（`git st`, `git diffc`, `git log1`, `git graph` など）
- Terminal bell の抑止（`inputrc`）
- ログインユーザーへの sudo NOPASSWD 権限付与
- 標準エディタを Neovim に
- 標準ブラウザを `powershell.exe start` に [WSL2のみ]


### 2. X ディスプレイ・サーバーの共有

- ログインユーザーの X 接続を root にも継承（`.bashrc` で `DISPLAY` と `.Xauthority` を引き継ぎ）
  - `sudo -i` 後、root から `xeyes` を起動するとログインユーザーの画面に転送される


### 3. SSH 調整

- SSH ログイン後の音声出力を Windows ホストへ転送
  - PulseAudio 接続を 24713/tcp で待ち受け（ローカルプロキシ → WSLg）[WSL2のみ]
  - ログイン時に `PULSE_SERVER=tcp:localhost:24713` を自動設定 [WSL2以外]
- `sudo -i` 時に `PULSE_SERVER` 環境変数を引き継ぎ


### 4. 基本的なツールのインストール

- neovim, tree, ssh
- git, git-lfs, GitHub CLI
- ripgrep, bat, delta
- AVAHI: avahi, libnss-mdns
- SIXEL: img2sixel
- UV python package manager: uv
- Node.js LTS: nvm, node
- Chrome: google-chrome, fonts-ipafont, fonts-noto-color-emoji, upower
- VoiceVox
- Claude Code


### 5. Claude Code 設定

- Spinner Verbs 日本語訳
- Status Line: プロジェクト名 / モデル名 / Context 消費 / レートリミット / 現在時刻
- 憲法 `/etc/claude-code/CLAUDE.md`
- 通知フック（後述）


### 6. Claude Code MCP / CLI

(TODO)


### 7. Claude Code 通知フック

待機通知、サブエージェントの完了報告、Claude Code からの質問などを VoiceVox で発話する `voicevox_claude_alerts` をインストールしています。

CLI としても利用でき、以下のサブコマンドがあります。

- `voicevox_claude_alerts help` — サブコマンド一覧
- `voicevox_claude_alerts events` — 対応フックの一覧
- `voicevox_claude_alerts log` — 直近の発話履歴
- `voicevox_claude_alerts say TEXT` — 任意のテキストを読み上げ

#### デバッグログ

環境変数 `CLAUDE_NOTIFY_DEBUG=1` を設定すると、Hook payload と発話内容がログに書き込まれます。ログの場所は 
既定では `~/.local/state/voicevox_claude_alerts/` です。

- Hook Payload： `dump.jsonl`
- 発話内容： `spoken.log`

環境変数は `~/.claude/settings.json` に書くこともできます。

    {
      "env": {
        "CLAUDE_NOTIFY_DEBUG": "1"
      }
    }

ログは無制限に増えるので、不要になったら削除してください。


### 8. WSL2 調整 [WSL2のみ]

- DNS 名前解決を Windows ホスト側にデリゲート
  - NAT モードの WSL2 上でも mDNS（`.local`）を利用可能
- systemd の有効化
- ホスト名の固定

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
