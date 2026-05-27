# Hook Template

Claude Code hook の典型 patterns。 hook は **settings.json への entry 登録** + **実行可能 script** の 2 要素で成立する。

## 1. settings.json hook entry

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "/absolute/path/to/hook-script" }
        ]
      }
    ]
  }
}
```

### Event 一覧 (主要)

| Event | Trigger | 典型 use |
|-------|---------|----------|
| `PreToolUse` | tool 実行前 | gating (deny / require additional check) |
| `PostToolUse` | tool 実行後 | log / cleanup |
| `UserPromptSubmit` | user prompt 送信時 | inject context |
| `Notification` | LLM が user 注意要求時 | external notify (sound / push) |
| `Stop` | turn 終了時 | summary / external notify |
| `SubagentStart` / `SubagentStop` | subagent fire / 終了 | log / notify |
| `PreCompact` | compaction 直前 | external notify |
| `SessionStart` / `SessionEnd` | session lifecycle | init / cleanup |
| `ConfigChange` | settings reload 時 | reload-aware action |

matcher は tool 名 (e.g. `Bash`, `Edit`) / regex / 空 (全 tool match)。

## 2. Python hook script skeleton

```python
#!/usr/bin/env python3
"""<one-line purpose>. <when fires>."""
import json
import sys

def main() -> int:
    payload = json.load(sys.stdin)  # hook event JSON
    # 例: PreToolUse:Bash の場合 payload["tool_input"]["command"] にコマンド文字列
    cmd = payload.get("tool_input", {}).get("command", "")

    if should_block(cmd):
        # exit 2 + stderr に reason を書くと user に表示される
        print(f"hook-name: <action-required + why>", file=sys.stderr)
        return 2

    return 0  # 0 = allow, 1 = non-blocking warning, 2 = block

def should_block(cmd: str) -> bool:
    return False  # TODO: gating logic

if __name__ == "__main__":
    sys.exit(main())
```

## 3. Bash hook script skeleton

```bash
#!/bin/bash
# <one-line purpose>. <when fires>.
set -euo pipefail

INPUT=$(cat)  # stdin から JSON payload
EVENT=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty')

case "$EVENT" in
  PreToolUse)
    # 例: tool_input から特定 pattern を deny
    CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
    if printf '%s' "$CMD" | grep -qE '<bad-pattern>'; then
      echo "hook-name: <action-required + why>" >&2
      exit 2
    fi
    ;;
esac

exit 0
```

## 4. Exit code convention

| exit | 効果 |
|------|------|
| `0` | allow / silent pass |
| `1` | non-blocking warning (stdout / stderr message を user に提示、 tool は実行) |
| `2` | **block** — tool 実行を中止、 stderr の message を user に提示 |

## 5. Writing convention (deny reason wording)

hook が deny する時の reason 文面:

- **hook を変更主体に誤読させない**: hook は judge であって作業主体ではない。 「hook が X を取り消した」 ではなく「Edit 前に Read が必要」 と書く
- **corrective 行動を直接書き下す**: 「verify-after-edit して」 ではなく「該当 region を Read で読み直してください — 反映確認も同時にでき、 次の Edit はそのまま通ります」
- **trim 抑止 comment を残す**: 短くしたくなる文面でも、 reader (LLM 含む) が混乱しないよう冗長性を残す。 trim する人がいたら「あえて長い」 ことを comment で明示

## 6. Deploy

- canonical source: `files/<hook-name>` (本 repo 配下)
- deploy 先 (project の install script で copy):
  - **org-wide**: `/etc/claude-code/hooks/<hook-name>` + `files/claude_managed-settings.json` に hook entry
  - **user-specific**: `~/.claude/hooks/<hook-name>` + `files/claude_user-settings.json` に hook entry
- **両方を同 session 内で同 content に保つ**: deploy 先だけ編集して repo の source を放置すると、 次に repo から再 deploy した時点で改造が静かに消える regression を抱える
