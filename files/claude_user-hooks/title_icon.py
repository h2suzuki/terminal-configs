#!/usr/bin/env python3
"""状態別ターミナルタブアイコン (遷移時のみ更新・/rename 追従・終了時に既定タイトルへ復元)."""

import getpass
import json
import os
import platform
import sys
from pathlib import Path

ICON = {"run": "", "wait": "💬", "ask": "❓", "perm": "⚠️"}  # この行で差替可
BELL = {"ask", "perm"}  # 突入時に BEL を鳴らす状態 (Windows Terminal のタブ点滅用)
BG_RUN_TYPES = {"workflow", "subagent"}  # 稼働中とみなす background_tasks の type
STATE_DIR = Path.home() / ".claude" / "title-icon-state"
SESS_DIR = Path.home() / ".claude" / "sessions"
SUMMARY_LEN = 24
SYNTHETIC = (
    "<task-notification>",
    "This session is being continued",
)  # 合成再入は summary 化しない


def parent_pid(pid):
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def session_entry(sid):
    """claude 本体の sessions/<pid>.json を親系譜で解決 (fallback: mtime 順 scan)。"""
    p = os.getppid()
    for _ in range(5):
        if p <= 1:
            break
        try:
            d = json.loads((SESS_DIR / f"{p}.json").read_text())
            if d.get("sessionId") == sid:
                return d
        except (OSError, ValueError):
            pass
        p = parent_pid(p)
    try:
        files = sorted(
            SESS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True
        )
    except OSError:
        return None
    for f in files[:60]:
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if d.get("sessionId") == sid:
            return d
    return None


def resolve_title(sid, summary, cwd):
    """優先度: /rename・AI 命名 > 直近プロンプト要約 > derived 名 > cwd basename。"""
    entry = session_entry(sid) or {}
    name = entry.get("name")
    # 2.1.199 実測: /rename は name を書き nameSource を消す (derived 時のみ明示)
    if name and entry.get("nameSource") != "derived":
        return name
    return summary or name or os.path.basename(cwd or "") or "claude"


def summarize(prompt):
    s = " ".join(
        "".join(ch for ch in prompt if ch.isprintable() or ch.isspace()).split()
    )
    return s[:SUMMARY_LEN] + "…" if len(s) > SUMMARY_LEN else s


def load_state(path):
    try:
        d = json.loads(path.read_text())
        return {"state": d.get("state", ""), "summary": d.get("summary", "")}
    except (OSError, ValueError):
        return {"state": "", "summary": ""}


def default_title(cwd):
    """Ubuntu 既定 PS1 相当の `user@host: cwd` タイトル (WT の title stack 未実装対策)。"""
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = os.environ.get("USER", "")
    home = str(Path.home())
    if cwd and (cwd == home or cwd.startswith(home + os.sep)):
        cwd_short = "~" + cwd[len(home) :]
    else:
        cwd_short = cwd or ""
    return f"{user}@{platform.node()}: {cwd_short}"


def emit(icon, title, bell):
    seq = f"\x1b]0;{icon + ' ' if icon else ''}{title}\x07"
    if bell:
        seq += "\x07"
    print(json.dumps({"terminalSequence": seq}))


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    ev = data.get("hook_event_name", "")
    sid = data.get("session_id", "")
    state_file = STATE_DIR / (sid or "default")
    st = load_state(state_file)

    if ev == "SessionEnd":
        if data.get("reason") != "clear":  # clear は同一 process 継続ゆえ復元しない
            title = default_title(data.get("cwd"))
            seq = f"\x1b]0;{title}\x07"
            print(json.dumps({"terminalSequence": seq}))
            try:
                state_file.unlink(missing_ok=True)
            except OSError:
                pass
        return

    new = None
    if ev == "SessionStart":
        new = "wait"
    elif ev == "UserPromptSubmit":
        prompt = data.get("prompt") or ""
        if prompt and not prompt.lstrip().startswith(SYNTHETIC):
            st["summary"] = summarize(prompt)
        new = "run"
    elif ev == "Stop":
        tasks = data.get("background_tasks")
        tasks = tasks if isinstance(tasks, list) else []
        running = any(
            isinstance(t, dict) and t.get("type") in BG_RUN_TYPES for t in tasks
        )
        new = "run" if running else "wait"
    elif ev == "PermissionRequest":
        new = "perm"
    elif ev == "PermissionDenied":
        new = "run"
    elif ev in ("PreToolUse", "PostToolUse"):
        if data.get("agent_id"):  # subagent の tool イベントでは動かさない
            return
        if ev == "PreToolUse" and data.get("tool_name") == "AskUserQuestion":
            new = "ask"
        elif st["state"] != "run":  # 回答・承認・stop-feedback 続行の復帰
            new = "run"

    if new is None or (new == st["state"] and ev != "UserPromptSubmit"):
        return
    bell = new in BELL and new != st["state"]
    st["state"] = new
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(st))
    except OSError:
        pass
    emit(ICON[new], resolve_title(sid, st["summary"], data.get("cwd")), bell)


main()
