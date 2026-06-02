#!/usr/bin/env python3
"""
Combined Stop hook for org-managed Claude Code:

  meta-announce-silence (enforcement, exit 2):
    「省略しません」「触りません」「mock しません」「催促しません」 系の
    compliance-non-execution 宣言を block。 silent compliance の rule 趣旨に反する
    (rule 遵守を発話で能動的に話題化する自体が rule 違反)。 phrase hit のみで block、
    persistence pairing 不要。

  hollow-claims (enforcement, exit 2):
    「学習しました」「記憶します」「肝に銘じ/留意します」「教訓/反省点として」「反省」
    「申し訳」「次回(は)…気をつけ/注意し」 系の introspective phrase
    は、 同 turn 内に memory subtree / skill dir / hook dir / CLAUDE.md への Write/Edit
    記録が無ければ block。 session reset で虚偽化するため persistence 行動とのペアを
    要求する。

  recognize-own-work (enforcement, exit 2):
    「想定外」「知らなかった」「あれ?」 系の surprise phrase を、 同 turn 内に
    git log / git show / git diff の Bash 呼出が無ければ block。 LLM session 揮発で
    前 session の自作業が unfamiliar に見える錯覚 対策。

  evaluative-terms (enforcement, exit 2):
    「大改造」「影響大」「アーキテクチャ(の)見直し/再設計/刷新」「改造が少ない」 系の
    規模・影響評価語を、 同 turn 内に Read/Grep/Glob/WebSearch/WebFetch が無ければ
    block。 report-by-evidence skill が射程外にした structured-doc (比較表 cell 等)
    への ungrounded 評価語混入を補う。 bare-term match (table cell に述語は付かない
    ため述語 anchor は張らない)。 compound/phrasal な高確度語のみ — 軽微/複雑/
    大変/抜本的/リスクが高い は流文 false-positive が広く除外。

  deferral (warning-only, exit 0):
    「後で対処」「別タスクに切り出」「TODO として」 系 phrase は、 同 turn 内に
    TaskCreate / TaskUpdate / TodoWrite または todos.md への Write/Edit が無ければ
    warn (block しない)。

  claim-without-evidence (warning-only, exit 0):
    「不明」「該当なし」「未確認」 系 phrase は、 同 turn 内に Read / Grep / Glob /
    WebSearch / WebFetch のいずれも使われていなければ warn (verify-before-claim の
    negative side)。

  provide-user-instructions (warning-only, exit 0):
    「お手元で」「手動実行」「以下を実行」 系の manual-execution 文脈がありつつ、 host
    コマンド (sudo cp/install, git push/checkout 等, gh pr, curl/wget+URL, claude
    --bg, deploy-root への cp) が fenced code block の外 (= bare prose) に残れば warn。
    strip_fences で fenced block と inline backtick span を除いた prose に host cmd が
    残る = 未 fence の違反。 skill: 手動実行コマンドは独立 fence に置く・inline backtick
    は実行用でない。 tool pairing 無しの純 text-shape 判定。

  verify-before-claim positive (warning-only, exit 0):
    「網羅した」「全部読んだ」「reasonable default」 系の completeness self-claim を、
    同 turn 内に EVIDENCE_TOOLS (Read/Grep/Glob/WebSearch/WebFetch) が無ければ warn。
    claim-without-evidence (negative side) と pairing 同一・polarity と message のみ別。
    確認済み は meta-text 多数 + Bash-backed 多数で意図的に除外 (ungrounded 確認済み の
    FN は承知)。

  turn-marker (bonus, exit 0 only):
    enforcement が pass した turn 終了時のみ、 per-turn marker (時刻 / Turn #N /
    context size / 当 turn の User Prompt からの経過) を JSON `systemMessage` で
    USER に表示する (Claude には非可視)。 経過は transcript の境界 user entry の
    timestamp 起点 (UserPromptSubmit marker は逆に前回 stop 起点の idle gap を出す)。
    block (exit 2) 時は turn が継続するので非表示。 1 turn の
    exit-0 Stop はちょうど 1 回 — block 無しの turn は clean な Stop が、 block した
    turn は advise-once gate が retry (stop_hook_active=true) を exit 0 に降格させた
    Stop が、 その 1 回。 どちらも marker を 1 回だけ載せる (= counter は turn 毎に
    1 bump)。 この once-per-turn 不変条件は memory_surface.py も同 .turns を読むので
    cross-hook で load-bearing。 完全 fail-open で enforcement の
    exit code に影響しない (= おまけ)。

Stop hook input: JSON via stdin with session_id, transcript_path,
hook_event_name = "Stop".

Transcript format: JSONL。 user / assistant / system / ... の type 列。 user entry は
human prompt なら content が str、 tool_result なら list。 assistant entry は text /
thinking / tool_use blocks の list。

Current-turn boundary: 直近の human-input user entry (content が str の entry) を
boundary とし、 そこ以降の assistant entry を current turn とみなす。 corrupted /
partial transcript の場合は空値を返して fall-broad scan しない。

Exit:
  0: no enforcement triggered, OR a would-be re-block on a stop_hook_active
     retry was demoted to a pass (advise-once). warnings may be emitted on stderr
  2: one of meta-announce-silence / hollow-claims / recognize-own-work /
     evaluative-terms triggered, on the turn's first Stop (stop_hook_active false)

The advise-once gate lives in _run (shared), so it INTENTIONALLY demotes every
block family — not just evaluative — to one-block-per-turn. All four families
fire on their own discussed trigger words, so a turn working on this hook would
otherwise self-block-loop until the harness's 8-block override, freezing the
turn counter. Do NOT narrow the gate to evaluative-only: that reintroduces the
loop for meta-announce / hollow-claims / recognize-own-work.

parse / IO error は fail-open (exit 0) — Stop hook で誤 block して user 作業を
止めないことを優先する。
"""

from __future__ import annotations

import datetime
import fcntl
import json
import os
import re
import sys
import time
import unittest

# --- Pattern: meta-announce-silence (block on hit, no pairing) ---
# 不実施宣言系 — rule 遵守を発話で能動的に話題化する pattern。
META_ANNOUNCE_PATTERNS: list[str] = [
    # 省略系
    r"省略(は)?しません",
    r"省略(は)?控えます",
    # 触れません系 (scope 制限)
    r"触りません",
    r"触らないでおきます",
    r"(には|は)触れません",
    # mock / dummy / skip 系
    r"mock\s?しません",
    r"ダミー(は)?入れません",
    # 催促・能動言及禁止系
    r"催促(は)?しません",
    r"再催促(は)?しません",
    # 推測・想像系
    r"推測で.{0,10}書きません",
    r"想像で.{0,10}埋めません",
    r"unverified.{0,10}断定しません",
    # rule 名 + 不実施宣言 (compliance 表明)
    r"rule\s?(に従って|通り).{0,20}控えます",
    r"rule\s?(に従って|通り).{0,20}触れません",
    r"scope\s?に従って.{0,20}触れません",
    # 判断保留宣言
    r"判断(は)?保留します",
]
META_ANNOUNCE_RE = re.compile("|".join(META_ANNOUNCE_PATTERNS), re.IGNORECASE)

# --- Pattern: hollow-claims (block on hit unless persistence in same turn) ---
# introspective phrase — 「学習・記銘」「改善宣言」「留意・省察」「教訓framing」
# 「formal apology」 系統。 否定形 / 中立形 / 記述用法を match させないよう
# conjugation を anchor (反省し → 反省しない を excludable)。 false-positive 抑制:
# 「記憶」 は記述的「X を記憶します」 を を-lookbehind で除外、 次回 は自己矯正動詞
# (気をつけ/注意/改め) に限定し task 動詞 (実装/着手 等) を除外、 「として」 で
# 名詞単体 (反省点の指摘) を除外。 broad phrase は除外。
HOLLOW_CLAIM_PATTERNS: list[str] = [
    # Learning / memorization
    r"学習し(た|ました)",
    r"勉強になっ(た|ました)",
    r"脳に刻ん(だ|でます|でいます)",
    # 記銘宣言「記憶します」系。 記述的「X を記憶します」(hook 等が主語) を弾くため
    # を の直後を除外 (negative lookbehind)。
    r"(?<!を)記憶し(ます|ました|ておきます|ておく)",
    # Keep-in-mind commitment
    r"肝に銘じ(ます|ました|ておきます|ています)",
    r"心に留め(ます|ました|ておきます)",
    r"留意し(ます|ました)",
    # Reform commitment。 次回 は自己矯正動詞限定 + 介在句を許す窓 ({0,15}) で
    # 「次回は…注意します」も拾う。 task 動詞 (実装/着手/確認 等) は入れない。
    r"次回(から)?(は)?[^。\n]{0,15}(気をつけ|注意し(ます|ました)|改め(ます|ました))",
    r"今後(は)?気をつけ",
    r"もう間違え(ない|ません)",
    r"もう繰り返しません",
    # Reflection / retrospection
    r"反省し(た|ました|て(い|ます)|ています)",
    r"振り返(り|って)(ます|ました|みます|みました)",
    # 「教訓として / 反省点として」 の framing。 「として」 で名詞単体を除外。
    r"(教訓|反省点)として",
    # Formal apology
    r"申し訳(ありません|ございません)",
]
HOLLOW_CLAIM_RE = re.compile("|".join(HOLLOW_CLAIM_PATTERNS), re.IGNORECASE)

# --- Pattern: recognize-own-work (block on hit unless git verify in same turn) ---
SURPRISE_PATTERNS: list[str] = [
    r"想定外",
    r"予想外",
    r"思っていなかった",
    r"思ってませんでした",
    r"思ってもいなかった",
    r"知らなかった",
    r"あれ[?？]",
    r"そんな構造に",
    r"そんな構造になっていたっけ",
    r"自分の知らない変更",
]
SURPRISE_RE = re.compile("|".join(SURPRISE_PATTERNS), re.IGNORECASE)

# git log / show / diff の Bash invocation を「実 verify 行動」 とみなす。
GIT_VERIFY_RE = re.compile(r"\bgit\s+(log|show|diff)\b", re.IGNORECASE)

# --- Pattern: evaluative-terms (block on hit unless evidence tool in same turn) ---
# 規模・影響の評価語。 report-by-evidence skill の structured-doc gap (比較表 cell 等
# への ungrounded 評価語混入 — 述語が付かないので skill の文末 judgment trigger が
# 射程外) を補う。 bare-term match (table cell に述語 anchor を張れない)。 同 turn に
# EVIDENCE_TOOLS が無ければ block。 compound/phrasal な高確度語のみ — 軽微/複雑/
# 大変/抜本的/リスクが高い は流文 false-positive が広いため除外。
EVALUATIVE_PATTERNS: list[str] = [
    r"大改造",
    r"影響大(?!き)",  # label 影響大 を拾い、 形容詞 影響大きい/大きく は除外
    r"アーキテクチャ(の)?(見直し|再設計|刷新)",
    r"改造が(少な|すくな)",
]
EVALUATIVE_RE = re.compile("|".join(EVALUATIVE_PATTERNS), re.IGNORECASE)

# --- Pattern: deferral (warning, no block) ---
DEFERRAL_RE = re.compile(
    r"後で(対処|やる|考える)|別タスクに(切り出|分け)|今は(処置|対処)しません|"
    r"後回し|TODO として|次回(に)?(対応|やる)"
)

# --- Pattern: claim-without-evidence (warning, no block) ---
CLAIM_RE = re.compile(
    r"不明|該当なし|存在しません|未確認|わかりません|分かりません"
)

# --- Pattern: provide-user-instructions (warning, no block) ---
# manual-execution 文脈 (MANUAL_EXEC) がありつつ host コマンド (HOST_CMD) が fenced /
# inline-backtick code span の外 (= bare prose) に残る時だけ warn。 skill: 手動実行
# コマンドは独立 fence に置く・inline backtick は readability 用で実行用でない。 ゆえ
# strip_fences で fence と inline span を除いた prose に host cmd が残れば未 fence の
# 違反。 host_cmd は deploy repo の高頻度 verb 限定 (curl/wget は URL を要求し prose
# 言及を除外)。 tool pairing 無しの純 text-shape 判定。 ホスト側 は exec 動詞を必須化
# (裸 match だと当 repo 頻出の中立語「ホスト側」が全 turn で発火するため)。
# 残留: pairing は turn-global ゆえ instruction phrase と無関係な
# 過去形 host cmd が遠隔で同 turn に共存すると稀に発火しうる (観測極小・warn のみ)。
HOST_CMD_PATTERNS: list[str] = [
    r"sudo\s+(cp|install|tee|mv|rm|ln)\b",
    r"\bgit\s+(push|pull|checkout|clone|fetch|reset|rebase|cherry-pick)\b",
    r"\bgit\s+commit\s+-F\b",
    r"\bgh\s+pr\s+(create|merge|checkout)\b",
    r"\bclaude\s+--(bg|print|resume)\b",
    r"\b(curl|wget)\s+(-[A-Za-z]+\s+)?https?://",
    r"\bcp\s+\S+\s+(/etc/claude-code|~/\.claude|/usr/local/bin)\S*",
]
HOST_CMD_RE = re.compile("|".join(HOST_CMD_PATTERNS), re.IGNORECASE)

MANUAL_EXEC_PATTERNS: list[str] = [
    r"お手元で",
    r"ホスト側(の)?(ターミナル|端末|シェル|プロンプト)?(で|から)(実行|叩いて|打って)",
    r"ユーザー(さん)?(の)?手動で",
    r"手動で(実行|叩いて|打って)",
    r"手動実行(して|を行|が必要|してください)",
    r"以下(の)?(コマンド)?を(手動で)?(実行|叩いて|打って)",
    r"以下を(手動で)?実行",
    r"次のコマンドを(手動で)?実行",
    r"(端末|ターミナル)(で|から)(実行|叩いて|打って)",
    r"コピペ(で|して)(実行|叩いて|流して)?",
    r"貼り付けて(実行|流して)",
]
MANUAL_EXEC_RE = re.compile("|".join(MANUAL_EXEC_PATTERNS), re.IGNORECASE)

# --- Pattern: verify-before-claim positive side (warning, no block) ---
# completeness self-claim。 negative side (CLAIM_RE: 不明/該当なし) と pairing 同一
# (EVIDENCE_TOOLS)・polarity と message のみ別。 確認済み は meta-text 多数 +
# Bash-backed 多数 (EVIDENCE_TOOLS 外) ゆえ意図的に除外 (ungrounded 確認済み の FN
# は承知)。 漏れはない/見落としはない の negative 形は CLAIM_RE 側に残し double-warn
# を回避し、 ここは positive completeness のみ。 _check では strip_fences 後の text に
# 当てる (Family A と一貫、 fence/inline 内に quote された claim 語を除外)。 reasonable
# default は assertion anchor (として/を採用/で良い 等) を要求 (裸だと code default の
# 議論「reasonable default を設定するか」で誤発火)。 lexeme は corpus 駆動で意図的に
# tight — 完了/隅々まで/一通り/カバー/チェック済み 等の口語 completeness は broad 化
# すると over-fire するため非対象 (FN 承知)。
POS_CLAIM_PATTERNS: list[str] = [
    r"(全部|全て|すべて)(の(ファイル|file|entry|箇所))?を?(読(んだ|みました|了|み終え)|確認しました)",
    r"網羅(し(た|ました)|的に(確認|読了|チェック|調査)し(た|ました))",
    r"漏れなく(確認|チェック|読)(した|しました)",
    r"(全件|全箇所|全entry)(を)?(確認|チェック|読)(した|しました|済)",
    r"reasonable\s+default\s*(として|を採用|で(良|い)|だと|です)",
]
POS_CLAIM_RE = re.compile("|".join(POS_CLAIM_PATTERNS), re.IGNORECASE)

# --- Persistence path (broader than memory only) ---
# memory subtree / skill dir / hook dir / CLAUDE.md への Write/Edit が hollow-claims の
# pairing を満たす。 「claude_managed-skills/」「claude_managed-hooks/」 等の
# hyphen separated dir 名も拾うため skills?[-_/] / hooks?[-_/] とする。
PERSISTENCE_PATH_RE = re.compile(
    r"(global-memory|/memory/|skills?[-_/]|hooks?[-_/]|CLAUDE\.md$)",
    re.IGNORECASE,
)

# todos.md path (deferral pairing)
TODOS_PATH_RE = re.compile(r"todos\.md$")

# Evidence tools (claim-without-evidence pairing)
EVIDENCE_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch"}

# Task tools (deferral pairing)
TASK_TOOLS = {"TaskCreate", "TaskUpdate", "TodoWrite"}

# Tools whose file_path / notebook_path inputs are recorded for path matching.
PATH_RECORDING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def strip_fences(text: str) -> str:
    # fenced block を先に除去し、 次に inline backtick span を除去 (順序が load-bearing:
    # fence 先除去で inline pass が fence 区切りの裸 ``` を食わない)。 [^`\n] guard で
    # inline pass を行内に限定し改行跨ぎの greedy strip を防ぐ (代償: 改行を含む
    # malformed inline span は strip されず残る — 許容)。
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", " ", text)


def _load_transcript(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _parse_ts(ts) -> float | None:
    """Transcript entry timestamp (ISO8601, trailing 'Z') -> epoch sec, else None."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _current_turn(
    entries: list[dict],
) -> tuple[str, set[str], list[str], bool, float | None]:
    """Return (assistant_text, tool_names, tool_paths, has_git_verify, prompt_epoch).

    Current turn starts after the most recent user entry whose
    `message.content` is a string (= human prompt; tool_result entries
    use a list of content blocks). If no such entry is found, return
    empty values (avoids fail-broad scanning of the whole transcript).

    has_git_verify: True if any Bash tool_use in this turn invokes
    git log / git show / git diff (for recognize-own-work pairing).

    prompt_epoch: the boundary user entry's timestamp (turn-start wall clock).
    """
    start_idx = -1
    prompt_epoch: float | None = None
    for i in range(len(entries) - 1, -1, -1):
        obj = entries[i]
        if obj.get("type") != "user":
            continue
        msg = obj.get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            start_idx = i + 1
            prompt_epoch = _parse_ts(obj.get("timestamp"))
            break
    if start_idx == -1:
        return "", set(), [], False, None

    text_parts: list[str] = []
    tool_names: set[str] = set()
    tool_paths: list[str] = []
    has_git_verify = False

    for obj in entries[start_idx:]:
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(str(block.get("text", "")))
            elif btype == "tool_use":
                name = str(block.get("name", ""))
                if name:
                    tool_names.add(name)
                inp = block.get("input") or {}
                if not isinstance(inp, dict):
                    continue
                if name in PATH_RECORDING_TOOLS:
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if isinstance(fp, str):
                        tool_paths.append(fp)
                if name == "Bash":
                    cmd = inp.get("command", "")
                    if isinstance(cmd, str) and GIT_VERIFY_RE.search(cmd):
                        has_git_verify = True

    return "\n".join(text_parts), tool_names, tool_paths, has_git_verify, prompt_epoch


def _check(
    text: str,
    tool_names: set[str],
    tool_paths: list[str],
    has_git_verify: bool,
) -> tuple[int, list[str], list[str]]:
    """Return (exit_code, warnings, blocking)."""
    warnings: list[str] = []
    blocking: list[str] = []

    # meta-announce-silence (block, no pairing)
    m = META_ANNOUNCE_RE.search(text)
    if m:
        blocking.append(
            f"meta-announce-silence: 「{m.group(0)}」 と発話。 "
            f"不実施宣言自体が rule の silent compliance 趣旨に反する。 "
            f"該当文を delete して再出力してください。 silent / 不実施で示すのが本筋で、 "
            f"「rule に従って〜しません」 と meta-announce すること自体が rule 違反になる。"
        )

    # hollow-claims (block unless persistence-path Write/Edit in turn)
    m = HOLLOW_CLAIM_RE.search(text)
    if m:
        persistence_recorded = any(
            PERSISTENCE_PATH_RE.search(p) for p in tool_paths
        )
        if not persistence_recorded:
            blocking.append(
                f"hollow-claims: 「{m.group(0)}」 と発話したが当ターンで "
                f"memory / skill / hook / CLAUDE.md への Write/Edit が記録されていません "
                f"(System §報告・応答)。 introspective phrase は persistence と "
                f"セットでない時 session reset で虚偽化する。 該当 phrase を delete "
                f"するか、 対応する persistence action を同 response 内で行ってから "
                f"再出力してください。"
            )

    # recognize-own-work (block unless git verify in turn)
    m = SURPRISE_RE.search(text)
    if m and not has_git_verify:
        blocking.append(
            f"recognize-own-work: 「{m.group(0)}」 と surprise 表現を発したが、 "
            f"同 turn 内に git log / git show / git diff の呼出が無い。 LLM session "
            f"は揮発的で前 session の自作業が unfamiliar に見える錯覚が起きる。 "
            f"git log <path> で関連 commit を確認し、 commit message から背景を "
            f"理解した上で 「想定外」 ではなく 「<hash> で <理由> により導入」 と "
            f"事実 framing に書き換えてから再出力してください。"
        )

    # evaluative-terms (block unless evidence tool in turn)
    m = EVALUATIVE_RE.search(text)
    if m and not (tool_names & EVIDENCE_TOOLS):
        blocking.append(
            f"evaluative-term: 「{m.group(0)}」 と規模・影響の評価語を発したが、 "
            f"同 turn 内に Read / Grep / Glob / WebSearch / WebFetch が無い "
            f"(System §報告・応答, report-by-evidence skill)。 評価語は実コード / "
            f"一次資料を読んだ上で、 影響ファイル数・節・呼出元など定量で述べる。 "
            f"該当語を delete するか、 根拠を読んでから 「N file / M 箇所」 等の "
            f"定量表現に書き換えてから再出力してください。"
        )

    # deferral (warning-only)
    m = DEFERRAL_RE.search(text)
    if m:
        todos_via_path = any(TODOS_PATH_RE.search(p) for p in tool_paths)
        todos_via_tool = bool(tool_names & TASK_TOOLS)
        if not (todos_via_path or todos_via_tool):
            warnings.append(
                f"deferral detected: 「{m.group(0)}」 と発話したが当ターンで "
                f"TaskCreate / TaskUpdate / TodoWrite の呼び出しまたは todos.md "
                f"への Write/Edit が記録されていません (System §計画と遂行)。"
            )

    # claim-without-evidence (warning-only)
    m = CLAIM_RE.search(text)
    if m:
        evidence_used = bool(tool_names & EVIDENCE_TOOLS)
        if not evidence_used:
            warnings.append(
                f"claim-without-evidence: 「{m.group(0)}」 と発話したが当ターンで "
                f"Read / Grep / Glob / WebSearch / WebFetch のいずれも使われていません "
                f"(System §報告・応答)。 verify-before-claim skill 参照。"
            )

    # provide-user-instructions (warning-only): manual-exec 文脈 + 未 fence host cmd
    instr = MANUAL_EXEC_RE.search(text)
    if instr:
        cmd = HOST_CMD_RE.search(strip_fences(text))
        if cmd:
            warnings.append(
                f"provide-user-instructions: 手動実行を依頼する文脈 (「{instr.group(0)}」) "
                f"がありますが host コマンド (「{cmd.group(0)}」) が fenced code block の "
                f"外にあります (provide-user-instructions skill)。 独立した fenced code "
                f"block に完全 path で置くと user がそのままコピペ実行できます。 inline "
                f"backtick は readability 用で実行用ではありません。"
            )

    # verify-before-claim positive side (warning-only): completeness claim w/o evidence
    m = POS_CLAIM_RE.search(strip_fences(text))
    if m and not (tool_names & EVIDENCE_TOOLS):
        warnings.append(
            f"verify-before-claim (positive): 「{m.group(0)}」 と網羅・完了の self-claim "
            f"を発したが当ターンで Read / Grep / Glob / WebSearch / WebFetch のいずれも "
            f"使われていません (verify-before-claim skill)。 入口 file 1 本 / INDEX 行だけ "
            f"読んで網羅と framing する LLM regression の典型です。 参照先の body file 群を "
            f"実体まで読んだか self-check し、 未読があれば 「INDEX 上位 N entry のみ確認、 "
            f"残りは未読」 等と scope を明示してください。"
        )

    exit_code = 2 if blocking else 0
    return exit_code, warnings, blocking


def _run(payload: dict) -> tuple[int, float | None]:
    # Returns (exit_code, prompt_epoch) — prompt_epoch feeds the marker gap.
    if not isinstance(payload, dict):
        return 0, None
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0, None
    entries = _load_transcript(transcript_path)
    if not entries:
        return 0, None
    text, tool_names, tool_paths, has_git_verify, prompt_epoch = _current_turn(entries)
    if not text:
        return 0, prompt_epoch
    exit_code, warnings, blocking = _check(text, tool_names, tool_paths, has_git_verify)
    # advise-once: a stop_hook_active retry never re-blocks — demote to pass (see docstring turn-marker / Exit).
    if exit_code == 2 and payload.get("stop_hook_active"):
        for line in blocking:
            sys.stderr.write("advise-once (block demoted to pass): " + line + "\n")
        for line in warnings:
            sys.stderr.write(line + "\n")
        return 0, prompt_epoch
    for line in warnings + blocking:
        sys.stderr.write(line + "\n")
    return exit_code, prompt_epoch


# --- Turn marker (bonus, exit 0 only) ---
# Shown to the USER via systemMessage at turn end, never entering model
# context. Emitted only on exit 0 (see main): a turn has exactly one exit-0
# Stop — the clean end, or the stop_hook_active retry that _run demotes from a
# block to a pass (advise-once) — so it counts once per turn. .turns (flock RMW)
# holds count + last-stop; the marker's gap = now - the turn's prompt epoch.

def _counter_path(payload: dict) -> str | None:
    transcript = payload.get("transcript_path") or ""
    if transcript:
        base = transcript[:-6] if transcript.endswith(".jsonl") else transcript
        return base + ".turns"
    session_id = payload.get("session_id") or ""
    if not session_id:
        return None
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    d = os.path.join(cache, "claude-turn-counter")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, session_id + ".turns")


def _bump(path: str, now: int) -> int:
    # Locked read-modify-write; bump count, persist "count now" (now = last-stop).
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    with os.fdopen(fd, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        parts = f.read().split()
        count = 0
        if parts:
            try:
                count = int(parts[0])
            except ValueError:
                count = 0
        count += 1
        f.seek(0)
        f.truncate()
        f.write("%d %d\n" % (count, now))
    return count


def _statusline(session_id: str) -> dict:
    if not session_id:
        return {}
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(cache, "claude-tui-statusline", session_id + ".json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _context_size(sl: dict):
    cw = (sl.get("stdin") or {}).get("context_window") or {}
    n = cw.get("total_input_tokens")
    if n is None:
        cu = cw.get("current_usage") or {}
        n = (cu.get("input_tokens", 0) + cu.get("cache_read_input_tokens", 0)
             + cu.get("cache_creation_input_tokens", 0)) or None
    return n


def _gap(elapsed: int) -> str:
    if elapsed >= 3600:
        return "%d hr %d min" % (elapsed // 3600, (elapsed % 3600) // 60)
    if elapsed >= 60:
        return "%d min" % (elapsed // 60)
    return "%d sec" % elapsed


def _emit_turn_marker(payload: dict, prompt_epoch: float | None) -> None:
    path = _counter_path(payload)
    if not path:
        return
    now_f = time.time()
    now = int(now_f)
    # _bump still writes last-stop for the next UserPromptSubmit's idle gap.
    count = _bump(path, now)
    sl = _statusline(payload.get("session_id"))
    parts = [time.strftime("%H:%M:%S", time.localtime(now)), "Turn #%d" % count]
    ctx = _context_size(sl)
    if isinstance(ctx, (int, float)) and ctx >= 0:
        parts.append("Context %dK" % round(ctx / 1000.0))
    # now_f keeps sub-second precision for the prompt_epoch comparison.
    if prompt_epoch is not None and 0 < prompt_epoch <= now_f:
        parts.append("(%s passed since the prompt)" % _gap(int(now_f - prompt_epoch)))
    else:
        started = sl.get("session_started_epoch")
        if isinstance(started, (int, float)) and 0 < started <= now_f:
            parts.append("(%s passed since the session start)" % _gap(int(now_f - started)))
    print(json.dumps({"systemMessage": " ".join(parts)}))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        exit_code, prompt_epoch = _run(payload)
    except Exception:
        exit_code, prompt_epoch = 0, None  # fail-open: an enforcement glitch never blocks the turn
    # Bonus: at a genuine turn end (enforcement passed, exit 0) show the
    # per-turn marker. Never on a block (exit 2) — the turn is continuing.
    # Fully isolated: a marker error must not change the enforcement result.
    if exit_code == 0:
        try:
            _emit_turn_marker(payload, prompt_epoch)
        except Exception:
            pass
    return exit_code


class TurnMarkerTest(unittest.TestCase):
    """Turn-marker unit tests. Run: python3 -m unittest stop_checks"""

    TS = "2026-06-02T04:45:24.945Z"

    @staticmethod
    def _user(ts=TS, content="q"):
        return {"type": "user", "timestamp": ts, "message": {"content": content}}

    @staticmethod
    def _asst(text):
        return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}

    @staticmethod
    def _transcript(entries):
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return p

    def _emit(self, prompt_epoch, now, statusline=None):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        payload = {"transcript_path": self._transcript([])}
        with mock.patch.object(time, "time", lambda: now), \
             mock.patch.object(sys.modules[__name__], "_statusline", lambda sid: statusline or {}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                _emit_turn_marker(payload, prompt_epoch)
        out = buf.getvalue().strip()
        return json.loads(out)["systemMessage"] if out else ""

    def test_parse_ts(self):
        want = datetime.datetime.fromisoformat("2026-06-02T04:45:24.945+00:00").timestamp()
        self.assertEqual(_parse_ts(self.TS), want)
        for bad in (None, "", "not-a-date", 123):
            self.assertIsNone(_parse_ts(bad))

    def test_current_turn_returns_prompt_epoch(self):
        text, _n, _p, _g, pe = _current_turn([self._user(), self._asst("done.")])
        self.assertEqual(text, "done.")
        self.assertEqual(pe, _parse_ts(self.TS))
        no_ts = [{"type": "user", "message": {"content": "x"}}, self._asst("y")]
        self.assertIsNone(_current_turn(no_ts)[4])
        tool_only = [{"type": "user", "message": {"content": [{"type": "tool_result"}]}}, self._asst("y")]
        self.assertEqual(_current_turn(tool_only), ("", set(), [], False, None))

    def test_bump_persists_count_and_last_stop(self):
        # .turns = "count last_stop"; last_stop feeds the next UPS idle gap.
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "x.turns")
        for n, want in ((1000, ["1", "1000"]), (2000, ["2", "2000"])):
            self.assertEqual(_bump(p, n), int(want[0]))
            with open(p) as f:
                self.assertEqual(f.read().split(), want)

    def test_marker_shows_since_the_prompt(self):
        msg = self._emit(1_000_000 - 150, 1_000_000)
        self.assertIn("2 min passed since the prompt", msg)
        self.assertIn("Turn #1", msg)

    def test_marker_subsecond_turn_not_dropped(self):
        self.assertIn("0 sec passed since the prompt", self._emit(1000.789, 1000.95))

    def test_marker_fallbacks(self):
        started = self._emit(None, 3_000_000, {"session_started_epoch": 3_000_000 - 600})
        self.assertIn("passed since the session start", started)
        degraded = self._emit(None, 3_000_000, {})
        self.assertNotIn("passed since", degraded)
        self.assertIn("Turn #", degraded)
        self.assertNotIn("since the prompt", self._emit(3_000_999, 3_000_000, {}))

    def test_enforcement_returns_code_and_epoch(self):
        import io
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()):
            blk = self._transcript([self._user(), self._asst("省略しません")])
            self.assertEqual(_run({"transcript_path": blk, "stop_hook_active": False}), (2, _parse_ts(self.TS)))
            self.assertEqual(_run({"transcript_path": blk, "stop_hook_active": True})[0], 0)
            clean = self._transcript([self._user(), self._asst("all good, here is the result.")])
            self.assertEqual(_run({"transcript_path": clean, "stop_hook_active": False})[0], 0)
        self.assertEqual(_run("nope"), (0, None))
        self.assertEqual(_run({}), (0, None))


if __name__ == "__main__":
    sys.exit(main())
