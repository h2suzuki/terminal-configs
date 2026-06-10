[[en]](README.en.md) [jp]

# Terminal Configs

ターミナル環境を素早くセットアップするための設定ファイルとスクリプトです。


## 使い方

### 基本セットアップ

環境に合うスクリプトを root で実行してください。

    # ./ubuntu2404-wsl.sh

もしくは

    # ./debian12.sh

### 追加セットアップ（opt-in）

基本セットアップの後、必要に応じて `extra/` 配下のスクリプトを root で実行します。

    # ./extra/claude_extensions.sh   # Claude Code のガードレイル・MCP・プラグイン
    # ./extra/voicevox.sh            # VoiceVox による音声通知
    # ./extra/signoz.sh              # SigNoz による Claude Code テレメトリ

いずれも再実行で上書き更新できます（VoiceVox Core 本体は導入済みならスキップされます）。


## 基本セットアップの内容

主な内容は、以下のとおりです。

### 1. Bash 環境の設定

ログインユーザーと root の設定をします。

- プロンプト色の調整（ログインユーザーの緑 → 紫）
- Bash エイリアスの調整・追加（`tree`, `diffy`, `rg`, `grip`, `mdr`, `node-x` など）
- Git の設定調整（エイリアス `git st`, `git diffc`, `git log1`, `git graph` など、delta による見やすい diff 表示、gh と連携した GitHub 認証）
- Terminal bell の抑止
- 標準エディタ： Neovim
- 標準ブラウザ： `powershell.exe start` [WSL2のみ]


### 2. X ディスプレイ・サーバーの共有

- ログインユーザーの X 接続を root にも継承（ `DISPLAY` と `.Xauthority` 設定）
  - `sudo -i` 後、root から `xeyes` を起動するとログインユーザーの画面に表示されます


### 3. SSH 調整

- アイドル接続が WSL2/Hyper-V の NAT タイムアウトで切れないよう keepalive を設定
- Windows Terminal の環境変数 `WT_SESSION` を SSH 接続先へ転送
  - SSH 接続先の Claude Code も Windows Terminal を認識し、拡張キー入力（Kitty protocol）を利用可能
  - Claude Code の `/terminal-setup` で Windows Terminal の認識状況を表示可能
- SSH ログイン後の音声出力を Windows ホストへ転送
  - PulseAudio 接続を 24713/tcp で待ち受けて WSLg へ転送（ローカルプロキシ） [WSL2のみ]
  - ログイン時に `PULSE_SERVER=tcp:localhost:24713` を自動設定 [Debian12のみ]


### 4. sudo 調整

- `sudo -i` 時に `PULSE_SERVER` 環境変数を引き継ぎ
- `sudo -i` 時に `WT_SESSION` 環境変数を引き継ぎ
- `sudo scp` / `sudo rsync` でログインユーザーの SSH agent を利用可能（`SSH_AUTH_SOCK` などを引き継ぎ）
- `sudo` グループに `NOPASSWD` 権限を付与（パスワードなしで sudo 実行可能）
  - ログインユーザーを `sudo` グループに追加


### 5. 基本的なツールのインストール

- neovim, tree, shellcheck
- git, git-lfs, GitHub CLI（gh）
- ripgrep, git-delta（delta）, markdown-reader（mdr）
- openssh-server/client
- avahi, libnss-mdns（mDNS 対応） [WSL2のみ]
- SIXEL（ターミナル内画像表示）: img2sixel
- Python: uv（パッケージマネージャ）, ruff（リンタ/フォーマッタ）, ty（型チェッカ）
- Node.js LTS: nvm, node
- Chrome（日本語フォント込み）
- Google Cloud CLI（gcloud）
- Claude Code（+ claude-monitor）
- Claude Code の補助ツール: bubblewrap, socat（Sandbox）, poppler-utils（PDF 読み取り）
- Antigravity CLI（agy）
- Codex CLI


### 6. Claude Code 基本設定

- Spinner Verbs 日本語訳
- Status Line: プロジェクト名 / モデル名 / Context 消費 / レートリミット / 現在時刻
- 憲法（org ルール） `/etc/claude-code/CLAUDE.md`
- ユーザー設定 `~/.claude/CLAUDE.md` / `~/.claude/settings.json`（auto 権限モード, effort 既定値など）


### 7. WSL2 調整 [WSL2のみ]

- mDNS（`.local`）の名前解決を Windows ホスト側に委譲
  - NAT モードの WSL2 上でも `.local` 名を解決可能
- systemd の有効化
- ホスト名の固定


## 追加セットアップの内容

### A. Claude Code 拡張（`extra/claude_extensions.sh`）

Claude Code に「信頼を高めるための仕組み」と外部ツール連携を入れます。

- **ガードレイル（フック / スキル）**: `CLAUDE.md` のルール（commit 規律・スキル発火・memory routing など）を機械的に強制するフック群を `/etc/claude-code/hooks/`・スキル群を `/etc/claude-code/skills/` に配置し、managed-settings の drop-in（追加設定ファイル）で登録します。あわせてユーザー側フック（commit 著者確認・push 催促検出・memory surface・subagent gate）を `~/.claude/hooks/` に入れます。仕組みの解説は `SKILL-HOOK-CONTRACT.md` を参照してください。
- **MCP サーバー（scope=user）**: Playwright（ブラウザ操作）, Serena（LSP によるコード解析）, CodeGraph（コード知識グラフ）, Cloud Run, Toolbox（BigQuery）
- **プラグイン**: security-guidance（既定で無効）, figma, vercel（Vercel の MCP はこのプラグイン経由で提供）
- **CLI**: agent-browser（Vercel Labs）, Vercel CLI

インストール後、Claude Code のコンソールで `/mcp` と `/doctor` を実行して OAuth2 認証を済ませてください。


### B. 音声通知（`extra/voicevox.sh`）

VoiceVox Core と、待機通知・サブエージェントの完了報告・Claude Code からの質問などを VoiceVox で発話する `voicevox_claude_alerts` をインストールします。発話フックは managed-settings の drop-in（`/etc/claude-code/managed-settings.d/voicevox.json`）として登録されるため、本スクリプトを実行していない基本セットアップ機には、存在しないフックへの参照が残りません。

`voicevox_claude_alerts` は CLI としても利用でき、以下のサブコマンドがあります。

- `voicevox_claude_alerts help` — サブコマンド一覧
- `voicevox_claude_alerts events` — 対応フックの一覧
- `voicevox_claude_alerts log` — 直近の発話履歴
- `voicevox_claude_alerts say TEXT` — 任意のテキストを読み上げ

また、合成音声を再生するコマンド `voicevox_paplay` も同梱します。発話フックは、PulseAudio で直接再生する代わりにローカルプロキシ経由で再生するオプション付きでこれを呼び出します。

#### ログ

ログは既定で `~/.local/state/voicevox_claude_alerts/` に書き込まれます。

- 発話内容： `spoken.log`（常時記録）
- Hook payload： `dump.jsonl`（環境変数 `CLAUDE_NOTIFY_DEBUG=1` の設定時のみ記録）

環境変数は `~/.claude/settings.json` に書くこともできます。

    {
      "env": {
        "CLAUDE_NOTIFY_DEBUG": "1"
      }
    }

ログは無制限に増えるので、不要になったら削除してください。


### C. SigNoz テレメトリ（`extra/signoz.sh`）

Docker をインストールし、SigNoz（オブザーバビリティ基盤）を docker compose で立ち上げて、Claude Code の OTEL（OpenTelemetry）テレメトリを可視化するダッシュボードを構築します。

- SigNoz UI は 14902/tcp で待ち受け
- ログイン用の管理ユーザーを自動作成（`admin@signoz.localhost` / `At4902.localhost`）
- Claude Code 用ダッシュボードを自動投入
- OTEL 環境変数を `/etc/claude-code/env.sh` に配置し、`~/.bashrc` から読み込み


----

音声まわりのトラブルシューティングは [`TROUBLE-SHOOTING.md`](TROUBLE-SHOOTING.md) を参照してください。

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
