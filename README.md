[[en]](README.en.md) [jp]

# Terminal Configs

Debian 12 と Ubuntu 24.04 on WSL2 向けに、ターミナルと AI コーディング環境をセットアップする設定・スクリプト集です。対象は x86_64 環境です。

## 導入されるもの

| 分野 | 主な内容 |
|---|---|
| OS設定 | Bash、Git、SSH keepalive、Windows Terminal の色・画像表示対応（SSH・sudo 先）、SSH 接続元への画面・音声転送（X11・PulseAudio、sudo -i にも対応）<br>WSL2：systemd 有効化、.local 名の解決、WSLg への音声転送 |
| 開発ツール | Neovim、ripgrep、delta、libsixel-bin、Node.js（nvm）、Chrome |
| AI ツール | Claude Code CLI、Codex CLI、Antigravity CLI、Typesafe.ai Jev |
| <div align="right">ツール設定</div> | `/etc/claude-code`、`/etc/codex`、Sandbox 設定など |
| <div align="right">Hooks</div> | mytask の利用促進\*、編集前のファイル確認\*、コミットメッセージの書式確認\*、根拠のない完了報告・不要な確認質問の抑止\* など |
| <div align="right">LSP</div> | clangd（C/C++）、TypeScript Language Server、Pyright |
| <div align="right">MCP</div> | Chrome DevTools、CodeGraph、Cloud Run、BigQuery（Toolbox）、mytask\*、Jev\* |
| <div align="right">Skill</div> | agent-browser、playwright-cli、mytask\*、memory-routing\*、browser-testing-guide\*、scratch-file-management\* など |
| <div align="right">Plugin</div> | Jev、Codex（Claude Code 用）、security-guidance、agent-coord（AIエージェント間通信）\* |
| <div align="right">CLI</div> | agent-browser、playwright-cli、GitHub CLI、uv・ruff・ty、Google Cloud CLI、Vercel CLI、agent_coord\*、scratch_file_management\*、claude_memory_sync\*、jev\* |

\* … 本レポジトリ独自のスクリプト

音声通知と SigNoz テレメトリは[追加セットアップ](#追加セットアップ)で導入できます。

## セットアップ

このスクリプトは `apt full-upgrade` によるシステム更新を行い、`/etc` 配下の設定やユーザーの Bash・Claude Code 設定を変更します。`~/.claude/CLAUDE.md` と `~/.claude/settings.json` は配布設定で上書きされ、`sudo` グループにはパスワード不要の sudo 権限が設定されます。

リポジトリを取得し、通常のターミナルから対象 OS のコマンドを実行してください。

```bash
git clone https://github.com/h2suzuki/terminal-configs.git
cd terminal-configs
```

| 対象 OS | 実行コマンド |
|---|---|
| Debian 12 | `sudo ./debian12.sh` |
| Ubuntu 24.04 on WSL2 | `sudo ./ubuntu2404-wsl.sh` |

完了後はシェルを開き直してください。WSL2 ではスクリプトの案内に従い、Windows 側で `wsl -t <ディストリビューション名>` を実行してから再接続します。

### スクリプトの呼び出し関係

両 OS のスクリプトは、システム全体の導入に続いて root とログインユーザーの環境を設定します。主な処理と呼び出し関係は次のとおりです。

```text
debian12.sh または ubuntu2404-wsl.sh（sudo で実行）
├── システム全体のツール・設定を導入
│   ├── OS パッケージの更新、Neovim・GitHub CLI・Google Cloud CLI の導入
│   ├── uv・ruff・ty、Chrome・日本語フォントの導入
│   ├── Claude Code・Antigravity CLI の導入
│   ├── Claude Code・Codex の共通設定・sandbox 設定の配備
│   ├── Jev のラッパー CLI・SDK 実行環境の導入
│   └── ユーザー用セットアップスクリプトを /usr/local/bin に配置
└── root とログインユーザー（検出できた場合）それぞれで実行
    └── setup_user_environment
        ├── Bash・Git のユーザー設定
        ├── nodejs_clean_installer             Node.js
        ├── Codex CLI の導入・リモート接続の有効化
        ├── Claude Code のユーザー設定
        ├── Antigravity の権限設定・リモート操作の登録（サインイン済みの場合）
        ├── install_claude_extensions          プラグイン・MCP・hooks・skills
        └── install_typesafe_extensions        Jev のプラグイン・スキル・MCP
```

### 追加ユーザーのセットアップ

セットアップ済みのマシンに別のユーザーを追加した場合は、そのユーザーでログインして次を実行します。

```bash
setup_user_environment
```

上のツリーの `setup_user_environment` 以下が実行されます。認証と API キーも、そのユーザーで設定してください。

## 初回の認証・接続

利用する機能について、利用する OS ユーザーの通常のターミナルで設定してください。

### Claude Code

```bash
claude auth login
```

認証後は `claude` で起動します。MCP の接続状況は Claude Code 内の `/mcp`、診断は `/doctor` で確認できます。

Claude Code から Codex を使う場合は、下記の Codex の認証後に Claude Code 内で `/codex:setup` を実行します。

### Codex

共通の作業指針は `files/codex_user-AGENTS.md` を原本とし、システム導入時に
`/etc/codex/skel/AGENTS.md`、`setup_user_environment` 実行時に各ユーザーの
`~/.codex/AGENTS.md` へコピーします。既存の同名ファイルは更新されます。

Claude Code の共通方針 (`files/claude_managed-CLAUDE.md`) も、この原本と本文・見出しを一致させます。差分は次の2点に限定します。

- 個人の呼称: Codex は `~/.codex/AGENTS.md` に含め、Claude は `~/.claude/CLAUDE.md` (`files/claude_user-CLAUDE.md`) に分離します。Claude managed の配備先は `/etc/claude-code/CLAUDE.md` なので、個人の呼称は含めません。
- Claude 固有の最終行書式: 既存の Stop hook `communication-lint` が検査するため、managed の独立した節に残します。Codex の共通方針には加えません。

共通方針を変更するときは両方を更新し、`python3 tests/agent_guidance.test.py` で一致を確認します。

```bash
codex login
```

デバイスコードで認証する場合は、代わりに `codex login --device-auth` を実行します。

スマートフォンからの操作は [スマートフォンからの操作 (Remote Control)](#スマートフォンからの操作-remote-control) を参照してください。

### Antigravity

`setup_user_environment` は `setup_agy_permissions --sandbox-auto --shared-policy /etc/antigravity-cli/skel/permissions.json` を通して、`~/.gemini/antigravity-cli/settings.json` を更新します。sandbox 内は自動実行 (`toolPermission: proceed-in-sandbox`, `enableTerminalSandbox: true`)、agent-coord のツールはサーバー単位 (`mcp(agent-coord_agent_coord/*)`) で許可します。[公式の sandbox 設定](https://www.antigravity.google/docs/sandbox?tab=cli)

共通許可の原本は `files/antigravity_user-permissions.json` です。Codex のレビュー済みコマンド例外11件とネットワーク許可、Claude の追加書込先と資格情報・ソケットの読取禁止を対応付け、`tests/setup_agy_permissions.test.py` で差分を検出します。実行形式の評価や拒否の優先順位は agy 自身の仕様に従い、Claude の動的な auto 判定や環境変数フィルターまで同一とはみなしません。広すぎる `command(*)`・`mcp(*)` や、曖昧な `node` の許可は追加しません。

既存設定・`deny`・`ask` は保持し、再実行でもルールを重複させません。明示的な `deny` / `ask` は追加した許可より優先されます。これらの許可設定は、セッション識別や待機中の起床の修正とは別です。[公式の権限仕様](https://www.antigravity.google/docs/permissions?tab=cli)

```bash
agy
```

初回起動時にログインプロンプトが表示されます。

- ローカル端末：自動で開くブラウザーで Google アカウントにログインします。
- SSH 接続先：端末に表示された認証 URL を手元のブラウザーで開いてログインし、発行された認証コードを SSH 端末に貼り付けます。

保存済みの有効な認証情報がある場合は自動ログインします。[公式の認証手順](https://antigravity.google/docs/cli/install#authentication-workflows)も参照してください。

### GitHub CLI

```bash
gh auth login
```

### Jev

API キーを入力すると、テストクエリーで有効性を確認してから保存します。`jev hello` でも接続を確認できます。

```bash
jev api-key set
jev hello
```

`jev api-key status` で保存状態と利用可否を確認できます（登録済みならテストクエリーを 1 回送信）。キーの更新も `jev api-key set`、削除は `jev api-key clear` で行います。エージェントからの利用方法や診断結果の見方は [Jev の利用手順](docs/typesafe.md) を参照してください。

### CodeGraph

コードを解析するリポジトリで実行します。

```bash
codegraph init -i
```

### Google Cloud

Cloud Run や BigQuery を利用するアカウントで認証します。

```bash
gcloud auth login
gcloud auth application-default login
```

BigQuery の MCP 接続には、使用するプロジェクトも指定します。

```bash
gcloud config set project <プロジェクトID>
```

## スマートフォンからの操作 (Remote Control)

Claude Code・Codex・Antigravity の CLI を、スマートフォンから操作できます。上の初回認証を済ませてから、使う OS ユーザーで設定してください。操作する間は、ホストをスリープさせずネットワークにつないでおきます。

| CLI | スマートフォンで開くもの | 常駐のしかた | 初回だけ必要な操作 |
|---|---|---|---|
| Claude Code | Claude アプリの **Code** | 起動した `claude` が自動で接続。または `claude remote-control` | プロジェクトのディレクトリで一度 `claude` を起動し、信頼確認を承認 |
| Codex | ChatGPT アプリの **Remote**（Mac / Windows のデスクトップアプリ経由） | `codex remote-control start` で daemon を起動 | デスクトップアプリでの接続設定、または `codex remote-control pair` |
| Antigravity | ブラウザーで [Remote Control Dashboard](https://antigravity.google.com) | `agy remote-control start` で daemon を登録（マシン起動時に自動起動） | なし（同じ Google アカウントでサインイン） |

### Claude Code

配布する `~/.claude/settings.json` は `remoteControlAtStartup: true` なので、起動した `claude` は自動で Remote Control に接続します。スマートフォンでは Claude アプリの **Code** を開き、緑の点が付いたセッションを選びます。

事前に、操作したいプロジェクトのディレクトリで一度 `claude` を起動し、信頼確認を承認してください。ホームディレクトリでは信頼が保存されないため、プロジェクトのディレクトリから起動します。

スマートフォンから新しいセッションを始めたい場合は、プロジェクトのディレクトリで次を起動したままにします。SSH 接続先では `tmux` などの中で実行します。

```bash
claude remote-control
```

初回だけ `Enable Remote Control? (y/n)` と聞かれるので `y` と答えます。スペースキーで QR コードを表示できます。アプリが入っていない場合は、Claude Code 内で `/mobile` を実行するとインストール用の QR コードが出ます。

Windows のデスクトップアプリでは **Settings > Claude Code > Enable remote control by default** が同じ設定です。[公式の Remote Control](https://code.claude.com/docs/en/remote-control)

### Codex

セットアップ時にユーザーごとに remote control を有効化しています（`codex app-server daemon enable-remote-control`）。止まっている daemon は自動では起動しないため、認証後に次を実行します。

```bash
codex remote-control start
codex remote-control pair
```

`pair` は、daemon の起動中に、短時間だけ有効な手動ペアリングコードを表示します。`codex remote-control pair --json` とすると、`pairingCode`・`manualPairingCode`・`environmentId`・`expiresAt` を JSON で出力します。[CLI リファレンス](https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-remote-control)

公式文書では、スマートフォンの ChatGPT アプリ **Remote** から操作できるホストは、macOS / Windows の ChatGPT デスクトップアプリを動かすマシンです。設定はデスクトップアプリから始め、Codex CLI からは設定できません。Linux のマシンを使う場合は、そのデスクトップアプリの **Settings > Connections** で SSH ホストとして追加し、スマートフォンはデスクトップアプリのホストにつなぎます。SSH ホスト側では、ログインシェルの `PATH` に `codex` があり、認証済みである必要があります。手動ペアリングコードを入力する画面は、公式文書には書かれていません。[Codex Remote](https://learn.chatgpt.com/docs/remote)・[Remote connections](https://learn.chatgpt.com/docs/remote-connections)

### Antigravity

`setup_user_environment` は、`agy` がサインイン済みで daemon が止まっている場合だけ daemon を登録します。初回は `agy` でサインインしてから次を実行します。

```bash
agy remote-control start
agy remote-control status
```

daemon は systemd のユーザーサービスとして登録され、マシン起動時に自動で起動します。`status` が表示するインスタンス名を、スマートフォンのブラウザーで開いた [Remote Control Dashboard](https://antigravity.google.com) で選びます（同じ Google アカウントでサインイン）。ホーム画面に Web アプリとして追加すると、プッシュ通知を受け取れます。

名前は `agy remote-control start --name <名前>` で変えられます（再実行すると daemon が再起動します）。一覧に出ないときは `journalctl --user -u antigravity-cli-daemon -n 50` でログを確認します。[公式の Remote Control](https://antigravity.google/docs/remote-control)

## 追加セットアップ

以下は OS のセットアップスクリプトからは呼び出されません。必要なものを、セットアップ完了後にリポジトリのルートから実行してください。

### 音声通知

```bash
sudo ./extra/voicevox.sh
```

VoiceVox Core と Claude Code の音声通知を導入します。GitHub の API 利用制限を避けるため、事前に `gh auth login` を済ませておくことを推奨します。

`voicevox_claude_alerts say TEXT` で読み上げを確認できます。操作一覧は `voicevox_claude_alerts help`、音が出ない場合は[音声のトラブルシューティング](docs/TROUBLE-SHOOTING.md)を参照してください。

### SigNoz テレメトリ

```bash
sudo ./extra/signoz.sh
```

Docker と SigNoz を導入し、Claude Code の OpenTelemetry データを可視化します。ダッシュボードは `http://localhost:14902`、初期ログインは `admin@signoz.localhost` / `At4902.localhost` です。導入後にシェルを開き直すと、テレメトリ用の環境変数が読み込まれます。

## 更新・設定変更

設定やスクリプトの変更は、リポジトリの `files/` 配下に反映します。変更したファイルだけを個別に `cp` して配備しても構いません。ファイル単体の変更でセットアップ全体を再実行する必要はありません。コピー先・所有者・権限は対象 OS の導入スクリプトに合わせ、複数箇所に配布されるファイルは各配布先に反映してください。

例えば `mytask` だけを変更した場合は、リポジトリのルートで次を実行します。

```bash
sudo cp files/shared_cli/mytask /usr/local/bin/mytask
```

依存パッケージの追加や設定の生成・登録も伴う変更は、対応する導入処理も実行してください。配備先の `/etc/claude-code/`、`/etc/codex/`、`/usr/local/bin/` などだけを直接編集すると、次の配備で上書きされます。

環境全体を更新する場合は、リポジトリを更新して `sudo ./debian12.sh` または `sudo ./ubuntu2404-wsl.sh` を実行します。[呼び出しツリー](#スクリプトの呼び出し関係)のとおり、システム全体と root・ログインユーザーの環境が更新されます。

追加ユーザーの環境を更新する場合は、そのユーザーで `setup_user_environment` を実行します。導入済みの音声通知や SigNoz を更新する場合は、それぞれの追加スクリプトを再実行してください。

変更を読み直す必要があるシェルや対象のエージェントは、更新後に開き直してください。
