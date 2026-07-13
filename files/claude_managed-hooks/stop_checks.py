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
     confirm-routing-to-user / intent-without-task), on the turn's first Stop (stop_hook_active false)

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
import sys
import time
import unittest

# Kept identical to claude_court_guard so the Stop hook remains fail-open without subprocess IO.
COURT_RE_STRAY = re.compile(r"(?m)^[ \t]*(?:court|count)[ \t]*$")
COURT_RE_INVOKE_LEAK = re.compile(r'(?m)^[ \t]*<invoke name="')


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
INTENT_DECLARE_RE = re.compile("|".join(INTENT_DECLARE_PATTERNS), re.IGNORECASE)

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
DONE_CLAIM_RE = re.compile(r"(実装|修正|対応)?完了|\bdone\b|\blanded\b|着地", re.IGNORECASE)
EXECUTABLE_ARTIFACT_RE = re.compile(
    r"\.(py|sh)$|/hooks/|/usr/local/bin/|settings.*\.json$", re.IGNORECASE
)
UI_ARTIFACT_RE = re.compile(
    r"\.(css|scss|tsx|jsx|vue|svelte|html)$", re.IGNORECASE
)

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

    # intent-without-task (block if work-execution declaration without task tool)
    m = INTENT_DECLARE_RE.search(stripped)
    if m and not (tool_names & TASK_TOOLS):
        if _tasks_gated_off(model):
            mytask_recorded = any(_is_mytask_path(p) for p in edited_paths)
            if not mytask_recorded:
                blocking.append(
                    f"intent-without-task: 作業遂行宣言「{m.group(0)}」を検出。現行モデルは "
                    f"tengu_vellum_ash gate で Task ツールが無効化されています。代替の "
                    f"CreateMyTask skill で drafts/tasks/<session>.json に作業を記録してから"
                    f"再出力してください。"
                )
        else:
            blocking.append(
                f"intent-without-task: 作業遂行宣言「{m.group(0)}」を検出しましたが、このターンに"
                f" TaskCreate/TaskUpdate/TodoWrite が記録されていません。"
                f" System §計画と遂行: 全作業項目を大小に関わらず Task で計画・追跡。"
                f" TaskCreate で作業を登録 (または既存タスクを TaskUpdate) してから再出力してください。"
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
        unrun_paths = [p for p in executable_paths if not _artifact_was_run(p, bash_commands)]
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


def _run(payload: dict) -> tuple[int, float | None, str]:
    # Returns (exit_code, prompt_epoch, text); text feeds Stop memory surfacing.
    if not isinstance(payload, dict):
        return 0, None, ""
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0, None, ""
    entries = _load_tail(transcript_path, turns=2)
    if not entries:
        return 0, None, ""
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
    if isinstance(last_msg, str) and last_msg:
        text = (text + "\n" + last_msg) if text else last_msg
        final_text = last_msg
    if not text:
        return 0, prompt_epoch, ""
    declare_active = _declare_proceed_active(entries, time.time())
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
    )
    # advise-once: a stop_hook_active retry never re-blocks — demote to pass (see docstring turn-marker / Exit).
    if exit_code == 2 and payload.get("stop_hook_active"):
        for line in blocking:
            sys.stderr.write("advise-once (block demoted to pass): " + line + "\n")
        for line in warnings:
            sys.stderr.write(line + "\n")
        return 0, prompt_epoch, text
    for line in warnings + blocking:
        sys.stderr.write(line + "\n")
    return exit_code, prompt_epoch, text


def _stop_latch_key(payload: dict) -> tuple[str, str] | None:
    """(turn key, latch-file path) or None; turn key = the .turns count, which bumps only at a clean turn end so it stays constant across a turn's Stops (incl. continuations)."""
    try:
        path = _counter_path(payload)  # session-id fallback may makedirs -> OSError
        if not path:
            return None
        with open(path, encoding="utf-8") as f:
            return f.read().split()[0], path + ".surf"
    except (OSError, IndexError):
        return None


def _stop_latched(payload: dict) -> bool:
    """True if a Stop memory surface already fired this turn (counter-keyed, independent of stop_hook_active)."""
    k = _stop_latch_key(payload)
    if k is None:
        return False
    key, lpath = k
    try:
        with open(lpath, encoding="utf-8") as f:
            return f.read().strip() == key
    except OSError:
        return False


def _stop_latch_set(payload: dict) -> None:
    k = _stop_latch_key(payload)
    if k is None:
        return
    key, lpath = k
    try:
        with open(lpath, "w", encoding="utf-8") as f:
            f.write(key)
    except OSError:
        pass


def _memory_surface_at_stop(payload: dict, text: str) -> str | None:
    """Regex-pass path: a Stop additionalContext reason surfacing the top memory entry for the turn's output `text`, else None; fires at most once/turn (stop_hook_active gate + counter latch + throttle) and is fully fail-open."""
    if _memory_surface_mod is None or payload.get("stop_hook_active"):
        return None
    if not text or not text.strip():
        return None
    # Turn-scoped latch: guarantee max-once even if the runtime does not set
    # stop_hook_active on the additionalContext continuation (belt to that gate).
    if _stop_latched(payload):
        return None
    session_id = payload.get("session_id") or ""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    project_id = _memory_surface_mod._encoded_project_id(cwd)
    try:
        picks = _memory_surface_mod.surface_for_text(text, session_id, project_id, 1)
    except Exception:
        return None
    if not picks:
        return None
    _stop_latch_set(payload)
    file_path, reminder, _score = picks[0]
    display = reminder or "(reminder 未設定)"
    return (
        "<memory-surface>\n"
        f"今ターンの出力に関連する過去の教訓: {display} 詳細: {file_path}\n"
        "完了前に今の応答がこの教訓に抵触しないか確認し、 抵触するなら修正してから完了して "
        "ください (抵触しなければそのまま完了して構いません)。\n"
        "</memory-surface>"
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
        exit_code, prompt_epoch, text = _run(payload)
    except Exception:
        # fail-open: an enforcement glitch never blocks the turn.
        exit_code, prompt_epoch, text = 0, None, ""
    if exit_code != 0:
        return exit_code  # regex enforcement blocked — unchanged path, no marker/memory
    # regex passed: surface one memory entry for the assistant's own output (if any) and
    # inject it via Stop additionalContext, which keeps the turn going (v2.1.163+).
    try:
        reason = _memory_surface_at_stop(payload, text)
    except Exception:
        reason = None
    if reason:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "Stop",
                        "additionalContext": reason,
                    },
                    "systemMessage": reason,
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
        self.assertEqual(_run("nope"), (0, None, ""))  # ty: ignore[invalid-argument-type]
        self.assertEqual(_run({}), (0, None, ""))


class EnforcementFamilyTest(unittest.TestCase):
    """H3 evaluative regression + H4 confirm/routing gate. Run: python3 -m unittest stop_checks"""

    @staticmethod
    def _c(
        text,
        tools=None,
        paths=None,
        commands=None,
        final_text=None,
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
        )

    def _blk(self, *a, **k):
        return self._c(*a, **k)[2]

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
            code = _run(
                {"transcript_path": transcript, "stop_hook_active": True}
            )[0]
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

    def test_intent_gated_without_mytask_blocks_for_create_mytask(self):
        with self._gate_config({"tengu_vellum_ash": ["opus-4-8"]}):
            blk = self._blk("修正します", model="claude-opus-4-8")
        self.assertTrue(any("CreateMyTask" in b for b in blk))

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
            blk = self._blk("修正します", model="claude-opus-4-8")
        self.assertTrue(any("TaskCreate で作業を登録" in b for b in blk))

    def test_intent_declare_alone_blocks(self):
        code, _w, blk = self._c("修正します")
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

    def test_intent_fenced_not_fired(self):
        # strip_fences removes the declaration; bare prose is clean so no block.
        text = "検討結果:\n```\nやります\n```\n以上です。"
        blk = self._blk(text)
        self.assertFalse(any("intent-without-task" in b for b in blk))

    def test_intent_independent_of_other_families(self):
        # intent-without-task fires on its own; other families are not required.
        blk = self._blk("実装します")
        self.assertTrue(any("intent-without-task" in b for b in blk))

    def test_existing_block_families_still_fire(self):
        # regression: pre-existing block families unaffected by the new declare_active param.
        self.assertEqual(self._c("省略しません")[0], 2)
        self.assertEqual(self._c("学習しました")[0], 2)
        self.assertEqual(self._c("想定外でした")[0], 2)
        self.assertTrue(
            any("known-possible" in b for b in self._blk("autosquash はできない"))
        )


class CourtWarningTest(unittest.TestCase):
    def _warnings(self, text: str) -> tuple[int, list[str]]:
        code, warnings, blocking = _check(
            text, text, set(), [], [], [], False, False
        )
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
            mock.patch.object(self.M, "_run", lambda p: (2, None, "txt")),
            mock.patch.object(self.M, "_memory_surface_at_stop") as ms,
            mock.patch.object(self.M, "_emit_turn_marker") as mk,
            mock.patch.object(sys, "stdin", io.StringIO("{}")),
        ):
            self.assertEqual(main(), 2)
            ms.assert_not_called()
            mk.assert_not_called()

    def test_main_regex_pass_with_memory_injects_additionalcontext(self):
        code, marker, out = self._main_out((0, 1.0, "txt"), "REASON-TEXT")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertEqual(
            payload["hookSpecificOutput"]["additionalContext"], "REASON-TEXT"
        )
        self.assertEqual(payload["systemMessage"], "REASON-TEXT")
        marker.assert_not_called()

    def test_main_regex_pass_no_memory_emits_marker(self):
        code, marker, out = self._main_out((0, 1.0, "txt"), None)
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


if __name__ == "__main__":
    sys.exit(main())
