[[en]](README.en.md) [jp]

# Terminal Configs

ターミナル環境を素早くセットアップするための、ささやかな設定ファイルとスクリプト群です。


## 使い方

環境に合うスクリプトを root で実行してください。

    # ./debian12.sh


## Claude Code 通知フック

Claude Code のイベントを Voicevox で読み上げる通知スクリプトは
`/usr/local/bin/voicevox_claude_alerts` にインストールされます。既定では
ログ出力は行いません（WAV キャッシュは `voicevox_paplay` が管理し、揮発的な
ランタイムファイルは `$XDG_RUNTIME_DIR/voicevox_claude_alerts/` 配下に置かれます）。

スクリプトは小さな CLI も提供します。`voicevox_claude_alerts help` で全一覧、
`events` で対応フックの一覧、`log` で直近の発話履歴、`say TEXT` で
Voicevox を介したテキスト読み上げが可能です。

フックは `voicevox_paplay` を 2 つのモードで呼び出します:

- **固定フレーズには `--cache`**（アイドル警告、許可プロンプト、サブエージェント
  開始/停止のフォールバック、ConfigChange / PreCompact / WorktreeCreate）。
  ユニークなフレーズごとに 1 度だけ合成され、`~/.claude/hooks/voicevox-cache/`
  に保存されます。以後の再生は瞬時に行われます。
- **動的な Haiku 要約にはキャッシュなし**（最終文が 30 文字を超える質問付きの
  Stop、および SubagentStop）。要約はその都度ユニークなのでキャッシュしても
  ディレクトリが肥大化するだけです。再生のたびに新規合成のコストがかかります。

最終文がすでに 30 文字以下の Stop フックは、Haiku を完全にバイパスして
その文をそのまま読み上げます（コールドスタート約 6 秒のレイテンシを節約）。
入力長に上限がないため、こちらもキャッシュは行いません。

発話内容と生のフック payload を記録したい場合（デバッグ用途）、
`CLAUDE_NOTIFY_DEBUG=1` を以下のいずれかの方法で有効化します:

- **一時的（シェル）** — 直後の Claude Code セッションのみ有効:

      export CLAUDE_NOTIFY_DEBUG=1

- **永続化（settings.json）** — すべてのセッションに自動適用。本リポジトリが
  インストールする `~/.claude/settings.json` に `env` ブロックを追加します:

      {
        "env": {
          "CLAUDE_NOTIFY_DEBUG": "1"
        },
        ...既存の他のキー...
      }

  この項目を削除する（あるいは `"0"` にする）と既定の無音状態に戻ります。

デバッグを有効にすると、`~/.claude/hooks/` 配下に追記専用の 2 ファイルが現れます:

- `dump.jsonl` — すべてのフック payload を行区切り JSON で記録
- `spoken.log` — 発話ごとの `<タイムスタンプ>\t<イベント>\t<発話テキスト>` を TSV で記録

いずれも無制限に増えていくので、不要になったら truncate または削除してください。

ロックを全 UID 間で直列化しつつ（オーディオは共有デバイスのため）、
セッション単位・ユーザー単位の状態は分離するため、ファイルはスコープごとに
分けて配置されます:

```
/tmp/voicevox_claude_alerts.voicevox.lock    ← システム全体共有 (mode 0666)
/tmp/voicevox_claude_alerts.haiku.lock         voicevox / claude -p 呼び出しを
                                               直列化するための flock 対象

$XDG_RUNTIME_DIR/voicevox_claude_alerts/     ← ユーザーごと
    (fallback: /tmp/voicevox_claude_alerts-<uid>, mode 0700)
├── spoke-recently-<sid>        idle_prompt 抑止マーカー
└── subagent-start-<sid>        SubagentStart の 30 秒抑止マーカー

$XDG_STATE_HOME/voicevox_claude_alerts/      ← ユーザーごと
    (fallback: ~/.local/state/voicevox_claude_alerts/)
├── dump.jsonl                  全 payload を JSONL で記録（デバッグ時のみ）
└── spoken.log                  全発話の TSV ログ（デバッグ時のみ）

$XDG_CACHE_HOME/voicevox_paplay/             ← ユーザーごと、voicevox_paplay
    (fallback: ~/.cache/voicevox_paplay/)      バイナリと共有
└── <text>_<hash>.wav           固定フレーズの合成結果キャッシュ
                                （voicevox_paplay 自身が管理）
```

これらのファイルはどれも削除して構いません。スクリプトは次回起動時に必要な
ものを再生成します。`*_<sid>` マーカーを消すと、その Claude Code セッションの
対応する抑止状態がリセットされるだけです。WAV キャッシュを削除すると、
固定フレーズごとに初回再生時に 1 回再合成のコストがかかります。
システム全体共有のロックファイルは 0 バイトで、必要に応じて mode 0666 で
自動再生成されます。

----
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/h2suzuki/terminal-configs.git)
