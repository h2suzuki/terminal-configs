[[en]](README.en.md) [jp]

# Terminal Configs

ターミナル環境を素早くセットアップするための設定ファイルとスクリプトです。


## 使い方

### 基本セットアップ

環境に合うスクリプトを root で実行してください。

    # ./ubuntu2404-wsl.sh

もしくは

    # ./debian12.sh

スクリプトは末尾でログインユーザーとして `setup_user_environment` を実行し、その中で
`install_claude_extensions`（Claude Code の hooks・skills・共有 memory clone のユーザー側インストール）まで
行います。別途実行する必要はありません。

共有 memory clone の取得元はメンテナ個人の private リポジトリです。アクセス権が無い環境ではこの clone だけが
スキップされ、セットアップは中断せず最後まで完走します。無効になるのは memory 機能だけで、hooks・skills・
MCP・CLI はすべて通常どおり導入されます。リポジトリの owner 本人で clone に失敗した場合は、`gh auth login`
の後に `install_claude_extensions` を再実行してください。

### 追加セットアップ（opt-in）

基本セットアップの後、必要に応じて `extra/` 配下のスクリプトを root で実行します。

    # ./extra/voicevox.sh            # VoiceVox による音声通知
    # ./extra/signoz.sh              # SigNoz による Claude Code テレメトリ

いずれも再実行で上書き更新できます（VoiceVox Core 本体は導入済みならスキップされます）。

### 新しいユーザーの追加

セットアップ済みのマシンにユーザーを追加する場合、上記スクリプトを再実行する必要はありません。追加したユーザーでログインし、以下を実行してください。

    $ /usr/local/bin/setup_user_environment

基本セットアップの内容のうちユーザーごとの部分（Bash・Git の設定、Node.js、Claude Code とその拡張、Codex CLI など）が、そのユーザーの環境に整います。

### `files/` を編集した後の再配備

設定の正本は `files/` 配下です。`/etc/claude-code/` や `~/.claude/`、`/usr/local/bin/` に置かれているものは
スクリプトの出力なので、変更は `files/` 側に加えてから配備し直します。

最も確実なのは、基本セットアップと同じスクリプトを root で再実行することです。

    # ./debian12.sh          # または ./ubuntu2404-wsl.sh

変更のないファイルは「already installed」と表示されてスキップされ、差分のあるものだけが上書きされます。
末尾でログインユーザーの `setup_user_environment` まで走るので、`~/.claude/hooks/` や `~/.claude/skills/`
のようなユーザー側の配備先も同時に更新されます。

配備先ごとの手順は次のとおりです。

| 編集した場所 | 配備コマンド |
|---|---|
| `files/` 全般 | `sudo ./debian12.sh`（または `sudo ./ubuntu2404-wsl.sh`） |
| `files/claude_user-hooks/`, `files/claude_user-skills/` | 上のスクリプトを実行後、別ユーザーは各自 `install_claude_extensions` を実行 |
| `files/voicevox_*`, `files/claude_managed-voicevox.json` | `sudo ./extra/voicevox.sh` |
| `files/signoz_*`, `files/claude_env.sh` | `sudo ./extra/signoz.sh` |

1 ファイルだけを急いで反映したい場合は、スクリプト内の `copy` 行で配備先を確認し、直接コピーします。

    $ grep -n 'copy.*<ファイル名>' debian12.sh extra/*.sh
    # cp files/<ファイル名> <配備先>

いずれの操作も、Claude Code のセッション内では実行できません（配備先は root 所有で、Bash サンドボックスは
sudo を通しません）。通常のターミナルから実行してください。


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

- neovim, tree, shellcheck, htop
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
- Claude Code の補助ツール: bubblewrap, socat, sandbox-runtime（Sandbox）, poppler-utils（PDF 読み取り）
- Antigravity CLI（agy）
- Codex CLI


### 6. Claude Code 基本設定

- Spinner Verbs 日本語訳
- Status Line: プロジェクト名 / モデル名 / Context 消費 / レートリミット / 現在時刻
- 憲法（org ルール） `/etc/claude-code/CLAUDE.md`
- ユーザー設定 `~/.claude/CLAUDE.md` / `~/.claude/settings.json`（auto 権限モード, effort 既定値など）
- Sandbox ポリシー（`/etc/claude-code/managed-settings.json`）: Bash サンドボックス有効化、書き込み許可パスの限定、認証情報ファイル・トークン環境変数の読み取り拒否


### 7. WSL2 調整 [WSL2のみ]

- mDNS（`.local`）の名前解決を Windows ホスト側に委譲
  - NAT モードの WSL2 上でも `.local` 名を解決可能
- systemd の有効化
- ホスト名の固定


### 8. Claude Code 拡張

Claude Code に「信頼を高めるための仕組み」と外部ツール連携を入れます。

- **ユーザー側フック**: commit 著者確認・push 催促検出・memory surface・subagent gate を `~/.claude/hooks/` に配置し、ユーザーごとの RAG memory インデックスを構築します。
- **LSP**: 言語サーバー（clangd は基本セットアップで APT 導入、typescript-language-server / pyright を npm 導入）と対応プラグイン（clangd-lsp / typescript-lsp / pyright-lsp）。
- **MCP サーバー（scope=user）**: Chrome DevTools（性能・メモリー調査。Codex にも登録）, CodeGraph（コード知識グラフ）, Cloud Run, Toolbox（BigQuery）
- **プラグイン**: security-guidance（既定で無効）, figma, codex（OpenAI Codex への委譲・コードレビュー）
- **CLI**: agent-browser（日常の画面確認）, Playwright CLI（テスト作成・再現調査）, Vercel CLI。ブラウザ操作の公式 Skill は Claude Code と Codex に配置し、旧 Playwright MCP 登録は削除します。

Chrome DevTools MCP は headless・isolated・memory-debugging を有効にし、利用統計と CrUX への URL 送信を無効にします。Chrome は基本セットアップで導入した Linux 版を使います。

繰り返す自動テストには、対象アプリごとに Playwright Test を開発用依存関係として導入します。未導入ならアプリのディレクトリで `npm init playwright@latest` → `npx playwright install --with-deps` を実行し、対象 URL・ブラウザ・期待結果を設定して `npx playwright test` で確認します。既存の設定・パッケージ管理方法を優先し、設定・テスト・lockfile はアプリ側で管理します。

セットアップ後、以下の認証 / 初期設定を済ませてください（ここで登録される MCP のみの一覧です。`claude mcp list` には他の手段で設定した MCP も表示されます）。

| MCP | 認証 / 初期設定コマンド |
|---|---|
| codegraph | リポジトリのトップディレクトリで `codegraph init -i` |
| cloud-run | `gcloud auth login`<br>`gcloud auth application-default login` |
| toolbox | `gcloud config set project <プロジェクトID>`<br>`gcloud auth application-default login` |
| figma | Claude Code のコンソールで `/mcp` から OAuth2 認証 |

認証後は `/mcp` と `/doctor` で接続状態を確認できます。

codex プラグインは `!codex login` で認証し、`/codex:setup` で疎通確認、`/reload-plugins` で現セッションへ反映します。


### 9. Codex と共通 worktree

Codex CLI は `setup_user_environment` で導入し、両 OS のセットアップで
`files/codex_config.toml` を `/etc/codex/config.toml` に配置します。
これは上書き可能なシステム既定値です。ユーザー設定・プロジェクト設定・起動オプションが
優先されるため、起動後に `/status` と `/permissions` で実効設定を確認してください。

- `sandbox_mode = "workspace-write"`: 作業ディレクトリと一時領域への書き込みを許可。
- `approval_policy = "never"`: 承認を求めず、明示的な許可ルールもない範囲外の操作は失敗します。
- `network_access = true`: sandbox 内のコマンドのネットワークアクセスを許可。
- `writable_roots = ["~/worktrees"]`: 起動ユーザーの worktree 保存先全体への書き込みを許可します。
- `[tui] status_line`: TUI のステータス行に表示する項目と順序。モデル・実行状態・作業ディレクトリ・
  ブランチ・コンテキスト使用量・週次上限・入出力トークン数・タスク進捗を並べます。
- `[tui] status_line_use_colors = true`: ステータス行に色を付けます。

Claude Code と Codex の手動 worktree は `~/worktrees/<repo>/<name>` に統一します。
`<name>` はブランチ名、または GitHub issue 番号に対応する `issue-123` などを推奨します。
これは命名の推奨であり、強制・自動検証はしません。ブランチ名の `/` をそのまま使う場合は、
`feature/foo` → `~/worktrees/<repo>/feature/foo` のように階層になります。
ユーザーセットアップで `~/worktrees` を作成します。同じタスクを引き継ぐ場合は同じ
worktree を使い、並行して編集する別タスクには別の worktree を割り当てます。
以下はホストのターミナルで、対象リポジトリから実行する例です（`myrepo` と `task-1` は置換）。

```bash
mkdir -p "$HOME/worktrees/myrepo"
git worktree add -b task-1 "$HOME/worktrees/myrepo/task-1"
codex
# このセッションで ~/worktrees/myrepo/task-1 を作業対象に指定
```

Claude Code は `sandbox.filesystem.allowWrite`、Codex は `sandbox_workspace_write.writable_roots`
で `~/worktrees` 全体を許可します。両方とも元のリポジトリで起動したセッションから
worktree を作成・編集でき、対象 worktree に移動して起動し直す必要はありません。
設定の変更は配置後に新しく起動する Codex セッションから適用されます。
初回の trust 確認は sandbox の書き込み許可とは別なので、対象を確認して応答してください。

Codex の `workspace-write` では `.git` とその参照先、`.agents`、`.codex` が保護されます。
共通のコマンド除外は、両 OS のセットアップで `files/codex_sandbox_exclusions.rules` を
`/etc/codex/rules/terminal-configs-sandbox-exclusions.rules` に配置します。
`prefix_rule` の `decision = "allow"` に一致するコマンドは承認なしで sandbox 外で実行されます。
Claude Code の共通 `excludedCommands` を個別に確認した対応は以下のとおりです。

| Claude 側の除外 | Codex 側の対応・理由 |
|---|---|
| `git *` | `git` を許可。Git 管理領域への書き込み・ホスト認証。 |
| `gh *` | `gh` を許可。GitHub 認証・ユーザー設定へのアクセス。 |
| `claude_memory_sync *` | 同名 CLI を許可。共有 memory clone と index を workspace 外で更新。Codex から共有メモリを操作する場合にも必要。 |
| `docker *` | `docker` を許可。ホストの Docker daemon への接続。 |
| `codex *` | `codex` を許可。子 CLI が自身の sandbox とユーザー状態を管理。 |
| `agent_coord *` | `agent_coord` を許可。host 側の台帳 daemon に接続し、worktree 作成などの Git 操作を host 権限で行う。 |
| `node *codex-companion.mjs*` | 共通ルールには移さない。prefix rule は引数内の glob に非対応。必要な環境で `node` と companion の絶対パスを指定する個別ルールを登録する。`node` 全体は許可しない。 |
| `codex_broker_reap*` | 実在する `codex_broker_reap` のみ許可。ホストのプロセス表を見ないと稼働中 broker を誤判定する。名前の前方一致は移さない。 |
| `agent-browser *` | `agent-browser` を許可。ホストのブラウザ・セッション・開発サーバーへのアクセス。 |
| `claude --bg *` | `claude --bg` のみ許可。自身の sandbox を持つ Claude のバックグラウンド起動。 |
| `claude agents *` | `claude agents` のみ許可。ホストの Claude セッション情報へのアクセス。 |

これは実行権限の設定であり、委譲や外部変更を自動で指示するものではありません。
除外コマンドの子プロセス（Git hooks など）もホスト権限で動作し、Docker はホストへの
広いアクセスを持ちます。子 Codex / Claude の sandbox 設定は子側の設定・起動引数に従います。
通常のコマンドは引き続き sandbox 内で動作します。Claude Code の認証情報読み取り拒否は
このルールでは再現していません。

プロジェクト固有の除外は org policy に含めず、各プロジェクトで管理する drop-in、
または各プロジェクトの `.claude` / `.codex` に設定します。
Claude の drop-in は共通 Codex ルールへ自動変換しません。

ルールは Codex の再起動後に読み込まれます。コマンドは裸名で呼び出してください。
複雑なシェルのラッパーはルールに一致しない場合があり、別の `prompt` / `forbidden`
ルールや管理制約がある場合は、そちらの制限が優先されます。

仕様: [Codex 設定](https://learn.chatgpt.com/docs/config-file/config-reference)、
[sandbox と保護パス](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots)、
[sandbox 外実行ルール](https://learn.chatgpt.com/docs/agent-configuration/rules)。


### 10. Agent 間協調（`agent_coord`）

`agent_coord` は、同じ OS ユーザーで動く Claude Code / Codex / Antigravity などの agent session を
横断して調整する、ホスト単位の CLI + daemon + MCP アダプタです。session 一覧、project/repo/all scope の
メッセージング、排他的な resource grant、worktree の所有権を daemon のメモリ上にある 1 つの ledger に
集約します（SQLite へ write-through で永続化し、再起動時に再構築。保存先 `~/.local/state/agent_coord/`）。
導入は基本セットアップが行い、手動の手順はありません。

| 構成要素 | 配置 |
|---|---|
| CLI / daemon / MCP アダプタ / hooks 本体 | `/usr/local/bin/agent_coord` |
| Claude Code・Codex 用 plugin bundle（client 別の manifest・hooks・MCP 宣言と共通 skill） | `/usr/local/share/agent_plugins/agent-coord/` |
| Antigravity 用 plugin bundle（Antigravity の hooks / mcp_config 形式） | `/usr/local/share/agent_plugins/agent-coord-antigravity/` |
| Claude Code への導入 | `install_claude_extensions` が marketplace 登録と `agent-coord@terminal-configs` の install を行う |
| Codex への導入 | 同 script が `codex plugin marketplace add` と `codex plugin add agent-coord@terminal-configs` を行う |
| Antigravity への導入 | 同 script が `agy plugin install` で専用 bundle を取り込む（`agy` がある環境のみ） |

連絡は投稿時に宛先ごとの inbox へ配送され、受信側の ack で消えます。未読が生じると、Claude Code
session には inbox socket 経由、Codex session には `codex queue` 経由で一度だけ起こしに行き、
Antigravity は hooks による pull のみです。どの client でも hooks が session 参加・未読注入・claim した
worktree 外への編集拒否を行い、MCP 経由で send/catchup/acquire/worktree などの tool が使えます。
daemon は hooks / MCP アダプタから自動起動します。人間が状況を見るだけなら `agent_coord status` /
`agent_coord watch` で足り、`agent_coord doctor` が接続・session・通知・強制・sandbox の各能力を
分けて表示します（LLM 不要）。


## 追加セットアップの内容

### A. 音声通知（`extra/voicevox.sh`）

VoiceVox Core と、待機通知・サブエージェントの完了報告・Claude Code からの質問などを VoiceVox で発話する `voicevox_claude_alerts` をインストールします。発話フックは managed-settings の drop-in（`/etc/claude-code/managed-settings.d/voicevox.json`）として登録されるため、本スクリプトを実行していない基本セットアップ機には、存在しないフックへの参照が残りません。

VoiceVox Core のダウンロードは GitHub の API 利用制限を受けるため、本スクリプトの実行前に `gh auth login` を済ませておくことを推奨します。なお、この認証は `/etc/gitconfig` の credential 設定経由で `git clone` などの GitHub ユーザー認証にも利用されます。

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


### B. SigNoz テレメトリ（`extra/signoz.sh`）

Docker をインストールし、SigNoz（オブザーバビリティ基盤）を docker compose で立ち上げて、Claude Code の OTEL（OpenTelemetry）テレメトリを可視化するダッシュボードを構築します。

- SigNoz UI は 14902/tcp で待ち受け
- ログイン用の管理ユーザーを自動作成（`admin@signoz.localhost` / `At4902.localhost`）
- Claude Code 用ダッシュボードを自動投入
- OTEL 環境変数を `/etc/claude-code/env.sh` に配置し、`~/.bashrc` から読み込み


----

音声まわりのトラブルシューティングは [`docs/TROUBLE-SHOOTING.md`](docs/TROUBLE-SHOOTING.md) を参照してください。

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
