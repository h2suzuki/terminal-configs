# トラブルシューティング

## WSLg の PulseAudio が無応答になる

### 症状

- `pactl info` は応答するが `pactl list sink-inputs` や `pactl list clients` がストールする
- `paplay` / `voicevox_paplay` などの新規再生が始まらない、または途中で止まる
- `pa_context_kill_sink_input` を libpulse 経由で投げても応答が返らない

### 発生条件

`pasimple` 系クライアント (`voicevox_paplay` 等) をストリーム書き込み中・drain 中に kill すると、WSLg 側 pulseaudio の sink-input がクリーンアップされず **幽霊 sink-input** として残る。列挙系 API がこれに触れるとデッドロックする。繰り返すと幽霊が蓄積する。

### 診断

```bash
# 幽霊の有無を確認 (ストールすれば幽霊あり)
timeout 3 pactl -s unix:/mnt/wslg/PulseServer list short sink-inputs

# 個別 index で応答するか探る (timeout が幽霊)
for i in $(seq 0 30); do
  start=$(date +%s.%N)
  timeout 2 pactl -s unix:/mnt/wslg/PulseServer set-sink-input-mute $i 0 >/dev/null 2>&1
  end=$(date +%s.%N)
  elapsed=$(awk "BEGIN{printf \"%.2f\", $end - $start}")
  [ "${elapsed%.*}" -ge 2 ] 2>/dev/null && echo "index $i: zombie"
done

# サーバ側 ESTAB に peer=0 (half-closed) の残骸があるか
ss -x | grep Pulse
```

### 回復手順

`wsl --shutdown` は不要。以下の 2 ステップで復旧する。

**1. Windows の PowerShell から WSLg の pulseaudio を kill する**

```powershell
# まず PID を確認 (ユーザー wslg の /usr/bin/pulseaudio)
wsl --system -d <DISTRO_NAME> bash -c "ps -ef | grep -i pulse"

# PID を指定して kill (WSLGd が自動で respawn する)
wsl --system -d <DISTRO_NAME> bash -c "kill <PID>"
```

- `<DISTRO_NAME>` は `wsl -l` で確認 (例: `Ubuntu-24.04`)
- WSLGd (PID 8 前後) が supervisor として自動再起動するので、手動での起動は不要
- respawn 確認: `ls -la /mnt/wslg/PulseServer` で mtime が更新されていれば成功

**2. distro 内で proxy を restart する**

```bash
sudo systemctl restart pulseaudio-proxy.service
```

- `pulseaudio-proxy.service` は `/etc/pulse/proxy.pa` で TCP 24713 → `/mnt/wslg/PulseServer` のトンネルを張っている
- kill で WSLg 側が作り直されたので、こちらの tunnel 接続も再構築が必要

### 動作確認

```bash
timeout 3 pactl -s unix:/mnt/wslg/PulseServer list short sink-inputs  # 即応答 (空) であれば OK
timeout 3 pactl -s tcp:localhost:24713 info                           # proxy 経由も OK
```

### 原因の詳細

`pasimple` は以下のシーケンスで動く:

1. `pa_simple_write(全PCM)` — PCM 全体をサーバへ一括投入
2. `pa_simple_drain()` — 「全部鳴らし終わるまで待て」をサーバに要求
3. プロセスが `pa_simple_free` を呼ぶ前に kill される
4. カーネルがソケットを close するが、WSLg pulseaudio 側では drain 契約中の sink-input が解放できない状態のまま保留

WSLg の pulseaudio はプロセス自体は生きているので `pactl info` は返る。ただし sink-input 列挙に入ると幽霊エントリでロックして全体が詰まる。
