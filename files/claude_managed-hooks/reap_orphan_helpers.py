#!/usr/bin/env python3
"""Best-effort Claude Code hook that registers session liveness tokens and reaps abandoned helper process subtrees from sessions proven dead."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import signal
import sys
import time

REG_DIR = os.path.expanduser("~/.claude/hooks/state/orphan_reaper/sessions")
LOCK = os.path.expanduser("~/.claude/hooks/state/orphan_reaper/lock")
CODEX_MARKER = "/.claude/plugins/cache/openai-codex"
CLASS_B_MARKERS = (
    "agent-browser",
    "@playwright/mcp",
    "playwright-mcp",
    "codegraph serve --mcp",
)
TERM_WAIT_SECONDS = 2.0


def _proc_path(pid: int, name: str) -> str:
    return os.path.join("/proc", str(pid), name)


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _read_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _parse_stat_fields(pid: int) -> list[str] | None:
    data = _read_text(_proc_path(pid, "stat"))
    if not data:
        return None
    close = data.rfind(")")
    if close < 0:
        return None
    return data[close + 1 :].strip().split()


def read_ppid(pid: int) -> int | None:
    try:
        fields = _parse_stat_fields(pid)
        return int(fields[1]) if fields and len(fields) > 1 else None
    except (OSError, ValueError):
        return None


def read_starttime(pid: int) -> str | None:
    try:
        fields = _parse_stat_fields(pid)
        return fields[19] if fields and len(fields) > 19 else None
    except (OSError, ValueError):
        return None


def read_cmdline(pid: int) -> str | None:
    data = _read_bytes(_proc_path(pid, "cmdline"))
    if data is None:
        return None
    parts = [part.decode("utf-8", "replace") for part in data.split(b"\0") if part]
    return " ".join(parts)


def read_euid(pid: int) -> int | None:
    data = _read_text(_proc_path(pid, "status"))
    if data is None:
        return None
    try:
        for line in data.splitlines():
            if line.startswith("Uid:"):
                values = line.split()[1:]
                return int(values[1]) if len(values) > 1 else None
    except (OSError, ValueError):
        return None
    return None


def read_env_value(pid: int, key: str) -> str | None:
    data = _read_bytes(_proc_path(pid, "environ"))
    if data is None:
        return None
    prefix = (key + "=").encode()
    for item in data.split(b"\0"):
        if item.startswith(prefix):
            return item[len(prefix) :].decode("utf-8", "replace")
    return ""


def read_comm(pid: int) -> str | None:
    data = _read_text(_proc_path(pid, "comm"))
    return data.strip() if data is not None else None


def iter_proc_pids() -> list[int]:
    try:
        names = os.listdir("/proc")
    except OSError:
        return []
    pids = []
    for name in names:
        if name.isdigit():
            try:
                pids.append(int(name))
            except ValueError:
                pass
    return pids


def session_state(session_id: str) -> str:
    if not session_id:
        return "unknown"
    try:
        with open(os.path.join(REG_DIR, session_id), encoding="utf-8") as handle:
            content = handle.read().strip()
    except OSError:
        return "unknown"
    if not content:
        return "unknown"
    try:
        pid_s, recorded_starttime = content.split()
        pid = int(pid_s)
    except ValueError:
        return "unknown"
    current_starttime = read_starttime(pid)
    if current_starttime is None:
        return "dead"
    return "alive" if current_starttime == recorded_starttime else "dead"


def _atomic_write(path: str, content: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, "." + os.path.basename(path) + "." + str(os.getpid()))
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.replace(tmp, path)


def _looks_like_claude(pid: int) -> bool:
    if read_comm(pid) == "claude":
        return True
    cmdline = read_cmdline(pid) or ""
    first = cmdline.split(" ", 1)[0]
    return os.path.basename(first) == "claude"


def find_claude_ancestor(start_pid: int) -> int | None:
    seen = set()
    pid = start_pid
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        if _looks_like_claude(pid):
            return pid
        next_pid = read_ppid(pid)
        if next_pid is None:
            return None
        pid = next_pid
    return None


def register_session(session_id: str) -> None:
    if not session_id:
        return
    claude_pid = find_claude_ancestor(os.getppid())
    if claude_pid is None:
        return
    starttime = read_starttime(claude_pid)
    if starttime is None:
        return
    _atomic_write(os.path.join(REG_DIR, session_id), f"{claude_pid} {starttime}")


def remove_session(session_id: str) -> None:
    if not session_id:
        return
    try:
        os.remove(os.path.join(REG_DIR, session_id))
    except OSError:
        pass


def _is_own_process_group(pid: int) -> bool:
    try:
        return os.getpgid(pid) == os.getpgrp()
    except OSError:
        return True


def _is_killable(pid: int) -> bool:
    return pid != os.getpid() and not _is_own_process_group(pid)


def _is_class_a(
    ppid: int | None, cmdline: str | None, pid_euid: int | None, euid: int
) -> bool:
    return ppid == 1 and pid_euid == euid and bool(cmdline and CODEX_MARKER in cmdline)


def _is_class_b(
    ppid: int | None, cmdline: str | None, pid_euid: int | None, euid: int
) -> bool:
    return (
        ppid == 1
        and pid_euid == euid
        and bool(cmdline and any(marker in cmdline for marker in CLASS_B_MARKERS))
    )


def _children_map() -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for pid in iter_proc_pids():
        ppid = read_ppid(pid)
        if ppid is not None:
            children.setdefault(ppid, []).append(pid)
    return children


def gather_subtree(root: int) -> list[int]:
    children = _children_map()
    ordered: list[int] = []
    seen = set()

    def visit(pid: int) -> None:
        if pid in seen:
            return
        seen.add(pid)
        for child in children.get(pid, ()):
            visit(child)
        if _is_killable(pid):
            ordered.append(pid)

    visit(root)
    return ordered


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError as exc:
        return exc.errno == errno.EPERM


def reap_subtree(root: int) -> None:
    targets = gather_subtree(root)
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + TERM_WAIT_SECONDS
    survivors = set(targets)
    while survivors and time.monotonic() < deadline:
        survivors = {pid for pid in survivors if _pid_exists(pid)}
        if survivors:
            time.sleep(0.05)
    for pid in list(survivors):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def prune_registry() -> None:
    try:
        names = os.listdir(REG_DIR)
    except OSError:
        return
    for name in names:
        path = os.path.join(REG_DIR, name)
        if not os.path.isfile(path):
            continue
        if session_state(name) == "dead":
            try:
                os.remove(path)
            except OSError:
                pass


def reap() -> None:
    euid = os.geteuid()
    for pid in iter_proc_pids():
        if pid == os.getpid() or _is_own_process_group(pid):
            continue
        ppid = read_ppid(pid)
        cmdline = read_cmdline(pid)
        pid_euid = read_euid(pid)
        if _is_class_a(ppid, cmdline, pid_euid, euid):
            owner = read_env_value(pid, "CLAUDE_CODE_SESSION_ID")
            if owner and session_state(owner) == "dead":
                reap_subtree(pid)
        elif _is_class_b(ppid, cmdline, pid_euid, euid):
            reap_subtree(pid)
    prune_registry()


def _with_lock(func) -> None:
    handle = None
    locked = False
    try:
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        handle = open(LOCK, "a+", encoding="utf-8")
        deadline = time.monotonic() + 0.25
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as exc:
                if (
                    exc.errno not in (errno.EACCES, errno.EAGAIN)
                    or time.monotonic() >= deadline
                ):
                    break
                time.sleep(0.025)
    except OSError:
        handle = None
    try:
        func()
    finally:
        if handle is not None:
            try:
                if locked:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
            except OSError:
                pass


def handle_event(payload: dict) -> None:
    session_id = str(payload.get("session_id") or "")
    event_name = payload.get("hook_event_name")
    if event_name == "SessionStart":
        register_session(session_id)
        reap()
    elif event_name == "SessionEnd":
        remove_session(session_id)
        reap()


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(payload, dict):
        return
    _with_lock(lambda: handle_event(payload))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
