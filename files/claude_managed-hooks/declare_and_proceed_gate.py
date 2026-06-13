#!/usr/bin/env python3
r"""PreToolUse:^AskUserQuestion$ deny-gate — declare-and-proceed enforcement.

When the question is a DECIDABLE routing ("A経由かB経由か" / "どちらから調査") or
per-unit/per-batch confirmation ("この draft で良い?"), the gate requires the
declare-and-proceed skill be invoked in the current turn within the last 5 min;
otherwise it DENIES via JSON permissionDecision so the 3-check (material 取得可? /
default 可? / parallel 両立可?) runs BEFORE the question, not after.

After invoking the skill the model either decides itself or, for a genuine
exception (user-taste / design-level / unrecoverable destructive-op pre-approval),
re-issues the question (now allowed). Such exceptions are phrased openly
("which X?") and do not match these narrow patterns, so they never need the skill.

Twin of skill_reminder_gate.py (turn-scan, 5-min window, JSON deny, fail-open),
scoped to one tool/skill. Narrow-recall/high-precision: a false-positive costs
one skill invoke + re-ask, a slip lets a decidable question reach the user ungated.

deploy: /etc/claude-code/hooks/ (copy_dir で自動)。canonical source は
files/claude_managed-hooks/。両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
import unittest

TARGET_SKILL = "declare-and-proceed"
SKILL_WINDOW_SECONDS = 300  # active 窓 = 現 turn かつ直近 5 分以内

# Per-unit/per-batch 確認 ("これで良い?" 系) の closed form のみ拾う。 design は
# 通常 open form ("which X?") なので除外。 高確度語限定で false positive 抑制。
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

# 調査/実行 route の binary/ternary ("どちらから" / "A 経由 か B 経由 か")。 design-level
# の "which architecture" を除外するため route 語に anchor する。
ROUTING_PATTERNS: list[str] = [
    r"どちら(から|を先に|で進め|を調査)",
    r"どっち(から|を先に)",
    r"経由\s*(で|か)[^。\n]{0,20}(経由|か[?？])",
    r"(から|を)\s*調査しますか",
    r"(から|を)\s*着手しますか",
    r"どこから\s*(調査|着手|始め|見)",
    r"先に\s*(調査|確認|読み?)\s*ますか",
    r"[ぁ-んァ-ヶ一-鿿\w]+するか\s*[ぁ-んァ-ヶ一-鿿\w]+するか",  # SKILL の正典 trigger
    r"(どう|どの|どれ)を?\s*[ぁ-んァ-ヶ一-鿿\w]+\s*しますか",  # 「<X> を どう <verb> しますか?」 form (options 列挙されると routing)
    r"それとも[^。\n]{0,40}(ますか|ましょうか|でしょうか|します[?？])",  # 「A ますか、それとも B ますか」 丁寧 alternation 二択
]

CONFIRM_RE = re.compile("|".join(CONFIRM_PATTERNS), re.IGNORECASE)
ROUTING_RE = re.compile("|".join(ROUTING_PATTERNS), re.IGNORECASE)


def _question_text(tool_input: dict) -> str:
    """Concatenate every question / header / option label for scanning."""
    parts: list[str] = []
    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        return ""
    for q in questions:
        if not isinstance(q, dict):
            continue
        for key in ("question", "header"):
            v = q.get(key)
            if isinstance(v, str):
                parts.append(v)
        options = q.get("options")
        if isinstance(options, list):
            for opt in options:
                if isinstance(opt, dict) and isinstance(opt.get("label"), str):
                    parts.append(opt["label"])
    return "\n".join(parts)


def _detect(text: str) -> str | None:
    """Return a citation string for the matched decidable pattern, or None."""
    m = CONFIRM_RE.search(text)
    if m:
        return "per-unit 確認: 「%s」" % m.group(0)
    m = ROUTING_RE.search(text)
    if m:
        return "routing: 「%s」" % m.group(0)
    return None


# --- current-turn skill scan ---


_TAIL_BUFSIZE = 128 * 1024  # 後方読みブロック。実測 turn mean≈110KB を 1 read で覆う


def _load_tail(path: str, turns: int = 1, bufsize: int = _TAIL_BUFSIZE) -> list[dict]:
    """末尾から turn boundary を turns 個含むまで後方読みで返す; boundary が turns 未満なら全件。"""
    try:
        with open(path, "rb") as f:
            pos = f.seek(0, os.SEEK_END)
            pending = b""  # 行頭が手前ブロックにある途中行 (次の読みで結合)
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
                    if _is_turn_boundary(obj):
                        seen += 1
                        if seen >= turns:
                            tail.reverse()
                            return tail
            line = pending.strip()  # BOF: 先頭断片は完全な 1 行
            if line:
                try:
                    tail.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            tail.reverse()
            return tail  # boundary < turns: 集めた全件
    except OSError:
        return []


def _is_turn_boundary(obj: dict) -> bool:
    """human-input turn の起点か。isMeta(skill 展開) と tool_result 継続は起点でない。"""
    if obj.get("type") != "user" or obj.get("isMeta"):
        return False
    msg = obj.get("message", {})
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") != "tool_result" for b in content
        )
    return False


def _parse_ts(ts) -> float | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _skill_active(
    entries: list[dict], skill: str, now: float, window_s: int
) -> bool | None:
    """target skill が 現 turn のうち直近 window_s 秒以内に invoke 済か (それより前は drop)。boundary 不在は None (fail-open ALLOW)。

    Skill 呼出形: assistant tool_use, name=="Skill", input=={"skill":"<name>"}.
    """
    start_idx = -1
    for i in range(len(entries) - 1, -1, -1):
        if _is_turn_boundary(entries[i]):
            start_idx = i + 1
            break
    if start_idx == -1:
        return None
    cutoff = now - window_s
    for idx, obj in enumerate(entries):
        if obj.get("type") != "assistant":
            continue
        if idx < start_idx:
            continue  # 現 turn 外
        ep = _parse_ts(obj.get("timestamp"))
        if ep is not None and ep < cutoff:
            continue  # 現 turn 内でも 300 秒以上前は drop
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Skill":
                continue
            inp = block.get("input") or {}
            if isinstance(inp, dict) and inp.get("skill") == skill:
                return True
    return False


# --- deny emission (writing-skills の deny-wording 規律。文面は意図的に冗長・trim 禁止) ---


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _deny(hit: str) -> None:
    _emit_deny(
        f"この AskUserQuestion は {hit} を含み、 自分で決められる routing / per-batch "
        f"確認に見えます。 編集前に /declare-and-proceed を当 turn で invoke して 3-check "
        f"(material が code/log/config/doc で取れるか / default で進めるか / parallel 実行で "
        f"両立できるか) を verbalize してください。 いずれか yes なら user に投げず自分で "
        f"決め、 1 unit 目で方針を宣言して proceed します。 genuine な user-taste / "
        f"design-level (architecture / naming / priority / scope) / 不可逆 destructive op "
        f"の pre-approval なら、 skill invoke 後そのまま AskUserQuestion が通ります "
        f"(hook 自身は質問を変更しません)。"
    )


def cmd_gate(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("tool_name") != "AskUserQuestion":
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    text = _question_text(tool_input)
    if not text:
        return
    hit = _detect(text)
    if hit is None:
        return  # decidable でない質問は素通り (genuine 例外を含む)
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return  # fail-open
    now = time.time()
    entries = _load_tail(
        transcript_path, 1
    )  # 現 turn のみ (drop は _skill_active が ts で実施)
    if not entries:
        return  # fail-open
    active = _skill_active(entries, TARGET_SKILL, now, SKILL_WINDOW_SECONDS)
    if active is None or active:
        return  # fail-open (boundary 不在) / skill 当 turn invoke 済 → 通す
    _deny(hit)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        cmd_gate(payload)
    except Exception:
        pass  # fail-open: hook bug が tool を block しない
    return 0


class GateTest(unittest.TestCase):
    """emit-vs-comply + branch coverage (lost /tmp smoke, now tracked).
    Run: python3 -m unittest declare_and_proceed_gate"""

    @staticmethod
    def _iso(ep):
        return datetime.datetime.fromtimestamp(ep, datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

    @staticmethod
    def _user(content="do it"):
        return {"type": "user", "message": {"content": content}}

    @classmethod
    def _skill(cls, name, ts=None):
        e = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": {"skill": name}}
                ]
            },
        }
        if ts is not None:
            e["timestamp"] = cls._iso(ts)
        return e

    @staticmethod
    def _transcript(entries):
        import tempfile

        p = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return p

    @staticmethod
    def _q(text):
        return [
            {
                "question": text,
                "header": "x",
                "options": [{"label": "A"}, {"label": "B"}],
            }
        ]

    def _gate(self, questions, entries=None, tool="AskUserQuestion", transcript=True):
        import io
        from contextlib import redirect_stdout

        payload = {"tool_name": tool, "tool_input": {"questions": questions}}
        if transcript:
            payload["transcript_path"] = self._transcript(entries or [])
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_gate(payload)
        out = buf.getvalue().strip()
        return json.loads(out) if out else None

    def _reason(self, result):
        self.assertIsNotNone(result)
        hso = result["hookSpecificOutput"]
        self.assertEqual(hso["permissionDecision"], "deny")
        return hso["permissionDecisionReason"]

    # --- D4: question-text aggregation ---
    def test_question_text_aggregates(self):
        ti = {
            "questions": [
                {
                    "question": "Q1",
                    "header": "H1",
                    "options": [{"label": "L1"}, {"label": "L2"}],
                },
                "not-a-dict",
            ]
        }
        text = _question_text(ti)
        for part in ("Q1", "H1", "L1", "L2"):
            self.assertIn(part, text)
        self.assertNotIn("not-a-dict", text)  # non-dict entries skipped
        self.assertEqual(_question_text({}), "")

    # --- D5: detect CONFIRM / ROUTING / open-design ---
    def test_detect_confirm(self):
        for q in (
            "これで良いですか?",
            "この方針で良いですか",
            "適用して良いですか",
            "進めて良いですか",
        ):
            self.assertTrue((_detect(q) or "").startswith("per-unit"), q)

    def test_detect_routing(self):
        for q in (
            "どちらから調査しますか?",
            "実装するか削除するか迷う",
            "どこから着手しますか",
            "設計を詰めますか、それとも実装に入りますか?",
        ):
            self.assertTrue((_detect(q) or "").startswith("routing"), q)

    def test_detect_open_design_none(self):
        for q in ("命名はどうするのが良いと思いますか?", "次に何をすべきでしょうか"):
            self.assertIsNone(_detect(q), q)

    # --- D6: skill-active = current turn AND within 5 min ---
    def test_skill_active(self):
        now, w, s = 1_000_000.0, SKILL_WINDOW_SECONDS, TARGET_SKILL
        u = self._user()
        self.assertTrue(_skill_active([u, self._skill(s, now - 60)], s, now, w))
        self.assertFalse(  # different skill
            _skill_active([u, self._skill("writing-code", now - 60)], s, now, w)
        )
        self.assertFalse(  # same turn but older than window
            _skill_active([u, self._skill(s, now - 600)], s, now, w)
        )
        self.assertFalse(  # prior-turn invoke excluded
            _skill_active([u, self._skill(s, now - 10), self._user()], s, now, w)
        )
        self.assertTrue(  # exactly at window edge -> kept (cutoff is strict <)
            _skill_active([u, self._skill(s, now - w)], s, now, w)
        )
        self.assertTrue(  # no timestamp -> not dropped
            _skill_active([u, self._skill(s)], s, now, w)
        )
        self.assertIsNone(_skill_active([self._skill(s)], s, now, w))  # boundary absent

    # --- D1/D2/D3/D7: cmd_gate emit-vs-comply ---
    def test_gate_denies_confirm_without_skill(self):
        r = self._reason(
            self._gate(self._q("この方針で良いですか?"), entries=[self._user()])
        )
        self.assertIn("declare-and-proceed", r)

    def test_gate_denies_routing_without_skill(self):
        r = self._reason(
            self._gate(self._q("どちらから調査しますか?"), entries=[self._user()])
        )
        self.assertIn("declare-and-proceed", r)
        self.assertIn("routing", r)  # routing-specific citation, not confirm

    def test_gate_allows_when_skill_active(self):  # D2 escape hatch
        self.assertIsNone(
            self._gate(
                self._q("この方針で良いですか?"),
                entries=[self._user(), self._skill(TARGET_SKILL)],
            )
        )

    def test_gate_allows_open_design(self):  # D3 not detected
        self.assertIsNone(
            self._gate(
                self._q("命名はどうするのが良いと思いますか?"), entries=[self._user()]
            )
        )

    def test_gate_failopen(self):
        q = self._q("この方針で良いですか?")
        self.assertIsNone(self._gate(q, tool="Edit"))  # non-AskUserQuestion
        self.assertIsNone(self._gate(q, transcript=False))  # no transcript
        self.assertIsNone(  # boundary absent
            self._gate(q, entries=[self._skill(TARGET_SKILL)])
        )
        self.assertIsNone(self._gate([], entries=[self._user()]))  # empty text
        self.assertIsNone(self._gate(q, entries=[]))  # empty transcript
        self.assertEqual(self._raw("nope"), "")  # non-dict payload
        self.assertEqual(  # non-dict tool_input
            self._raw({"tool_name": "AskUserQuestion", "tool_input": None}), ""
        )

    @staticmethod
    def _raw(payload):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_gate(payload)
        return buf.getvalue().strip()

    def test_gate_denies_when_skill_too_old(self):
        # D6 end-to-end: same-turn invoke older than 5 min is dropped -> deny.
        old = 1_000_000  # epoch far before real time.time()
        self.assertIsNotNone(
            self._gate(
                self._q("この方針で良いですか?"),
                entries=[self._user(), self._skill(TARGET_SKILL, old)],
            )
        )

    def test_main_failopen_on_exception(self):
        # fail-open: hook bug が tool を block しない (_load_tail raising -> no deny).
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        payload = json.dumps(
            {
                "tool_name": "AskUserQuestion",
                "tool_input": {"questions": self._q("この方針で良いですか?")},
                "transcript_path": "/x",
            }
        )
        buf = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", io.StringIO(payload)),
            mock.patch.object(
                sys.modules[__name__], "_load_tail", side_effect=RuntimeError("boom")
            ),
            redirect_stdout(buf),
        ):
            rc = main()
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "")  # no deny emitted

    def test_is_turn_boundary(self):
        self.assertTrue(
            _is_turn_boundary({"type": "user", "message": {"content": "hi"}})
        )
        self.assertFalse(  # isMeta (skill expansion) is not a boundary
            _is_turn_boundary(
                {"type": "user", "isMeta": True, "message": {"content": "x"}}
            )
        )
        self.assertFalse(_is_turn_boundary({"type": "assistant", "message": {}}))
        self.assertFalse(  # list of only tool_result -> continuation
            _is_turn_boundary(
                {"type": "user", "message": {"content": [{"type": "tool_result"}]}}
            )
        )
        self.assertTrue(  # list with a non-tool_result block -> boundary
            _is_turn_boundary(
                {
                    "type": "user",
                    "message": {"content": [{"type": "tool_result"}, {"type": "text"}]},
                }
            )
        )
        self.assertFalse(_is_turn_boundary({"type": "user", "message": {}}))

    def test_parse_ts(self):
        self.assertIsNotNone(_parse_ts("2026-06-02T04:45:24.945Z"))
        for bad in (None, "", "not-a-date", 123):
            self.assertIsNone(_parse_ts(bad))


if __name__ == "__main__":
    sys.exit(main())
