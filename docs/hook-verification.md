# hook を配備する前の検証手順

hook・settings・MCP の配線のように、配備してから壊れると全セッションの作業が止まるものは、配備対象 (`files/`) に入れる前に、`drafts/` の実験用リポジトリで実際の Claude のセッションを動かして確かめます。配備対象へ移すのは、検証が済み、利用者が了承してからです。

## 1. 実験用リポジトリを作る

- `drafts/<名前>/probe/` で `git init` し、試したい hook と許可を `probe/.claude/settings.json` に置きます。`.claude/` は probe の `.gitignore` に入れます。
- 作者 (`git config user.name` / `user.email`) は普段と同じにします。違うと、利用者設定のコミット作者の検査がコミットを止めます。
- 配線の試験と判定の中身の試験は分けます。配線の試験では、対象のファイルを中身のないダミーにし、結果はコミットメッセージの目印などで強制します。

## 2. Claude のセッションを起動する

信頼済みのリポジトリ (このリポジトリ) を作業ディレクトリにして、次を 1 回の Bash 呼び出しで単独に実行します。

```bash
claude --bg '<1 行の依頼>' --model <モデル> --permission-mode dontAsk \
  --setting-sources user --settings <probe>/.claude/settings.json \
  --allowedTools '<許可する道具>' --mcp-config '<JSON>' --strict-mcp-config
```

- `claude --bg` はサンドボックスの除外コマンドなので、サンドボックスの外で利用者の認証のまま起動します。除外は単独のコマンドが先頭で一致したときだけ効きます。パイプ・リダイレクト・環境変数の前置きを付けると、サンドボックスの中で動き、`~/.claude/jobs` を作れずに失敗します。
- Claude Code 2.1.283 (2026-09-27 確認) の `claude --bg` は、未信頼のフォルダでは「Workspace not trusted」で起動しません (2.1.280 では起動できました)。親フォルダの信頼も引き継ぎません。そこで、実験用リポジトリの hook は `--settings` で渡し、`--setting-sources user` でこのリポジトリの project と local の設定を外します。信頼の設定は変えません。
- 依頼の中のコミットは `git -C <probe> commit ...` と書き、`--allowedTools` も `Bash(git -C <probe> commit *)` に限ります。このリポジトリへのコミットを許さないためです。
- 同じ実験用リポジトリで何度もコミットさせるときは `--allow-empty` を付けます (`-- <file>` と一緒に使えます)。
- `claude -p` はサンドボックスの中で動き、認証情報を読めずに「Not logged in」で止まるので、使いません。
- 起動したセッションの Bash はサンドボックスの中で動きます。hook から呼ぶスクリプトが記録を残すときは、コマンドの `-C` の先 (実験用リポジトリ) の中に書き、このリポジトリの直下には書きません。
- hook の中で何が起きたかを追うときは、`--debug-file <path>` も付けます。

## 3. 続けて操作する

- 起動したセッションは、1 回の依頼を終えると待機します。次の依頼を SendMessage (宛先は ListAgents に出る名前) で送ると、そのセッションが起きて実行します。起動したセッションは agent-coord にも参加します。
- セッションの一覧は `claude agents --json`、止めるのは `claude stop <id>` です。
- コミットのような操作の場面は、SendMessage で続けて送らず、場面ごと (または場面の並びごと) に新しいセッションを起動して、最初の依頼で渡します。SendMessage で送った依頼でコミットしたセッションは、利用者の承認の無い依頼だったとして止まった状態 (blocked) になりました。

## 4. 観察する場所

| 知りたいこと | 場所 |
|---|---|
| 道具の呼び出し・結果・hook の出力 | `~/.claude/projects/<作業ディレクトリの / を - にした名前>/<セッション id>.jsonl` |
| 依頼ごとの開始と終了の時刻 | `~/.claude/jobs/<短い id>/timeline.jsonl` |
| MCP サーバーの道具の呼び出しと所要時間 | `~/.cache/claude-cli-nodejs/<作業ディレクトリの / を - にした名前>/mcp-logs-<サーバー名>/*.jsonl` |
| Jev 文脈ゲートの判定 | `~/.claude/hooks/state/jev_context_gate/log.jsonl` |

- agent 型 hook のサブエージェントの道具の呼び出し・許可・エラーは、`--debug-file` の記録に出ます (`source=hook_agent` の API 要求の間の `tool_dispatch_start` / `tool_dispatch_end`、`permission denied` の行)。サブエージェントの会話そのものは、セッションの記録に入りません。
- `--debug-file` の記録では、次の行も確かめます。`Hooks: Got structured output` は agent 型 hook の答え、`Agent hook did not return structured output` は期限切れ、`mcp_tool hook skipped — MCP server '<名前>' not connected` は MCP サーバーが見えずに省略したことを示します。最初の `Dynamic tool loading` の行 (最初のターンの始まり) が `MCP server "<名前>": Successfully connected` より前だと、そのターンの hook から MCP サーバーが見えないことがあります。
- agent 型 hook が通したときは、理由がどこにも出ません。止めたときだけ、道具の結果に理由が出ます。通したことを利用者に見せるには、PostToolUse の command 型 hook が `systemMessage` を出します。
- サブエージェントが道具を呼んだかは、サブエージェントの答えの文ではなく、`--debug-file` の記録 (`Calling MCP tool: <道具>` など) で数えます。答えの文には、呼んでいない道具の結果が書かれることがあります。
- 手順を守る割合を見るときは、同じ場面を 5 セッション以上で繰り返します。

## 5. 本番のキーを使わない

- 配備済みの `mcp_tool` の Jev 文脈ゲートは、実験用リポジトリのコミットでも動きます。`--mcp-config` で `jev` サーバーを `"env": {"JEV_CONTEXT_GATE_DEADLINE": "0"}` 付きで起動し、`--strict-mcp-config` を付けると、ゲートは API を呼ぶ前に判定を省略します。省略したことは `jev_context_gate/log.jsonl` の `"outcome": "skip"` で確かめます。
- 実験から Jev を呼ぶときは、必ず `profile` に `test` を渡します。

## 6. 配備の条件

- 想定する場面 (通す・止める・境界・対象外のコマンド・依存先が使えないとき) をすべて実行し、結果と所要時間を記録してから、配備対象に移す案を利用者に示します。
- 場面には、同じ操作の別の書き方 (`git -C <dir> commit` など)、hook の期限切れ、セッションの最初のターン (起動直後に依頼を渡す `claude --bg '<依頼>'`) も入れます。期限切れと、MCP サーバーが見えないときの省略は、どちらもコマンドを通します。
- 配備対象 (`files/`) に移すのは、利用者が了承してからです。
