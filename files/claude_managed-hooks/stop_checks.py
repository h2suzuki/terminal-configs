#!/usr/bin/env python3
"""Validate a Claude Stop event against the current turn and local state."""

import datetime
import fcntl
import json
import os
import re
import sys
import unicodedata

TURN_WINDOW_BYTES = 512 * 1024
BACKGROUND_WINDOW_BYTES = 2 * 1024 * 1024
LEDGER_MIN_EDITS = 3
TASK_TOOLS = {"TaskCreate", "TaskUpdate", "TodoWrite"}
EVIDENCE_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch"}
PERSISTENCE_WORDS = ("memory", "skills", "hooks", "CLAUDE.md", "SKILL.md")
DECISION_WORDS = ("決裁", "裁定", "判断待ち", "承認待ち", "要確認")
EXECUTABLE_SUFFIXES = (".py", ".sh", ".mjs", ".js")
UI_SUFFIXES = (".css", ".scss", ".tsx", ".jsx", ".vue", ".svelte", ".html")
DEFAULT_MEMORY_ROOT = "/var/lib/claude-rag-memory/claude-lessons-learned"
PROMPT_PREFIXES = (
    "<task-notification>",
    "<system-reminder>",
    "<local-command",
    "Skill /",
    "Stop hook feedback",
)
CONTINUATION_ENDINGS = (
    "継続します",
    "再開します",
    "進めます",
    "進みます",
    "続けます",
    "着手します",
    "実施します",
    "実装します",
    "取り掛かります",
    "対応します",
    "調整します",
    "やります",
    "修正します",
    "削除します",
    "追加します",
    "作成します",
    "変更します",
    "反映します",
    "統合します",
    "置換します",
    "コミットします",
    "commit します",
    "デプロイします",
    "deploy します",
    "始めます",
    "報告します",
    "提示します",
    "検証します",
    "直します",
    "自走を続け",
    "作業を続け",
)
QUESTION_ENDINGS = ("?", "？", "ますか", "ましょうか", "ください", "でしょうか")


def _read_tail(path, limit):
    with open(path, "rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        start = max(0, size - limit)
        stream.seek(start)
        data = stream.read()
    if start and b"\n" in data:
        data = data.split(b"\n", 1)[1]
    return data.decode("utf-8", errors="replace"), size > limit


def _entries(path, limit):
    text, truncated = _read_tail(path, limit)
    result = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(item, dict):
            result.append(item)
    return result, truncated


def _user_text(entry):
    if entry.get("type") != "user":
        return ""
    message = entry.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _is_boundary(entry):
    text = _user_text(entry)
    return bool(text) and not text.startswith(PROMPT_PREFIXES)


def _assistant_blocks(entry):
    if entry.get("type") != "assistant":
        return []
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    return content if isinstance(content, list) else []


def _tool_path(name, data):
    if not isinstance(data, dict):
        return ""
    keys = (
        ("file_path", "path")
        if name in {"Read", "Write", "Edit"}
        else (
            "path",
            "file_path",
        )
    )
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""


def _empty_turn(path=""):
    return {
        "valid": False,
        "transcript_path": path,
        "final_text": "",
        "turn_text": "",
        "tool_names": [],
        "tool_paths": [],
        "edited_paths": [],
        "bash_commands": [],
        "prompt_text": "",
        "prompt_identity": "",
        "has_workflow": False,
        "models": [],
    }


def _turn_funnel(payload):
    path = payload.get("transcript_path")
    if not isinstance(path, str) or not path:
        result = _empty_turn("")
        supplied = payload.get("last_assistant_message")
        result["final_text"] = supplied if isinstance(supplied, str) else ""
        return result
    try:
        entries, _ = _entries(path, TURN_WINDOW_BYTES)
    except OSError:
        result = _empty_turn(path)
        supplied = payload.get("last_assistant_message")
        result["final_text"] = supplied if isinstance(supplied, str) else ""
        return result
    boundary = -1
    for index, entry in enumerate(entries):
        if _is_boundary(entry):
            boundary = index
    if boundary < 0:
        result = _empty_turn(path)
        supplied = payload.get("last_assistant_message")
        result["final_text"] = supplied if isinstance(supplied, str) else ""
        return result
    chosen = entries[boundary:]
    result = _empty_turn(path)
    result["valid"] = True
    prompt_entry = chosen[0]
    result["prompt_text"] = _user_text(prompt_entry)
    identity = prompt_entry.get("uuid") or prompt_entry.get("timestamp")
    result["prompt_identity"] = identity if isinstance(identity, str) else ""
    texts = []
    for entry in chosen:
        user_text = _user_text(entry)
        if "<task-notification>" in user_text:
            result["has_workflow"] = True
        message = entry.get("message")
        if isinstance(message, dict) and isinstance(message.get("model"), str):
            result["models"].append(message["model"])
        if isinstance(message, dict) and isinstance(message.get("content"), list):
            for item in message["content"]:
                if not isinstance(item, dict) or item.get("type") != "tool_result":
                    continue
                body = item.get("content")
                if isinstance(body, str) and "background" in body.lower():
                    texts.append(body)
        for block in _assistant_blocks(entry):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
                continue
            if block.get("type") != "tool_use":
                continue
            name = block.get("name")
            data = block.get("input")
            if not isinstance(name, str):
                continue
            result["tool_names"].append(name)
            path_value = _tool_path(name, data)
            if name == "Skill" and isinstance(data, dict):
                skill = data.get("skill")
                if isinstance(skill, str):
                    result["tool_paths"].append(skill)
            if path_value and name in {"Read", "Grep", "Glob", "Write", "Edit"}:
                result["tool_paths"].append(path_value)
            if path_value and name in {"Write", "Edit"}:
                result["edited_paths"].append(path_value)
            if name == "Bash" and isinstance(data, dict):
                command = data.get("command")
                if isinstance(command, str):
                    result["bash_commands"].append(command)
    supplied = payload.get("last_assistant_message")
    result["final_text"] = (
        supplied if isinstance(supplied, str) else (texts[-1] if texts else "")
    )
    result["turn_text"] = "\n".join(texts)
    return result


def _strip_fences_and_quotes(text):
    text = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"~~~[^\n]*\n.*?~~~", "", text, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines() if not re.match(r"^\s*>", line))


def _strip_code_and_quotes(text):
    text = _strip_fences_and_quotes(text)
    return re.sub(r"`+[^`\n]*`+", "", text)


def _normalized_text(final_text):
    normalized = unicodedata.normalize("NFKC", final_text)
    scan = _strip_code_and_quotes(normalized)
    return normalized, scan


def _line(message_id, observed, repair):
    return f"{message_id}: {observed}。{repair}"


def _safe_family(function, *args):
    try:
        return function(*args)
    except Exception:
        return []


def _task_tool(name):
    return name in TASK_TOOLS or "mytask" in name.lower()


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError, TypeError):
        return None
    return value


def _task_records(payload):
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return []
    records = []
    home = os.environ.get("HOME", "")
    native = os.path.join(home, ".claude", "tasks", session)
    try:
        names = sorted(os.listdir(native))
    except OSError:
        names = []
    for name in names:
        if name.endswith(".json"):
            value = _load_json(os.path.join(native, name))
            if isinstance(value, dict):
                records.append(value)
    roots = []
    for root in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if isinstance(root, str) and root and root not in roots:
            roots.append(root)
    for root in roots:
        value = _load_json(os.path.join(root, "drafts", "tasks", session + ".json"))
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            nested = value.get("tasks")
            if isinstance(nested, list):
                records.extend(item for item in nested if isinstance(item, dict))
            else:
                records.append(value)
    return records


def _task_name(task):
    for key in ("subject", "content", "activeForm", "name", "id"):
        value = task.get(key)
        if isinstance(value, str) and value:
            return value
    return "名称不明"


def _open_tasks(tasks):
    return [
        task
        for task in tasks
        if str(task.get("status", "")).lower() not in {"completed", "cancelled"}
    ]


def _decision_tasks(tasks):
    return [
        task
        for task in _open_tasks(tasks)
        if any(word in _task_name(task) for word in DECISION_WORDS)
    ]


def _wind_down(payload):
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return False
    home = os.environ.get("HOME", "")
    path = os.path.join(home, ".claude", "hooks", "state", "wind_down_signal", session)
    return os.path.isfile(path)


def _sentences(text):
    result = []
    for line in text.splitlines():
        for sentence in re.split(r"[。！？!?]", line):
            sentence = sentence.strip()
            if sentence:
                result.append((sentence, line))
    return result


def _continuation_sentences(scan):
    result = []
    for sentence, line in _sentences(scan):
        candidate = re.sub(r"(?:\s|[（(][^（()）]*[)）]|[^\w])+$", "", sentence)
        if not candidate:
            candidate = re.sub(r"[^\w]+$", "", sentence)  # a fully bracketed sentence
        if not candidate.endswith(CONTINUATION_ENDINGS):
            continue
        if re.match(r"^\s*(?:[-*+]\s|\d+[.)]\s)", line) or "|" in line:
            continue
        result.append((sentence, line))
    return result


def _continuation(turn, scan):
    matches = _continuation_sentences(scan)
    background_ids = re.findall(
        r"(?:background with ID:|background\. Task ID:)\s*([\w.-]+)",
        turn["turn_text"],
        flags=re.IGNORECASE,
    )
    if any(task_id in scan for task_id in background_ids):
        return []
    for sentence, line in matches:
        if re.search(r"必要なら|ご希望であれば|必要であれば", sentence):
            continue
        if "ここで停止" in line and "再開条件" in line:
            continue
        return [
            _line(
                "continuation-claim",
                "未来の遂行宣言を検出",
                "完了した作業だけを報告する",
            )
        ]
    return []


def _done_state(turn, scan):
    done_sentences = [
        sentence
        for sentence, _line_text in _sentences(scan)
        if re.search(r"完了|done|終わりました|済み", sentence, re.IGNORECASE)
    ]
    if not done_sentences:
        return []
    commands = "\n".join(turn["bash_commands"])
    lower_commands = commands.lower()
    failures = []
    checks = (
        (r"\bcommit\b", r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+commit\b", "commit"),
        (r"\bpush\b", r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+push\b", "push"),
        (r"\bmerge\b", r"\bgit\b(?:\s+-{1,2}\S+(?:[ =]\S+)?)*\s+merge\b", "merge"),
    )
    gate_pattern = r"(?:\bruff\b|\bty\b|\btest\b|変異|\blint\b|\bselftest\b|\bgate\b)"
    for sentence in done_sentences:
        for pattern, evidence, label in checks:
            if re.search(pattern, sentence, re.IGNORECASE) and not re.search(
                evidence, commands, re.IGNORECASE
            ):
                failures.append(label)
        gate = re.search(gate_pattern, sentence, re.IGNORECASE)
        if gate and re.search(r"[0-9]|\bOK\b", sentence):
            if gate.group(0).lower() not in lower_commands:
                failures.append("gate")
        if re.search(r"E2E|実機|live|実測", sentence, re.IGNORECASE) and not any(
            re.search(word, lower_commands, re.IGNORECASE)
            for word in ("e2e", "実機", "live", "実測")
        ):
            failures.append("E2E")
    for path in turn["edited_paths"]:
        lower = path.lower()
        if lower.endswith(EXECUTABLE_SUFFIXES) and not any(
            path in command for command in turn["bash_commands"]
        ):
            failures.append(path)
        if lower.endswith(UI_SUFFIXES) and not any(
            "screenshot" in name.lower() for name in turn["tool_names"]
        ):
            failures.append(path)
    if not failures:
        return []
    return [
        _line(
            "done-state-ledger",
            "完了主張の証跡不足: " + ", ".join(dict.fromkeys(failures)),
            "証跡に合う本文へ直す",
        )
    ]


def _tasks_gated_off(turn):
    home = os.environ.get("HOME", "")
    config = _load_json(os.path.join(home, ".claude.json"))
    if not isinstance(config, dict):
        return False
    features = config.get("cachedGrowthBookFeatures")
    if not isinstance(features, dict):
        return False
    gate = features.get("tengu_vellum_ash")
    if gate is True:
        return True
    if isinstance(gate, list):
        return not turn["models"] or any(model in gate for model in turn["models"])
    return False


def _task_plan(turn):
    names = turn["tool_names"]
    if not names or _tasks_gated_off(turn):
        return []
    if len(names) <= 2 and not turn["edited_paths"]:
        return []
    first_work = next(
        (index for index, name in enumerate(names) if not _task_tool(name)), None
    )
    if first_work is None:
        return []
    if not any(_task_tool(name) for name in names[:first_work]):
        return [
            _line(
                "task-plan-first",
                "作業 tool より前の Task 更新がない",
                "先に Task を更新する",
            )
        ]
    return []


def _task_drift(turn, scan, tasks):
    edited_paths = turn["edited_paths"]
    heavy_edit = len(edited_paths) >= LEDGER_MIN_EDITS
    work_claim = bool(_continuation_sentences(scan))
    deferral = bool(re.search(r"別タスクに切り出し|今は処置しません", scan))
    if (
        (heavy_edit or work_claim or deferral)
        and not tasks
        and not any(_task_tool(name) for name in turn["tool_names"])
    ):
        return [
            _line("task-ledger-drift", "作業に対応する Task がない", "Task を記録する")
        ]
    return []


def _path_tokens(text):
    pattern = (
        r"/var/lib/claude-rag-memory/[\w./-]+"
        r"|(?<![\w:@/.-])(?:/|\.{0,2}/)?[\w.-]+(?:/[\w.-]+)+\.[A-Za-z][A-Za-z0-9]{0,5}"
    )
    return list(dict.fromkeys(re.findall(pattern, text)))


def _ruling(turn, normalized):
    has_agent = any(name in {"Agent", "Task"} for name in turn["tool_names"])
    if not (has_agent or turn["has_workflow"]):
        return []
    if not re.search(r"妥当|判断|裁定|評価|採用|却下", normalized):
        return []
    paths = _path_tokens(normalized)
    unread = [
        path
        for path in paths
        if not any(path in opened for opened in turn["tool_paths"])
    ]
    if unread:
        return [
            _line(
                "ruling-without-reading",
                "開いていない path: " + ", ".join(unread),
                "開いてから裁定する",
            )
        ]
    return []


def _open_task_block(tasks):
    opened = _open_tasks(tasks)
    if not opened:
        return []
    names = ", ".join(_task_name(task) for task in opened)
    return [
        _line("wind-down-open-tasks", "未完了 Task: " + names, "完了または取消にする")
    ]


def _background_sets(path):
    entries, truncated = _entries(path, BACKGROUND_WINDOW_BYTES)
    launches = set()
    notices = set()
    for entry in entries:
        text = _user_text(entry)
        notices.update(
            re.findall(
                r"<task-notification>.*?<task-id>([^<]+)</task-id>",
                text,
                flags=re.DOTALL,
            )
        )
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            body = block.get("content")
            if not isinstance(body, str):
                continue
            launches.update(
                re.findall(
                    r"(?:Command running in background with ID:|Workflow launched in background\. Task ID:)\s*([\w.-]+)",
                    body,
                )
            )
    return launches, notices, truncated


def _background(payload, turn):
    path = turn["transcript_path"]
    if not path:
        return [], []
    try:
        launches, notices, truncated = _background_sets(path)
    except OSError:
        return [], []
    unreaped = sorted(launches - notices)
    missing_launch = notices - launches
    if truncated or missing_launch:
        if unreaped:
            return [], [
                _line(
                    "wind-down-background-unreaped",
                    "background 状態の一部が窓外"
                    + ("、起動なし通知あり" if missing_launch else ""),
                    "窓内で状態を確認する",
                )
            ]
        return [], []
    if unreaped:
        return [
            _line(
                "wind-down-background-unreaped",
                "未回収 background id: " + ", ".join(unreaped),
                "完了通知を回収する",
            )
        ], []
    return [], []


def _handoff(payload, turn, final_text):
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return []
    candidates = []
    for path in turn["edited_paths"]:
        normalized_path = path.replace("\\", "/")
        base = os.path.basename(path).lower()
        if (base.endswith(".md") and "handoff" in base) or "/docs/handoff/" in (
            "/" + normalized_path.lstrip("/")
        ):
            candidates.append(path)
    missing = []
    for path in candidates:
        if session in final_text:
            continue
        actual = path
        if not os.path.isabs(actual):
            actual = os.path.join(str(payload.get("cwd", "")), actual)
        try:
            with open(actual, encoding="utf-8") as stream:
                body = stream.read()
        except OSError:
            body = ""
        if session not in body:
            missing.append(path)
    if missing:
        return [
            _line(
                "handoff-doc-without-marker",
                "session marker がない: " + ", ".join(missing),
                "full session id を記載する",
            )
        ]
    return []


def _persistence_edit(turn):
    return any(
        any(word.lower() in path.lower() for word in PERSISTENCE_WORDS)
        for path in turn["edited_paths"]
    )


def _self_report(turn, scan, paired=True):
    lines = []
    meta_pattern = (
        r"省略(?:は)?しません|省略(?:は)?控えます|触りません|触らないでおきます|"
        r"(?:には|は)触れません|mock ?しません|ダミー(?:は)?入れません|"
        r"(?:再)?催促(?:は)?しません|推測で.{0,10}書きません|"
        r"想像で.{0,10}埋めません|実行しません|判断(?:は)?保留します|"
        r"(?:rule|scope) ?(?:に従って|通り).{0,20}(?:控えます|触れません)"
    )
    if re.search(meta_pattern, scan, re.IGNORECASE):
        lines.append(
            _line(
                "self-report-honesty",
                "規則1 不実施の meta-announce",
                "実施結果だけを書く",
            )
        )
    if paired and re.search(r"反省|以後気をつけ", scan) and not _persistence_edit(turn):
        lines.append(
            _line("self-report-honesty", "規則2 内省 phrase", "永続化した対策を示す")
        )
    if (
        paired
        and re.search(r"いつの間に|覚えがない", scan)
        and not any(
            re.search(r"git\s+(?:log|show|diff)\b", command)
            for command in turn["bash_commands"]
        )
    ):
        lines.append(
            _line(
                "self-report-honesty",
                "規則3 自分の作業への驚き",
                "履歴を確認した結果を書く",
            )
        )
    if re.search(r"(?:報告|記述|発話)[^\n。]{0,30}誤解を招く", scan) and not re.search(
        r"(?:label|命名)[^\n。]{0,20}誤解を招く", scan, re.IGNORECASE
    ):
        lines.append(
            _line("self-report-honesty", "規則4 婉曲な自己評価", "誤りを直接記す")
        )
    if re.search(
        r"(?:既存の|reasonable default).{0,60}(?:誤り|ミス|間違)",
        scan,
        re.DOTALL | re.IGNORECASE,
    ):
        lines.append(
            _line("self-report-honesty", "規則5 帰属ぼかし", "自分の判断として記す")
        )
    return lines


def _offload(turn, normalized, scan):
    reasons = []
    question_lines = []
    for line in scan.splitlines():
        stripped = line.strip().rstrip("。！!").strip()
        if stripped.endswith("ください") and re.search(r"かは|かについては", stripped):
            continue  # a topicalized report, not a question to the user
        if stripped.endswith(QUESTION_ENDINGS):
            question_lines.append(stripped)
    questions = "\n".join(question_lines)
    if re.search(r"どちらを先に|どの順で", questions):
        reasons.append("順序質問")
    routing = bool(
        re.search(r"(?:するか|しますか).{0,25}(?:するか|しますか)", questions)
        or re.search(r"A\s*にしますか.{0,20}B\s*にしますか", questions, re.IGNORECASE)
        or re.search(r"どちら(?:にしますか|がよいですか)", questions)
    )
    declared = (
        any(name == "Skill" for name in turn["tool_names"])
        and "declare-and-proceed" in turn["tool_paths"]
    )
    if routing and not declared:
        reasons.append("二択 routing")
    outside_fences = _strip_fences_and_quotes(normalized)
    if re.search(r"`?!`?\s*を付けて実行してください", outside_fences):
        reasons.append("! prefix 実行依頼")
    if reasons:
        return [
            _line(
                "offload-to-user",
                ", ".join(reasons) + "を検出",
                "自律的に判断して進める",
            )
        ]
    return []


def _host_command(normalized):
    if not re.search(r"お手元|ターミナル|実行してください", normalized):
        return []
    fences = re.findall(r"```[^\n]*\n(.*?)```", normalized, re.DOTALL)
    inline_commands = re.findall(
        r"(?<!`)`((?:git|python3|python|ruff|ty|npm|pnpm|yarn)\s+[^`\n]+)`(?!`)",
        normalized,
    )
    bad = any(
        not any(command in body for body in fences) for command in inline_commands
    )
    for body in fences:
        for match in re.finditer(r"(?m)^\s*(?:python3?|bash|sh)\s+([^\s;&|]+)", body):
            argument = match.group(1).strip("'\"")
            if "/" not in argument and not os.path.isabs(argument):
                bad = True
    if bad:
        return [
            _line(
                "host-command-format",
                "手動 command の形式が不十分",
                "独立 fence と root 起点 path に直す",
            )
        ]
    return []


def _claim_without_evidence(turn, scan):
    patterns = (
        r"不明|該当なし|存在しません|できません",
        r"大改造|影響大",
        r"非対話では実行できません",
        r"網羅した|全て確認し",
    )
    if any(re.search(pattern, scan) for pattern in patterns) and not any(
        name in EVIDENCE_TOOLS for name in turn["tool_names"]
    ):
        return [
            _line(
                "claim-without-evidence",
                "根拠 tool のない断定を検出",
                "根拠を確認して本文へ反映する",
            )
        ]
    return []


def _emoji_led(line):
    stripped = line.lstrip()
    if not stripped:
        return False
    code = ord(stripped[0])
    return 0x1F000 <= code <= 0x1FAFF or 0x2500 <= code <= 0x2BFF


def _communication(scan, prompt_text, tasks):
    lines = [line.strip() for line in scan.splitlines() if line.strip()]
    if not lines:
        return []
    final_line = lines[-1]
    reasons = []
    question = final_line.endswith(("?", "？"))
    if not question and not _emoji_led(final_line):
        reasons.append("最終行を絵文字始まりまたは疑問形にする")
    if re.search(r"(?:候補|選択肢)\s*[0-9]+(?![0-9]|\s*(?:件|つ))", scan):
        reasons.append("自己採番参照を解消する")
    decisions = _decision_tasks(tasks)
    if question and not decisions:
        reasons.append("疑問文に対応する decision Task を記録する")
    prompt = re.sub(r"^<[^>]+>\s*", "", prompt_text).strip()
    if 0 < len(prompt) <= 20 and decisions:
        reasons.append("短文決裁を decision Task に反映する")
    if question and re.search(r"さっきの|先ほどの案", final_line):
        reasons.append("質問を自己完結させる")
    if reasons:
        return ["communication-lint: " + " ".join(reasons)]
    return []


def _front_matter(path):
    try:
        with open(path, encoding="utf-8") as stream:
            body = stream.read()
    except (OSError, UnicodeDecodeError):
        return {}
    if not body.startswith("---\n"):
        return {}
    end = body.find("\n---", 4)
    if end < 0:
        return {}
    values = {}
    for line in body[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _normalize_origin(url):
    """Same slug rule as the memory surface hook: github.com-<owner>-<repo>."""
    text = url.strip()
    head, _, tail = text.partition("://")
    text = tail or head
    first = text.split("/", 1)[0]
    if "@" in first and ":" in first.split("@", 1)[1]:
        text = text.replace(":", "/", 1)
    first = text.split("/", 1)[0]
    if "@" in first:
        text = text.split("@", 1)[1]
    host, _, path = text.partition("/")
    text = (host.lower() + "/" + path).rstrip("/").removesuffix(".git")
    return text.replace("/", "-").replace(":", "-")


def _project_id(cwd):
    if not isinstance(cwd, str) or not cwd:
        return ""
    git = os.path.join(cwd, ".git")
    config = os.path.join(git, "config")
    url = ""
    try:
        if os.path.isfile(git):
            with open(git, encoding="utf-8") as stream:
                gitdir = stream.read().partition("gitdir:")[2].strip()
            if not os.path.isabs(gitdir):
                gitdir = os.path.join(cwd, gitdir)
            config = os.path.join(gitdir.split("/worktrees/")[0], "config")
        with open(config, encoding="utf-8") as stream:
            section = ""
            for line in stream:
                line = line.strip()
                if line.startswith("["):
                    section = line
                elif section == '[remote "origin"]' and line.startswith("url"):
                    url = line.partition("=")[2].strip()
                    break
    except OSError:
        url = ""
    return _normalize_origin(url) if url else cwd.replace("/", "-")


def _memory_entries(root, project_id):
    selected = []
    if not os.path.isdir(root):
        return selected
    scopes = ["org", "user"] + (
        [os.path.join("project", project_id)] if project_id else []
    )
    for scope in scopes:
        base = os.path.join(root, scope)
        if not os.path.isdir(base):
            continue
        for directory, dirs, files in os.walk(base):
            dirs.sort()
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(directory, name)
                fields = _front_matter(path)
                check = fields.get("check", "")
                when = fields.get("when", "")
                if check and "stop" in when.lower():
                    selected.append((check, path))
    return selected


def _waste_line(turn):
    if not re.search(r"無駄|浪費|もったいない", turn["prompt_text"]):
        return ""
    if _persistence_edit(turn):
        return ""
    identity = turn["prompt_identity"]
    path = turn["transcript_path"]
    if not identity or not path:
        return ""
    latch = (
        path[: -len(".jsonl")] + ".turns.waste"
        if path.endswith(".jsonl")
        else path + ".turns.waste"
    )
    try:
        with open(latch, encoding="utf-8") as stream:
            if identity in {line.strip() for line in stream if line.strip()}:
                return ""
    except OSError:
        pass
    return _line(
        "memory-reminder", "prompt に無駄の指摘がある", "永続的な改善へ反映する"
    )


def _record_waste(turn):
    identity = turn["prompt_identity"]
    path = turn["transcript_path"]
    if not identity or not path:
        return
    latch = (
        path[: -len(".jsonl")] + ".turns.waste"
        if path.endswith(".jsonl")
        else path + ".turns.waste"
    )
    try:
        with open(latch, "a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.seek(0)
            seen = {line.strip() for line in stream if line.strip()}
            if identity not in seen:
                stream.write(identity + "\n")
                stream.flush()
    except OSError:
        return


def _memory(payload, turn):
    root = os.environ.get("STOP_CHECKS_MEMORY_ROOT", DEFAULT_MEMORY_ROOT)
    if not os.path.isdir(root):
        return []
    lines = []
    entries = _memory_entries(root, _project_id(payload.get("cwd")))
    if entries:
        details = " ".join(f"{check} ({path})" for check, path in entries)
        lines.append(
            "memory-reminder: "
            + details
            + " 抵触するなら修正してから完了。しなければ何も書かない"
        )
    waste = _waste_line(turn)
    if waste:
        lines.append(waste)
    return lines


def _counter_path(transcript):
    if transcript.endswith(".jsonl"):
        return transcript[: -len(".jsonl")] + ".turns"
    return transcript + ".turns"


def _statusline(payload, fallback_epoch):
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return "-", fallback_epoch
    home = os.environ.get("HOME", "")
    cache_root = os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache")
    path = os.path.join(cache_root, "claude-tui-statusline", session + ".json")
    data = _load_json(path)
    if not isinstance(data, dict):
        return "-", fallback_epoch
    stdin_data = data.get("stdin")
    if isinstance(stdin_data, str):
        try:
            stdin_data = json.loads(stdin_data)
        except (ValueError, TypeError):
            stdin_data = None
    used = None
    if isinstance(stdin_data, dict):
        window = stdin_data.get("context_window")
        if isinstance(window, dict):
            used = window.get("used_percentage")
    label = f"{used:g}%" if isinstance(used, (int, float)) else "-"
    started = data.get("session_started_epoch")
    epoch = int(started) if isinstance(started, (int, float)) else fallback_epoch
    return label, epoch


def _turn_marker(payload, turn):
    transcript = turn["transcript_path"]
    if not transcript:
        return ""
    path = _counter_path(transcript)
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    try:
        with open(path, "a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.seek(0)
            content = stream.read().split()
            previous_count = int(content[0]) if content else 0
            previous_epoch = int(content[1]) if len(content) > 1 else now
            count = previous_count + 1
            stream.seek(0)
            stream.truncate()
            stream.write(f"{count} {now}\n")
            stream.flush()
    except (OSError, ValueError, TypeError):
        return ""
    context, started_epoch = _statusline(payload, previous_epoch)
    elapsed = max(0, now - started_epoch)
    stamp = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat()
    return f"{stamp} / Turn #{count} / Context {context} / 経過 {elapsed} 秒"


def _warn_json(lines):
    body = "\n\n".join(lines)
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": body,
        },
        "systemMessage": body,
    }


def _marker_json(message):
    return {"systemMessage": message}


def _evaluate(payload, turn):
    if not turn["valid"]:
        scan = _normalized_text(turn["final_text"])[1]
        tasks = _task_records(payload)
        blocks = []
        warnings = []
        blocks.extend(_safe_family(_self_report, turn, scan, False))
        warnings.extend(_safe_family(_memory, payload, turn))
        if _wind_down(payload):
            blocks.extend(_safe_family(_open_task_block, tasks))
            background_blocks, background_warnings = _safe_family(
                _background, payload, turn
            ) or ([], [])
            blocks.extend(background_blocks)
            warnings.extend(background_warnings)
        return blocks, warnings
    final_text = turn["final_text"]
    normalized, scan = _normalized_text(final_text)
    tasks = _task_records(payload)
    blocks = []
    warnings = []
    block_calls = (
        (_continuation, (turn, scan)),
        (_done_state, (turn, scan)),
        (_task_plan, (turn,)),
        (_ruling, (turn, normalized)),
        (_self_report, (turn, scan)),
        (_offload, (turn, normalized, scan)),
    )
    for function, args in block_calls:
        blocks.extend(_safe_family(function, *args))
    warnings.extend(_safe_family(_task_drift, turn, scan, tasks))
    if _wind_down(payload):
        blocks.extend(_safe_family(_open_task_block, tasks))
        background_blocks, background_warnings = _safe_family(
            _background, payload, turn
        ) or ([], [])
        blocks.extend(background_blocks)
        warnings.extend(background_warnings)
        blocks.extend(_safe_family(_handoff, payload, turn, final_text))
    warn_calls = (
        (_host_command, (normalized,)),
        (_claim_without_evidence, (turn, scan)),
        (_communication, (scan, turn["prompt_text"], tasks)),
        (_memory, (payload, turn)),
    )
    for function, args in warn_calls:
        warnings.extend(_safe_family(function, *args))
    return blocks, warnings


def _emit(payload, turn, blocks, warnings):
    if blocks:
        if payload.get("stop_hook_active"):
            prefix = "advise-once (block demoted to pass): "
            sys.stderr.write("\n".join(prefix + line for line in blocks) + "\n")
            return 0
        sys.stderr.write("\n".join(blocks) + "\n")
        return 2
    if payload.get("stop_hook_active"):
        return 0  # a continuation Stop ends the turn: no warn, no marker
    if warnings:
        sys.stdout.write(json.dumps(_warn_json(warnings), ensure_ascii=False) + "\n")
        waste_prefix = "memory-reminder: prompt に無駄の指摘がある"
        if any(line.startswith(waste_prefix) for line in warnings):
            _record_waste(turn)
        return 0
    marker = _turn_marker(payload, turn)
    if marker:
        sys.stdout.write(json.dumps(_marker_json(marker), ensure_ascii=False) + "\n")
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception as error:
        sys.stderr.write(f"stop-checks fail-open: {type(error).__name__}\n")
        return 0
    try:
        turn = _turn_funnel(payload)
        blocks, warnings = _evaluate(payload, turn)
        return _emit(payload, turn, blocks, warnings)
    except Exception as error:
        sys.stderr.write(f"stop-checks fail-open: {type(error).__name__}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
