#!/usr/bin/env python3
"""Minimal skill reminder gate for Claude Code tool hooks."""

from __future__ import annotations

import json
import math
import os
import shlex
import sys
import tempfile
import time


SKILL_WINDOW_SECONDS = 1800
DENY_PREFIX = "skill-reminder-gate: "
STATE_MISSING = object()

CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".sh",
        ".bash",
        ".zsh",
        ".rb",
        ".ts",
        ".js",
        ".mjs",
        ".rs",
        ".go",
        ".c",
        ".h",
        ".cpp",
        ".java",
        ".kt",
        ".swift",
        ".lua",
        ".pl",
    }
)
GATED_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def _state_root() -> str | None:
    override = os.environ.get("SKILL_REMINDER_STATE_DIR")
    if override:
        return override
    home = os.environ.get("HOME")
    if not home:
        return None
    return os.path.join(home, ".claude", "hooks", "state", "skill_reminder")


STATE_ROOT = _state_root()


def _state_path(payload: dict) -> str | None:
    session_id = payload.get("session_id")
    if STATE_ROOT is None or not isinstance(session_id, str) or not session_id:
        return None
    if "/" in session_id or ".." in session_id:
        return None
    return os.path.join(STATE_ROOT, "active", session_id, "main.json")


def _load_state(path: str) -> object:
    try:
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict):
            return None
        for skill, record in state.items():
            if not isinstance(skill, str) or not isinstance(record, dict):
                return None
            record_ts = record.get("ts")
            if (
                isinstance(record_ts, bool)
                or not isinstance(record_ts, (int, float))
                or not math.isfinite(record_ts)
                or "prompt_id" not in record
            ):
                return None
        return state
    except FileNotFoundError:
        return STATE_MISSING
    except Exception:
        return None  # corrupt / unreadable state -> fail open


def _has_agent(payload: dict) -> bool:
    value = payload.get("agent_id")
    return isinstance(value, str) and bool(value)


def _record_is_active(record: dict, payload: dict, now: float) -> bool:
    record_ts = record["ts"]
    same_prompt = "prompt_id" in payload and record["prompt_id"] == payload["prompt_id"]
    fresh = now - record_ts <= SKILL_WINDOW_SECONDS
    return same_prompt or fresh


def _deny_reason(required: set[str], label: str, payload: dict) -> str | None:
    if not required:
        return None
    path = _state_path(payload)
    if path is None:
        return None
    state = _load_state(path)
    if state is None:
        return None
    if state is STATE_MISSING:
        missing = set(required)
    elif isinstance(state, dict):
        now = time.time()
        missing = {
            skill
            for skill in required
            if not isinstance(state.get(skill), dict)
            or not _record_is_active(state[skill], payload, now)
        }
    else:
        return None
    if not missing:
        return None
    return (
        f"{DENY_PREFIX}{label}: {' '.join(sorted(missing))} を invoke してから書き直せ"
    )


def _contains_anchor(path: str, anchor: str) -> bool:
    if anchor in path:
        return True
    return not path.startswith("/") and anchor in "/" + path


def _is_test_file(name: str, extension: str) -> bool:
    if extension not in {".py", ".ts", ".rb"}:
        return False
    stem = name[: -len(extension)].lower()
    if extension == ".py":
        return stem.startswith("test_") or stem.endswith(("_test", ".test"))
    if extension == ".ts":
        return stem.endswith((".test", ".spec"))
    return stem.endswith(".spec")


def _required_for_path(path: str) -> set[str]:
    if _contains_anchor(path, "/var/lib/claude-rag-memory/"):
        return set()

    name = os.path.basename(path)
    if name == "todos.md":
        return {"writing-todos"}
    if name == "handoff.md" or name.endswith(("-handoff.md", "_handoff.md")):
        return {"handoff"}

    required: set[str] = set()
    if (
        name == "SKILL.md"
        or _contains_anchor(path, "/files/claude_managed-hooks/")
        or _contains_anchor(path, "/etc/claude-code/hooks/")
    ):
        required.add("writing-skills")

    ext = os.path.splitext(name)[1].lower()
    if ext not in CODE_EXTENSIONS:
        return required

    required.add("writing-code")
    if ext == ".py":
        required.add("writing-python")
    elif ext in {".sh", ".bash", ".zsh"}:
        required.add("writing-bash")

    if _is_test_file(name, ext) or any(
        _contains_anchor(path, anchor) for anchor in ("/tests/", "/test/", "/spec/")
    ):
        required.add("writing-tests")
    return required


def _gate_reason(payload: dict) -> str | None:
    if _has_agent(payload) or payload.get("tool_name") not in GATED_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    key = "file_path" if "file_path" in tool_input else "notebook_path"
    path_value = tool_input.get(key)
    if not isinstance(path_value, str) or not path_value:
        return None
    if os.path.isabs(path_value):
        path = os.path.realpath(path_value)
    else:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            return None
        path = os.path.realpath(os.path.join(cwd, path_value))
    return _deny_reason(_required_for_path(path), path, payload)


def _write_state(path: str, state: dict) -> None:
    directory = os.path.dirname(path)
    temporary: str | None = None
    descriptor: int | None = None
    try:
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".main-", dir=directory)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
        temporary = None
    except Exception:
        pass
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _record_succeeded(response: object) -> bool:
    if not isinstance(response, dict):
        return True
    if response.get("is_error") is True:
        return False
    if response.get("error"):
        return False
    if response.get("success") is False:
        return False
    return response.get("status") not in {"error", "failed", "failure"}


def _record_skill(payload: dict) -> None:
    if (
        _has_agent(payload)
        or payload.get("hook_event_name") != "PostToolUse"
        or payload.get("tool_name") != "Skill"
    ):
        return
    tool_input = payload.get("tool_input")
    skill = tool_input.get("skill") if isinstance(tool_input, dict) else None
    session_id = payload.get("session_id")
    if not isinstance(skill, str) or not skill:
        return
    if not isinstance(session_id, str) or not session_id:
        return
    if not _record_succeeded(payload.get("tool_response")):
        return
    path = _state_path(payload)
    if path is None:
        return
    for _ in range(5):
        state = _load_state(path)
        if state is STATE_MISSING or state is None:
            state = {}
        elif isinstance(state, dict):
            state = dict(state)
        else:
            state = {}
        observed_keys = set(state)
        state[skill] = {"ts": time.time(), "prompt_id": payload.get("prompt_id")}
        _write_state(path, state)
        time.sleep(0.01)
        latest = _load_state(path)
        if isinstance(latest, dict) and observed_keys | {skill} <= set(latest):
            return


COMMAND_BREAKS = frozenset(
    {";", "&&", "||", "|", "&", "(", ")", "{", "}", ">", ">>", "<", "<<"}
)
NON_LITERAL_CHARS = frozenset("*?[]$`")


def _command_segments(command: str) -> list[list[str]]:
    command = command.replace("\\\n", " ")
    segments: list[list[str]] = []
    for line in command.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|(){}<>")
        lexer.whitespace_split = True
        current: list[str] = []
        for token in lexer:
            if token in COMMAND_BREAKS:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(token)
        if current:
            segments.append(current)
    return segments


def _commit_pathspec_requirements(command: str) -> tuple[list[str], set[str]]:
    labels: list[str] = []
    required: set[str] = set()
    seen: set[str] = set()
    for segment in _command_segments(command):
        if not segment or segment[0] != "git":
            continue
        commit_index = 1
        while commit_index < len(segment):
            token = segment[commit_index]
            if token in {"-C", "-c"}:
                commit_index += 2
            elif token.startswith("--") and token != "--":
                commit_index += 1
            else:
                break
        if commit_index >= len(segment) or segment[commit_index] != "commit":
            continue
        try:
            separator = segment.index("--", commit_index + 1)
        except ValueError:
            continue
        for token in segment[separator + 1 :]:
            if not token or any(char in token for char in NON_LITERAL_CHARS):
                continue
            demands = _required_for_path(token)
            if not demands:
                continue
            required.update(demands)
            if token not in seen:
                seen.add(token)
                labels.append(token)
    return labels, required


def _commit_gate_reason(payload: dict) -> str | None:
    if _has_agent(payload) or payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return None

    try:
        from check_uncommitted_at_handoff import writes_handoff_doc
    except ImportError:
        return None
    if writes_handoff_doc(command):
        return _deny_reason({"handoff"}, "handoff doc", payload)

    labels, required = _commit_pathspec_requirements(command)
    if not labels:
        return None
    return _deny_reason(required, ", ".join(labels), payload)


def _emit_deny(reason: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")


def _dispatch(mode: str, payload: dict) -> str | None:
    if mode == "gate":
        return _gate_reason(payload)
    if mode == "commit-gate":
        return _commit_gate_reason(payload)
    if mode == "record-skill":
        _record_skill(payload)
    return None


def main() -> int:
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else ""
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        reason = _dispatch(mode, payload)
        if reason is not None:
            _emit_deny(reason)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
