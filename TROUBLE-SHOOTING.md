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

---

## WSLg direct の散発的劣化 (調査中)

幽霊 sink-input 蓄積とは別の、`unix:/mnt/wslg/PulseServer` に対する**散発的な応答劣化**。原因を特定しきれていない。

### 症状

- `pactl -s unix:/mnt/wslg/PulseServer info` が 3 秒 timeout する
- `pactl list sinks` 等も同様にストール
- `ss -x` で `PulseServer N * 0` 形式の half-closed socket が累積
- proxy 経由 (`tcp:localhost:24713`) は同じ WSLg pulseaudio に繋がっているが**影響を受けない**

### 現状のユーザー向け回避策

`voicevox_paplay --loopback` を使う。内部で `PULSE_SERVER=tcp:localhost:24713` に切り替わり proxy 経由になるため、direct の不安定性を完全に回避できる。実測: 5 連続再生で direct に影響ゼロ (Phase 1 test)。

根治が必要な場合は前章の回復手順 (WSLg pulseaudio kill → WSLGd が respawn → proxy restart) を実施。

### これまでに検証した仮説と結果

| 仮説 | 検証 | 結論 |
|---|---|---|
| `pa.flush()` が原因 | 削除前後で比較 | **部分的に正解**。`pa_simple_flush` は tunnel-sink 経由で 12 秒以上かかり、サーバ状態を悪化させる。commit `f90daad` で削除済 |
| `drain` 契約が原因 | drain を一切呼ばない設計に | `f90daad` で drain 廃止済。幽霊は作られないが direct 劣化は残る |
| `play_wav_pulse` の pulse 操作が原因 | pure Python 合成 (pulse 操作なし) でも劣化する場面あり | **不成立**。voicevox_paplay の pulse 操作と無関係に劣化する |
| voicevox_core / ONNX が原因 | `import voicevox_core` だけ、`synth.synthesis()` だけを実行 | **不成立**。純粋な合成では劣化しない |
| `_shutdown` パス (中断時) 固有 | 正常完了 (E3) でも direct が劣化する場面を確認 | **部分的に正解**だが唯一の原因ではない |
| 時間経過 / バックグラウンド | 操作 0 のまま 16 秒観察しても回復せず、セッション間ギャップで突然劣化することもある | **可能性あり** (バックグラウンドイベント？) |

### 悪循環 (観測済)

1. 何らかの要因で direct が劣化開始
2. `pactl info` など client 接続が timeout する
3. timeout した client が残した半閉じ socket (`PulseServer N * 0`) が WSLg 側に累積
4. 累積した半閉じ socket がさらに劣化を悪化させる

→ **劣化した direct に対して `pactl` で観察すること自体が状態を悪化させる**。調査時は最小限の測定にとどめること。

### 次回調査のために収集すべき情報

劣化が再発したとき、**最初に以下を取得**してから何かを操作する:

```bash
# (1) いつから劣化しているか: WSLg pulseaudio の uptime
stat /mnt/wslg/PulseServer | grep -E "Modify|Birth"
ps -eo pid,etime,cmd | grep -v grep | grep pulseaudio

# (2) socket 状態: 半閉じ socket の数と inode
ss -x | awk 'NR==1 || /Pulse/'

# (3) WSLg 側 pulseaudio のログ (上書きされてなければ)
tail -30 /mnt/wslg/pulseaudio.log

# (4) proxy 側は健全か (direct だけの問題か全体か)
timeout 3 pactl -s tcp:localhost:24713 info
timeout 3 pactl -s tcp:localhost:24713 list sinks | grep -E "Name|State|Latency"

# (5) direct への応答時間 (測定 1 回のみ。繰り返すと劣化を加速する)
t0=$(date +%s.%N); timeout 3 pactl -s unix:/mnt/wslg/PulseServer info > /dev/null 2>&1
echo "direct info: $(awk "BEGIN{printf \"%.3f\", $(date +%s.%N) - $t0}")s"

# (6) Windows 側 RDP audio 消費が詰まっていないか (RDPSink Recv-Q)
ss -x | awk '/PulseAudioRDPSink/{print "RDPSink Recv-Q:", $3}'
```

### 調査の切り口候補

- **proxy の `module-tunnel-sink-new`** の tunnel 接続が劣化の触媒になっていないか。proxy を停止した状態で direct に client を繋いで劣化するか観察
- **Windows 側の RDP audio 消費** が停滞すると RDPSink の Recv-Q が伸びる。この停滞が WSLg pulseaudio 側の別経路 (PulseServer) の応答性にも影響している可能性
- **WSLg pulseaudio のログレベルを上げて再起動**できれば、どの操作でサーバが block しているか特定できる (ただし WSLg system distro 側の config 変更が必要)
- **半閉じ socket** を作る client は誰か。WSLg 側の sshd / dbus / weston などが短命 pulse 接続をしていないか特定する

### 関連 commit (参考)

- `1c5813d` TROUBLE-SHOOTING.md 追加 (幽霊 sink-input 回復手順)
- `c51ef78` drain 廃止 + get_latency-based tail
- `5d279c3` tail を wall-clock sleep に戻す
- `f90daad` `pa.flush()` 廃止
- `a482608` `--loopback` オプション追加
