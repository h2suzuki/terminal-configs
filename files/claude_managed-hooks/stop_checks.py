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
    既知で実行可能と判明済みの操作 (KNOWN_POSSIBLE: rebase autosquash 等) を
    「できない/不可/無理」 と同一行で断定したら block。 verify させ直すのでなく、 可能と
    分かっている既知 method を実行させる (verify-before-claim の不可断定側)。 pairing 無し
    (op が既知可能ゆえ証拠の有無に関わらず否定が誤り)。 strip_fences 適用・不可能/不可避
    等は lookahead 除外。 新たな「実は可能」が判明する度 KNOWN_POSSIBLE に 1 行追加。

  order-question-to-user (enforcement, exit 2):
    prose で 「どちらを先に/から」 系の順序質問を user に投げたら block。 順序は 3 分解
    (両方やる / 正解あり / どちらでも) で常に自決可能 (declare-and-proceed)。 pairing 無し。
    AskUserQuestion 内の同種は declare_and_proceed_gate.py が PreToolUse で deny。

  confirm/routing-to-user (enforcement, exit 2):
    散文の decidable な per-unit 確認 (「これで良い?」) / routing 二択 (「A するか B するか」) を、
    当 turn かつ直近 5 分以内に declare-and-proceed skill の invoke が無ければ block。 検出 regex は
    declare_and_proceed_gate.py の CONFIRM/ROUTING の prose 版 copy。 skill invoke が SKIP
    escape hatch (genuine user-taste/design/priority/不可逆 op pre-approval)。

  intent-without-task (enforcement, exit 2):
    作業遂行宣言 (「やります」「実施します」「修正します」等) を、同 turn 内に TaskCreate/TaskUpdate/TodoWrite が無ければ block。
    全作業項目を Task で追跡する org rule (CLAUDE.md §計画と遂行) の機械 proxy。speech-act 動詞 (確認/説明/報告/共有/提案) は除外し FP 抑制。deferral (warn) の deny 版。

  work-without-task (enforcement, exit 2):
    session の Task 記録 (native store + mytask store、status 不問) がゼロのまま、
    当 turn で Edit/Write を閾値以上実行したら block。intent-without-task が宣言
    phrase 依存で取りこぼす「無宣言で作業に直行した session」を store 側から捕捉する
    (§計画と遂行「まず最初の依頼を Task に登録する」の session 級 proxy)。

  continuation-claim (enforcement, exit 2):
    turn 最終 assistant message の未来形遂行宣言 (「進めます」「続けます」等) を block。
    発話時点で真偽が確定する 3 形式 (実行中 / 完了 / 停止) への書き直しを要求する。
    fence / inline backtick 内とユーザー選択条件の提案は除外し、 background の有無は免除にしない。
    payload の last_assistant_message 由来と確認できる final_text だけを enforcement 対象にする。

  open-tasks-at-wind-down (enforcement, exit 2):
    user prompt が wind-down phrase (check_uncommitted_at_handoff と同一 regex) で、
    session の Task store (native ~/.claude/tasks/<sid>/ + mytask drafts/tasks/<sid>.json)
    に open 項目が残っていれば block。 持ち越しは todos.md へ転記し全 open Task を close
    させる (handoff skill Task 残処理の deny 版。 同 sibling hook の inject が案内層)。

  handoff-doc-without-marker (enforcement, exit 2):
    wind-down 宣言が session 内に一度でもあり (sticky、 sibling hook が記録)、 当 turn に
    handoff doc (規約置き場の mtime 観測 — Bash / python / subagent 経由の書込も捕捉) が
    更新され、 transcript tail + 当 turn 出力に full-sid handoff marker が無ければ block。
    protocol 完了 (cross-check readback + marker) を宣言後の doc 書込 turn に強制する。
    宣言前の途中編集は skill_reminder_gate の handoff skill 要求のみで marker は求めない。

  deferral (warning-only, exit 0):
    「後で対処」「別タスクに切り出」等 は、 同 turn 内に TaskCreate/TaskUpdate/
    TodoWrite が無ければ warn。

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

  honest-attribution (warning-only, exit 0):
    自セッションの誤 pattern を 「既存/繰り越し/reasonable default/段階的拡張」 等で
    ownership ぼかしする発話を warn。 attribute-existing-issues skill の機械 proxy。
    blur phrase と wrong-marker の 60 字近接 pairing で FP 抑制 (v1 observe-then-tighten)。

  edited-executable-not-run (warning-only, exit 0):
    実行可能 artifact を Edit/Write して done-claim したが、 同 turn の Bash で
    該当 file を一度も実行/テストしていなければ warn。

  ui-edit-without-screenshot (warning-only, exit 0):
    UI artifact を Edit/Write して done-claim したが、 同 turn に screenshot 系
    tool_use が無ければ warn。

  worktree-cleanup (warning-only, exit 0):
    payload の cwd に属する linked worktree が clean かつ本線の祖先なら、削除候補と
    実行可能な git worktree remove コマンドを知らせる。判定不能時は fail-open。
    block 時は blocking reason、pass / retry 時は additionalContext 経由で model に届ける。
    memory-surface reason と同 turn なら 1 payload に結合 (reason が先)。
    .wt latch は初回を通して turn 内の 2 回目以降を抑えるが stop_hook_active retry は再配達する。
    射程: 本線は refs/heads/main / master のみ (他 trunk の repo では無音)、
    入れ子 worktree の子は候補外。 いずれも鳴らない側の限界。

  codex-shared-write (warning-only, exit 0):
    job state を照合し、共有 checkout で write task が実行された事後検知を知らせる。
    state / JSON / git の異常は fail-open、job id 単位の latch で重複通知を抑える。
    job record の field 名 (write / workspaceRoot / sessionId) と status 語彙
    (queued / running を停止可能とみなす) に依存し、変われば静かに劣化する。

  decision-question-task / decision-record (warning-only, exit 0):
    質問終端時の open decision 型 task の欠落と、短文決裁受領時の
    open decision 型 task を照合し、状態記録の自己確認を促す。

  communication-final-line / communication-self-number (warning-only, exit 0):
    最終非空行が絵文字始まりまたは質問終端でない場合と、散文の
    自己採番参照を検知する。code block・inline code・Markdown 引用は除外する。

  上記 3 family と下記 2 family は family ごと 1 行・合計 5 行以内にし、block 時は reason
  本文、pass 時は additionalContext / systemMessage へ出す。stop_hook_active retry でも再生成する。

  waste-keyword-memory (warning-only, exit 0):
    当 turn の user prompt に無駄・浪費・もったいないがあり、同 turn に persistence
    path への Write が無ければ、memory entry 化を一拍検討するよう促す。

  question-self-containment (warning-only, exit 0):
    最終非空行が質問終端かつ過去参照語を含む場合、単体で読める質問 template を促す。
    code block・inline code・Markdown 引用は除外する。

  turn-marker (bonus, exit 0 only):
    enforcement が pass した turn 終了時のみ、 per-turn marker (時刻 / Turn #N / context
    size / User Prompt からの経過) を JSON `systemMessage` で USER に表示 (Claude には非可視)。
    経過は境界 user entry の timestamp 起点。 block (exit 2) 時は turn 継続のため非表示。
    1 turn の exit-0 Stop はちょうど 1 回 — clean な Stop か、 advise-once gate が retry
    (stop_hook_active=true) を exit 0 に降格させた Stop。 どちらも marker を 1 回だけ載せる
    (counter は turn 毎 1 bump)。 この once-per-turn 不変条件は memory_surface.py も同
    .turns を読むので cross-hook で load-bearing。 完全 fail-open。

  memory-surface (bonus, regex-pass path, exit 0):
    enforcement が pass し block しない turn の first Stop でのみ、 当 turn の assistant 出力 (text)
    を query に memory_surface.surface_for_text を呼び、 最良 1 件を hookSpecificOutput.additionalContext
    で model に inject + systemMessage で user 表示 (Stop の additionalContext は v2.1.163+ で turn を
    継続させ feedback を返す channel)。 turn 毎最大 1 回 — stop_hook_active gate に加え .turns count を
    key にした turn-latch (継続で stop_hook_active が立たない場合の belt) で継続 Stop を抑え、
    surface_for_text の throttle が UPS surface と同一 entry の重複を抑止。 import / DB 不在は fail-open で
    surfacing 無効。 surfacing した Stop では counter を bump せず、 clean 終了 (継続後の retry) 側で 1 回 bump。

  muted-memory-at-wall (bonus, exit 0 / block 併記):
    「できない」 系の断定 / 誤読の自認を検出した turn の first Stop でのみ、 否定の周辺 ±120 字を
    query に memory_surface.search_unfiltered (model filter を通さない) を引き、 実行中モデルの
    tag を持たない上位 1 件を additionalContext で inject する。 sibling の memory-surface は
    model filter 越しなので、 tag の無い entry はこの family でしか見えない。 floor 0.35 は実測
    (該当局面の top 0.397 / 無関係文の top 0.270) の分離点。 enforcement が block した turn は
    additionalContext 経路に届かず継続 Stop も stop_hook_active で閉じるため、 block 側は
    _run が block stderr へ併記する。 stop_hook_active gate + .muted latch で turn 内 1 回、
    import / DB 不在も含め完全 fail-open。

Stop hook input: JSON via stdin with session_id, transcript_path,
hook_event_name = "Stop".

Transcript format: JSONL。 user entry は human prompt なら content が str、 tool_result なら
list。 assistant entry は text / thinking / tool_use blocks の list。

Current-turn boundary: 直近の human-input user entry (content が str) 以降の assistant
entry を current turn とみなす。 corrupted/partial は空値を返し fall-broad scan しない。

Exit:
  0: no enforcement triggered, OR a would-be re-block on a stop_hook_active
     retry was demoted to a pass (advise-once). warnings may be emitted on stderr
  2: an enforcement block family triggered (meta-announce-silence / hollow-claims /
     recognize-own-work / evaluative-terms / known-possible-denial / order-question-to-user /
     confirm-routing-to-user / continuation-claim / intent-without-task), on the turn's first Stop
     (stop_hook_active false)

The advise-once gate lives in _run (shared), so it INTENTIONALLY demotes every
block family — not just evaluative — to one-block-per-turn. All of them
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
import shlex
import subprocess
import sys
import threading
import time
import unittest

# Kept identical to claude_court_guard so the Stop hook remains fail-open without subprocess IO.
COURT_RE_STRAY = re.compile(r"(?m)^[ \t]*(?:court|count)[ \t]*$")
COURT_RE_INVOKE_LEAK = re.compile(r'(?m)^[ \t]*<invoke name="')

_GIT_COMMAND_TIMEOUT_SECONDS = 5


def _git_command(
    args: list[str], expected_returncodes: frozenset[int] = frozenset()
) -> subprocess.CompletedProcess[str] | None:
    command = " ".join(shlex.quote(arg) for arg in ("git", *args))
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(
            f"worktree-cleanup: {command} timed out after "
            f"{_GIT_COMMAND_TIMEOUT_SECONDS}s",
            file=sys.stderr,
        )
        return None
    except OSError as exc:
        print(f"worktree-cleanup: {command} failed to start: {exc}", file=sys.stderr)
        return None
    if result.returncode != 0 and result.returncode not in expected_returncodes:
        detail = (result.stderr or result.stdout).strip()
        suffix = f": {detail}" if detail else ""
        print(
            f"worktree-cleanup: {command} failed with exit {result.returncode}{suffix}",
            file=sys.stderr,
        )
        return None
    return result


def _parse_worktree_records(output: str) -> list[tuple[str, bool]]:
    records: list[tuple[str, bool]] = []
    path: str | None = None
    prunable = False
    for line in output.splitlines():
        if line.startswith("worktree "):
            if path is not None:
                records.append((path, prunable))
            raw_path = line.removeprefix("worktree ")
            path = os.path.realpath(raw_path) if raw_path else None
            prunable = False
        elif path is not None and (line == "prunable" or line.startswith("prunable ")):
            prunable = True
    if path is not None:
        records.append((path, prunable))
    return records


def _worktree_paths(cwd: str) -> tuple[str, list[tuple[str, bool]]] | None:
    current = os.path.abspath(cwd)
    root_result = _git_command(["-C", current, "rev-parse", "--show-toplevel"])
    if root_result is None:
        return None
    repo = os.path.realpath(root_result.stdout.strip())
    if not repo:
        print(
            "worktree-cleanup: git returned an empty repository root", file=sys.stderr
        )
        return None
    list_result = _git_command(["-C", repo, "worktree", "list", "--porcelain"])
    if list_result is None:
        return None
    records = _parse_worktree_records(list_result.stdout)
    if not records:
        print("worktree-cleanup: git returned no worktree paths", file=sys.stderr)
        return None
    return records[0][0], records


def _main_head(repo: str) -> str | None:
    for branch in ("refs/heads/main", "refs/heads/master"):
        result = _git_command(
            ["-C", repo, "rev-parse", "--verify", branch],
            frozenset({128}),
        )
        if result is not None and result.returncode == 0:
            head = result.stdout.strip()
            if head:
                return head
    return None


def _clean_merged_worktree(repo: str, path: str, main_head: str) -> bool:
    # ignored/untracked も見る: gitignore 下の codex 成果物を「空」と誤判定しないため
    status = _git_command(
        ["-C", path, "status", "--porcelain", "--ignored", "--untracked-files=normal"]
    )
    if status is None or status.stdout:
        return False
    head_result = _git_command(["-C", path, "rev-parse", "--verify", "HEAD"])
    if head_result is None:
        return False
    head = head_result.stdout.strip()
    if not head:
        return False
    ancestor = _git_command(
        ["-C", repo, "merge-base", "--is-ancestor", head, main_head],
        frozenset({1}),
    )
    return ancestor is not None and ancestor.returncode == 0


def _paths_related(left: str, right: str) -> bool:
    try:
        return os.path.commonpath((left, right)) in (left, right)
    except ValueError:
        return False


def _path_is_ancestor(ancestor: str, path: str) -> bool:
    try:
        return os.path.commonpath((ancestor, path)) == ancestor
    except ValueError:
        return False


def _worktree_candidates(cwd: str) -> tuple[str, str, list[str]] | None:
    if not isinstance(cwd, str) or not cwd:
        return None
    info = _worktree_paths(cwd)
    if info is None:
        return None
    primary, records = info
    repo = primary
    main_head = _main_head(repo)
    if main_head is None:
        return None
    current = os.path.realpath(cwd)
    current_worktree = max(
        (path for path, _prunable in records if _path_is_ancestor(path, current)),
        key=len,
        default=primary,
    )
    linked_paths = [path for path, prunable in records[1:] if not prunable]
    candidates = [
        path
        for path in linked_paths
        if (current_worktree == primary or not _paths_related(path, current_worktree))
        and not any(
            path != other and _paths_related(path, other) for other in linked_paths
        )
    ]
    return repo, main_head, candidates


def _worktree_cleanup_warnings(cwd: str | None) -> list[str]:
    info = _worktree_candidates(cwd) if isinstance(cwd, str) else None
    if info is None:
        return []
    repo, main_head, candidates = info
    busy = _codex_busy_roots() if candidates else set()
    warnings: list[str] = []
    for path in candidates:
        if os.path.realpath(path) in busy:
            continue
        if _clean_merged_worktree(repo, path, main_head):
            command = (
                f"git -C {shlex.quote(repo)} worktree remove -- {shlex.quote(path)}"
            )
            warnings.append(
                f"worktree-cleanup: clean かつ本線に取り込み済みの linked worktree "
                f"{path} を検出しました。hook 自身は削除しません。不要なら次のコマンドを"
                f"そのまま実行してください: {command}。次回は本線への取り込み後に削除し、"
                "同じ状態を放置しないでください。"
            )
    return warnings


_CODEX_STATE_ROOT = "~/.claude/plugins/data/codex-openai-codex/state"
_CODEX_LATCH_SUFFIX = ".codex-shared-write"
_CODEX_JOB_LATCH_SUFFIX = _CODEX_LATCH_SUFFIX + ".jobs"


def _codex_is_linked_worktree(path: str) -> bool | None:
    if not os.path.isdir(path):
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir", "--git-common-dir"],
            cwd=path,
            capture_output=True,
            check=False,
            text=True,
            timeout=_GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    lines = result.stdout.splitlines()
    if len(lines) != 2 or not all(lines):
        return None
    git_dir, common_dir = (
        os.path.realpath(
            os.path.abspath(
                value if os.path.isabs(value) else os.path.join(path, value)
            )
        )
        for value in lines
    )
    return git_dir != common_dir


def _codex_job_records(session_id: str | None) -> list[dict]:
    records: list[dict] = []
    try:
        state_root = os.path.expanduser(_CODEX_STATE_ROOT)
        with os.scandir(state_root) as workspaces:
            for workspace in workspaces:
                if not workspace.is_dir():
                    continue
                jobs = os.path.join(workspace.path, "jobs")
                try:
                    entries = os.scandir(jobs)
                except OSError:
                    continue
                with entries:
                    for entry in entries:
                        if not entry.is_file() or not entry.name.endswith(".json"):
                            continue
                        try:
                            with open(entry.path, encoding="utf-8") as stream:
                                record = json.load(stream)
                        except (OSError, ValueError):
                            continue
                        if isinstance(record, dict) and (
                            session_id is None or record.get("sessionId") == session_id
                        ):
                            records.append(record)
    except OSError:
        return []
    return records


def _codex_busy_roots() -> set[str]:
    """未完了 codex job の作業 root — 壊れるのは job ゆえ session を跨いで全部拾う。"""
    return {
        os.path.realpath(record["workspaceRoot"])
        for record in _codex_job_records(None)
        if record.get("status") in ("queued", "running")
        and isinstance(record.get("workspaceRoot"), str)
        and record["workspaceRoot"]
    }


def _codex_job_sort_key(record: dict) -> tuple[bool, float]:
    timestamp = record.get("updatedAt", record.get("startedAt"))
    if isinstance(timestamp, (int, float)):
        epoch = float(timestamp)
    else:
        parsed = _parse_ts(timestamp)
        epoch = parsed if parsed is not None else float("-inf")
    return record.get("status") in ("queued", "running"), epoch


def _codex_shared_write_warnings(payload: dict) -> list[str]:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return []
    try:
        jobs = []
        linked_memo: dict[str, bool | None] = {}
        for record in _codex_job_records(session_id):
            path = record.get("workspaceRoot")
            if (
                record.get("write") is True
                and isinstance(record.get("id"), str)
                and isinstance(path, str)
                and os.path.isabs(path)
                and os.path.isdir(path)
            ):
                if path not in linked_memo:
                    linked_memo[path] = _codex_is_linked_worktree(path)
                if linked_memo[path] is False:
                    jobs.append(record)
        latch = _stop_latch_key(payload, _CODEX_JOB_LATCH_SUFFIX)
        if latch is None:
            counter = _counter_path(payload)
            if not counter:
                return []
            latch_path = counter + _CODEX_JOB_LATCH_SUFFIX
        else:
            _key, latch_path = latch
        seen: set[str] = set()
        try:
            with open(latch_path, encoding="utf-8") as stream:
                seen = set(stream.read().splitlines())
        except OSError:
            pass
        fresh = [job for job in jobs if job["id"] not in seen]
        if not fresh:
            return []
        try:
            os.makedirs(os.path.dirname(latch_path), exist_ok=True)
            with open(latch_path, "w", encoding="utf-8") as stream:
                stream.write("\n".join(sorted(seen | {job["id"] for job in fresh})))
                stream.write("\n")
        except OSError:
            return []
        lines = []
        fresh.sort(key=_codex_job_sort_key, reverse=True)
        for job in fresh[:3]:
            status = job.get("status", "unknown")
            action = (
                f"{status} のため cancel {job['id']} で止めてください"
                if status in ("running", "queued")
                else "git status で混入を確認してください"
            )
            lines.append(
                f"codex-shared-write: 共有 checkout で write を伴う codex task が"
                f"走った (走っている) ことを検知しました。job {job['id']}、"
                f"workspaceRoot={job['workspaceRoot']}、status={status}。{action}。"
                "job 記録に基づく検知なので、コマンドの書き方に依存しません。"
            )
        extra = len(fresh) - 3
        if extra > 0:
            lines.append(
                f"codex-shared-write: 追加で {extra} 件の該当 job があります。"
            )
        return lines
    except Exception:
        return []


def _court_contaminated(text: str) -> bool:
    return bool(COURT_RE_STRAY.search(text) or COURT_RE_INVOKE_LEAK.search(text))


# Reuse memory_surface's retrieval engine at Stop via a guarded cross-tree import
# (managed→user layering, repo-deployed together; absent/broken hook → surfacing off).
sys.path.append(os.path.expanduser("~/.claude/hooks"))
try:
    # ty can't resolve this runtime sys.path import; guarded + fail-open below.
    import memory_surface as _memory_surface_mod  # ty: ignore[unresolved-import]
except Exception:
    _memory_surface_mod = None

# Wind-down regex + open-task readers live in the sibling UserPromptSubmit hook
# (single source, same deployed dir; absent/broken hook → this gate off).
try:
    import check_uncommitted_at_handoff as _handoff_mod
except Exception:
    _handoff_mod = None  # fail-open sentinel, guarded by `is not None`

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
    # 名詞「学び」の claim 形。 修飾用法 (学びのある/学びを深める) は非対象。
    r"学びが(あった|あり(ました|ます))",
    r"学びで(す|した)",
    r"学びを得(た|ました)",
    r"学びました",
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
    r"もう(し|いた|致し)ません",
    r"二度と(し|やり|繰り返し)ません",
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

# --- Pattern: bang-prefix-host-escape (block on hit, no pairing) ---
# `!` prefix は auto mode の実行許可を与えるだけで sandbox の外には出ない。 user へ
# 「`!` で流して」 と依頼しても host 実行にならず、 prose ゆえ tool hook では捕捉不能
# — Stop が唯一の channel (provide-user-instructions)。
BANG_HOST_REQUEST_RE = re.compile(
    r"`?!`?\s*(?:prefix|プレフィックス)?\s*(?:を\s*(?:付けて|つけて)|付きで|で)"
    r"[^。\n]{0,30}?(?:実行|起動|流)[^。\n]{0,15}?"
    r"(?:ください|下さい|いただけ|もらえ|ましょう|します)"
)
# 同一文が「出ません」等で否定していれば本 rule の説明文なので発火させない。
BANG_HOST_NEGATION_RE = re.compile(
    r"出ません|出られません|なりません|ありません|ではない|効きません|限りません"
)
# provide-user-instructions が code block 提示を求めるため、 依頼は fence と散文に割れて
# inline 文言に一致しない。 fence 冒頭行の `!` と散文側の実行依頼を対で捕捉する。
BANG_FENCE_BODY_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
BANG_FENCED_HEAD_RE = re.compile(r"\A[ \t]*!\s+\S")
BANG_EXEC_REQUEST_RE = re.compile(
    r"(?:実行|起動|流|deploy|デプロイ)[^。\n]{0,20}?"
    r"(?:ください|下さい|いただけ|もらえ|ましょう|お願い)"
)


def _bang_host_escape(text: str) -> str | None:
    """Return a block reason when `!` is offered to the user as a sandbox escape."""
    # strip_fences は inline backtick span も消すため使えない — `!` 自体が消える。
    prose = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    for line in re.split(r"[。\n]", prose):
        m = BANG_HOST_REQUEST_RE.search(line)
        if m and not BANG_HOST_NEGATION_RE.search(line):
            return _bang_host_reason(m.group(0).strip())
    if BANG_EXEC_REQUEST_RE.search(prose):
        for body in BANG_FENCE_BODY_RE.findall(text):
            head = next((ln for ln in body.splitlines() if ln.strip()), "")
            if BANG_FENCED_HEAD_RE.match(head):
                return _bang_host_reason(head.strip())
    return None


def _bang_host_reason(quoted: str) -> str:
    """Render the shared block reason for the inline and fenced request forms."""
    return (
        f"bang-prefix-host-escape: 「{quoted}」 と `!` での実行を user に "
        "依頼しています。 `!` が与えるのは auto mode の実行許可だけで、 コマンド自体は "
        "sandbox 内で走ります — sandbox を出る手段ではありません。 host 権限が要るなら "
        "sandbox.excludedCommands 登録済みのコマンドを使い、 一覧に無い作業 (/etc への "
        "書き込み・sudo 必須の deploy 等) は 「Claude Code の外の terminal で実行して "
        "ください」 と明示して依頼してください (provide-user-instructions)。 "
        "該当文を書き換えてから再出力してください。"
    )


# --- Pattern: confirm/routing-to-user (block unless declare-and-proceed invoked this turn) ---
# 散文の decidable な確認 (「これで良い?」) / routing 二択 (「A するか B するか」) の user 投げを Stop で捕捉。
# AskUserQuestion 版は declare_and_proceed_gate.py が PreToolUse で deny、 散文は Stop の decision:block が唯一の channel。
# CONFIRM/ROUTING regex は declare_and_proceed_gate.py の prose 版 copy (twin・drift 時は両者同期)。 SKIP は skill invoke が escape hatch。
DECLARE_PROCEED_SKILL = "declare-and-proceed"
SKILL_WINDOW_SECONDS = 300  # active 窓 = 現 turn かつ直近 5 分以内
CONFIRM_PATTERNS: list[str] = [
    r"これで(良|よ)い",
    r"で(良|よ)いです(か|ね)",
    r"で(良|よ)い\s*[?？]",
    r"で問題(ありません|ない)\s*(か|ですか|でしょうか)",
    r"進めて(も)?(良|よ)い",
    r"この(まま|style|スタイル|形式|方針|案|内容|draft|wording)で(良|よ|問題な)",
    r"適用して(も)?(良|よ)い",
    r"してもよいですか",
]
ROUTING_PATTERNS: list[str] = [
    r"どちら(から|を先に|で進め|を調査)",
    r"どっち(から|を先に)",
    r"経由\s*(で|か)[^。\n]{0,20}(経由|か[?？])",
    r"(から|を)\s*調査しますか",
    r"(から|を)\s*着手しますか",
    r"どこから\s*(調査|着手|始め|見)",
    r"先に\s*(調査|確認|読み?)\s*ますか",
    r"[ぁ-んァ-ヶ一-鿿\w]+するか\s*[ぁ-んァ-ヶ一-鿿\w]+するか",
    r"(どう|どの|どれ)を?\s*[ぁ-んァ-ヶ一-鿿\w]+\s*しますか",
    r"それとも[^。\n]{0,40}(ますか|ましょうか|でしょうか|します[?？])",  # 「A ますか、それとも B ますか」 丁寧 alternation 二択
]
CONFIRM_RE = re.compile("|".join(CONFIRM_PATTERNS), re.IGNORECASE)
ROUTING_RE = re.compile("|".join(ROUTING_PATTERNS), re.IGNORECASE)

# --- Pattern: deferral (warning, no block) ---
DEFERRAL_RE = re.compile(
    r"後で(対処|やる|考える)|別タスクに(切り出|分け)|今は(処置|対処)しません|"
    r"後回し|TODO として|次回(に)?(対応|やる)"
)

# --- Pattern: intent-without-task (block if no TaskCreate/TaskUpdate/TodoWrite this turn) ---
# 作業遂行宣言動詞のみ — speech-act 動詞 (確認/説明/報告/共有/提案/回答) は含まない。
INTENT_DECLARE_PATTERNS: list[str] = [
    r"やります",
    r"実施します",
    r"対応します",
    r"着手します",
    r"進めます",
    r"修正します",
    r"削除します",
    r"追加します",
    r"実装します",
    r"作成します",
    r"変更します",
    r"反映します",
    r"統合します",
    r"置換します",
    r"コミットします",
    r"commit\s?します",
    r"デプロイします",
    r"deploy\s?します",
]
# 疑問の終助詞 「か」 が続く形は user への問いかけ (declare-and-proceed の担当) で宣言ではない。
_INTENT_QUESTION_TAIL = r"(?!(?:でしょう)?か[ねなよ]?(?:[?？。、,!！)\]」』]|\s|$))"
INTENT_DECLARE_RE = re.compile(
    "(?:" + "|".join(INTENT_DECLARE_PATTERNS) + ")" + _INTENT_QUESTION_TAIL,
    re.IGNORECASE,
)

# --- Pattern: continuation-claim (block final assistant message on hit) ---
CONTINUATION_CLAIM_PATTERNS: list[str] = [
    r"継続します",
    r"再開します",
    r"進めます",
    r"進みます",
    r"続けます",
    r"着手します",
    r"実施します",
    r"実装します",
    r"取り掛かります",
    r"対応します",
    r"調整します",
    r"やります",
    r"修正します",
    r"削除します",
    r"追加します",
    r"作成します",
    r"変更します",
    r"反映します",
    r"統合します",
    r"置換します",
    r"コミットします",
    r"commit\s?します",
    r"デプロイします",
    r"deploy\s?します",
    r"自走を続け",
    r"作業を続け",
]
CONTINUATION_CLAIM_RE = re.compile(
    "(?:" + "|".join(CONTINUATION_CLAIM_PATTERNS) + ")" + _INTENT_QUESTION_TAIL,
    re.IGNORECASE,
)
CONTINUATION_USER_CHOICE_RE = re.compile(
    r"必要(?:なら|であれば|に応じて)|(?:ご希望|ご要望|お望み)"
    r"(?:なら|であれば|の場合|に応じて|があれば)"
)
CONTINUATION_LIST_RE = re.compile(r"^\s*(?:[-*・]|\d+[.)])\s*")
CONTINUATION_TABLE_RE = re.compile(r"^\s*\|")
CONTINUATION_STOP_RE = re.compile(r"ここで停止|再開条件")
CONTINUATION_SUBJECT_RE = re.compile(
    r"^\s*(?:(?:[A-Za-z_][\w.-]*)|(?:(?:この|その|本)\s*\S+)|検出語)?\s*は"
)


def _continuation_line_is_explanatory(line: str, match: re.Match[str]) -> bool:
    """Whether a matching line is a fixture/list label or impersonal explanation."""
    if CONTINUATION_TABLE_RE.search(line):
        return True
    marker = CONTINUATION_LIST_RE.match(line)
    if marker and re.fullmatch(
        rf"\s*(?:{CONTINUATION_CLAIM_RE.pattern})\s*[。.!！]?\s*",
        line[marker.end() :],
        re.IGNORECASE,
    ):
        return True
    subject = CONTINUATION_SUBJECT_RE.search(line[: match.start()])
    return bool(subject)


def _conditional_continuation_proposal(text: str) -> bool:
    """Whether user-choice wording precedes the claim (or heads a following list)."""
    choice = CONTINUATION_USER_CHOICE_RE.search(text)
    if not choice:
        return False
    claim = CONTINUATION_CLAIM_RE.search(text)
    return claim is None or choice.start() < claim.start()


def _continuation_claim(text: str) -> re.Match[str] | None:
    """Return the first unconditional continuation claim in final-message prose."""
    choice_list_scope = False
    for line in strip_fences(text).splitlines():
        is_list = bool(CONTINUATION_LIST_RE.search(line))
        if choice_list_scope:
            if is_list:
                continue
            choice_list_scope = False
        if not line.strip():
            continue
        if CONTINUATION_STOP_RE.search(line) or CONTINUATION_TABLE_RE.search(line):
            continue
        if _conditional_continuation_proposal(line):
            choice_list_scope = True
        for sentence in re.split(r"。", line):
            match = CONTINUATION_CLAIM_RE.search(sentence)
            if not match:
                continue
            if _conditional_continuation_proposal(sentence):
                continue
            if _continuation_line_is_explanatory(sentence, match):
                continue
            return match
    return None


def _without_final_sentence_identities(text: str, final_text: str) -> str:
    """Drop every turn sentence whose stripped identity occurs in final_text."""
    final_units = {
        unit.strip()
        for unit in re.split(r"[。\n]", strip_fences(final_text))
        if unit.strip()
    }
    return "\n".join(
        unit
        for unit in re.split(r"[。\n]", strip_fences(text))
        if unit.strip() and unit.strip() not in final_units
    )


# --- Pattern: euphemism-for-error (block) ---
# 自分の発言を 「誤解を招く X」 と評した時だけ捕まえる。 設計対象 (命名・ラベル・doc) への
# 同じ評価は正当な技術用語ゆえ落とす (実 corpus 8064 件で裸の 「誤解」 は 21 hit・うち 17 が正当)。
EUPHEMISM_RE = re.compile(
    r"誤解を(?:招く|招き(?:やすい|うる|かねない)|生む)(?:ような)?"
    r"(?:記述|表現|書き方|説明|言い方|文言|記載|報告|回答|answer|framing)"
    r"|誤解を招きました|誤解させ(?:まし|てしまい)"
)

# --- Pattern: claim-without-evidence (warning, no block) ---
# 「無い」系だけでなく「できない / 書かれていない」系も対象 (実測 2026-08-08: 探索範囲を確かめずに
# 「どのスキルにも書かれていません」、 正規ルート未試行で「権限では実施できません」と誤断定した)。
CLAIM_PATTERNS: list[str] = [
    r"不明|該当なし|存在しません|未確認|わかりません|分かりません",
    r"(書かれて|記載されて|定義されて)(いません|いない)",
    r"(実施|実行|編集|取得|参照|アクセス|変更|確認|対応)(でき|出来)(ません|ない)",
    r"見つかりません|見当たりません|ヒットしません",
]
CLAIM_RE = re.compile("|".join(CLAIM_PATTERNS))

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

# --- Pattern: honest-attribution (warning, no block) ---
# 自セッションの誤 pattern を「既存/繰り越し/reasonable default」等で ownership ぼかしする発話を warn (attribute-existing-issues proxy)。
# blur phrase と wrong-marker の 60 字近接 pairing で FP 抑制 (whole-message AND より tight、 v1 observe-then-tighten)。
HONEST_BLUR_RE = re.compile(
    r"既存(?:の)?(?:まま|パターン|挙動|設計|もの)|繰り越し|carried[ -]?over|"
    r"reasonable default|段階的(?:な)?拡張|incremental extension|見落と|"
    r"didn'?t notice|気づか(?:なかった|ず)",
    re.IGNORECASE,
)
HONEST_WRONG_RE = re.compile(
    r"誤(?:り|った|字|用|認識)|間違|wrong|バグ|\bbug\b|違反|欠陥|regression|"
    r"壊し|不正|不適切|問題(?:だ|の|が|点)|に過ぎ|だっただけ",
    re.IGNORECASE,
)

# --- Pattern: post-edit verification (warning, no block) ---
DONE_CLAIM_RE = re.compile(
    r"(実装|修正|対応)?完了|\bdone\b|\blanded\b|着地", re.IGNORECASE
)
EXECUTABLE_ARTIFACT_RE = re.compile(
    r"\.(py|sh)$|/hooks/|/usr/local/bin/|settings.*\.json$", re.IGNORECASE
)
UI_ARTIFACT_RE = re.compile(r"\.(css|scss|tsx|jsx|vue|svelte|html)$", re.IGNORECASE)

# --- Pattern: known-possible-denial (block, no pairing) ---
# 既知で可能と判明済みの操作を「できない/不可」と断定したら却下を促す。 op-keyword と
# 不可語が同一行で共起した時のみ block (verify し直させず既知 method を実行させる)。
KNOWN_POSSIBLE: list[tuple[re.Pattern[str], str]] = [
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

# --- Pattern: muted-memory-at-wall (bonus, exit 0 via additionalContext) ---
# 「できない」断定と誤読の自認は、 過去の教訓が最も効く局面。 surface hook は model filter を
# 通すので tag の無い entry はそこに出ず、 この family だけが見せられる。 known-possible-denial
# が既知可能 op の否定を block する側、 こちらは未知の否定に材料を出す側。
# 動詞を並べるのをやめ、 可能形の否定そのものを核にする — 「実行できません」 だけを見ていると
# 「権限がないため変更できません」 を落とし、 「実行」 に釣られて疑問文まで拾っていた。
_DENIAL = r"(?:でき|出来)(?:ない|ず|ません|なかった|ませんでした)|不可能|実行不能"
# 断定だけを残す尾: 文末に来るか、 判断を表明する語が続くか。 「〜ないか」「〜ない場合」
# 「〜ないわけではない」「〜ないかもしれない」 は同じ核を含むが断定ではないので、 ここで落ちる。
_ASSERTED = r"(?:\s*(?:と(?:判断|結論)|と考え|です|でした)|\s*[。．.!！?？\n]|$)"
# 自認だけを拾うため過去形に限る — te 形は 「空行を block と誤読して落とします」 のように
# プログラムの誤読を叙述する側にも出る (実 transcript で計測)。
_MISREAD = (
    r"(?:誤読|勘違い|早とちり|思い込)(?:(?:んで|して|し)い?(?:た|まし)|でし)"
    r"|読み違え(?:てい)?(?:た|まし)"
)
WALL_DECLARATION_RE = re.compile(
    rf"(?:{_DENIAL}){_ASSERTED}|{_MISREAD}"
    # 英語側も宣言の枠を要求する — 裸の "hard limit" は語の言及であって断定ではない。
    r"|(?:is|was|hits?|hit|reached)\s+(?:a\s+)?hard\s?(?:wall|limit)"
    r"|(?:壁|限界)\s?(?:だ|です|と(?:判断|結論)(?:し(?:た|まし)|です))",
    re.IGNORECASE,
)
MUTED_FLOOR = 0.35  # 実測: 該当局面の top hit 0.397 / 無関係文の top hit 0.270
_MUTED_LATCH = ".muted"
_SEARCH_TIMEOUT_SECONDS = 20.0

# --- Pattern: waste-keyword-memory / question-self-containment (warning) ---
NEW_WARNING_FAMILIES_LIMIT = 5
WASTE_KEYWORD_RE = re.compile(r"無駄|浪費|もったいない")
HARNESS_USER_PREFIXES = (
    "/compact ",
    "<command-name>",
    "<task-notification>",
    "<system-reminder>",
    "Stop hook feedback:",
    "This session is being continued",
)
QUESTION_PAST_REFERENCE_RE = re.compile(
    r"前ターン|前のターン|先ほど|さきほど|上記|前回|上で述べた|既述"
)
JAPANESE_QUOTED_SPAN_RE = re.compile(r"「[^」]*」")

# --- Persistence path (broader than memory only) ---
# memory subtree / skill dir / hook dir / CLAUDE.md への Write/Edit が hollow-claims の
# pairing を満たす。 「claude_managed-skills/」「claude_managed-hooks/」 等の
# hyphen separated dir 名も拾うため skills?[-_/] / hooks?[-_/] とする。
PERSISTENCE_PATH_RE = re.compile(
    r"(global-memory|/memory/|skills?[-_/]|hooks?[-_/]|CLAUDE\.md$)",
    re.IGNORECASE,
)

# Evidence tools (claim-without-evidence pairing)
EVIDENCE_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch"}

# Task tools (deferral pairing)
TASK_TOOLS = {"TaskCreate", "TaskUpdate", "TodoWrite"}

# mytask MCP tools that record work when native Task tools are gated off.
MYTASK_MCP_TOOLS = {"mcp__mytask__TaskCreate", "mcp__mytask__TaskUpdate"}

# work-without-task が「実質的な作業 turn」とみなす Edit/Write 回数の下限
WORK_WITHOUT_TASK_MIN_EDITS = 3
NATIVE_TASKS_DIR = os.path.expanduser(os.path.join("~", ".claude", "tasks"))
OPEN_TASK_STATUSES = frozenset({"pending", "in_progress", "blocked"})
DECISION_TASK_RE = re.compile(
    r"(?:採否待ち|判断待ち|決裁待ち|ご判断待ち|ご回答待ち|ご指示待ち)"
    r"(?!(?:ではな|でなく))"
)
SHORT_DECISION_RE = re.compile(
    r"(?:\(?[a-z0-9]\)?|(?:やって|進めて)(?:ください|下さい)|"
    r"お願いします|承認(?:します|です)?|よい|良い|いい|はい|"
    r"ok|オーケー|それで|その案で|採用|却下)",
    re.IGNORECASE,
)


def _mytask_store_path(session_id: str, cwd: str | None) -> str | None:
    """Writer anchors on the project dir, so search it and every cwd ancestor."""
    relative = os.path.join("drafts", "tasks", f"{session_id}.json")
    roots = [os.environ.get("CLAUDE_PROJECT_DIR")]
    current = os.path.abspath(cwd or ".")
    while True:
        roots.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return next(
        (
            os.path.join(root, relative)
            for root in roots
            if root and os.path.isfile(os.path.join(root, relative))
        ),
        None,
    )


def _session_task_store(
    session_id: str | None, cwd: str | None
) -> tuple[list[dict], bool]:
    """Normalized native + mytask records and whether every present store parsed."""
    if not session_id:
        return [], False
    records: list[dict] = []
    native_dir = os.path.join(NATIVE_TASKS_DIR, session_id)
    try:
        native_entries = list(os.scandir(native_dir))
    except FileNotFoundError:
        native_entries = []
    except OSError:
        return [], False
    for entry in sorted(native_entries, key=lambda item: item.name):
        try:
            is_task_file = entry.is_file() and entry.name.endswith(".json")
        except OSError:
            return [], False
        if not is_task_file:
            continue
        try:
            with open(entry.path, encoding="utf-8") as stream:
                task = json.load(stream)
        except (OSError, ValueError):
            return [], False
        if not isinstance(task, dict):
            return [], False
        records.append(
            {
                "id": task.get("id", "?"),
                "name": task.get("subject", ""),
                "status": task.get("status"),
            }
        )

    mytask_path = _mytask_store_path(session_id, cwd)
    raw = []
    if mytask_path:
        try:
            with open(mytask_path, encoding="utf-8") as stream:
                raw = json.load(stream)
        except FileNotFoundError:
            raw = []
        except (OSError, ValueError):
            return [], False
    if not isinstance(raw, list):
        return [], False
    for task in raw:
        if not isinstance(task, dict):
            return [], False
        records.append(
            {
                "id": task.get("id", "?"),
                "name": task.get("content", ""),
                "status": task.get("status"),
            }
        )
    return records, True


def _session_has_task_records(session_id: str | None, cwd: str | None) -> bool:
    """Any task record this session, any status; True on doubt (fail-open)."""
    if not session_id:
        return True
    try:
        records, reliable = _session_task_store(session_id, cwd)
    except Exception:
        return True
    return bool(records) if reliable else True


# Tools whose file_path / notebook_path inputs are recorded for path matching.
PATH_RECORDING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _tasks_gated_off(model: str | None) -> bool:
    if not model:
        return False
    try:
        with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as f:
            features = json.load(f).get("cachedGrowthBookFeatures")
        if not isinstance(features, dict) or "tengu_vellum_ash" not in features:
            return False
        gate = features["tengu_vellum_ash"]
        if not isinstance(gate, list) or not gate:
            return False
        return any(isinstance(e, str) and e and e in model for e in gate)
    except Exception:
        return False


def _is_mytask_path(path: str) -> bool:
    normalized = os.path.normpath(path).replace("\\", "/").replace(os.sep, "/")
    return "drafts/tasks/" in normalized and normalized.endswith(".json")


def strip_fences(text: str) -> str:
    # fenced block を先に除去し、 次に inline backtick span を除去 (順序が load-bearing:
    # fence 先除去で inline pass が fence 区切りの裸 ``` を食わない)。 [^`\n] guard で
    # inline pass を行内に限定し改行跨ぎの greedy strip を防ぐ (代償: 改行を含む
    # malformed inline span は strip されず残る — 許容)。
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", " ", text)


SELF_NUMBER_RE = re.compile(r"(?:候補|案|選択肢|パターン)\s?[0-9]")
# ☀ (U+2600) 起点だと U+2300 台の ⌛ ⏰ ⏳ ⏸ が漏れるので、 該当 range を個別に足す。
EMOJI_START_RE = re.compile(
    r"[⌚⌛⏩-⏳⏸-⏺☀-➿\U0001f1e6-\U0001f1ff\U0001f300-\U0001faff]"
)


def _strip_code_and_quotes(text: str) -> str:
    prose = strip_fences(text)
    return "\n".join(
        "" if re.match(r"^\s*>", line) else line for line in prose.splitlines()
    )


def _last_prose_line(text: str) -> str:
    return next(
        (
            line.strip()
            for line in reversed(_strip_code_and_quotes(text).splitlines())
            if line.strip()
        ),
        "",
    )


def _latest_user_prompt(entries: list[dict]) -> str:
    for obj in reversed(entries):
        if obj.get("type") != "user":
            continue
        message = obj.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def _tool_use_blocks(entries: list[dict]):
    for obj in entries:
        if obj.get("type") != "assistant":
            continue
        message = obj.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block


def _waste_keyword_memory_warning(entries: list[dict]) -> str | None:
    user_prompt = _latest_user_prompt(entries)
    # harness の注入形式に依存し、形式変更時はこの除外が静かに効かなくなる。
    if user_prompt.lstrip().startswith(HARNESS_USER_PREFIXES):
        return None
    user_prose = JAPANESE_QUOTED_SPAN_RE.sub(" ", _strip_code_and_quotes(user_prompt))
    match = WASTE_KEYWORD_RE.search(user_prose)
    if match is None:
        return None
    for block in _tool_use_blocks(entries):
        inputs = block.get("input")
        path = inputs.get("file_path") if isinstance(inputs, dict) else None
        if (
            block.get("name") == "Write"
            and isinstance(path, str)
            and PERSISTENCE_PATH_RE.search(path)
        ):
            return None
    return (
        f"waste-keyword-memory: ユーザー発話に「{match.group(0)}」がありますが、"
        "同 turn に memory entry への Write がありません。記録すべき教訓があるかを"
        "一拍考え、必要なら memory-routing の手順で entry 化してください。"
    )


def _question_self_containment_warning(final_text: str) -> str | None:
    final_line = _last_prose_line(final_text)
    if not final_line.endswith(("?", "？")):
        return None
    match = QUESTION_PAST_REFERENCE_RE.search(final_line)
    if match is None:
        return None
    return (
        f"question-self-containment: 最終質問が過去参照表現「{match.group(0)}」に"
        "依存しています。単体で読めるよう書き直してください。template: "
        "「決めてほしいこと N 件」/「各件の 問題 / やること / "
        "承認と却下それぞれの帰結」/「略語と内部呼称を使わない」。"
    )


def _open_task_records(session_id: str | None, cwd: str | None) -> list[dict] | None:
    records, reliable = _session_task_store(session_id, cwd)
    if not reliable:
        return None
    return [record for record in records if record.get("status") in OPEN_TASK_STATUSES]


def _decision_task(record: dict) -> bool:
    name = record.get("name")
    return isinstance(name, str) and bool(DECISION_TASK_RE.search(name))


def _task_listing(records: list[dict]) -> str:
    if not records:
        return "(なし)"
    labels = [
        f"#{record.get('id', '?')} {record.get('name', '')}".strip()
        for record in records
    ]
    listing = ", ".join(labels[:10])
    return listing + (f", 他 {len(labels) - 10} 件" if len(labels) > 10 else "")


def _decision_question_warning(
    final_text: str, session_id: str | None, cwd: str | None
) -> str | None:
    final_line = _last_prose_line(final_text)
    if not final_line.endswith(("?", "？")):
        return None
    open_tasks = _open_task_records(session_id, cwd)
    if open_tasks is None or any(_decision_task(record) for record in open_tasks):
        return None
    return (
        "decision-question-task: 最終行が質問ですが open な decision 型 task "
        f"がありません。open task: {_task_listing(open_tasks)}。"
        "質問と task の対応を自己照合してください。"
    )


def _decision_record_warning(
    user_prompt: str, session_id: str | None, cwd: str | None
) -> str | None:
    prompt = user_prompt.strip()
    if len(prompt) > 20 or SHORT_DECISION_RE.fullmatch(prompt) is None:
        return None
    open_tasks = _open_task_records(session_id, cwd)
    if open_tasks is None:
        return None
    decisions = [record for record in open_tasks if _decision_task(record)]
    if not decisions:
        return None
    return (
        f"decision-record: 短文決裁「{prompt}」と open decision 型 task "
        f"({_task_listing(decisions)}) を検出しました。"
        "決裁内容を台帳 / todos へ記録し、task 状態を更新したか確認してください。"
    )


def _communication_lint_warnings(
    final_text: str, assistant_text: str | None = None
) -> list[str]:
    prose = _strip_code_and_quotes(
        final_text if assistant_text is None else assistant_text
    )
    final_line = _last_prose_line(final_text)
    warnings: list[str] = []
    if (
        final_line
        and not final_line.endswith(("?", "？"))
        and not EMOJI_START_RE.match(final_line)
    ):
        warnings.append(
            "communication-final-line: 最終非空行が絵文字始まりでも "
            "`?` / `？` 終端でもありません。org 規約の最終行形式に直してください。"
        )
    match = SELF_NUMBER_RE.search(prose)
    if match:
        warnings.append(
            f"communication-self-number: 自己採番参照「{match.group(0)}」を検出しました。"
            "番号ではなく選択内容を言い換えてください。"
        )
    return warnings


def _new_warning_families(
    entries: list[dict],
    final_text: str,
    payload: dict,
    assistant_text: str | None = None,
) -> list[str]:
    warnings: list[str] = []
    session_id = payload.get("session_id")
    session_id = session_id if isinstance(session_id, str) else None
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) else None
    try:
        warning = _decision_question_warning(final_text, session_id, cwd)
        if warning:
            warnings.append(warning)
    except Exception:
        pass
    try:
        warning = _decision_record_warning(
            _latest_user_prompt(entries), session_id, cwd
        )
        if warning:
            warnings.append(warning)
    except Exception:
        pass
    try:
        communication = _communication_lint_warnings(final_text, assistant_text)
        if communication:
            warnings.append(" ".join(communication))
    except Exception:
        pass
    try:
        warning = _waste_keyword_memory_warning(entries)
        if warning:
            warnings.append(warning)
    except Exception:
        pass
    try:
        warning = _question_self_containment_warning(final_text)
        if warning:
            warnings.append(warning)
    except Exception:
        pass
    return [
        re.sub(r"\s+", " ", warning).strip()
        for warning in warnings[:NEW_WARNING_FAMILIES_LIMIT]
    ]


_TAIL_BUFSIZE = 128 * 1024  # 実測 2545 turn の mean≈110KB / p75≈119KB を 1 read で覆う


def _is_prompt(obj: dict) -> bool:
    msg = obj.get("message", {})
    return obj.get("type") == "user" and isinstance(msg.get("content"), str)


def _load_tail(
    path: str,
    turns: int | None = 1,
    bufsize: int = _TAIL_BUFSIZE,
    max_bytes: int | None = None,
) -> list[dict]:
    """末尾から turn boundary を turns 個含むまで返す。"""
    try:
        with open(path, "rb") as f:
            pos = f.seek(0, os.SEEK_END)
            floor = max(0, pos - max_bytes) if max_bytes is not None else 0
            pending = b""  # 行頭が手前ブロックにある途中行 (次の読みで結合される)
            tail: list[dict] = []  # newest-first
            seen = 0
            while pos > floor:
                step = min(bufsize, pos - floor)
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
                        if turns is not None and seen >= turns:
                            tail.reverse()
                            return tail
            line = pending.strip()
            if floor == 0 and line:
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
) -> tuple[
    str, str, set[str], list[str], list[str], list[str], bool, float | None, str | None
]:
    """Return current-turn text, tools, paths, commands, git state, prompt time, and model."""
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
        return "", "", set(), [], [], [], False, None, None

    text_parts: list[str] = []
    final_text = ""
    tool_names: set[str] = set()
    tool_paths: list[str] = []
    edited_paths: list[str] = []
    bash_commands: list[str] = []
    has_git_verify = False
    model: str | None = None

    for obj in entries[start_idx:]:
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("model"), str):
            model = msg["model"]
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                final_text = str(block.get("text", ""))
                text_parts.append(final_text)
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
                        if name in {"Edit", "Write"}:
                            edited_paths.append(fp)
                if name == "Bash":
                    cmd = inp.get("command", "")
                    if isinstance(cmd, str):
                        bash_commands.append(cmd)
                        if GIT_VERIFY_RE.search(cmd):
                            has_git_verify = True

    if model is None:
        for obj in reversed(entries):
            if obj.get("type") != "assistant":
                continue
            msg = obj.get("message", {})
            if isinstance(msg, dict) and isinstance(msg.get("model"), str):
                model = msg["model"]
                break

    return (
        "\n".join(text_parts),
        final_text,
        tool_names,
        tool_paths,
        edited_paths,
        bash_commands,
        has_git_verify,
        prompt_epoch,
        model,
    )


def _artifact_was_run(path: str, bash_commands: list[str]) -> bool:
    basename = os.path.basename(path).lower()
    module = os.path.splitext(basename)[0]
    for command in bash_commands:
        lowered = command.lower()
        if basename in lowered:
            return True
        module_named = module and re.search(
            rf"(?<![\w]){re.escape(module)}(?![\w])", lowered
        )
        if re.search(r"\b(unittest|pytest)\b", lowered) and module_named:
            return True
    return False


def _declare_proceed_active(entries: list[dict], now: float) -> bool:
    """declare-and-proceed が現 turn 内 かつ直近 SKILL_WINDOW_SECONDS 以内に invoke 済か (declare_and_proceed_gate._skill_active と同一窓)。"""
    start_idx = -1
    for i in range(len(entries) - 1, -1, -1):
        obj = entries[i]
        if obj.get("type") == "user":
            msg = obj.get("message", {})
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                start_idx = i + 1
                break
    if start_idx == -1:
        return False
    cutoff = now - SKILL_WINDOW_SECONDS
    for obj in entries[start_idx:]:
        if obj.get("type") != "assistant":
            continue
        ep = _parse_ts(obj.get("timestamp"))
        if ep is not None and ep < cutoff:
            continue  # 現 turn 内でも 5 分以上前は drop
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "Skill"
            ):
                inp = block.get("input") or {}
                if isinstance(inp, dict) and inp.get("skill") == DECLARE_PROCEED_SKILL:
                    return True
    return False


def _handoff_docs_awaiting_marker(
    payload: dict, text: str, prompt_epoch: float | None
) -> list[str]:
    """宣言済 wind-down session で当 turn に mtime が動いた handoff doc (marker 未出力のもの)。
    mtime 観測ゆえ Bash / python / subagent 経由の書込も捕捉。 判定不能は [] (fail-open)。"""
    if _handoff_mod is None or prompt_epoch is None:
        return []
    try:
        session_id = str(payload.get("session_id") or "")
        if not session_id or not _handoff_mod.wind_down_declared(session_id):
            return []
        touched = [
            p
            for p in _handoff_mod.handoff_docs(str(payload.get("cwd") or ""))
            if os.path.getmtime(p) >= prompt_epoch
        ]
        if not touched:
            return []
        scan = _handoff_mod.tail_text(str(payload.get("transcript_path") or "")) + text
        if _handoff_mod.has_handoff_marker(scan, session_id):
            return []
        return touched
    except Exception:
        return []


WORK_FILE_RE = re.compile(r"^Work file:\s*(.*)$")
# 見出し名でなく参照で判定する — 名前一致は todos block の改名だけで誤検出に変わる。
PATH_TOKEN_RE = re.compile(r"`([^`\s]+\.[A-Za-z0-9]{1,5})`")
# doc 本文の token は「path らしさ」で絞る — URL / mail / glob / placeholder を除く。
_NON_PATH_CHARS = "*?[]<>@"
_HEADING_RE = re.compile(r"^#{1,6}\s")


def _looks_like_path(token: str) -> bool:
    return not token.startswith("/") and not any(c in token for c in _NON_PATH_CHARS)


def _required_reading_tokens(text: str) -> set[str]:
    """`### 必読` 節の token だけを実在検査の対象にする (SKILL.md が Read 推奨 file と定義する唯一の節)。"""
    tokens: set[str] = set()
    inside = False
    for line in text.splitlines():
        if _HEADING_RE.match(line):
            inside = line.startswith("### ") and line[4:].lstrip().startswith("必読")
        elif inside:
            tokens.update(PATH_TOKEN_RE.findall(line))
    return tokens


def _tracked_basenames(cwd: str) -> set[str]:
    """git 管理下 file の basename 索引。 root 直下に無い参照を救う。"""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "ls-files", "-z"],
            capture_output=True,
            timeout=5,
            check=True,
        ).stdout.decode("utf-8", "replace")
    except Exception:
        return set()
    return {os.path.basename(p) for p in out.split("\0") if p}


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _handoff_todos_sync_warnings(cwd: str) -> list[str]:
    """どの todos block からも指されない handoff doc と、 消えた path を指す doc の警告。
    判定不能は [] (fail-open)。 出所 2026-08-23: e905965 が doc と task を消し section を残した。"""
    if _handoff_mod is None:
        return []
    try:
        docs = _handoff_mod.handoff_docs(cwd)
        todos = _read_text(os.path.join(cwd, "todos.md")) if docs else None
        if not docs or todos is None:
            return []
        tracked = {
            os.path.basename(token)
            for line in todos.splitlines()
            if (m := WORK_FILE_RE.match(line))
            for token in PATH_TOKEN_RE.findall(m.group(1))
        }
        warnings: list[str] = []
        basenames: set[str] | None = None
        for doc in docs:
            name = os.path.basename(doc)
            if name not in tracked:
                warnings.append(
                    f"handoff-todos-sync: {name} を `Work file:` で指している todos.md の "
                    "task block がありません。 作業が終わっているなら doc を削除し、 続くなら "
                    "対応 block の Work file にこの doc を書いてください。"
                )
                continue
            unresolved = {
                token
                for token in _required_reading_tokens(_read_text(doc) or "")
                if _looks_like_path(token)
                and not os.path.exists(os.path.join(cwd, token))
            }
            if unresolved and basenames is None:
                basenames = _tracked_basenames(cwd)  # 索引は cwd 単位で不変。
            missing = sorted(
                token
                for token in unresolved
                if os.path.basename(token) not in (basenames or ())
            )
            if missing:
                warnings.append(
                    f"handoff-todos-sync: {name} が実在しない path "
                    f"{'・'.join(missing)} を参照しています。 追跡対象が消えた section は "
                    "再開に使えないので、 参照を更新するか section ごと削除してください。"
                )
        return warnings
    except Exception:
        return []


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
    final_text: str,
    tool_names: set[str],
    tool_paths: list[str],
    edited_paths: list[str],
    bash_commands: list[str],
    has_git_verify: bool,
    declare_active: bool,
    model: str | None = None,
    cwd: str | None = None,
    worktree_warnings: list[str] | None = None,
    wind_down_open_tasks: list[str] | None = None,
    final_text_authoritative: bool = True,
    session_task_records: bool = True,
    handoff_doc_without_marker: list[str] | None = None,
) -> tuple[int, list[str], list[str]]:
    """Return (exit_code, warnings, blocking)."""
    warnings: list[str] = []
    blocking: list[str] = []
    stripped = strip_fences(text)  # fenced-block を除いた判定用 (各チェックで共有)

    if _court_contaminated(text):
        warnings.append(
            "court-guard: stray token / invoke-leak を検出 — court バグ汚染の疑い。"
            "session reset 推奨 (#64108)"
        )

    warnings.extend(
        _worktree_cleanup_warnings(cwd)
        if worktree_warnings is None
        else worktree_warnings
    )

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

    # bang-prefix-host-escape (block, no pairing): `!` は sandbox の外に出る手段ではない
    bang = _bang_host_escape(text)
    if bang:
        blocking.append(bang)

    # order-question-to-user (block, no pairing): 順序質問の user 投げは judgment 回避
    m = ORDER_QUESTION_RE.search(stripped)
    if m:
        blocking.append(
            f"order-question-to-user: 「{m.group(0)}」 と順序質問を user に投げています。 "
            f"「どちらを先に」 系は (1) 両方やる → 順序不問で自決 / "
            f"(2) 順序に正解あり → 自分で決まる / (3) どちらでも OK → 最初の方から、 "
            f"の 3 分解で常に自決可能で user に valuable answer を求めることはできません "
            f"(declare-and-proceed skill, feedback_order_questions_are_avoidable)。 "
            f"該当文を delete し、 3 分解 self-check して自分で proceed してから再出力してください。"
        )

    # confirm/routing-to-user (block unless declare-and-proceed invoked this turn)
    if not declare_active:
        m = CONFIRM_RE.search(stripped) or ROUTING_RE.search(stripped)
        if m:
            blocking.append(
                f"declare-and-proceed (prose): 「{m.group(0)}」 と decidable な確認/routing 質問を "
                f"散文で user に投げていますが、 当 turn かつ直近 5 分以内に declare-and-proceed skill の "
                f"invoke がありません (5 分以上前の同 turn invoke は stale ゆえ要 re-invoke。 "
                f"AskUserQuestion は declare_and_proceed_gate が PreToolUse で gate しますが "
                f"散文は Stop でしか捕捉できません)。 /declare-and-proceed を invoke し 3-check "
                f"(material が code/log/config/doc で取れるか / default で進めるか / parallel 両立か) を "
                f"verbalize → いずれか yes なら自分で決めて proceed、 genuine な user-taste / design / "
                f"priority / 不可逆 op の pre-approval なら質問のまま再出力 (skill invoke 後は本 gate を "
                f"通過) してください。"
            )

    # euphemism-for-error (block, no pairing): 誤りを相手の読み方の問題にすり替えない
    m = EUPHEMISM_RE.search(stripped)
    if m:
        blocking.append(
            "euphemism-for-error: 「誤解」 系の語を検出しました。 「誤解を招く」 "
            "「誤解されやすい」 は自分の誤りを相手の読み方の問題にすり替える言い換えで、 "
            "読み手には ごまかし に見えます。 間違っていたなら 「〜は間違いだった」 と "
            "名指しし、 正しい事実を 1 行で併記してください。 そのうえで、 ごまかしが "
            "無いこと — 要件自体が不成立だったのか / 記述だけが不正確だったのか / "
            "実装は正しかったのか — を切り分けて verbalize してから再出力してください。 "
            "user の発言を引用する等で語そのものが要る場合は fence 内に置いてください。"
        )

    # continuation-claim (block future performance claim in final assistant message)
    continuation_match = (
        _continuation_claim(final_text) if final_text_authoritative else None
    )
    if continuation_match:
        blocking.append(
            f"continuation-claim: 「{continuation_match.group(0)}」 — 未来形の遂行宣言。"
            f"遂行文は 3 形式のみ — ①実行中 (検証可能な id/path 付き現在形) "
            f"②完了 (証跡付き) ③停止 (「ここで停止。再開条件 = Y」)。"
            f"発話時点で真偽が確定しない文は書かない。該当文を 3 形式のいずれかに書き直して"
            f"再出力してください (これから作業するなら、宣言でなく実際に tool 呼び出しで開始して"
            f"から ① の形で書く)"
        )

    # intent-without-task (block if work-execution declaration without task tool)
    # final 文の identity は turn 内の全出現を落とし、中間文だけを従来どおり検査する。
    intent_text = _without_final_sentence_identities(text, final_text)
    m = INTENT_DECLARE_RE.search(intent_text)
    # mytask 記録は gate 検出と無関係に常に有効 — gate リスト未収載の新モデルが
    # native Task tool を持たない session で FP block になる (fable-5 実測 2026-08-19)。
    mytask_recorded = bool(tool_names & MYTASK_MCP_TOOLS) or any(
        _is_mytask_path(p) for p in edited_paths
    )
    if m and not (tool_names & TASK_TOOLS) and not mytask_recorded:
        if _tasks_gated_off(model):
            blocking.append(
                f"intent-without-task: 作業遂行宣言「{m.group(0)}」を検出。現行モデルは "
                f"tengu_vellum_ash gate で Task ツールが無効化されています。mytask skill に従い "
                f"MCP で作業を記録してから再出力してください。"
            )
        else:
            blocking.append(
                f"intent-without-task: 作業遂行宣言「{m.group(0)}」を検出しましたが、このターンに"
                f" TaskCreate/TaskUpdate/TodoWrite (または mytask MCP) が記録されていません。"
                f" System §計画と遂行: 全作業項目を大小に関わらず Task で計画・追跡。"
                f" TaskCreate (native Task tool が無い session では mytask MCP) で作業を"
                f"登録してから再出力してください。"
            )

    # work-without-task (block substantive edits while the session store is empty)
    if (
        not session_task_records
        and len(edited_paths) >= WORK_WITHOUT_TASK_MIN_EDITS
        and not (tool_names & TASK_TOOLS)
        and not (tool_names & MYTASK_MCP_TOOLS)
        and not any(_is_mytask_path(p) for p in edited_paths)
    ):
        blocking.append(
            f"work-without-task: このターンで {len(edited_paths)} 件の Edit/Write を"
            f"実行しましたが、session の Task 記録が 1 件もありません。System §計画と遂行"
            f"「まず最初の依頼を Task に登録する」の store 側検査です (遂行宣言の文言に"
            f"依存しない)。TaskCreate (Task tool が gate 中なら mytask MCP) で現在の"
            f"作業項目を登録してから再出力してください。"
        )

    # open-tasks-at-wind-down (block if a wind-down prompt leaves open tasks)
    if wind_down_open_tasks:
        listed = ", ".join(wind_down_open_tasks[:10])
        blocking.append(
            f"open-tasks-at-wind-down: セッション終了示唆の prompt に対し open な Task が "
            f"{len(wind_down_open_tasks)} 件残っています ({listed})。 セッション終了で "
            f"Task list は死蔵され、 次 session からは見えません。 handoff skill の "
            f"Task 残処理に従い、 次 session へ持ち越す項目は todos.md の parent block へ "
            f"転記 (詳細があれば handoff doc も更新) し、 全 open Task を close してから "
            f"再出力してください。"
        )

    # handoff-doc-without-marker (declared wind-down + doc update this turn without the marker)
    if handoff_doc_without_marker:
        names = ", ".join(os.path.basename(p) for p in handoff_doc_without_marker)
        # 文面は意図的に冗長 (deny-wording 規律)・trim 禁止。
        blocking.append(
            f"handoff-doc-without-marker: この session は終了示唆 (wind-down) 宣言済みで、 "
            f"当 turn に handoff doc ({names}) が更新されましたが、 handoff 完了 marker が "
            f"未出力です。 handoff skill の protocol を完了してください — cross-check readback "
            f"(fresh subagent) を経て、 session-end message の 1 行目に full session id 入りの "
            f"marker 行 (~~~~ <曜日>, <日時> Handoff (<full sid>) ~~~~) を出力して再出力。 "
            f"まだ終了せず作業を継続する (途中の進捗反映) 場合は、 偽の marker を出さず、 "
            f"継続の旨を 1 文添えて再出力してください。"
        )

    # deferral (warning-only)
    m = DEFERRAL_RE.search(text)
    if m:
        todos_via_tool = bool(tool_names & TASK_TOOLS)
        if not todos_via_tool:
            warnings.append(
                f"deferral detected: 「{m.group(0)}」 と発話したが当ターンで "
                f"TaskCreate / TaskUpdate / TodoWrite の呼び出しが記録されていません "
                f"(System §計画と遂行)。"
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
        cmd = HOST_CMD_RE.search(stripped)
        if cmd:
            warnings.append(
                f"provide-user-instructions: 手動実行を依頼する文脈 (「{instr.group(0)}」) "
                f"がありますが host コマンド (「{cmd.group(0)}」) が fenced code block の "
                f"外にあります (provide-user-instructions skill)。 独立した fenced code "
                f"block に完全 path で置くと user がそのままコピペ実行できます。 inline "
                f"backtick は readability 用で実行用ではありません。"
            )

    # verify-before-claim positive side (warning-only): completeness claim w/o evidence
    m = POS_CLAIM_RE.search(stripped)
    if m and not (tool_names & EVIDENCE_TOOLS):
        warnings.append(
            f"verify-before-claim (positive): 「{m.group(0)}」 と網羅・完了の self-claim "
            f"を発したが当ターンで Read / Grep / Glob / WebSearch / WebFetch のいずれも "
            f"使われていません (verify-before-claim skill)。 入口 file 1 本 / INDEX 行だけ "
            f"読んで網羅と framing する LLM regression の典型です。 参照先の body file 群を "
            f"実体まで読んだか self-check し、 未読があれば 「INDEX 上位 N entry のみ確認、 "
            f"残りは未読」 等と scope を明示してください。"
        )

    # honest-attribution (warning-only): 誤 pattern を ownership ぼかしで attribute
    mb = HONEST_BLUR_RE.search(text)
    if mb:
        near = text[max(0, mb.start() - 60) : mb.end() + 60]
        if HONEST_WRONG_RE.search(near):
            warnings.append(
                f"honest-attribution: 「{mb.group(0)}」 と誤 pattern を ownership "
                f"ぼかし的に attribute している可能性 (attribute-existing-issues skill)。 "
                f"persisted text (commit message / memory / doc) では自セッションの "
                f"action を 「既存」「繰り越し」「reasonable default」 で曖昧化せず、 "
                f"pre-existing pattern に対する自分の行為を honest に名指してください。"
            )

    # edited-executable-not-run (warning-only): done claim after an unobserved edit
    if DONE_CLAIM_RE.search(final_text):
        executable_paths = [p for p in edited_paths if EXECUTABLE_ARTIFACT_RE.search(p)]
        unrun_paths = [
            p for p in executable_paths if not _artifact_was_run(p, bash_commands)
        ]
        if unrun_paths:
            warnings.append(
                f"edited-executable-not-run: {', '.join(os.path.basename(p) for p in unrun_paths)} "
                f"を Edit/Write して done-claim していますが、 同 turn の Bash で実行した "
                f"記録がありません。 実行して結果を観測してから done を出してください。"
            )

        ui_edited = any(UI_ARTIFACT_RE.search(p) for p in edited_paths)
        screenshot_used = "browser_take_screenshot" in tool_names or any(
            "screenshot" in command.lower() for command in bash_commands
        )
        if ui_edited and not screenshot_used:
            warnings.append(
                "ui-edit-without-screenshot: UI file を Edit/Write して done-claim していますが、 "
                "同 turn に screenshot の記録がありません。 screenshot で表示を観測してから "
                "done を出してください。"
            )

    exit_code = 2 if blocking else 0
    return exit_code, warnings, blocking


def _run(payload: dict) -> tuple[int, float | None, str, list[str]]:
    # Returns (exit_code, prompt_epoch, text, surfaced_warnings); main() feeds text/warnings onward.
    if not isinstance(payload, dict):
        return 0, None, "", []
    stop_hook_active = bool(payload.get("stop_hook_active"))
    warning_stop_allowed = stop_hook_active or _stop_latch_claim(payload, ".wt")
    worktree_warnings = _worktree_cleanup_warnings(payload.get("cwd"))
    if worktree_warnings and not warning_stop_allowed:
        worktree_warnings = []
    codex_warnings = []
    if stop_hook_active or _stop_latch_claim(payload, _CODEX_LATCH_SUFFIX):
        codex_warnings = _codex_shared_write_warnings(payload)
    worktree_warnings += codex_warnings
    if stop_hook_active or _stop_latch_claim(payload, ".hts"):
        worktree_warnings += _handoff_todos_sync_warnings(str(payload.get("cwd") or ""))
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0, None, "", worktree_warnings
    entries = _load_tail(transcript_path)
    if not entries:
        return 0, None, "", worktree_warnings
    (
        text,
        final_text,
        tool_names,
        tool_paths,
        edited_paths,
        bash_commands,
        has_git_verify,
        prompt_epoch,
        model,
    ) = _current_turn(entries)
    # Claude Code が Stop hook を invoke する時点で最新 assistant text はまだ transcript に
    # flush されていない (v2.1.47+ で payload に last_assistant_message が提供されたのはこの
    # gap を埋めるため)。 transcript 由来 text に concat して全 family の取りこぼしを防ぐ。
    last_msg = payload.get("last_assistant_message")
    final_text_authoritative = isinstance(last_msg, str) and bool(last_msg)
    if isinstance(last_msg, str) and last_msg:
        text = (text + "\n" + last_msg) if text else last_msg
        final_text = last_msg
    if not text:
        return 0, prompt_epoch, "", worktree_warnings
    declare_active = _declare_proceed_active(entries, time.time())
    # wind-down 判定は prompt を受け取れる UserPromptSubmit hook が記録済 (transcript は見ない)。
    wind_down_tasks: list[str] = []
    session_id = str(payload.get("session_id") or "")
    if _handoff_mod is not None and _handoff_mod.wind_down_signalled(session_id):
        wind_down_tasks = _handoff_mod.open_tasks(
            session_id, str(payload.get("cwd") or "")
        )
    exit_code, warnings, blocking = _check(
        text,
        final_text,
        tool_names,
        tool_paths,
        edited_paths,
        bash_commands,
        has_git_verify,
        declare_active,
        model,
        cwd=payload.get("cwd"),
        worktree_warnings=worktree_warnings,
        wind_down_open_tasks=wind_down_tasks,
        final_text_authoritative=final_text_authoritative,
        session_task_records=_session_has_task_records(
            session_id, str(payload.get("cwd") or "")
        ),
        handoff_doc_without_marker=_handoff_docs_awaiting_marker(
            payload, text, prompt_epoch
        ),
    )
    new_warnings: list[str] = []
    if warning_stop_allowed:
        new_warnings = _new_warning_families(entries, final_text, payload, text)
        warnings.extend(new_warnings)
    surfaced_warnings = worktree_warnings + new_warnings
    if exit_code == 2 and stop_hook_active:
        _deliver_stop_feedback(warnings, blocking, surfaced_warnings, demoted=True)
        return 0, prompt_epoch, text, surfaced_warnings
    _deliver_stop_feedback(warnings, blocking, surfaced_warnings)
    if exit_code != 0:
        # block した turn は main() の bonus 経路に届かず継続 Stop も gate される — 出すならここだけ。
        try:
            muted = _muted_memory_at_stop(payload, text)
        except Exception:
            muted = None
        if muted:
            sys.stderr.write(muted + "\n")
    return exit_code, prompt_epoch, text, surfaced_warnings


def _deliver_stop_feedback(
    warnings: list[str],
    blocking: list[str],
    surfaced_warnings: list[str],
    demoted: bool = False,
) -> None:
    surfaced = set(surfaced_warnings)
    feedback = [
        ("advise-once (block demoted to pass): " if demoted else "") + line
        for line in blocking
    ]
    if blocking and not demoted:
        feedback.extend(warnings)
    else:
        feedback.extend(line for line in warnings if line not in surfaced)
    if feedback:
        sys.stderr.write("\n".join(feedback) + "\n")


def _stop_latch_key(payload: dict, suffix: str = ".surf") -> tuple[str, str] | None:
    """(turn key, latch-file path) or None; turn key = the .turns count, which bumps only at a clean turn end so it stays constant across a turn's Stops (incl. continuations).
    suffix namespaces the latch file per feature-family (worktree-cleanup vs memory-surface no longer share one file)."""
    try:
        path = _counter_path(payload)  # session-id fallback may makedirs -> OSError
    except OSError:
        return None
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().split()[0], path + suffix
    except (OSError, IndexError):
        # .turns は clean な turn 終了で初めて生まれる — 不在を欠測にすると初回 turn の latch が no-op。
        return "0", path + suffix


def _stop_latch_claim(payload: dict, suffix: str = ".surf") -> bool:
    """suffix ごとに同一 turn の最初の Stop だけを排他的に取得し、取得不能時は True へ fail-open する。"""
    k = _stop_latch_key(payload, suffix)
    if k is None:
        return True
    key, lpath = k
    try:
        fd = os.open(lpath, os.O_RDWR | os.O_CREAT, 0o644)
        with os.fdopen(fd, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            if f.read().strip() == key:
                return False
            f.seek(0)
            f.truncate()
            f.write(key)
    except OSError:
        return True
    return True


def _memory_surface_at_stop(payload: dict, text: str) -> str | None:
    """Regex-pass path: a Stop additionalContext reason surfacing the top memory entry for the turn's output `text`, else None; fires at most once/turn (stop_hook_active gate + counter latch + throttle) and is fully fail-open."""
    if _memory_surface_mod is None or payload.get("stop_hook_active"):
        return None
    if not text or not text.strip():
        return None
    # Turn-scoped latch: guarantee max-once even if the runtime does not set
    # stop_hook_active on the additionalContext continuation (belt to that gate).
    if not _stop_latch_claim(payload):
        return None
    session_id = payload.get("session_id") or ""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    project_id = _memory_surface_mod._encoded_project_id(cwd)
    try:
        model = _memory_surface_mod._resolve_model(payload)
    except Exception:
        model = None  # 旧 deploy の memory_surface に helper 不在でも fail-open
    try:
        picks = _memory_surface_mod.surface_for_text(
            text, session_id, project_id, 1, model
        )
    except Exception:
        return None
    if not picks:
        return None
    file_path, reminder, _score = picks[0]
    display = reminder or "(reminder 未設定)"
    return (
        "<memory-surface>\n"
        f"今ターンの出力に関連する過去の教訓: {display} 詳細: {file_path}\n"
        "完了前に今の応答がこの教訓に抵触しないか確認し、 抵触するなら修正してから完了して "
        "ください (抵触しなければそのまま完了して構いません)。\n"
        "</memory-surface>"
    )


def _bounded(call):
    """`call()` の値、 または timeout / 例外なら None。 daemon thread なので居残っても Stop の終了は待たされない。"""
    out: list = []

    def run():
        # thread 内の例外は excepthook が traceback を stderr に出す — 旧 deploy の
        # memory_surface に helper が無いだけで Stop が壊れて見える。 黙って諦める。
        try:
            out.append(call())
        except Exception:
            pass

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(_SEARCH_TIMEOUT_SECONDS)
    return out[0] if out else None


def _situation_window(text: str, match: re.Match[str]) -> str:
    """否定の周辺文が状況語を持つ — 一致 phrase 単体では検索語が痩せる。"""
    lo, hi = max(0, match.start() - 120), min(len(text), match.end() + 120)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


def _muted_memory_at_stop(payload: dict, text: str) -> str | None:
    """Wall-declaration path: a Stop additionalContext reason naming the top entry the model filter muted, else None; fires at most once/turn and is fully fail-open."""
    if _memory_surface_mod is None or payload.get("stop_hook_active"):
        return None
    stripped = strip_fences(text or "")
    m = WALL_DECLARATION_RE.search(stripped)
    if not m or not _stop_latch_claim(payload, _MUTED_LATCH):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()

    surface = _memory_surface_mod

    def lookup():
        return (
            surface._resolve_model(payload),
            surface.search_unfiltered(
                _situation_window(stripped, m),
                surface._encoded_project_id(cwd),
            ),
        )

    # 旧 deploy に helper が無ければ例外、 DB が返らなければ hang — 後者に except は効かない。
    found = _bounded(lookup)
    if found is None:
        return None
    model, hits = found
    if not model or not hits:
        return None
    muted = [h for h in hits if h[0] >= MUTED_FLOOR and model not in h[1].split()]
    if not muted:
        return None
    _score, models, path, reminder = muted[0]
    return (
        "<muted-memory>\n"
        f"「{m.group(0)}」 と結論していますが、 この状況に一致する過去の教訓が models: に "
        f"{model} を持たないため surface されていません (models={models}): "
        f"{reminder or '(reminder 未設定)'} 詳細: {path}\n"
        "読んでから結論を出し直してください。 今の状況にも当てはまるなら memory-routing skill の "
        "Tag propagation で models: に自分の tag を追記し、 当てはまらなければそのまま完了して "
        "構いません (「効きそうだから」 で tag を盛らない)。\n"
        "</muted-memory>"
    )


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
        exit_code, prompt_epoch, text, worktree_warnings = _run(payload)
    except Exception:
        # fail-open: an enforcement glitch never blocks the turn.
        exit_code, prompt_epoch, text, worktree_warnings = 0, None, "", []
    if exit_code != 0:
        return exit_code  # regex enforcement blocked — unchanged path, no marker/memory
    # regex passed: surface one memory entry for the assistant's own output (if any) and
    # inject it via Stop additionalContext, which keeps the turn going (v2.1.163+).
    try:
        reason = _memory_surface_at_stop(payload, text)
    except Exception:
        reason = None
    try:
        muted = _muted_memory_at_stop(payload, text)
    except Exception:
        muted = None
    # surfaced warnings ride the same additionalContext channel so the model actually sees them.
    wt_text = "\n\n".join(worktree_warnings)
    combined = "\n\n".join(p for p in (reason, muted, wt_text) if p)
    if combined:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "Stop",
                        "additionalContext": combined,
                    },
                    "systemMessage": combined,
                },
                ensure_ascii=False,
            )
        )
        return 0
    # No memory surfacing → genuine turn end: the turn's single counter bump + marker.
    try:
        _emit_turn_marker(payload, prompt_epoch)
    except Exception:
        pass
    return 0


_TEST_CACHE_PATCHES: list = []


def setUpModule():
    """latch を実 HOME の cache から隔離する — 共有すると並行実行が互いを偽 fail させる。"""
    import tempfile
    from unittest import mock

    patch = mock.patch.dict(
        os.environ, {"XDG_CACHE_HOME": tempfile.mkdtemp(prefix="stop-cache-")}
    )
    patch.start()
    _TEST_CACHE_PATCHES.append(patch)


def tearDownModule():
    while _TEST_CACHE_PATCHES:
        _TEST_CACHE_PATCHES.pop().stop()


class TurnMarkerTest(unittest.TestCase):
    """Turn-marker unit tests. Run: python3 -m unittest stop_checks"""

    def test_counter_path_honours_xdg_cache_home(self):
        """session_id だけの payload でも latch は XDG_CACHE_HOME 配下に落ちる。"""
        import tempfile
        from unittest import mock

        cache = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}):
            path = _counter_path({"session_id": "sid"})

        assert path is not None
        self.assertTrue(path.startswith(cache), path)

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
        text, final, _n, _p, _e, _b, _g, pe, model = _current_turn(
            [self._user(), self._asst("done.")]
        )
        self.assertEqual(text, "done.")
        self.assertEqual(final, "done.")
        self.assertEqual(pe, _parse_ts(self.TS))
        self.assertIsNone(model)
        no_ts = [{"type": "user", "message": {"content": "x"}}, self._asst("y")]
        self.assertIsNone(_current_turn(no_ts)[7])
        tool_only = [
            {"type": "user", "message": {"content": [{"type": "tool_result"}]}},
            self._asst("y"),
        ]
        self.assertEqual(
            _current_turn(tool_only), ("", "", set(), [], [], [], False, None, None)
        )

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
                _run({"transcript_path": blk, "stop_hook_active": False})[:2],
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
        self.assertEqual(_run("nope"), (0, None, "", []))  # ty: ignore[invalid-argument-type]
        self.assertEqual(_run({}), (0, None, "", []))


class EnforcementFamilyTest(unittest.TestCase):
    """H3 evaluative regression + H4 confirm/routing gate. Run: python3 -m unittest stop_checks"""

    @staticmethod
    def _c(
        text,
        tools=None,
        paths=None,
        commands=None,
        final_text=None,
        final_text_authoritative=True,
        declare_active=False,
        model=None,
    ):
        return _check(
            text,
            text if final_text is None else final_text,
            set(tools or []),
            list(paths or []),
            list(paths or []),
            list(commands or []),
            False,
            declare_active,
            model,
            final_text_authoritative=final_text_authoritative,
        )

    def _blk(self, *a, **k):
        return self._c(*a, **k)[2]

    # --- continuation-claim ---
    def test_continuation_claim_blocks_declared_cases(self):
        for value in (
            "レビューが終わったら実装します",
            "完了通知が来たら対応します",
            "r57 が終わり次第、着手します",
            "このまま自走を続けます",
        ):
            with self.subTest(value=value):
                code, _warnings, blocking = self._c(value)
                self.assertEqual(code, 2)
                self.assertTrue(any("continuation-claim" in item for item in blocking))

    def test_continuation_claim_allows_grounded_forms(self):
        for value in (
            "ここで停止します。再開条件 = 完了通知",
            "実行中です (job task-x・sentinel abc)",
        ):
            with self.subTest(value=value):
                self.assertEqual(self._c(value)[0], 0)

    def test_continuation_claim_allows_question_and_conditional_offer(self):
        for value in (
            "先に deploy しますか?",
            "必要なら test を追加します",
            "ご希望なら詳細を説明します",
            "必要に応じて調整します",
        ):
            with self.subTest(value=value):
                self.assertEqual(self._c(value)[0], 0)

    def test_continuation_claim_allows_multiline_choice_blocks(self):
        for value in (
            "必要に応じて以下を実施します:\n- test を追加します\n- doc を修正します",
            "ご希望なら次を対応できます。\n1. lint を修正します\n2. README を追加します",
            "必要なら:\n- test を追加します",
        ):
            with self.subTest(value=value):
                self.assertEqual(self._c(value)[0], 0)

    def test_continuation_claim_does_not_treat_bare_choice_words_as_condition(self):
        for value in (
            "ご希望の通り、このまま自走を続けます",
            "ご要望に沿って進めます",
            "希望的観測は避けます — 検証は済んだので、このまま実装を進めます",
        ):
            with self.subTest(value=value):
                self.assertEqual(self._c(value)[0], 2)

    def test_continuation_claim_duplicate_final_identity_is_removed_from_intent(self):
        final = "必要なら test を追加します"
        self.assertEqual(self._c(final + "\n" + final, final_text=final)[0], 0)

    def test_continuation_claim_allows_stop_lines(self):
        for value in (
            "ここで停止します。再開条件 = 完了通知が来たら再開します",
            "ここで停止します。再開条件 = r57 完了。その時点で着手します",
        ):
            with self.subTest(value=value):
                self.assertEqual(self._c(value)[0], 0)
        self.assertEqual(self._c("再開します")[0], 2)

    def test_continuation_claim_allows_explanations_tables_and_verb_lists(self):
        values = (
            "strip_fences は fence を空白に置換します",
            "この hook は該当行を削除します",
            "| input | result |\n|---|---|\n| x | 進めます |",
            "1. 進めます\n2. 着手します\n3. 対応します",
            "検出語は 進めます / 続けます / 着手します の 3 つです",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(self._c(value)[0], 0)

    def test_continuation_claim_question_tail_allows_sentence_particle(self):
        self.assertEqual(self._c("先に deploy しますかね?")[0], 0)
        blocking = self._blk("先に deploy しますかね?\n完了", final_text="完了")
        self.assertFalse(any("intent-without-task" in item for item in blocking))

    def test_continuation_claim_allows_inline_quote(self):
        self.assertEqual(self._c("引用は `進めます` です")[0], 0)

    def test_continuation_claim_uses_only_final_text(self):
        blocking = self._blk(
            "中間では実装します\n完了しました",
            final_text="完了しました",
        )
        self.assertFalse(any("continuation-claim" in item for item in blocking))

    def test_continuation_claim_final_identity_is_not_intent_duplicate(self):
        blocking = self._blk("実装します")
        self.assertEqual(
            [item.split(":", 1)[0] for item in blocking],
            ["continuation-claim"],
        )

    def test_continuation_claim_keeps_independent_intermediate_intent(self):
        blocking = self._blk("まず修正します\n進めます", final_text="進めます")
        families = [item.split(":", 1)[0] for item in blocking]
        self.assertIn("continuation-claim", families)
        self.assertIn("intent-without-task", families)

    def test_continuation_claim_message_keeps_three_forms(self):
        blocking = self._blk("このまま作業を続けます")
        message = next(item for item in blocking if "continuation-claim" in item)
        self.assertIn("①実行中", message)
        self.assertIn("②完了", message)
        self.assertIn("③停止", message)

    def test_continuation_claim_advise_once(self):
        import io
        import tempfile
        from contextlib import redirect_stderr

        transcript = os.path.join(tempfile.mkdtemp(), "turn.jsonl")
        entries = [
            {"type": "user", "message": {"content": "continue"}},
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "このまま自走を続けます"}]
                },
            },
        ]
        with open(transcript, "w", encoding="utf-8") as stream:
            for entry in entries:
                stream.write(json.dumps(entry) + "\n")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = _run(
                {
                    "transcript_path": transcript,
                    "stop_hook_active": True,
                    "last_assistant_message": "このまま自走を続けます",
                }
            )[0]
        self.assertEqual(code, 0)
        self.assertIn("continuation-claim", stderr.getvalue())

    def test_continuation_claim_requires_authoritative_last_message(self):
        import io
        import tempfile
        from contextlib import redirect_stderr

        transcript = os.path.join(tempfile.mkdtemp(), "turn.jsonl")
        entries = [
            {"type": "user", "message": {"content": "implement"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "TaskCreate",
                            "input": {"subject": "implementation"},
                        },
                        {"type": "text", "text": "では実装します"},
                    ]
                },
            },
        ]
        with open(transcript, "w", encoding="utf-8") as stream:
            for entry in entries:
                stream.write(json.dumps(entry) + "\n")
        with redirect_stderr(io.StringIO()):
            code = _run({"transcript_path": transcript})[0]
        self.assertEqual(code, 0)

    # --- H3: evaluative-terms (lost /tmp smoke, now tracked) ---
    def test_evaluative_blocks_without_evidence(self):
        code, _w, blk = self._c("これは大改造になります")
        self.assertEqual(code, 2)
        self.assertTrue(any("evaluative-term" in b for b in blk))

    def test_evaluative_freepass_with_evidence(self):
        blk = self._blk("これは大改造になります", tools=["Read"])
        self.assertFalse(any("evaluative-term" in b for b in blk))

    def test_evaluative_adjective_excluded(self):
        # 影響大きい (形容詞) は除外、 影響大 (label) は発火。
        self.assertFalse(any("evaluative" in b for b in self._blk("影響大きいと思う")))
        self.assertTrue(any("evaluative" in b for b in self._blk("影響大と評価")))

    # --- bang-prefix-host-escape: `!` は sandbox の外に出る手段ではない ---
    def test_bang_prefix_host_request_blocks(self):
        for q in (
            "この 2 行を `!` を付けて流していただけますか?",
            "! を付けて実行してください",
            "`!` プレフィックスでホスト起動を依頼します",
        ):
            code, _w, blk = self._c(q)
            self.assertEqual(code, 2, q)
            self.assertTrue(any("bang-prefix-host-escape" in b for b in blk), q)

    def test_bang_prefix_correction_and_plain_requests_pass(self):
        for q in (
            "`!` を付けて流しても host 実行にはなりません",
            "`!` prefix は auto mode の許可だけで sandbox の外には出ません",
            "Claude Code の外の terminal で実行してください",
            "この 2 行を実行していただけますか?",
        ):
            self.assertFalse(
                any("bang-prefix-host-escape" in b for b in self._blk(q)), q
            )

    def test_bang_prefix_fenced_command_blocks(self):
        q = "deploy はこれを実行してください:\n\n```\n! sudo cp /a/b.json /etc/c/b.json\n```"
        code, _w, blk = self._c(q)
        self.assertEqual(code, 2, q)
        self.assertTrue(any("bang-prefix-host-escape" in b for b in blk), q)

    def test_bang_prefix_fenced_without_pairing_passes(self):
        for q in (
            "```\n! sudo cp /a/b.json /etc/c/b.json\n```",
            "外の terminal で実行してください:\n\n```\nsudo cp /a/b.json /etc/c/b.json\n```",
        ):
            self.assertFalse(
                any("bang-prefix-host-escape" in b for b in self._blk(q)), q
            )

    # --- H4: confirm/routing-to-user prose gate ---
    def test_confirm_prose_blocks_without_skill(self):
        for q in (
            "この方針で良いですか?",
            "これで良い?",
            "進めて良いですか",
            "適用して良いですか",
        ):
            self.assertTrue(
                any("declare-and-proceed (prose)" in b for b in self._blk(q)), q
            )

    def test_routing_prose_blocks_without_skill(self):
        for q in (
            "実装するか削除するか迷います?",
            "どこから着手しますか?",
            "どちらから調査しますか?",
            "設計を詰めますか、それとも実装に入りますか?",
        ):
            blk = self._blk(q)
            self.assertTrue(
                any(
                    ("declare-and-proceed (prose)" in b) or ("order-question" in b)
                    for b in blk
                ),
                q,
            )

    def test_passes_when_declare_active(self):
        # declare-and-proceed invoked this turn -> escape hatch.
        for q in ("この方針で良いですか?", "実装するか削除するか?"):
            blk = self._blk(q, declare_active=True)
            self.assertFalse(any("declare-and-proceed (prose)" in b for b in blk), q)

    def test_open_design_question_not_flagged(self):
        # open design question (no closed-form / route anchor) -> no prose block.
        blk = self._blk("命名はどうするのが良いと思いますか?")
        self.assertFalse(any("declare-and-proceed (prose)" in b for b in blk))

    def test_declare_proceed_active_detection(self):
        now = 1_000_000.0

        def _iso(ep):
            return datetime.datetime.fromtimestamp(ep, datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )

        def asst(skill, ts=None):
            e = {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Skill", "input": {"skill": skill}}
                    ]
                },
            }
            if ts is not None:
                e["timestamp"] = _iso(ts)
            return e

        user = {"type": "user", "message": {"content": "do it"}}
        self.assertTrue(
            _declare_proceed_active([user, asst("declare-and-proceed")], now)
        )
        self.assertFalse(_declare_proceed_active([user, asst("writing-code")], now))
        self.assertFalse(_declare_proceed_active([user], now))
        self.assertFalse(_declare_proceed_active([], now))
        # 5-min sub-window (AND condition): same-turn invoke older than 5 min is dropped.
        self.assertTrue(
            _declare_proceed_active([user, asst("declare-and-proceed", now - 60)], now)
        )
        self.assertFalse(
            _declare_proceed_active([user, asst("declare-and-proceed", now - 600)], now)
        )

    # --- honest-attribution (warning-only) ---
    def _warn(self, *a, **k):
        return self._c(*a, **k)[1]

    def test_honest_attribution_warns_on_blur_plus_wrong(self):
        w = self._warn("既存のパターンを踏襲しただけだが、 これは誤った挙動だった")
        self.assertTrue(any("honest-attribution" in x for x in w))

    def test_honest_attribution_no_warn_without_wrong_marker(self):
        w = self._warn("既存のパターンを踏襲して実装した")
        self.assertFalse(any("honest-attribution" in x for x in w))

    def test_honest_attribution_no_warn_without_blur(self):
        w = self._warn("これは誤った挙動だった")
        self.assertFalse(any("honest-attribution" in x for x in w))

    def test_honest_attribution_proximity_bound(self):
        far = "既存のパターンを採用した。" + ("あ" * 70) + "別件で誤りがあった"
        self.assertFalse(any("honest-attribution" in x for x in self._warn(far)))

    # --- edited-executable-not-run (warning-only) ---
    def test_edited_executable_not_run_warns(self):
        warnings = self._warn("実装完了", paths=["/project/hooks/check.py"])
        self.assertTrue(any("edited-executable-not-run" in x for x in warnings))

    def test_edited_executable_not_run_passes_after_module_test(self):
        warnings = self._warn(
            "done",
            paths=["/project/hooks/check.py"],
            commands=["python3 -m unittest check"],
        )
        self.assertFalse(any("edited-executable-not-run" in x for x in warnings))

    def test_edited_executable_not_run_active_retry_is_nonblocking(self):
        code, stderr = self._run_warning_retry("/project/hooks/check.py")
        self.assertEqual(code, 0)
        self.assertIn("edited-executable-not-run", stderr)

    # --- ui-edit-without-screenshot (warning-only) ---
    def test_ui_edit_without_screenshot_warns(self):
        warnings = self._warn("対応完了", paths=["/project/app.tsx"])
        self.assertTrue(any("ui-edit-without-screenshot" in x for x in warnings))

    def test_ui_edit_without_screenshot_passes_with_browser_capture(self):
        warnings = self._warn(
            "landed", paths=["/project/app.tsx"], tools=["browser_take_screenshot"]
        )
        self.assertFalse(any("ui-edit-without-screenshot" in x for x in warnings))

    def test_ui_edit_without_screenshot_active_retry_is_nonblocking(self):
        code, stderr = self._run_warning_retry("/project/app.tsx")
        self.assertEqual(code, 0)
        self.assertIn("ui-edit-without-screenshot", stderr)

    @staticmethod
    def _run_warning_retry(path):
        import io
        import tempfile
        from contextlib import redirect_stderr

        entries = [
            {"type": "user", "message": {"content": "implement"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": path},
                        },
                        {"type": "text", "text": "実装完了"},
                    ]
                },
            },
        ]
        transcript = os.path.join(tempfile.mkdtemp(), "turn.jsonl")
        with open(transcript, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = _run({"transcript_path": transcript, "stop_hook_active": True})[0]
        return code, stderr.getvalue()

    # --- intent-without-task ---
    @staticmethod
    def _gate_config(features):
        import tempfile
        from unittest import mock

        path = os.path.join(tempfile.mkdtemp(), ".claude.json")
        if features is not None:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"cachedGrowthBookFeatures": features}, f)
        return mock.patch.object(os.path, "expanduser", return_value=path)

    def test_tasks_gated_off_missing_file(self):
        with self._gate_config(None):
            self.assertFalse(_tasks_gated_off("claude-opus-4-8"))

    def test_tasks_gated_off_missing_key(self):
        with self._gate_config({}):
            self.assertFalse(_tasks_gated_off("claude-opus-4-8"))

    def test_tasks_gated_off_matching_model(self):
        with self._gate_config({"tengu_vellum_ash": ["opus-4-8"]}):
            self.assertTrue(_tasks_gated_off("claude-opus-4-8"))

    def test_tasks_gated_off_nonmatching_model(self):
        with self._gate_config({"tengu_vellum_ash": ["sonnet-5"]}):
            self.assertFalse(_tasks_gated_off("claude-opus-4-8"))

    def test_current_turn_uses_last_assistant_model_as_fallback(self):
        entries = [
            {
                "type": "assistant",
                "message": {"model": "claude-opus-4-8", "content": []},
            },
            {"type": "user", "message": {"content": "do it"}},
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "done"}]},
            },
        ]
        self.assertEqual(_current_turn(entries)[8], "claude-opus-4-8")

    def test_intent_gated_without_mytask_blocks(self):
        with self._gate_config({"tengu_vellum_ash": ["opus-4-8"]}):
            blk = self._blk(
                "修正します\n完了", final_text="完了", model="claude-opus-4-8"
            )
        self.assertTrue(any("mytask skill" in b for b in blk))

    def test_intent_gated_with_mcp_tool_passes(self):
        with self._gate_config({"tengu_vellum_ash": ["opus-4-8"]}):
            blk = self._blk(
                "修正します",
                tools=["mcp__mytask__TaskCreate"],
                model="claude-opus-4-8",
            )
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_intent_gated_with_mytask_edit_passes(self):
        with self._gate_config({"tengu_vellum_ash": ["opus-4-8"]}):
            blk = self._blk(
                "修正します",
                paths=["/project/drafts/tasks/session.json"],
                model="claude-opus-4-8",
            )
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_intent_not_gated_keeps_taskcreate_message(self):
        with self._gate_config({"tengu_vellum_ash": ["sonnet-5"]}):
            blk = self._blk(
                "修正します\n完了", final_text="完了", model="claude-opus-4-8"
            )
        self.assertTrue(any("TaskCreate" in b and "登録してから" in b for b in blk))

    def test_intent_ungated_with_mcp_tool_passes(self):
        """gate リスト未収載モデルでも mytask MCP 記録で満たす (fable-5 FP の regression)。"""
        with self._gate_config({"tengu_vellum_ash": ["sonnet-5"]}):
            blk = self._blk(
                "修正します",
                tools=["mcp__mytask__TaskUpdate"],
                model="claude-fable-5",
            )
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_intent_ungated_with_mytask_edit_passes(self):
        with self._gate_config({"tengu_vellum_ash": ["sonnet-5"]}):
            blk = self._blk(
                "修正します",
                paths=["/project/drafts/tasks/session.json"],
                model="claude-fable-5",
            )
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_intent_declare_alone_blocks(self):
        code, _w, blk = self._c("修正します\n完了", final_text="完了")
        self.assertEqual(code, 2)
        self.assertTrue(any("intent-without-task" in b for b in blk))

    def test_intent_declare_passes_with_task_create(self):
        blk = self._blk("修正します", tools=["TaskCreate"])
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_intent_declare_passes_with_task_update(self):
        blk = self._blk("修正します", tools=["TaskUpdate"])
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_speech_act_kakunin_excluded(self):
        blk = self._blk("確認します")
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_speech_act_setsumei_excluded(self):
        blk = self._blk("説明します")
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_euphemism_for_error_blocks(self):
        """自分の発言を 「誤解を招く X」 と評すのは、 誤りを相手の読み方にすり替える言い換え。"""
        for text in (
            "誤解を招く記述でした。",
            "誤解を招きやすい書き方でした。",
            "誤解を招くような説明でした。",
            "誤解を招きました。",
            "誤解させてしまいました。",
        ):
            with self.subTest(text=text):
                code, _w, blk = self._c(text)
                self.assertEqual(code, 2)
                self.assertTrue(any("euphemism-for-error" in b for b in blk))

    def test_misleading_design_artifact_is_not_blocked(self):
        """設計対象への同じ評価は正当な技術用語 — 実 corpus の多数派はこちら。"""
        for text in (
            "誤解を招く「内」を廃止し、全銘柄中 N 件と表示します。",
            "create 寄りの名前で誤解を招くので rename を提案します。",
            "誤解が残っていれば指摘してください。",
            "次に読む人が両者を矛盾と誤解することはありません。",
        ):
            with self.subTest(text=text):
                blk = self._blk(text)
                self.assertFalse(any("euphemism-for-error" in b for b in blk))

    def test_plain_admission_is_not_blocked(self):
        """名指しの誤り認定は通す — 婉曲表現だけを捕まえる。"""
        blk = self._blk("あの記述は間違いでした。正しくは最大 2 件出します。")
        self.assertFalse(any("euphemism-for-error" in b for b in blk))

    def test_euphemism_inside_fence_not_fired(self):
        blk = self._blk("引用:\n```\n誤解を招く\n```\n以上です。")
        self.assertFalse(any("euphemism-for-error" in b for b in blk))

    def test_interrogative_is_not_a_declaration(self):
        """疑問形の「〜ますか」 は user への問いかけで、 遂行宣言ではない。"""
        for text in (
            "どれから進めますか?",
            "先に修正しますか？",
            "この順で対応しますか",
            "実装しますか、それとも設計から詰めますか?",
        ):
            with self.subTest(text=text):
                blk = self._blk(text)
                self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_declaration_with_causal_kara_still_blocks(self):
        """除外は疑問の 「か」 だけに効き、 「〜ますから」 の宣言を落とさない。"""
        blk = self._blk(
            "先に修正しますから、その後で見てください。\n完了", final_text="完了"
        )
        self.assertTrue(any("intent-without-task" in b for b in blk))

    def test_declaration_alongside_question_still_blocks(self):
        blk = self._blk(
            "まず修正します。次はどれから進めますか?\n完了", final_text="完了"
        )
        self.assertTrue(any("intent-without-task" in b for b in blk))

    def test_intent_fenced_not_fired(self):
        # strip_fences removes the declaration; bare prose is clean so no block.
        text = "検討結果:\n```\nやります\n```\n以上です。"
        blk = self._blk(text)
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_intent_independent_of_other_families(self):
        # intent-without-task fires on its own; other families are not required.
        blk = self._blk("実装します\n完了", final_text="完了")
        self.assertTrue(any("intent-without-task" in b for b in blk))

    def test_existing_block_families_still_fire(self):
        # regression: pre-existing block families unaffected by the new declare_active param.
        self.assertEqual(self._c("省略しません")[0], 2)
        self.assertEqual(self._c("学習しました")[0], 2)
        self.assertEqual(self._c("想定外でした")[0], 2)
        self.assertTrue(
            any("known-possible" in b for b in self._blk("autosquash はできない"))
        )

    def test_hollow_manabi_and_moushimasen_fire(self):
        for t in (
            "大きな学びがあった",
            "良い学びです",
            "多くを学びました",
            "今後もうしません",
            "二度としません",
        ):
            self.assertEqual(self._c(t)[0], 2, t)
        for t in ("学びのある記事", "学びを深める設計"):
            self.assertEqual(self._c(t)[0], 0, t)


class WorkWithoutTaskTest(unittest.TestCase):
    """work-without-task: store 空のまま実質作業 turn なら block。 Run: python3 -m unittest stop_checks"""

    @staticmethod
    def _blk(edits, tools=(), records=False):
        return _check(
            "done",
            "done",
            set(tools),
            list(edits),
            list(edits),
            [],
            False,
            False,
            None,
            session_task_records=records,
        )[2]

    def _hit(self, blk):
        return any("work-without-task" in b for b in blk)

    def test_blocks_three_edits_with_empty_store(self):
        self.assertTrue(self._hit(self._blk(["/a.py", "/b.py", "/c.py"])))

    def test_below_threshold_passes(self):
        self.assertFalse(self._hit(self._blk(["/a.py", "/b.py"])))

    def test_store_records_pass(self):
        self.assertFalse(self._hit(self._blk(["/a", "/b", "/c"], records=True)))

    def test_task_tool_this_turn_passes(self):
        self.assertFalse(self._hit(self._blk(["/a", "/b", "/c"], tools={"TaskCreate"})))

    def test_mytask_mcp_this_turn_passes(self):
        self.assertFalse(
            self._hit(self._blk(["/a", "/b", "/c"], tools={"mcp__mytask__TaskCreate"}))
        )

    def test_mytask_store_write_passes(self):
        edits = ["/x/drafts/tasks/s1.json", "/a.py", "/b.py"]
        self.assertFalse(self._hit(self._blk(edits)))

    def test_store_probe_reads_native_and_mytask(self):
        import tempfile
        from unittest import mock

        home = tempfile.mkdtemp()
        cwd = tempfile.mkdtemp()
        mod = sys.modules[__name__]
        with mock.patch.object(mod, "NATIVE_TASKS_DIR", home):
            self.assertFalse(_session_has_task_records("s1", cwd))
            os.makedirs(os.path.join(home, "s1"))
            self.assertFalse(_session_has_task_records("s1", cwd))  # 空 dir は記録なし
            with open(os.path.join(home, "s1", "1.json"), "w", encoding="utf-8") as f:
                f.write("{}")
            self.assertTrue(_session_has_task_records("s1", cwd))
            os.makedirs(os.path.join(cwd, "drafts", "tasks"))
            with open(
                os.path.join(cwd, "drafts", "tasks", "s2.json"), "w", encoding="utf-8"
            ) as f:
                f.write('[{"id": "1", "content": "x", "status": "completed"}]')
            self.assertTrue(_session_has_task_records("s2", cwd))  # status 不問
            self.assertTrue(
                _session_has_task_records(None, cwd)
            )  # 帰属不能は fail-open


class _DecisionStoreFixture:
    SID = "sid-warn-family"

    def setUp(self):
        import tempfile
        from unittest import mock

        assert isinstance(self, unittest.TestCase)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.cwd = temp.name
        self.native = os.path.join(temp.name, "native-tasks")
        patcher = mock.patch.object(
            sys.modules[__name__], "NATIVE_TASKS_DIR", self.native
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _native(self, tid, status, subject):
        directory = os.path.join(self.native, self.SID)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, f"{tid}.json"), "w", encoding="utf-8") as f:
            json.dump({"id": tid, "subject": subject, "status": status}, f)

    def _mytask(self, items):
        directory = os.path.join(self.cwd, "drafts", "tasks")
        os.makedirs(directory, exist_ok=True)
        with open(
            os.path.join(directory, f"{self.SID}.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(items, f)


class DecisionQuestionWarningTest(_DecisionStoreFixture, unittest.TestCase):
    def test_question_without_decision_task_warns_and_lists_open_tasks(self):
        self._native("1", "pending", "API 調査")
        warning = _decision_question_warning("どちらにしますか？", self.SID, self.cwd)
        assert warning is not None
        self.assertIn("#1 API 調査", warning)

    def test_open_decision_task_in_either_store_suppresses_warning(self):
        for store in ("native", "mytask"):
            with self.subTest(store=store):
                if store == "native":
                    self._native("1", "pending", "判断待ち: API")
                else:
                    self._mytask(
                        [
                            {
                                "id": "1",
                                "content": "ご回答待ち: API",
                                "status": "blocked",
                            }
                        ]
                    )
                self.assertIsNone(
                    _decision_question_warning("どちらにしますか?", self.SID, self.cwd)
                )
                if store == "native":
                    os.unlink(os.path.join(self.native, self.SID, "1.json"))

    def test_mytask_store_found_from_subdirectory_cwd(self):
        self._mytask([{"id": "1", "content": "判断待ち: deploy", "status": "pending"}])
        nested = os.path.join(self.cwd, "files", "hooks")
        os.makedirs(nested, exist_ok=True)
        self.assertIsNone(
            _decision_question_warning("どちらにしますか?", self.SID, nested)
        )

    def test_mytask_store_found_via_project_dir_env(self):
        from unittest import mock

        self._mytask([{"id": "1", "content": "判断待ち: deploy", "status": "pending"}])
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.cwd}):
            self.assertIsNone(
                _decision_question_warning(
                    "どちらにしますか?", self.SID, os.path.join(self.cwd, "absent")
                )
            )

    def test_negated_decision_name_does_not_count(self):
        self._native("1", "pending", "判断待ちではなく実装中")
        self.assertIsNotNone(
            _decision_question_warning("実行しますか?", self.SID, self.cwd)
        )

    def test_code_block_question_and_numbering_are_ignored(self):
        text = "```\n候補 1 ですか?\n```"
        self.assertIsNone(_decision_question_warning(text, self.SID, self.cwd))
        self.assertEqual(_communication_lint_warnings(text), [])

    def test_malformed_store_skips_only_store_dependent_family(self):
        from unittest import mock

        directory = os.path.join(self.cwd, "drafts", "tasks")
        os.makedirs(directory, exist_ok=True)
        with open(
            os.path.join(directory, f"{self.SID}.json"), "w", encoding="utf-8"
        ) as f:
            f.write("not json")
        entries = [
            {"type": "user", "message": {"content": "q"}},
            TurnMarkerTest._asst("通常行"),
        ]
        warnings = _new_warning_families(
            entries,
            "質問ですか?\n通常行",
            {"session_id": self.SID, "cwd": self.cwd},
        )
        self.assertFalse(any("decision-question-task" in item for item in warnings))
        self.assertTrue(any("communication-final-line" in item for item in warnings))
        with mock.patch.object(
            sys.modules[__name__],
            "_decision_question_warning",
            side_effect=RuntimeError,
        ):
            warnings = _new_warning_families(entries, "通常行", {})
        self.assertTrue(any("communication-final-line" in item for item in warnings))


class DecisionRecordWarningTest(_DecisionStoreFixture, unittest.TestCase):
    def test_short_decision_with_open_decision_task_warns(self):
        self._mytask(
            [{"id": "1", "content": "決裁待ち: deploy", "status": "in_progress"}]
        )
        warning = _decision_record_warning("承認", self.SID, self.cwd)
        assert warning is not None
        self.assertIn("台帳 / todos", warning)

    def test_non_decision_or_long_turn_does_not_warn(self):
        self._native("1", "pending", "ご指示待ち: deploy")
        self.assertIsNone(_decision_record_warning("検討中です", self.SID, self.cwd))
        self.assertIsNone(
            _decision_record_warning(
                "やってください。ただし先に調査してください", self.SID, self.cwd
            )
        )


class CommunicationLintWarningTest(unittest.TestCase):
    def test_final_line_requires_emoji_or_question(self):
        warnings = _communication_lint_warnings("作業は完了しました。")
        self.assertTrue(any("communication-final-line" in item for item in warnings))
        for text in ("完了です\n✅ 完了", "どうしますか？"):
            with self.subTest(text=text):
                self.assertFalse(
                    any(
                        "communication-final-line" in item
                        for item in _communication_lint_warnings(text)
                    )
                )

    def test_low_block_emoji_start_is_accepted(self):
        """U+2300 台の絵文字は ☀ (U+2600) 起点の範囲から丸ごと漏れていた。"""
        for final in ("⏳ 待機中", "⏸️ 保留", "⌛ 計測中", "⏰ 期限"):
            with self.subTest(final=final):
                self.assertFalse(
                    any(
                        "communication-final-line" in item
                        for item in _communication_lint_warnings(final)
                    )
                )

    def test_self_numbering_ignores_code_and_quotes(self):
        text = "```\n候補 1\n```\n> 案 2\n✅ 終了"
        self.assertFalse(
            any(
                "communication-self-number" in item
                for item in _communication_lint_warnings(text)
            )
        )
        self.assertTrue(
            any(
                "communication-self-number" in item
                for item in _communication_lint_warnings("選択肢 3 を採用\n✅ 完了")
            )
        )

    def test_all_new_families_are_warning_only(self):
        entries = [TurnMarkerTest._asst("通常行")]
        warnings = _new_warning_families(entries, "案 1 で完了", {})
        self.assertTrue(warnings)
        code, _old_warnings, blocking = _check(
            "done", "done", set(), [], [], [], False, False
        )
        self.assertEqual(code, 0)
        self.assertEqual(blocking, [])

    def test_warning_families_are_one_line_each_and_bounded_to_three(self):
        from unittest import mock

        values = ["question\nwarning", "record"]
        with (
            mock.patch.object(
                sys.modules[__name__],
                "_decision_question_warning",
                return_value=values[0],
            ),
            mock.patch.object(
                sys.modules[__name__],
                "_decision_record_warning",
                return_value=values[1],
            ),
            mock.patch.object(
                sys.modules[__name__],
                "_communication_lint_warnings",
                return_value=["communication-a", "communication-b"],
            ),
        ):
            warnings = _new_warning_families([], "done", {})
        self.assertEqual(len(warnings), 3)
        self.assertTrue(all("\n" not in warning for warning in warnings))
        self.assertIn("communication-a", warnings[-1])
        self.assertIn("communication-b", warnings[-1])

    def test_warning_limit_and_docstring_are_five(self):
        from unittest import mock

        module = sys.modules[__name__]
        assert module.__doc__ is not None
        self.assertIn(f"合計 {NEW_WARNING_FAMILIES_LIMIT} 行以内", module.__doc__)
        with (
            mock.patch.object(module, "_decision_question_warning", return_value="one"),
            mock.patch.object(module, "_decision_record_warning", return_value="two"),
            mock.patch.object(
                module, "_communication_lint_warnings", return_value=["three"]
            ),
            mock.patch.object(
                module, "_waste_keyword_memory_warning", return_value="four"
            ),
            mock.patch.object(
                module, "_question_self_containment_warning", return_value="five"
            ),
        ):
            warnings = _new_warning_families([], "done", {})
        self.assertEqual(len(warnings), NEW_WARNING_FAMILIES_LIMIT)

    def test_run_returns_new_warnings_for_active_retry_delivery(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        transcript = TurnMarkerTest._transcript(
            [TurnMarkerTest._user(), TurnMarkerTest._asst("✅ done")]
        )
        payload = {"transcript_path": transcript, "session_id": "warn-sid"}
        with (
            mock.patch.object(
                sys.modules[__name__],
                "_new_warning_families",
                return_value=["MODEL-WARN"],
            ),
            redirect_stderr(io.StringIO()),
        ):
            first = _run(payload)[3]
            retry = _run({**payload, "stop_hook_active": True})[3]
        self.assertIn("MODEL-WARN", first)
        self.assertIn("MODEL-WARN", retry)

    def test_each_warning_family_crosses_pass_block_and_active_paths(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        module = sys.modules[__name__]
        for family in (
            "question",
            "record",
            "communication",
            "worktree",
            "codex-shared-write",
        ):
            marker = f"{family.upper()}-WARN"
            for mode in ("pass", "block", "active"):
                with self.subTest(family=family, mode=mode):
                    active = mode == "active"
                    blocked = mode in {"block", "active"}
                    transcript = TurnMarkerTest._transcript(
                        [
                            TurnMarkerTest._user(),
                            TurnMarkerTest._asst(
                                "省略しません" if blocked else "✅ done"
                            ),
                        ]
                    )
                    with (
                        mock.patch.object(
                            module, "_stop_latch_claim", return_value=True
                        ),
                        mock.patch.object(
                            module,
                            "_worktree_cleanup_warnings",
                            return_value=[marker] if family == "worktree" else [],
                        ),
                        mock.patch.object(
                            module,
                            "_codex_shared_write_warnings",
                            return_value=[marker]
                            if family == "codex-shared-write"
                            else [],
                        ),
                        mock.patch.object(
                            module,
                            "_decision_question_warning",
                            return_value=marker if family == "question" else None,
                        ),
                        mock.patch.object(
                            module,
                            "_decision_record_warning",
                            return_value=marker if family == "record" else None,
                        ),
                        mock.patch.object(
                            module,
                            "_communication_lint_warnings",
                            return_value=[marker] if family == "communication" else [],
                        ),
                    ):
                        err = io.StringIO()
                        with redirect_stderr(err):
                            code, _epoch, _text, surfaced = _run(
                                {
                                    "transcript_path": transcript,
                                    "stop_hook_active": active,
                                }
                            )
                    output = err.getvalue()
                    if mode == "pass":
                        self.assertEqual(code, 0)
                        self.assertNotIn(marker, output)
                        self.assertIn(marker, surfaced)
                    elif mode == "block":
                        self.assertEqual(code, 2)
                        self.assertIn(marker, output)
                        self.assertIn("meta-announce-silence:", output)
                        self.assertLess(
                            output.index("meta-announce-silence:"), output.index(marker)
                        )
                    else:
                        self.assertEqual(code, 0)
                        self.assertNotIn(marker, output)
                        self.assertIn(marker, surfaced)
                        self.assertIn(
                            "advise-once (block demoted to pass): "
                            "meta-announce-silence:",
                            output,
                        )


class WasteKeywordMemoryWarningTest(unittest.TestCase):
    @staticmethod
    def _write(path: str, name: str = "Write") -> dict:
        return {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": name,
                        "input": {"file_path": path, "content": "lesson"},
                    }
                ]
            },
        }

    def test_each_user_keyword_warns_without_persistence_write(self):
        for keyword in ("無駄", "浪費", "もったいない"):
            with self.subTest(keyword=keyword):
                warning = _waste_keyword_memory_warning(
                    [TurnMarkerTest._user(content=f"この作業は{keyword}でした")]
                )
                assert warning is not None
                self.assertIn("waste-keyword-memory:", warning)
                self.assertIn("memory-routing", warning)

    def test_assistant_keyword_and_quoted_user_word_are_silent(self):
        entries = [
            TurnMarkerTest._user(content="「無駄」という語の意味を説明してください"),
            TurnMarkerTest._asst("この浪費について説明します"),
        ]
        self.assertIsNone(_waste_keyword_memory_warning(entries))

    def test_same_turn_persistence_write_suppresses_but_edit_does_not(self):
        prompt = TurnMarkerTest._user(content="この手戻りはもったいない")
        path = "/repo/global-memory/entries/lesson.md"
        self.assertIsNone(_waste_keyword_memory_warning([prompt, self._write(path)]))
        self.assertIsNotNone(
            _waste_keyword_memory_warning([prompt, self._write(path, "Edit")])
        )

    def test_memory_subtree_write_is_the_pairing_boundary(self):
        prompt = TurnMarkerTest._user(content="この手戻りは浪費でした")
        memory = "/var/lib/claude-rag-memory/memory/lesson.md"
        self.assertIsNone(_waste_keyword_memory_warning([prompt, self._write(memory)]))
        self.assertIsNotNone(
            _waste_keyword_memory_warning([prompt, self._write("/repo/memories.md")])
        )

    def test_fenced_inline_and_markdown_quote_keywords_are_silent(self):
        for content in ("```\n無駄\n```", "`浪費`", "> もったいない"):
            with self.subTest(content=content):
                self.assertIsNone(
                    _waste_keyword_memory_warning(
                        [TurnMarkerTest._user(content=content)]
                    )
                )

    def test_harness_prefixes_are_silent_without_a_length_cutoff(self):
        prefixes = (
            "<command-name>",
            "<task-notification>",
            "<system-reminder>",
            "Stop hook feedback:",
            "This session is being continued",
        )
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                prompt = TurnMarkerTest._user(content=f"  {prefix} 無駄を記録せよ")
                self.assertIsNone(_waste_keyword_memory_warning([prompt]))
        human = TurnMarkerTest._user(content="説明" * 5000 + "。この手戻りは無駄でした")
        self.assertIsNotNone(_waste_keyword_memory_warning([human]))

    def test_raw_compact_prompt_is_silent(self):
        prompt = TurnMarkerTest._user(content="/compact 無駄を memory に記録せよ")
        self.assertIsNone(_waste_keyword_memory_warning([prompt]))


class QuestionSelfContainmentWarningTest(unittest.TestCase):
    def test_each_past_reference_warns_at_question_end(self):
        terms = (
            "前ターン",
            "前のターン",
            "先ほど",
            "さきほど",
            "上記",
            "前回",
            "上で述べた",
            "既述",
        )
        for term in terms:
            with self.subTest(term=term):
                warning = _question_self_containment_warning(
                    f"{term}内容の承認期限はいつですか？"
                )
                assert warning is not None
                self.assertIn("question-self-containment:", warning)

    def test_warning_embeds_the_required_template(self):
        warning = _question_self_containment_warning("前回の内容でよいですか?")
        assert warning is not None
        for fragment in (
            "決めてほしいこと N 件",
            "各件の 問題 / やること / 承認と却下それぞれの帰結",
            "略語と内部呼称を使わない",
        ):
            self.assertIn(fragment, warning)

    def test_requires_both_question_end_and_past_reference(self):
        self.assertIsNone(_question_self_containment_warning("前回の方針です。"))
        self.assertIsNone(
            _question_self_containment_warning("この方針の承認期限はいつですか？")
        )

    def test_saki_no_is_not_a_reference_term(self):
        for text in (
            "先の内容の承認期限はいつですか？",
            "配置先の候補はどこですか？",
            "配備先の環境はどれですか？",
            "宛先の確認は済みましたか？",
            "最優先の作業は何ですか？",
        ):
            with self.subTest(text=text):
                self.assertIsNone(_question_self_containment_warning(text))

    def test_reference_terms_warn_after_kanji_symbols_and_quotes(self):
        for text in (
            "この方針を採用した前回の判断でよいですか？",
            "確認対象→上記の条件でよいですか？",
            "確認対象『既述の条件』でよいですか？",
        ):
            with self.subTest(text=text):
                self.assertIsNotNone(_question_self_containment_warning(text))

    def test_code_fence_and_quote_line_questions_are_silent(self):
        text = "```\n前回の方針でよいですか？\n```\n> 上記でよいですか？"
        self.assertIsNone(_question_self_containment_warning(text))

    def test_both_families_use_the_warning_collection_and_keep_exit_zero(self):
        from unittest import mock

        transcript = TurnMarkerTest._transcript(
            [
                TurnMarkerTest._user(content="この手戻りは無駄でした"),
                TurnMarkerTest._asst("前回の承認期限はいつですか？"),
            ]
        )
        with mock.patch.object(
            sys.modules[__name__], "_stop_latch_claim", return_value=True
        ):
            code, _epoch, _text, warnings = _run({"transcript_path": transcript})
        self.assertEqual(code, 0)
        self.assertTrue(any("waste-keyword-memory:" in item for item in warnings))
        self.assertTrue(any("question-self-containment:" in item for item in warnings))


class TurnScopeTest(unittest.TestCase):
    """warning family は当 turn の entries だけを見る (session 全体を遡らない)。"""

    def test_run_passes_current_turn_entries_to_warning_families(self):
        import io
        import tempfile
        from contextlib import redirect_stderr
        from unittest import mock

        current = [
            TurnMarkerTest._user(content="current"),
            TurnMarkerTest._asst("✅ done"),
        ]
        seen = {}

        def decision(_final, _sid, _cwd):
            seen["decision"] = True

        def record(prompt, _sid, _cwd):
            seen["record"] = prompt

        transcript = os.path.join(tempfile.mkdtemp(), "transcript.jsonl")
        with (
            mock.patch.object(
                sys.modules[__name__], "_load_tail", return_value=current
            ),
            mock.patch.object(
                sys.modules[__name__],
                "_decision_question_warning",
                side_effect=decision,
            ),
            mock.patch.object(
                sys.modules[__name__],
                "_decision_record_warning",
                side_effect=record,
            ),
            mock.patch.object(
                sys.modules[__name__],
                "_communication_lint_warnings",
                return_value=[],
            ),
            redirect_stderr(io.StringIO()),
        ):
            _run({"transcript_path": transcript})
        self.assertEqual(seen["record"], "current")
        self.assertTrue(seen["decision"])


class OpenTasksAtWindDownTest(unittest.TestCase):
    """open-tasks-at-wind-down: wind-down prompt で open Task 残があれば block。"""

    @staticmethod
    def _c(tasks):
        return _check(
            "done",
            "done",
            set(),
            [],
            [],
            [],
            False,
            False,
            None,
            wind_down_open_tasks=tasks,
        )

    def test_open_tasks_block(self):
        code, _w, blk = self._c(["#1 a", "#2 b"])
        self.assertEqual(code, 2)
        self.assertTrue(any("open-tasks-at-wind-down" in b for b in blk))
        self.assertTrue(any("2 件" in b for b in blk))

    def test_empty_tasks_pass(self):
        code, _w, blk = self._c([])
        self.assertEqual(code, 0)
        self.assertFalse(blk)

    def _run_with(self, signalled, tasks):
        import io
        import types
        from contextlib import redirect_stderr
        from unittest import mock

        p = TurnMarkerTest._transcript(
            [TurnMarkerTest._user(content="作業して"), TurnMarkerTest._asst("done.")]
        )
        fake = types.SimpleNamespace(
            wind_down_signalled=lambda sid: signalled,
            open_tasks=lambda sid, cwd: tasks,
        )
        with (
            mock.patch.object(sys.modules[__name__], "_handoff_mod", fake),
            redirect_stderr(io.StringIO()),
        ):
            return _run({"transcript_path": p, "stop_hook_active": False})[0]

    def test_run_blocks_when_signal_recorded_with_open_tasks(self):
        self.assertEqual(self._run_with(True, ["#1 a"]), 2)

    def test_run_passes_without_signal(self):
        self.assertEqual(self._run_with(False, ["#1 a"]), 0)

    def test_run_passes_with_clean_tasks(self):
        self.assertEqual(self._run_with(True, []), 0)


class HandoffTodosSyncTest(unittest.TestCase):
    """handoff-todos-sync: handoff doc の section が todos.md の task block と 1-to-1 か。
    出所: 2026-08-23 実測 — 対象 doc も todos block も消えた section が 11 日残存
    (c2f083a が pointer だけ外し、 e905965 が block を消して section を残した)。"""

    TRACKED = "### 作業 A\n\nWork file: `last-session-handoff.md`\n"

    def _repo(self, todos, handoff, extra=()):
        import shutil
        import tempfile

        root = tempfile.mkdtemp(prefix="handoff-sync-")
        self.addCleanup(shutil.rmtree, root, True)
        files = [("todos.md", todos), ("last-session-handoff.md", handoff)]
        files.extend((name, "本文\n") for name in extra)
        for name, text in files:
            if text is None:
                continue
            with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        return root

    def _tracked_repo(self, todos, handoff, paths):
        root = self._repo(todos, handoff)
        for rel in paths:
            os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write("本文\n")
        for args in (["init", "-q"], ["add", "-A"]):
            subprocess.run(["git", "-C", root, *args], check=True, capture_output=True)
        return root

    def test_tracked_doc_with_live_references_is_silent(self):
        root = self._repo(
            self.TRACKED, "## 作業 A\n\n### 必読\n- `spec.md`\n", extra=("spec.md",)
        )
        self.assertEqual(_handoff_todos_sync_warnings(root), [])

    def test_doc_no_task_points_at_warns(self):
        """block ごと消えて doc だけ残る形 (e905965 の class) を捕まえる。"""
        root = self._repo("### 別の作業\n\nWork file: なし\n", "## 消えた作業\n")

        warnings = _handoff_todos_sync_warnings(root)

        self.assertEqual(len(warnings), 1)
        self.assertIn("last-session-handoff.md", warnings[0])
        self.assertIn("Work file:", warnings[0])

    def test_reference_to_deleted_path_warns(self):
        """11 日 stale だった実例 = 削除済み doc の review 待ちを指したままの section。"""
        root = self._repo(self.TRACKED, "## 作業 A\n\n### 必読\n- `SKILL-HOOK.md`\n")

        warnings = _handoff_todos_sync_warnings(root)

        self.assertEqual(len(warnings), 1)
        self.assertIn("SKILL-HOOK.md", warnings[0])

    def test_reference_outside_required_reading_is_ignored(self):
        """SKILL.md section schema 上、 Read 推奨 file を並べる節は `### 必読` だけ。"""
        root = self._repo(self.TRACKED, "## 作業 A\n\n### Caveat\n- `gone.md` が罠\n")
        self.assertEqual(_handoff_todos_sync_warnings(root), [])

    def test_non_path_shapes_are_ignored(self):
        """URL / mail / glob / placeholder / 絶対 path は path でない (末尾 `.io` `.com` が match していた)。"""
        body = "## 作業 A\n\n### 必読\n- `/socket.io` `dev@sparrow.com` `drafts/*.md` `<slug>.md`\n"
        self.assertEqual(
            _handoff_todos_sync_warnings(self._repo(self.TRACKED, body)), []
        )

    def test_heading_closes_required_reading_section(self):
        """必読 節は次の見出しで閉じる — 閉じ損ねると後続節の prose token を実在検査にかける。"""
        body = "## 作業 A\n\n### 必読\n- `spec.md`\n\n# 付録\n\n- `gone.md` は未作成\n"
        root = self._repo(self.TRACKED, body, extra=("spec.md",))
        self.assertEqual(_handoff_todos_sync_warnings(root), [])

    def test_reference_resolved_in_subdirectory_is_silent(self):
        """root 直下に無くても git 管理下に実在すれば不在ではない。"""
        root = self._tracked_repo(
            self.TRACKED,
            "## 作業 A\n\n### 必読\n- `RunAll.sh`\n",
            ("scripts/RunAll.sh",),
        )
        self.assertEqual(_handoff_todos_sync_warnings(root), [])

    def test_git_index_is_skipped_when_references_resolve(self):
        """root 直下で解決する限り git を spawn しない — Stop hook は毎 turn 走る。"""
        from unittest import mock

        root = self._repo(
            self.TRACKED, "## 作業 A\n\n### 必読\n- `spec.md`\n", extra=("spec.md",)
        )
        with mock.patch(f"{__name__}._tracked_basenames") as index:
            self.assertEqual(_handoff_todos_sync_warnings(root), [])
        index.assert_not_called()

    def test_git_index_is_consulted_once_across_docs(self):
        """doc 数だけ git を spawn しない (索引は cwd 単位で不変)。"""
        from unittest import mock

        root = self._repo(
            self.TRACKED + "\n### 作業 B\n\nWork file: `b-handoff.md`\n",
            "## 作業 A\n\n### 必読\n- `gone.md`\n",
        )
        os.makedirs(os.path.join(root, "drafts"))
        with open(
            os.path.join(root, "drafts", "b-handoff.md"), "w", encoding="utf-8"
        ) as fh:
            fh.write("## 作業 B\n\n### 必読\n- `gone.md`\n")

        with mock.patch(f"{__name__}._tracked_basenames", return_value=set()) as index:
            warnings = _handoff_todos_sync_warnings(root)

        self.assertEqual(len(warnings), 2)
        index.assert_called_once()

    def test_renaming_a_task_block_does_not_warn(self):
        """名前一致をやめた核心 — 見出しを改名しても参照が生きていれば黙る。"""
        renamed = self.TRACKED.replace("作業 A", "作業 A — 凍結中")
        root = self._repo(renamed, "## まったく別の見出し\n")
        self.assertEqual(_handoff_todos_sync_warnings(root), [])

    def test_missing_handoff_doc_is_silent(self):
        self.assertEqual(
            _handoff_todos_sync_warnings(self._repo(self.TRACKED, None)), []
        )

    def test_missing_todos_is_silent(self):
        """todos.md を持たない repo で doc を宙吊りと報告しない (fail-open)。"""
        self.assertEqual(_handoff_todos_sync_warnings(self._repo(None, "## x\n")), [])

    def test_unreadable_cwd_is_silent(self):
        self.assertEqual(_handoff_todos_sync_warnings(""), [])


class HandoffDocWithoutMarkerTest(unittest.TestCase):
    """handoff-doc-without-marker: 宣言済 session の doc 更新 turn に marker を強制。
    出所: 2026-08-20 実機 — リセット宣言後に Bash heredoc で handoff doc を編集して
    marker 無しで素通り (Edit/Write 観測・揮発 wind-down signal の双方が不発)。"""

    SID = "sid-handoff-marker-test"

    @staticmethod
    def _c(docs):
        return _check(
            "done",
            "done",
            set(),
            [],
            [],
            [],
            False,
            False,
            None,
            handoff_doc_without_marker=docs,
        )

    def test_unmarked_doc_blocks(self):
        code, _w, blk = self._c(["/r/drafts/rebuild-handoff.md"])
        self.assertEqual(code, 2)
        self.assertTrue(any("handoff-doc-without-marker" in b for b in blk))
        self.assertTrue(any("rebuild-handoff.md" in b for b in blk))

    def test_no_docs_pass(self):
        code, _w, blk = self._c([])
        self.assertEqual(code, 0)
        self.assertFalse(blk)

    def _awaiting(
        self, declared=True, mtime_delta=5.0, marker_in="none", broken_mod=False
    ):
        import tempfile
        import types
        from unittest import mock

        import check_uncommitted_at_handoff as real

        with tempfile.TemporaryDirectory() as d:
            doc = os.path.join(d, "drafts", "x-handoff.md")
            os.makedirs(os.path.dirname(doc))
            open(doc, "w").close()
            prompt_epoch = 1_000_000.0
            stamp = prompt_epoch + mtime_delta
            os.utime(doc, (stamp, stamp))
            marker = f"~~~~ Mon Handoff ({self.SID}) ~~~~"
            transcript = os.path.join(d, "t.jsonl")
            with open(transcript, "w", encoding="utf-8") as f:
                f.write(marker if marker_in == "tail" else "log")
            text = "done" + (marker if marker_in == "text" else "")
            fake = (
                types.SimpleNamespace()
                if broken_mod
                else types.SimpleNamespace(
                    wind_down_declared=lambda sid: declared,
                    handoff_docs=real.handoff_docs,
                    tail_text=real.tail_text,
                    has_handoff_marker=real.has_handoff_marker,
                )
            )
            payload = {"session_id": self.SID, "cwd": d, "transcript_path": transcript}
            with mock.patch.object(sys.modules[__name__], "_handoff_mod", fake):
                return _handoff_docs_awaiting_marker(payload, text, prompt_epoch)

    def test_declared_touch_without_marker_returned(self):
        docs = self._awaiting()
        self.assertEqual(len(docs), 1)
        self.assertTrue(docs[0].endswith("x-handoff.md"))

    def test_undeclared_session_ignored(self):
        self.assertEqual(self._awaiting(declared=False), [])

    def test_pre_turn_mtime_ignored(self):
        self.assertEqual(self._awaiting(mtime_delta=-5.0), [])

    def test_marker_in_tail_or_text_satisfies(self):
        self.assertEqual(self._awaiting(marker_in="tail"), [])
        self.assertEqual(self._awaiting(marker_in="text"), [])

    def test_stale_module_fails_open(self):
        self.assertEqual(self._awaiting(broken_mod=True), [])

    def _run_with(self, declared, mtime_delta, asst_text="done."):
        import io
        import tempfile
        import types
        from contextlib import redirect_stderr
        from unittest import mock

        import check_uncommitted_at_handoff as real

        p = TurnMarkerTest._transcript(
            [TurnMarkerTest._user(content="作業して"), TurnMarkerTest._asst(asst_text)]
        )
        with tempfile.TemporaryDirectory() as d:
            doc = os.path.join(d, "last-session-handoff.md")
            open(doc, "w").close()
            stamp = _parse_ts(TurnMarkerTest.TS) + mtime_delta
            os.utime(doc, (stamp, stamp))
            fake = types.SimpleNamespace(
                wind_down_signalled=lambda sid: False,
                open_tasks=lambda sid, cwd: [],
                wind_down_declared=lambda sid: declared,
                handoff_docs=real.handoff_docs,
                tail_text=real.tail_text,
                has_handoff_marker=real.has_handoff_marker,
            )
            payload = {
                "transcript_path": p,
                "stop_hook_active": False,
                "session_id": self.SID,
                "cwd": d,
            }
            with (
                mock.patch.object(sys.modules[__name__], "_handoff_mod", fake),
                redirect_stderr(io.StringIO()),
            ):
                return _run(payload)[0]

    def test_run_blocks_declared_session_doc_update(self):
        self.assertEqual(self._run_with(True, 5.0), 2)

    def test_run_passes_when_marker_emitted(self):
        marked = f"~~~~ Mon Handoff ({self.SID}) ~~~~\ndone."
        self.assertEqual(self._run_with(True, 5.0, asst_text=marked), 0)

    def test_run_passes_without_declaration(self):
        self.assertEqual(self._run_with(False, 5.0), 0)


class ClaimRegexTest(unittest.TestCase):
    """CLAIM_RE: 「無い」系に加え「できない / 書かれていない」系の否定断定も拾う。
    出所: 2026-08-08 実機 — 下記 2 文がいずれも素通りし、 後に両方とも誤りと判明した。"""

    MATCHING = (
        "どのスキルにも書かれていません",
        "memory routing は私の権限では実施できません",
        "該当する entry は見つかりません",
        "根拠は不明",
    )

    def test_negative_claims_match(self):
        for text in self.MATCHING:
            with self.subTest(text=text):
                self.assertTrue(CLAIM_RE.search(text))

    def test_neutral_sentences_do_not_match(self):
        for text in ("実装を追加しました", "テストは 3 件とも通っています"):
            with self.subTest(text=text):
                self.assertIsNone(CLAIM_RE.search(text))


class CourtWarningTest(unittest.TestCase):
    def _warnings(self, text: str) -> tuple[int, list[str]]:
        code, warnings, blocking = _check(text, text, set(), [], [], [], False, False)
        self.assertEqual(blocking, [])
        return code, warnings

    def test_court_warning_hits_stray_token(self):
        code, warnings = self._warnings("回答です。\n\ncourt")
        self.assertEqual(code, 0)
        self.assertTrue(any("court-guard" in warning for warning in warnings))

    def test_court_warning_hits_invoke_leak(self):
        code, warnings = self._warnings('\ncâu\n<invoke name="Bash">')
        self.assertEqual(code, 0)
        self.assertTrue(any("court-guard" in warning for warning in warnings))

    def test_court_warning_ignores_inline_discussion(self):
        code, warnings = self._warnings('raw <invoke name="Bash"> を説明')
        self.assertEqual(code, 0)
        self.assertFalse(any("court-guard" in warning for warning in warnings))


class StopMemorySurfaceTest(unittest.TestCase):
    """RAG memory surface on the regex-pass Stop path. Run: python3 -m unittest stop_checks"""

    M = sys.modules[__name__]

    @staticmethod
    def _fake_mod(picks):
        from unittest import mock

        m = mock.Mock()
        m._encoded_project_id = lambda c: c.replace("/", "-")
        m.surface_for_text = lambda *a, **k: list(picks)
        return m

    @staticmethod
    def _fake_search(hits, model="claude-opus-5[1m]"):
        from unittest import mock

        m = mock.Mock()
        m._encoded_project_id = lambda c: c.replace("/", "-")
        m._resolve_model = lambda p: model.removeprefix("claude-").removesuffix("[1m]")
        m.search_unfiltered = lambda *a, **k: list(hits)
        return m

    def test_none_when_module_absent(self):
        from unittest import mock

        with mock.patch.object(self.M, "_memory_surface_mod", None):
            self.assertIsNone(
                _memory_surface_at_stop({"stop_hook_active": False}, "output text")
            )

    def test_none_when_stop_hook_active(self):
        from unittest import mock

        mod = self._fake_mod([("/m/x.md", "lesson X", 0.6)])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(
                _memory_surface_at_stop(
                    {"stop_hook_active": True, "cwd": "/p"}, "output text"
                )
            )

    def test_none_when_text_blank(self):
        from unittest import mock

        mod = self._fake_mod([("/m/x.md", "lesson X", 0.6)])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(
                _memory_surface_at_stop({"stop_hook_active": False, "cwd": "/p"}, "  ")
            )

    def test_reason_built_from_top_pick(self):
        from unittest import mock

        mod = self._fake_mod([("/m/x.md", "lesson X", 0.6)])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            r = _memory_surface_at_stop(
                {"stop_hook_active": False, "cwd": "/p", "session_id": "s"}, "output"
            )
        assert r is not None
        self.assertIn("lesson X", r)
        self.assertIn("/m/x.md", r)
        self.assertIn("memory-surface", r)

    def test_none_when_no_picks(self):
        from unittest import mock

        mod = self._fake_mod([])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(
                _memory_surface_at_stop({"stop_hook_active": False, "cwd": "/p"}, "out")
            )

    def test_muted_stays_quiet_when_the_deployed_helper_is_missing(self):
        """fail-open は戻り値だけでなく黙ることまで — thread へ投げた例外は traceback を stderr へ出す。"""
        from unittest import mock

        class Older:  # search_unfiltered を持たない旧 deploy の memory_surface
            _resolve_model = staticmethod(lambda p: "opus-5")
            _encoded_project_id = staticmethod(lambda c: c)

        raised: list = []
        with (
            mock.patch.object(self.M, "_memory_surface_mod", Older()),
            mock.patch.object(threading, "excepthook", raised.append),
        ):
            self.assertIsNone(
                _muted_memory_at_stop(
                    {"stop_hook_active": False, "cwd": "/p"}, "実行できません"
                )
            )
        self.assertEqual(raised, [])

    def test_muted_gives_up_on_a_search_that_does_not_return(self):
        """例外 catch は hang に効かない — 元 probe の 20 秒 watchdog を失うと Stop 全体が止まる。"""
        from unittest import mock

        mod = self._fake_search([(0.9, "opus-4.8", "/m/x.md", "lesson")])
        mod.search_unfiltered = lambda *a, **k: time.sleep(30)
        started = time.time()
        with (
            mock.patch.object(self.M, "_memory_surface_mod", mod),
            mock.patch.object(self.M, "_SEARCH_TIMEOUT_SECONDS", 0.05),
        ):
            self.assertIsNone(
                _muted_memory_at_stop(
                    {"stop_hook_active": False, "cwd": "/p"}, "実行できません"
                )
            )
        self.assertLess(time.time() - started, 5.0)

    def test_muted_none_when_module_absent(self):
        from unittest import mock

        with mock.patch.object(self.M, "_memory_surface_mod", None):
            self.assertIsNone(
                _muted_memory_at_stop({"stop_hook_active": False}, "実行できません")
            )

    def test_muted_none_when_stop_hook_active(self):
        from unittest import mock

        mod = self._fake_search([(0.9, "opus-4.8", "/m/x.md", "lesson X")])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(
                _muted_memory_at_stop(
                    {"stop_hook_active": True, "cwd": "/p"}, "実行できません"
                )
            )

    def test_muted_none_without_wall_declaration(self):
        """壁宣言が無い turn では検索そのものを走らせない。"""
        from unittest import mock

        mod = self._fake_search([(0.9, "opus-4.8", "/m/x.md", "lesson X")])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(
                _muted_memory_at_stop(
                    {"stop_hook_active": False, "cwd": "/p"}, "テストが通りました。"
                )
            )

    def test_muted_none_below_floor(self):
        """MUTED_FLOOR 未満は無関係語の noise — 実測で無関係文の top hit は 0.270。"""
        from unittest import mock

        mod = self._fake_search([(MUTED_FLOOR - 0.01, "opus-4.8", "/m/x.md", "lesson")])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(
                _muted_memory_at_stop(
                    {"stop_hook_active": False, "cwd": "/p"}, "実行できません"
                )
            )

    def test_muted_none_when_running_model_is_tagged(self):
        """自 tag を持つ entry は surface hook 側が既に出せる — 本 family の対象外。"""
        from unittest import mock

        mod = self._fake_search([(0.9, "opus-4.8 opus-5", "/m/x.md", "lesson")])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(
                _muted_memory_at_stop(
                    {"stop_hook_active": False, "cwd": "/p"}, "実行できません"
                )
            )

    def test_muted_reason_names_entry_and_retag_step(self):
        """mute された上位 entry を reminder / path / tag 追記手順つきで返す。"""
        from unittest import mock

        mod = self._fake_search(
            [
                (0.9, "opus-5", "/m/tagged.md", "見えている教訓"),
                (0.8, "opus-4.8", "/m/muted.md", "mute された教訓"),
            ]
        )
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            r = _muted_memory_at_stop(
                {"stop_hook_active": False, "cwd": "/p"}, "実行できません"
            )
        assert r is not None
        self.assertIn("mute された教訓", r)
        self.assertIn("/m/muted.md", r)
        self.assertIn("Tag propagation", r)
        self.assertNotIn("/m/tagged.md", r)

    # 壁宣言 = 「できない」 の断定と誤読の自認。 疑問 / 条件 / 二重否定 / 成功報告は同じ語を
    # 含むだけで断定ではないので、 両側を同数そろえて regex を pin する。
    WALL_HITS = (
        "実行できません",
        "実行はできません。",
        "権限がないため変更できません。",
        "sandbox からは PID を取得できません",
        "この session では対応できないと判断しました",
        "そのファイルには書き込みできませんでした。",
        "並列実行は不可能です。",
        "ここが限界だと判断しました",
        "this is a hard wall for the sandbox",
        "誤読しました",
        "誤読していました。",
        "勘違いしていました",
        "読み違えました",
        "思い込んでいました。",
    )
    WALL_MISSES = (
        "実行できないか検討します",
        "実行できないわけではありません。",
        "実行できない場合は再試行します",
        "別のセッションでも実行できました。",
        "この session だけで完結させます",
        "テストが通りました",
        "実行できないかもしれません",
        "権限が無いときは変更できないので確認します",
        "誤読を防ぐため regex を pin します",
        "勘違いしやすい箇所にコメントを足しました",
        "読み違えないよう docstring と assert を突き合わせます",
        "hard limit の有無を調べます",
        "書き込みできないという前提を疑います",
        "取得できないとしたら原因は何かを調べます",
        # 以下 2 件は実 transcript で新 regex が誤検知した実例。
        "壁と結論する前に横断検索する導線を足しました",
        "段落内の空行を次の block と誤読して真の event を落とします",
    )

    def test_wall_regex_fires_on_assertions_only(self):
        """断定 14 / 非断定 16 で pin する — 疑問・条件・二重否定・成功報告は同じ語を含むだけ。"""
        for hit in self.WALL_HITS:
            self.assertTrue(WALL_DECLARATION_RE.search(hit), hit)
        for miss in self.WALL_MISSES:
            self.assertFalse(WALL_DECLARATION_RE.search(miss), miss)

    @staticmethod
    def _fresh_session_payload():
        """`.turns` を書かない = clean な turn 終了をまだ迎えていない fresh session。"""
        import tempfile

        return {
            "stop_hook_active": False,
            "cwd": "/p",
            "transcript_path": os.path.join(tempfile.mkdtemp(), "s.jsonl"),
        }

    def test_latch_key_treats_missing_turns_as_zero(self):
        """`.turns` 不在を欠測にすると初回 turn の latch が丸ごと no-op になる。"""
        payload = self._fresh_session_payload()
        base = payload["transcript_path"][:-6] + ".turns"
        self.assertEqual(_stop_latch_key(payload, ".x"), ("0", base + ".x"))

    def test_latch_claim_is_once_per_turn_key(self):
        """同一 turn key では 1 度だけ掴め、key が進めば再び掴める。"""
        payload = self._fresh_session_payload()
        turns = payload["transcript_path"][:-6] + ".turns"
        self.assertTrue(_stop_latch_claim(payload, ".x"))
        self.assertFalse(_stop_latch_claim(payload, ".x"))
        with open(turns, "w", encoding="utf-8") as f:
            f.write("1 1000\n")
        self.assertTrue(_stop_latch_claim(payload, ".x"))

    def test_muted_fires_once_in_a_fresh_session(self):
        """fresh session でも 2 度目の Stop は latch で抑える (旧実装は latch が効かず二重発火)。"""
        from unittest import mock

        payload = self._fresh_session_payload()
        mod = self._fake_search([(0.9, "opus-4.8", "/m/muted.md", "mute された教訓")])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNotNone(_muted_memory_at_stop(payload, "実行できません"))
            self.assertIsNone(_muted_memory_at_stop(payload, "実行できません"))

    def test_muted_without_wall_declaration_leaves_latch_free(self):
        """壁宣言の無い Stop が latch を焼くと、同 turn の後続 Stop が発火できなくなる。"""
        from unittest import mock

        payload = self._fresh_session_payload()
        mod = self._fake_search([(0.9, "opus-4.8", "/m/muted.md", "mute された教訓")])
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            self.assertIsNone(_muted_memory_at_stop(payload, "テストが通りました。"))
            self.assertIsNotNone(_muted_memory_at_stop(payload, "実行できません"))

    def _run_with_block(self, payload):
        """_check を block 固定にした _run の 1 回実行。 返り値は (exit code, stderr)。"""
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        with (
            mock.patch.object(self.M, "_worktree_cleanup_warnings", lambda c: []),
            mock.patch.object(self.M, "_load_tail", lambda p, turns=2: [{}]),
            mock.patch.object(
                self.M,
                "_current_turn",
                lambda e: ("壁", "壁", set(), [], [], [], False, None, "opus-5"),
            ),
            mock.patch.object(self.M, "_declare_proceed_active", lambda e, n: False),
            mock.patch.object(self.M, "_handoff_mod", None),
            mock.patch.object(
                self.M, "_check", lambda *a, **k: (2, [], ["BLOCK-LINE"])
            ),
            mock.patch.object(
                self.M, "_muted_memory_at_stop", lambda p, t: "MUTED-TEXT"
            ),
        ):
            buf = io.StringIO()
            with redirect_stderr(buf):
                code = _run(payload)[0]
        return code, buf.getvalue()

    def test_run_reports_muted_memory_on_the_blocking_path(self):
        """block した turn は main() の bonus 経路に届かず継続 Stop も gate される — block stderr に併記する。"""
        code, err = self._run_with_block({"transcript_path": "/x.jsonl"})
        self.assertEqual(code, 2)
        self.assertIn("BLOCK-LINE", err)
        self.assertIn("MUTED-TEXT", err)

    def test_run_demoted_retry_leaves_muted_to_main(self):
        """advise-once の降格 Stop は exit 0 で main() 経路に戻る — block stderr 側で二重に出さない。"""
        code, err = self._run_with_block(
            {"transcript_path": "/x.jsonl", "stop_hook_active": True}
        )
        self.assertEqual(code, 0)
        self.assertNotIn("MUTED-TEXT", err)

    def _main_out(self, run_ret, reason):
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        marker = mock.Mock()
        with (
            mock.patch.object(self.M, "_run", lambda p: run_ret),
            mock.patch.object(self.M, "_memory_surface_at_stop", lambda p, t: reason),
            mock.patch.object(self.M, "_emit_turn_marker", marker),
            mock.patch.object(sys, "stdin", io.StringIO("{}")),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main()
        return code, marker, buf.getvalue().strip()

    def test_main_regex_block_skips_memory_and_marker(self):
        import io
        from unittest import mock

        with (
            mock.patch.object(self.M, "_run", lambda p: (2, None, "txt", [])),
            mock.patch.object(self.M, "_memory_surface_at_stop") as ms,
            mock.patch.object(self.M, "_emit_turn_marker") as mk,
            mock.patch.object(sys, "stdin", io.StringIO("{}")),
        ):
            self.assertEqual(main(), 2)
            ms.assert_not_called()
            mk.assert_not_called()

    def test_main_blocking_exit_skips_additionalcontext_even_with_worktree(self):
        # non-zero exit from _run must stay exactly as before, even if worktree warnings exist.
        import io
        from unittest import mock

        with (
            mock.patch.object(self.M, "_run", lambda p: (2, None, "txt", ["WT-WARN"])),
            mock.patch.object(self.M, "_memory_surface_at_stop") as ms,
            mock.patch.object(self.M, "_emit_turn_marker") as mk,
            mock.patch.object(sys, "stdin", io.StringIO("{}")),
        ):
            self.assertEqual(main(), 2)
            ms.assert_not_called()
            mk.assert_not_called()

    def test_main_regex_pass_with_memory_injects_additionalcontext(self):
        code, marker, out = self._main_out((0, 1.0, "txt", []), "REASON-TEXT")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertEqual(
            payload["hookSpecificOutput"]["additionalContext"], "REASON-TEXT"
        )
        self.assertEqual(payload["systemMessage"], "REASON-TEXT")
        marker.assert_not_called()

    def test_main_worktree_only_injects_additionalcontext(self):
        code, marker, out = self._main_out((0, 1.0, "txt", ["WT-WARN"]), None)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["additionalContext"], "WT-WARN")
        self.assertEqual(payload["systemMessage"], "WT-WARN")
        marker.assert_not_called()

    def test_main_combines_memory_and_worktree_reason_first(self):
        code, marker, out = self._main_out((0, 1.0, "txt", ["WT-WARN"]), "REASON-TEXT")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        combined = payload["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(combined, "REASON-TEXT\n\nWT-WARN")
        self.assertEqual(payload["systemMessage"], combined)
        marker.assert_not_called()

    def test_main_regex_pass_no_memory_emits_marker(self):
        code, marker, out = self._main_out((0, 1.0, "txt", []), None)
        self.assertEqual(code, 0)
        marker.assert_called_once()
        self.assertEqual(out, "")

    def test_end_to_end_through_real_surface_for_text(self):
        # Real cross-module chain: load the repo-source memory_surface (not the deployed
        # copy), seed a temp DB, stub only retrieval scoring, verify a reason is built.
        import importlib.util
        import tempfile
        from unittest import mock

        ms_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "claude_user-hooks",
            "memory_surface.py",
        )
        if not os.path.exists(ms_path):
            self.skipTest("repo-source memory_surface.py not found")
        spec = importlib.util.spec_from_file_location("memory_surface_src", ms_path)
        assert spec is not None and spec.loader is not None
        ms = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ms)
        db = os.path.join(tempfile.mkdtemp(), "idx.sqlite3")
        pick = [("/mem/feedback_x.md", "deploy 先だけ編集して repo を放置しない", -5.0)]
        with (
            mock.patch.object(ms, "DB_PATH", db),
            mock.patch.object(ms, "_hybrid_picks", lambda *a: list(pick)),
            mock.patch.object(self.M, "_memory_surface_mod", ms),
        ):
            r = _memory_surface_at_stop(
                {"stop_hook_active": False, "cwd": "/proj", "session_id": "sess"},
                "deploy したので repo も更新する",
            )
        assert r is not None
        self.assertIn("repo を放置しない", r)
        self.assertIn("/mem/feedback_x.md", r)

    def test_stop_latch_prevents_repeat_when_active_false(self):
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        tp = os.path.join(d, "t.jsonl")
        open(tp, "w").close()
        with open(tp[:-6] + ".turns", "w", encoding="utf-8") as f:
            f.write(
                "5 1000\n"
            )  # current-turn count "5", stable across the turn's Stops
        mod = self._fake_mod([("/m/x.md", "lesson X", 0.6)])
        payload = {
            "stop_hook_active": False,
            "cwd": "/p",
            "session_id": "s",
            "transcript_path": tp,
        }
        with mock.patch.object(self.M, "_memory_surface_mod", mod):
            first = _memory_surface_at_stop(payload, "output")
            second = _memory_surface_at_stop(payload, "output")
            with open(tp[:-6] + ".turns", "w", encoding="utf-8") as f:
                f.write("6 2000\n")  # next turn -> latch key differs -> allowed again
            third = _memory_surface_at_stop(payload, "output")
        assert first is not None
        self.assertIsNone(second)  # same turn -> latched
        assert third is not None  # new turn -> surfaces again


class WorktreeFixtureMixin:
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory(prefix="stop-worktree-")
        self.addCleanup(self.tmp.cleanup)  # ty: ignore[unresolved-attribute]
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": os.path.join(self.tmp.name, "home"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_EDITOR": "true",
                "GIT_SEQUENCE_EDITOR": "true",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        os.makedirs(self.env["HOME"])
        from unittest import mock

        home_patch = mock.patch.dict(os.environ, {"HOME": self.env["HOME"]})
        home_patch.start()
        self.addCleanup(home_patch.stop)  # ty: ignore[unresolved-attribute]

    def _job(
        self,
        root,
        job_id,
        session="session",
        write=True,
        status="completed",
        updated_at=None,
    ):
        path = os.path.join(
            self.env["HOME"], ".claude/plugins/data/codex-openai-codex/state/test/jobs"
        )
        os.makedirs(path, exist_ok=True)
        with open(
            os.path.join(path, job_id + ".json"), "w", encoding="utf-8"
        ) as stream:
            record = {
                "id": job_id,
                "sessionId": session,
                "write": write,
                "workspaceRoot": str(root),
                "status": status,
            }
            if updated_at is not None:
                record["updatedAt"] = updated_at
            json.dump(record, stream)

    def _git(self, *args, cwd):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def _repo(self, branch="main"):
        from pathlib import Path

        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        self._git("init", "-q", "-b", branch, cwd=repo)
        self._git("config", "user.name", "Stop test", cwd=repo)
        self._git("config", "user.email", "stop@example.invalid", cwd=repo)
        (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
        self._git("add", "tracked.txt", cwd=repo)
        self._git("commit", "-qm", "initial", cwd=repo)
        return repo

    def _linked(self, repo, name="linked", base="main"):
        from pathlib import Path

        path = Path(self.tmp.name) / name
        self._git(
            "worktree",
            "add",
            "-q",
            "-b",
            "codex/" + name,
            str(path),
            base,
            cwd=repo,
        )
        return path

    def _advance_main(self, repo):
        self._git("config", "user.name", "Stop test", cwd=repo)
        (repo / "tracked.txt").write_text("main advanced\n", encoding="utf-8")
        self._git("add", "tracked.txt", cwd=repo)
        self._git("commit", "-qm", "advance main", cwd=repo)

    def _check_cwd(self, cwd):
        return _check(
            "result",
            "result",
            set(),
            [],
            [],
            [],
            False,
            True,
            cwd=str(cwd),
        )

    def _check_repo(self, repo):
        return self._check_cwd(repo)


def _diagnostic_count(stderr: str) -> int:
    """fail-open 診断の件数 — git stderr が何行に跨っても 1 件は 1 件。"""
    return sum(line.startswith("worktree-cleanup:") for line in stderr.splitlines())


class WorktreeCleanupTest(WorktreeFixtureMixin, unittest.TestCase):
    """Worktree warning claims. Run: python3 -m unittest stop_checks"""

    def test_clean_merged_linked_worktree_warns(self):
        repo = self._repo()
        linked = self._linked(repo)
        self._advance_main(repo)

        code, warnings, blocking = self._check_repo(repo)

        self.assertEqual(code, 0)
        self.assertEqual(blocking, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn(
            f"git -C {shlex.quote(str(repo))} worktree remove -- {shlex.quote(str(linked))}",
            warnings[0],
        )
        self.assertNotIn("--force", warnings[0])
        self.assertIn("取り込み後", warnings[0])

    def test_running_codex_job_keeps_its_worktree_off_the_list(self):
        """稼働中 job の作業 root は、 成果物を書く前で clean に見えても削除候補にしない。"""
        repo = self._repo()
        linked = self._linked(repo)
        self._advance_main(repo)
        self._job(linked, "job-1", status="running")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_running_job_of_another_session_also_protects(self):
        """別 session の job でも作業 root は守る — 壊れるのは job であって session ではない。"""
        repo = self._repo()
        linked = self._linked(repo)
        self._advance_main(repo)
        self._job(linked, "job-1", session="other-session", status="queued")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_finished_codex_job_leaves_its_worktree_removable(self):
        repo = self._repo()
        linked = self._linked(repo)
        self._advance_main(repo)
        self._job(linked, "job-1", status="completed")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(len(warnings), 1)
        self.assertIn(str(linked), warnings[0])

    def test_running_job_elsewhere_does_not_shield_other_worktrees(self):
        repo = self._repo()
        linked = self._linked(repo)
        self._advance_main(repo)
        self._job(repo, "job-1", status="running")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(len(warnings), 1)
        self.assertIn(str(linked), warnings[0])

    def test_linked_worktree_under_repo_is_detected_from_main_cwd(self):
        repo = self._repo()
        linked = repo / ".claude" / "worktrees" / "linked"
        linked.parent.mkdir(parents=True)
        self._git(
            "worktree",
            "add",
            "-q",
            "-b",
            "codex/in-repo",
            str(linked),
            "main",
            cwd=repo,
        )
        self._advance_main(repo)

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(len(warnings), 1)
        self.assertIn(str(linked), warnings[0])

    def test_run_returns_warning_for_additional_context_and_keeps_exit_zero(self):
        import io
        from contextlib import redirect_stderr
        from pathlib import Path

        repo = self._repo()
        linked = self._linked(repo)
        transcript = Path(self.tmp.name) / "turn.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {"content": "check"},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "result"}]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code, _prompt_epoch, _text, warnings = _run(
                {"cwd": str(repo), "transcript_path": str(transcript)}
            )

        self.assertEqual(code, 0)
        self.assertNotIn(str(linked), stderr.getvalue())
        self.assertIn(str(linked), warnings[0])

    def test_run_routes_warning_without_transcript_text(self):
        import io
        from contextlib import redirect_stderr

        repo = self._repo()
        linked = self._linked(repo)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code, _prompt_epoch, _text, warnings = _run({"cwd": str(repo)})

        self.assertEqual(code, 0)
        self.assertNotIn(str(linked), stderr.getvalue())
        self.assertIn(str(linked), warnings[0])

    def test_dirty_linked_worktree_is_silent(self):
        repo = self._repo()
        linked = self._linked(repo)
        (linked / "tracked.txt").write_text("dirty\n", encoding="utf-8")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_clean_unreachable_commit_is_silent(self):
        repo = self._repo()
        linked = self._linked(repo)
        (linked / "tracked.txt").write_text("unmerged\n", encoding="utf-8")
        self._git("add", "tracked.txt", cwd=linked)
        self._git("commit", "-qm", "unmerged", cwd=linked)

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_ignored_only_worktree_is_silent(self):
        repo = self._repo()
        (repo / ".gitignore").write_text("drafts/\n", encoding="utf-8")
        self._git("add", ".gitignore", cwd=repo)
        self._git("commit", "-qm", "ignore drafts", cwd=repo)
        linked = self._linked(repo)
        (linked / "drafts").mkdir()
        (linked / "drafts" / "x.md").write_text("draft\n", encoding="utf-8")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_untracked_worktree_is_silent(self):
        repo = self._repo()
        linked = self._linked(repo)
        self._git("config", "status.showUntrackedFiles", "no", cwd=linked)
        (linked / "untracked.txt").write_text("untracked\n", encoding="utf-8")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_cwd_worktree_is_not_a_warning_candidate(self):
        repo = self._repo()
        current = self._linked(repo, "current")
        other = self._linked(repo, "other")
        self._advance_main(repo)

        _code, warnings, _blocking = self._check_cwd(current)

        self.assertEqual(len(warnings), 1)
        self.assertNotIn(str(current), warnings[0])
        self.assertIn(str(other), warnings[0])

    def test_nested_worktrees_are_excluded_from_candidates(self):
        repo = self._repo()
        parent = self._linked(repo, "parent")
        child = parent / "child"
        self._git(
            "worktree",
            "add",
            "-q",
            "-b",
            "codex/child",
            str(child),
            "main",
            cwd=repo,
        )
        (child / "tracked.txt").write_text("child dirty\n", encoding="utf-8")

        _code, warnings, _blocking = self._check_repo(repo)
        candidates = _worktree_candidates(str(repo))

        self.assertEqual(warnings, [])
        self.assertIsNotNone(candidates)
        assert candidates is not None
        self.assertNotIn(os.path.realpath(parent), candidates[2])
        self.assertNotIn(os.path.realpath(child), candidates[2])

    def test_main_tag_without_main_branch_is_silent(self):
        repo = self._repo()
        self._git("branch", "-m", "develop", cwd=repo)
        self._git("tag", "main", cwd=repo)
        self._linked(repo, "tagged", base="develop")

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_repeated_stop_warns_once_per_turn(self):
        import io
        from contextlib import redirect_stderr
        from pathlib import Path

        repo = self._repo()
        linked = self._linked(repo)
        self._advance_main(repo)
        transcript = Path(self.tmp.name) / "latch.jsonl"
        transcript.write_text(
            json.dumps({"type": "user", "message": {"content": "check"}})
            + "\n"
            + json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "result"}]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with open(str(transcript)[:-6] + ".turns", "w", encoding="utf-8") as turns:
            turns.write("7 1000\n")
        payload = {"cwd": str(repo), "transcript_path": str(transcript)}

        first_stderr = io.StringIO()
        with redirect_stderr(first_stderr):
            first_code, _epoch, _text, first_wt = _run(payload)
        second_stderr = io.StringIO()
        with redirect_stderr(second_stderr):
            second_code, _epoch, _text, second_wt = _run(payload)

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0)
        self.assertNotIn(str(linked), first_stderr.getvalue())
        self.assertNotIn(str(linked), second_stderr.getvalue())
        self.assertIn(str(linked), first_wt[0])
        self.assertEqual(second_wt, [])  # same-turn latch suppresses the repeat

    def test_stop_hook_active_retry_redelivers_before_turns_file_exists(self):
        import io
        from contextlib import redirect_stderr

        repo = self._repo()
        linked = self._linked(repo)
        self._advance_main(repo)

        with redirect_stderr(io.StringIO()):
            first_code, _e1, _t1, first_wt = _run(
                {"cwd": str(repo), "stop_hook_active": False}
            )
            second_code, _e2, _t2, second_wt = _run(
                {"cwd": str(repo), "stop_hook_active": True}
            )

        self.assertEqual(first_code, 0)
        self.assertIn(str(linked), first_wt[0])
        self.assertEqual(second_code, 0)
        self.assertIn(str(linked), second_wt[0])

    def test_prunable_worktree_is_silent_but_other_candidates_continue(self):
        import io
        import shutil
        from contextlib import redirect_stderr

        repo = self._repo()
        good = self._linked(repo, "good")
        prunable = self._linked(repo, "prunable")
        shutil.rmtree(prunable)
        self._advance_main(repo)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(len(warnings), 1)
        self.assertIn(str(good), warnings[0])
        self.assertNotIn(str(prunable), warnings[0])
        self.assertEqual(stderr.getvalue(), "")

    def test_no_linked_worktree_is_silent(self):
        _code, warnings, _blocking = self._check_repo(self._repo())

        self.assertEqual(warnings, [])

    def test_missing_main_and_master_is_silent(self):
        repo = self._repo()
        self._linked(repo)
        self._git("branch", "-m", "trunk", cwd=repo)

        _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_non_repo_fails_open_with_diagnostic(self):
        import io
        from contextlib import redirect_stderr
        from pathlib import Path

        path = Path(self.tmp.name) / "not-a-repo"
        path.mkdir()
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            warnings = _worktree_cleanup_warnings(str(path))

        self.assertEqual(warnings, [])
        self.assertIn("rev-parse --show-toplevel failed", stderr.getvalue())
        self.assertEqual(1, _diagnostic_count(stderr.getvalue()))

    def test_multiline_git_stderr_is_still_one_diagnostic(self):
        """診断は 1 件という主張を、 git stderr の行数に依存せず pin する。"""
        import io
        from contextlib import redirect_stderr
        from pathlib import Path
        from unittest import mock

        path = Path(self.tmp.name) / "not-a-repo"
        path.mkdir()
        stderr = io.StringIO()
        failure = subprocess.CompletedProcess([], 128, "", "line one\nline two")
        with (
            mock.patch.object(subprocess, "run", return_value=failure),
            redirect_stderr(stderr),
        ):
            warnings = _worktree_cleanup_warnings(str(path))

        self.assertEqual(warnings, [])
        self.assertGreater(len(stderr.getvalue().strip().splitlines()), 1)
        self.assertEqual(1, _diagnostic_count(stderr.getvalue()))

    def test_git_missing_fails_open_with_diagnostic(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": ""}, clear=False):
            with redirect_stderr(stderr):
                warnings = _worktree_cleanup_warnings(self.tmp.name)

        self.assertEqual(warnings, [])
        self.assertIn("worktree-cleanup", stderr.getvalue())

    def test_git_timeout_fails_open_with_diagnostic(self):
        import io
        from contextlib import redirect_stderr
        from pathlib import Path
        from unittest import mock

        fake_bin = Path(self.tmp.name) / "fake-bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text("#!/bin/sh\nexec /bin/sleep 1\n", encoding="utf-8")
        fake_git.chmod(0o755)
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"PATH": str(fake_bin)}, clear=False),
            mock.patch.object(
                sys.modules[__name__], "_GIT_COMMAND_TIMEOUT_SECONDS", 0.05
            ),
            redirect_stderr(stderr),
        ):
            warnings = _worktree_cleanup_warnings(self.tmp.name)

        self.assertEqual(warnings, [])
        self.assertIn("timed out", stderr.getvalue())

    @staticmethod
    def _fail_git_call(match, returncode=1, stderr="boom"):
        """Patch subprocess.run so a git call matching match(args) fails with returncode; other calls (incl. setUp's _git) run for real."""
        from unittest import mock

        real_run = subprocess.run

        def fake_run(args, **kwargs):
            if args[:1] == ["git"] and match(args[1:]):
                return subprocess.CompletedProcess(
                    args, returncode, stdout="", stderr=stderr
                )
            return real_run(args, **kwargs)

        return mock.patch.object(subprocess, "run", side_effect=fake_run)

    def test_git_command_returns_none_on_nonzero_exit(self):
        # unit-level pin: _git_command itself must fail-safe (None), not surface the CompletedProcess.
        with self._fail_git_call(lambda a: True):
            self.assertIsNone(_git_command(["status", "--porcelain"]))

    def test_failing_git_status_keeps_candidate_silent(self):
        # git status crashing must not be misread as "clean" -> no false removal warning.
        repo = self._repo()
        self._linked(repo)
        self._advance_main(repo)

        with self._fail_git_call(lambda a: "status" in a):
            code, warnings, blocking = self._check_repo(repo)

        self.assertEqual(code, 0)
        self.assertEqual(blocking, [])
        self.assertEqual(warnings, [])

    def test_failing_merge_base_keeps_candidate_silent(self):
        repo = self._repo()
        self._linked(repo)
        self._advance_main(repo)

        with self._fail_git_call(lambda a: "merge-base" in a, returncode=128):
            _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])

    def test_failing_worktree_list_keeps_all_silent(self):
        repo = self._repo()
        self._linked(repo)
        self._advance_main(repo)

        with self._fail_git_call(lambda a: "worktree" in a and "list" in a):
            _code, warnings, _blocking = self._check_repo(repo)

        self.assertEqual(warnings, [])


class CodexSharedWriteTest(WorktreeFixtureMixin, unittest.TestCase):
    """Codex job-state warning claims. Run: python3 -m unittest stop_checks"""

    def _payload(self):
        return {
            "session_id": "session",
            "transcript_path": os.path.join(self.tmp.name, "turn.jsonl"),
        }

    def test_primary_write_warns_and_latches_by_job(self):
        repo = self._repo()
        self._job(repo, "job-1", status="running")
        first = _codex_shared_write_warnings(self._payload())
        second = _codex_shared_write_warnings(self._payload())
        self.assertEqual(len(first), 1)
        self.assertIn("job-1", first[0])
        self.assertIn(str(repo), first[0])
        self.assertIn("cancel job-1", first[0])
        self.assertEqual(second, [])

    def test_symlinked_primary_warns_but_symlinked_linked_is_silent(self):
        repo = self._repo()
        main_alias = os.path.join(self.tmp.name, "repo-alias")
        linked = self._linked(repo)
        linked_alias = os.path.join(self.tmp.name, "linked-alias")
        os.symlink(repo, main_alias)
        os.symlink(linked, linked_alias)
        self._job(main_alias, "job-main-alias")
        self._job(linked_alias, "job-linked-alias")

        warnings = _codex_shared_write_warnings(self._payload())

        self.assertEqual(len(warnings), 1)
        self.assertIn("job-main-alias", warnings[0])
        self.assertIn(f"workspaceRoot={main_alias}", warnings[0])
        self.assertNotIn("job-linked-alias", warnings[0])

    def test_queued_write_warns_with_cancel_action(self):
        repo = self._repo()
        self._job(repo, "job-queued", status="queued")

        warnings = _codex_shared_write_warnings(self._payload())

        self.assertEqual(len(warnings), 1)
        self.assertIn("status=queued", warnings[0])
        self.assertIn("cancel job-queued", warnings[0])
        self.assertNotIn("完了済み", warnings[0])

    def test_new_job_warns_and_nonmatching_jobs_are_silent(self):
        repo = self._repo()
        self._job(self._linked(repo), "job-linked")
        self._job(repo, "job-read", write=False)
        self._job(repo, "job-other", session="other")
        self.assertEqual(_codex_shared_write_warnings(self._payload()), [])
        self._job(repo, "job-2")
        self.assertEqual(len(_codex_shared_write_warnings(self._payload())), 1)

    def test_missing_and_broken_state_are_fail_open_and_valid_job_survives(self):
        payload = self._payload()
        self.assertEqual(_codex_shared_write_warnings(payload), [])
        repo = self._repo()
        jobs = os.path.join(
            self.env["HOME"], ".claude/plugins/data/codex-openai-codex/state/test/jobs"
        )
        os.makedirs(jobs, exist_ok=True)
        with open(os.path.join(jobs, "broken.json"), "w", encoding="utf-8") as stream:
            stream.write("{")
        self._job(repo, "job-valid")
        self.assertEqual(len(_codex_shared_write_warnings(payload)), 1)

    def test_four_jobs_list_three_and_count_extra(self):
        repo = self._repo()
        self._job(repo, "job-completed-new", updated_at="2026-07-23T04:00:00Z")
        self._job(
            repo,
            "job-queued-old",
            status="queued",
            updated_at="2026-07-23T01:00:00Z",
        )
        self._job(
            repo,
            "job-running-new",
            status="running",
            updated_at="2026-07-23T03:00:00Z",
        )
        self._job(
            repo,
            "job-queued-new",
            status="queued",
            updated_at="2026-07-23T02:00:00Z",
        )
        warnings = _codex_shared_write_warnings(self._payload())
        self.assertEqual(len(warnings), 4)
        self.assertEqual(sum("workspaceRoot=" in warning for warning in warnings), 3)
        self.assertIn("job-running-new", warnings[0])
        self.assertIn("job-queued-new", warnings[1])
        self.assertIn("job-queued-old", warnings[2])
        self.assertNotIn("job-completed-new", warnings[:3])
        self.assertIn("追加で 1 件", warnings[-1])

    def test_turn_latches_are_independent_with_turns(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        repo = self._repo()
        self._job(repo, "job-1")
        transcript = os.path.join(self.tmp.name, "turn.jsonl")
        with open(transcript, "w", encoding="utf-8") as stream:
            stream.write("{}\n")
        with open(transcript[:-6] + ".turns", "w", encoding="utf-8") as stream:
            stream.write("1 1000\n")
        payload = {
            "session_id": "session",
            "transcript_path": transcript,
            "stop_hook_active": False,
        }
        with (
            mock.patch(
                f"{__name__}._worktree_cleanup_warnings",
                side_effect=[["wt"], [], ["wt2"]],
            ),
            redirect_stderr(io.StringIO()),
        ):
            _code, _epoch, _text, first = _run(payload)
            _code, _epoch, _text, second = _run(payload)
            self._job(repo, "job-2")
            with open(transcript[:-6] + ".turns", "w", encoding="utf-8") as stream:
                stream.write("2 1000\n")
            _code, _epoch, _text, third = _run(payload)

        self.assertEqual(len(first), 2)
        self.assertIn("wt", first[0])
        self.assertIn("job-1", first[1])
        self.assertEqual(second, [])
        self.assertEqual(len(third), 2)
        self.assertIn("wt2", third[0])
        self.assertIn("job-2", third[1])

    def test_stop_hook_active_delivers_all_structural_checks(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        payload = {
            "transcript_path": self._payload()["transcript_path"],
            "stop_hook_active": True,
        }
        with (
            mock.patch(f"{__name__}._worktree_cleanup_warnings", return_value=["wt"]),
            mock.patch(
                f"{__name__}._codex_shared_write_warnings", return_value=["codex"]
            ) as codex_check,
            mock.patch(
                f"{__name__}._handoff_todos_sync_warnings", return_value=["handoff"]
            ) as handoff_check,
            redirect_stderr(io.StringIO()),
        ):
            _code, _epoch, _text, warnings = _run(payload)
        self.assertEqual(warnings, ["wt", "codex", "handoff"])
        codex_check.assert_called_once()
        handoff_check.assert_called_once()


if __name__ == "__main__":
    sys.exit(main())
