#!/usr/bin/env python3
"""
Combined Stop hook for org-managed Claude Code:

  meta-announce-silence (enforcement, exit 2):
    不実施宣言 (「省略しません」「mock しません」等) を block。 rule 遵守を発話で
    話題化する自体が silent compliance 趣旨に反する。 phrase hit のみ、 pairing 不要。

  hollow-claims (enforcement, exit 2):
    introspective phrase (「学習しました」「肝に銘じ」「反省」「申し訳」等) は、 同
    turn 内に memory / skill / hook / CLAUDE.md への Write/Edit が無ければ block。
    session reset で虚偽化するため persistence とのペアを要求する。

  recognize-own-work (enforcement, exit 2):
    surprise phrase (「想定外」「知らなかった」等) を、 同 turn 内に git log/show/diff の
    Bash 呼出が無ければ block。 LLM session 揮発で自作業が unfamiliar に見える錯覚対策。

  evaluative-terms (enforcement, exit 2):
    規模・影響評価語 (「大改造」「影響大」等) を、 同 turn 内に Read/Grep/Glob/
    WebSearch/WebFetch が無ければ block。 report-by-evidence skill が射程外にした
    structured-doc (比較表 cell 等) への ungrounded 混入を補う。 bare-term match
    (table cell に述語 anchor を張れない)。 compound/phrasal な高確度語のみ — 軽微/
    複雑/大変/抜本的/リスクが高い は流文 false-positive が広く除外。

  known-possible-denial (enforcement, exit 2):
    既知で実行可能と判明済みの操作 (KNOWN_POSSIBLE: 部分 stage / rebase autosquash 等) を
    「できない/不可/無理」 と同一行で断定したら block。 verify させ直すのでなく、 可能と
    分かっている既知 method を実行させる (verify-before-claim の不可断定側)。 pairing 無し
    (op が既知可能ゆえ証拠の有無に関わらず否定が誤り)。 strip_fences 適用・不可能/不可避
    等は lookahead 除外。 新たな「実は可能」が判明する度 KNOWN_POSSIBLE に 1 行追加。

  deferral (warning-only, exit 0):
    「後で対処」「別タスクに切り出」等 は、 同 turn 内に TaskCreate/TaskUpdate/
    TodoWrite または todos.md への Write/Edit が無ければ warn。

  claim-without-evidence (warning-only, exit 0):
    「不明」「該当なし」「未確認」 系は、 同 turn 内に EVIDENCE_TOOLS が無ければ warn
    (verify-before-claim の negative side)。

  provide-user-instructions (warning-only, exit 0):
    manual-execution 文脈がありつつ host コマンド (sudo cp, git push, gh pr, curl+URL,
    claude --bg, deploy-root への cp) が strip_fences 後の prose (= fence/inline span の外)
    に残れば warn。 手動実行コマンドは独立 fence に置く・inline backtick は実行用でない。
    tool pairing 無しの純 text-shape 判定。

  verify-before-claim positive (warning-only, exit 0):
    completeness self-claim (「網羅した」「reasonable default」等) を、 同 turn 内に
    EVIDENCE_TOOLS が無ければ warn。 claim-without-evidence と pairing 同一、 polarity と
    message のみ別。 確認済み は meta-text/Bash-backed 多数で意図的に除外 (FN 承知)。

  turn-marker (bonus, exit 0 only):
    enforcement が pass した turn 終了時のみ、 per-turn marker (時刻 / Turn #N / context
    size / User Prompt からの経過) を JSON `systemMessage` で USER に表示 (Claude には非可視)。
    経過は境界 user entry の timestamp 起点。 block (exit 2) 時は turn 継続のため非表示。
    1 turn の exit-0 Stop はちょうど 1 回 — clean な Stop か、 advise-once gate が retry
    (stop_hook_active=true) を exit 0 に降格させた Stop。 どちらも marker を 1 回だけ載せる
    (counter は turn 毎 1 bump)。 この once-per-turn 不変条件は memory_surface.py も同
    .turns を読むので cross-hook で load-bearing。 完全 fail-open。

Stop hook input: JSON via stdin with session_id, transcript_path,
hook_event_name = "Stop".

Transcript format: JSONL。 user entry は human prompt なら content が str、 tool_result なら
list。 assistant entry は text / thinking / tool_use blocks の list。

Current-turn boundary: 直近の human-input user entry (content が str) 以降の assistant
entry を current turn とみなす。 corrupted/partial は空値を返し fall-broad scan しない。

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

parse / IO error は fail-open (exit 0) — 誤 block で user 作業を止めないことを優先。
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
# introspective phrase (学習/改善宣言/省察/apology)。 conjugation を anchor し否定/中立/記述用法を除外
# (反省しない, を-lookbehind で「X を記憶」, 次回は自己矯正動詞限定, としてで名詞単体, broad phrase)。
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
# 規模・影響評価語。 report-by-evidence の structured-doc gap (述語なし = skill の文末 trigger 外) を補う
# bare-term match、 同 turn に EVIDENCE_TOOLS 無ければ block。 compound/phrasal 高確度語のみ (軽微/複雑/大変/抜本的/リスクが高い は流文 FP で除外)。
EVALUATIVE_PATTERNS: list[str] = [
    r"大改造",
    r"影響大(?!き)",  # label 影響大 を拾い、 形容詞 影響大きい/大きく は除外
    r"アーキテクチャ(の)?(見直し|再設計|刷新)",
    r"改造が(少な|すくな)",
]
EVALUATIVE_RE = re.compile("|".join(EVALUATIVE_PATTERNS), re.IGNORECASE)

# --- Pattern: order-question-to-user (block on hit, no pairing) ---
# prose で 「どちらを先に」 「どちらから」 等の順序質問を user に投げるのは judgment 回避。
# 順序は 3 分解で常に自決可能 (declare-and-proceed application detail)。 hook scope は prose のみ
# — AskUserQuestion 内の同種は declare_and_proceed_gate.py が PreToolUse で deny する。
ORDER_QUESTION_PATTERNS: list[str] = [
    r"どちら\s*(を)?\s*(先に|から)\s*[^。\n]{0,20}(ますか|しょうか|でしょう)",
    r"どっち\s*(を)?\s*(先に|から)\s*[^。\n]{0,20}(ますか|しょうか|でしょう)",
]
ORDER_QUESTION_RE = re.compile("|".join(ORDER_QUESTION_PATTERNS), re.IGNORECASE)

# --- Pattern: deferral (warning, no block) ---
DEFERRAL_RE = re.compile(
    r"後で(対処|やる|考える)|別タスクに(切り出|分け)|今は(処置|対処)しません|"
    r"後回し|TODO として|次回(に)?(対応|やる)"
)

# --- Pattern: claim-without-evidence (warning, no block) ---
CLAIM_RE = re.compile(r"不明|該当なし|存在しません|未確認|わかりません|分かりません")

# --- Pattern: provide-user-instructions (warning, no block) ---
# MANUAL_EXEC 文脈ありつつ HOST_CMD が strip_fences 後の bare prose に残る時だけ warn (host_cmd は頻出 verb 限定、 ホスト側 は exec 動詞必須 — 裸だと中立語が全 turn 発火)。
# 残留: turn-global pairing ゆえ無関係の過去形 host cmd と同 turn 共存で稀に発火 (warn のみ)。
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
# positive completeness self-claim。 CLAIM_RE (negative) と pairing/EVIDENCE_TOOLS 同一、 polarity/message のみ別。 negative 形は CLAIM_RE 側に残し double-warn 回避。
# strip_fences 後の text に当てる (quote された claim 語除外)。 reasonable default は assertion anchor 要求 (裸だと code default 議論で誤発火)。 lexeme は corpus 駆動で tight (口語 completeness は over-fire で非対象, FN 承知, 確認済みも意図除外)。
POS_CLAIM_PATTERNS: list[str] = [
    r"(全部|全て|すべて)(の(ファイル|file|entry|箇所))?を?(読(んだ|みました|了|み終え)|確認しました)",
    r"網羅(し(た|ました)|的に(確認|読了|チェック|調査)し(た|ました))",
    r"漏れなく(確認|チェック|読)(した|しました)",
    r"(全件|全箇所|全entry)(を)?(確認|チェック|読)(した|しました|済)",
    r"reasonable\s+default\s*(として|を採用|で(良|い)|だと|です)",
]
POS_CLAIM_RE = re.compile("|".join(POS_CLAIM_PATTERNS), re.IGNORECASE)

# --- Pattern: known-possible-denial (block, no pairing) ---
# 既知で可能と判明済みの操作を「できない/不可」と断定したら却下を促す。 op-keyword と
# 不可語が同一行で共起した時のみ block (verify し直させず既知 method を実行させる)。
KNOWN_POSSIBLE: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"部分(コミット|ステージ|stage)|partial[ _-]*stag|git add -p", re.IGNORECASE
        ),
        "`git apply --cached` で hunk 単位の部分 stage が可能 (feedback_partial_stage_foreign_changes)",
    ),
    (
        re.compile(
            r"autosquash|rebase\s+-i|fixup.*squash|squash.*fixup", re.IGNORECASE
        ),
        "`GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash` で非対話に可能 (feedback_rebase_autosquash_needs_interactive)",
    ),
]
IMPOSSIBLE_RE = re.compile(
    r"でき(ない|ません|ず)(?!か|わけ|こと)|不可(?!能|逆|避|分|欠|侵)|無理|no-?op",
    re.IGNORECASE,
)

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


_TAIL_BUFSIZE = 128 * 1024  # 実測 2545 turn の mean≈110KB / p75≈119KB を 1 read で覆う


def _is_prompt(obj: dict) -> bool:
    msg = obj.get("message", {})
    return obj.get("type") == "user" and isinstance(msg.get("content"), str)


def _load_tail(path: str, turns: int = 1, bufsize: int = _TAIL_BUFSIZE) -> list[dict]:
    """末尾から turn boundary を turns 個含むまで後方読みで返す; boundary が turns 未満なら全件。"""
    try:
        with open(path, "rb") as f:
            pos = f.seek(0, os.SEEK_END)
            pending = b""  # 行頭が手前ブロックにある途中行 (次の読みで結合される)
            tail: list[dict] = []  # newest-first
            seen = 0
            while pos > 0:
                step = min(bufsize, pos)
                pos -= step
                f.seek(pos)
                parts = (f.read(step) + pending).split(b"\n")
                pending = parts.pop(0)
                for raw in reversed(parts):
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tail.append(obj)
                    if _is_prompt(obj):
                        seen += 1
                        if seen >= turns:
                            tail.reverse()
                            return tail
            line = pending.strip()  # BOF: 先頭断片はこの時点で完全な 1 行
            if line:
                try:
                    tail.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            tail.reverse()
            return tail  # boundary < turns: 集めた全件
    except OSError:
        return []


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
    """Return (assistant_text, tool_names, tool_paths, has_git_verify, prompt_epoch) for the turn after the most recent string-content user entry; empty values if none (avoids fail-broad whole-transcript scan)."""
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


def _known_possible_denial(text: str) -> str | None:
    """Block message when an op known to be doable is asserted impossible on one line; else None."""
    for line in strip_fences(text).splitlines():
        if not IMPOSSIBLE_RE.search(line):
            continue
        for op_re, hint in KNOWN_POSSIBLE:
            mop = op_re.search(line)
            if mop:
                return (
                    f"known-possible-denial: 「{mop.group(0)}」 を「できない/不可」と "
                    f"断定していますが、 この操作は既知で実行可能です。 その否定を却下し、 "
                    f"verify し直さずそのまま実行してください — {hint}。 "
                    f"(verify-before-claim の不可断定側: 可能と判明済みの method を実行する)"
                )
    return None


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
        persistence_recorded = any(PERSISTENCE_PATH_RE.search(p) for p in tool_paths)
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

    # known-possible-denial (block, no pairing): 既知で可能な操作への 不可 断定
    denial = _known_possible_denial(text)
    if denial:
        blocking.append(denial)

    # order-question-to-user (block, no pairing): 順序質問の user 投げは judgment 回避
    m = ORDER_QUESTION_RE.search(strip_fences(text))
    if m:
        blocking.append(
            f"order-question-to-user: 「{m.group(0)}」 と順序質問を user に投げています。 "
            f"「どちらを先に」 系は (1) 両方やる → 順序不問で自決 / "
            f"(2) 順序に正解あり → 自分で決まる / (3) どちらでも OK → 最初の方から、 "
            f"の 3 分解で常に自決可能で user に valuable answer を求めることはできません "
            f"(declare-and-proceed skill, feedback_order_questions_are_avoidable)。 "
            f"該当文を delete し、 3 分解 self-check して自分で proceed してから再出力してください。"
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
    entries = _load_tail(transcript_path)
    if not entries:
        return 0, None
    text, tool_names, tool_paths, has_git_verify, prompt_epoch = _current_turn(entries)
    # Claude Code が Stop hook を invoke する時点で最新 assistant text はまだ transcript に
    # flush されていない (v2.1.47+ で payload に last_assistant_message が提供されたのはこの
    # gap を埋めるため)。 transcript 由来 text に concat して全 family の取りこぼしを防ぐ。
    last_msg = payload.get("last_assistant_message")
    if isinstance(last_msg, str) and last_msg:
        text = (text + "\n" + last_msg) if text else last_msg
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
                pass
        count += 1
        f.seek(0)
        f.truncate()
        f.write("%d %d\n" % (count, now))
    return count


def _statusline(session_id: str | None) -> dict:
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
        n = (
            cu.get("input_tokens", 0)
            + cu.get("cache_read_input_tokens", 0)
            + cu.get("cache_creation_input_tokens", 0)
        ) or None
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
        parts.append("(%s passed for this turn)" % _gap(int(now_f - prompt_epoch)))
    else:
        started = sl.get("session_started_epoch")
        if isinstance(started, (int, float)) and 0 < started <= now_f:
            parts.append(
                "(%s passed since the session start)" % _gap(int(now_f - started))
            )
    print(json.dumps({"systemMessage": " ".join(parts)}))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        exit_code, prompt_epoch = _run(payload)
    except Exception:
        exit_code, prompt_epoch = (
            0,
            None,
        )  # fail-open: an enforcement glitch never blocks the turn
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
        return {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": text}]},
        }

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
        with (
            mock.patch.object(time, "time", lambda: now),
            mock.patch.object(
                sys.modules[__name__], "_statusline", lambda sid: statusline or {}
            ),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                _emit_turn_marker(payload, prompt_epoch)
        out = buf.getvalue().strip()
        return json.loads(out)["systemMessage"] if out else ""

    def test_parse_ts(self):
        want = datetime.datetime.fromisoformat(
            "2026-06-02T04:45:24.945+00:00"
        ).timestamp()
        self.assertEqual(_parse_ts(self.TS), want)
        for bad in (None, "", "not-a-date", 123):
            self.assertIsNone(_parse_ts(bad))

    def test_current_turn_returns_prompt_epoch(self):
        text, _n, _p, _g, pe = _current_turn([self._user(), self._asst("done.")])
        self.assertEqual(text, "done.")
        self.assertEqual(pe, _parse_ts(self.TS))
        no_ts = [{"type": "user", "message": {"content": "x"}}, self._asst("y")]
        self.assertIsNone(_current_turn(no_ts)[4])
        tool_only = [
            {"type": "user", "message": {"content": [{"type": "tool_result"}]}},
            self._asst("y"),
        ]
        self.assertEqual(_current_turn(tool_only), ("", set(), [], False, None))

    def test_load_tail_matches_whole_transcript(self):
        u1, a1 = self._user(content="q1"), self._asst("a1")
        u2, a2 = self._user(content="q2"), self._asst("a2 省略しません")
        p = self._transcript([u1, a1, u2, a2])
        tail = _load_tail(p)
        self.assertTrue(_is_prompt(tail[0]))  # 先頭は境界 prompt
        self.assertEqual(_current_turn(tail), _current_turn([u1, a1, u2, a2]))
        self.assertEqual(
            _load_tail(p, bufsize=1), tail
        )  # 1-byte buffer でも同一 (pending)
        self.assertEqual(len(_load_tail(p, turns=2)), 4)  # turns=2 は 2 turn 分
        self.assertEqual(sum(_is_prompt(e) for e in _load_tail(p, turns=2)), 2)
        no_prompt_entries = [
            a1,
            {"type": "user", "message": {"content": [{"type": "tool_result"}]}},
        ]
        no_prompt = self._transcript(no_prompt_entries)
        # prompt 無し: tail は全件 (旧は []) だが _current_turn は両者とも空 = consumer 等価
        self.assertEqual(
            _current_turn(_load_tail(no_prompt)), _current_turn(no_prompt_entries)
        )

    def test_bump_persists_count_and_last_stop(self):
        # .turns = "count last_stop"; last_stop feeds the next UPS idle gap.
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "x.turns")
        for n, want in ((1000, ["1", "1000"]), (2000, ["2", "2000"])):
            self.assertEqual(_bump(p, n), int(want[0]))
            with open(p) as f:
                self.assertEqual(f.read().split(), want)

    def test_marker_shows_turn_elapsed(self):
        msg = self._emit(1_000_000 - 150, 1_000_000)
        self.assertIn("2 min passed for this turn", msg)
        self.assertIn("Turn #1", msg)

    def test_marker_subsecond_turn_not_dropped(self):
        self.assertIn("0 sec passed for this turn", self._emit(1000.789, 1000.95))

    def test_marker_fallbacks(self):
        started = self._emit(
            None, 3_000_000, {"session_started_epoch": 3_000_000 - 600}
        )
        self.assertIn("passed since the session start", started)
        degraded = self._emit(None, 3_000_000, {})
        self.assertNotIn("passed since", degraded)
        self.assertIn("Turn #", degraded)
        self.assertNotIn("for this turn", self._emit(3_000_999, 3_000_000, {}))

    def test_enforcement_returns_code_and_epoch(self):
        import io
        from contextlib import redirect_stderr

        with redirect_stderr(io.StringIO()):
            blk = self._transcript([self._user(), self._asst("省略しません")])
            self.assertEqual(
                _run({"transcript_path": blk, "stop_hook_active": False}),
                (2, _parse_ts(self.TS)),
            )
            self.assertEqual(
                _run({"transcript_path": blk, "stop_hook_active": True})[0], 0
            )
            clean = self._transcript(
                [self._user(), self._asst("all good, here is the result.")]
            )
            self.assertEqual(
                _run({"transcript_path": clean, "stop_hook_active": False})[0], 0
            )
        # _run tolerates non-dict input via its isinstance guard; verify it.
        self.assertEqual(_run("nope"), (0, None))  # ty: ignore[invalid-argument-type]
        self.assertEqual(_run({}), (0, None))


if __name__ == "__main__":
    sys.exit(main())
