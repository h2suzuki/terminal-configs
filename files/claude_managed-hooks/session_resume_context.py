#!/usr/bin/env python3
"""SessionStart hook: inject the prior session's last RECENT_TURNS turns as resume context (startup / clear only; fail-open)."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import unittest


HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
# resume context として読む直近 turn 数 (handoff は末尾数 turn に残る公算)
RECENT_TURNS = 3
MAX_INJECT_LEN = 4000  # 超過時は末尾 (= 最新 = handoff 側) を残して truncate
MIN_TEXT_LEN = 30  # これ未満の抽出 text は inject しない


def _encoded_project_id(cwd: str) -> str:
    """Match Claude Code's projects/<encoded-cwd>/ form: '/' -> '-'."""
    return cwd.replace("/", "-")


AGENTS_TIMEOUT = 5  # `claude agents --json` の上限 (startup blocking ゆえ短く)


def _live_session_ids() -> set[str] | None:
    """`claude agents --json` が報告する live session の sid 集合。 取得失敗時 None。"""
    try:
        r = subprocess.run(
            ["claude", "agents", "--json"],
            capture_output=True,
            text=True,
            timeout=AGENTS_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    return {a["sessionId"] for a in data if isinstance(a, dict) and a.get("sessionId")}


def _select_prior(files: list[str], live_sids: set[str] | None) -> str | None:
    """files=mtime 降順 (= 最近使った順)。 live でない最新を継ぐ; registry 不明 (None) なら最新で best-effort。"""
    for f in files:
        if live_sids is None or os.path.basename(f).rsplit(".", 1)[0] not in live_sids:
            return f
    return None  # 候補が全て live → 引き継ぐ「終了済」session 無し


def _find_prior_session(cwd: str, current_session_id: str) -> str | None:
    project_dir = os.path.join(PROJECTS_DIR, _encoded_project_id(cwd))
    if not os.path.isdir(project_dir):
        return None
    files = [
        f
        for f in glob.glob(os.path.join(project_dir, "*.jsonl"))
        if os.path.basename(f).rsplit(".", 1)[0] != current_session_id
    ]
    if not files:
        return None
    # 最近使った順に並べ、 live でない先頭を継ぐ
    files.sort(key=os.path.getmtime, reverse=True)
    return _select_prior(files, _live_session_ids())


_TAIL_BUFSIZE = 128 * 1024  # 後方読みブロック


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


def _turns_text(entries: list[dict]) -> str:
    """entries (= 直近 turn 群) から user prompt と assistant text を時系列で抽出・整形。"""
    parts: list[str] = []
    for obj in entries:
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if (
            obj.get("type") == "user"
            and not obj.get("isMeta")
            and isinstance(content, str)
        ):
            t = content.strip()
            if t:
                parts.append("👤 " + t)
        elif obj.get("type") == "assistant" and isinstance(content, list):
            texts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
            ]
            joined = "\n".join(texts).strip()
            if joined:
                parts.append("🤖 " + joined)
    return "\n\n".join(parts)


# /handoff skill が chat 出力冒頭に出す区切りマーカー (~~~~ … Handoff (<sid>) … ~~~~)。
# SKILL.md の例・body 抜粋・過去 handoff も同形ゆえ、 prior session の full sid を含む marker のみを anchor とする。
_MARKER_RE = re.compile(r"~{4,}[^\n]*\bHandoff\b[^\n]*~{2,}", re.IGNORECASE)


def _trim_before_handoff(text: str, sid: str = "") -> str:
    """prior session の full sid を含む handoff マーカー以降を返す。 template/抜粋 marker (sid 無し) は除外、 該当無し・sid 空は原文。"""
    cands = [m for m in _MARKER_RE.finditer(text) if sid and sid in m.group()]
    if not cands:
        return text
    m = cands[-1]  # 同 sid 複数 = 同 session 再 handoff、 最新 (最後) を採る
    bs = text.rfind("\n\n", 0, m.start())
    return text[bs + 2 :] if bs >= 0 else text


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    source = payload.get("source")
    if source not in ("startup", "clear"):
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return 0
    session_id = payload.get("session_id") or ""
    prior = _find_prior_session(cwd, session_id)
    if not prior:
        return 0
    prior_sid = os.path.basename(prior).rsplit(".", 1)[0]
    text = _trim_before_handoff(
        _turns_text(_load_tail(prior, RECENT_TURNS)), prior_sid
    ).strip()
    if len(text) < MIN_TEXT_LEN:
        return 0
    if len(text) > MAX_INJECT_LEN:  # 末尾 (最新=handoff 側) を残す
        text = "…(truncated)\n" + text[-MAX_INJECT_LEN:].lstrip()
    ctx = (
        "## Prior session tail (resume context)\n"
        f"\nSource: `{prior}`\n"
        f"\n前回 session の最終 {RECENT_TURNS} turn (👤=ユーザ / 🤖=assistant、handoff 検出時はそれ以降):\n"
        f"\n---\n{text}\n---\n"
        "\n必要なら上記 jsonl を Read で full log 確認、 "
        "`todos.md` / handoff doc も併せて参照。"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }
    json.dump(out, sys.stdout)
    return 0


class TrimBeforeHandoffTest(unittest.TestCase):
    """_trim_before_handoff の sid-anchor 回帰 (SKILL.md L98: marker は full $CLAUDE_CODE_SESSION_ID を埋める)。
    出所: 2026-06-08 実機 — 直近 3 turn の text に SKILL.md の template marker (placeholder sid) と
    handoff body 内の省略引用 (~~~~ … Handoff (<8桁>…) ~~~~) が混入し、 first-match search が
    template を誤 anchor → wind-down が trim されず 4000 字超で truncate した。"""

    SID = "5262c4b2-7933-4f6b-893f-35405925375c"

    def _mk(self, *blocks: str) -> str:
        return "\n\n".join(blocks)

    def test_picks_sid_marker_over_earlier_template(self):
        text = self._mk(
            "👤 wind-down 議論",
            "🤖 例: ~~~~ Monday Handoff (session ID) ~~~~ という形式です",
            f"🤖 ~~~~~~~~ Monday, 2026/6/8 09:19 Handoff ({self.SID}) ~~~~~~\n## 引き継ぎ本体",
        )
        out = _trim_before_handoff(text, self.SID)
        self.assertTrue(out.startswith("🤖 ~~~~~~~~ Monday"))
        self.assertIn("## 引き継ぎ本体", out)
        self.assertNotIn("wind-down 議論", out)
        self.assertNotIn("session ID", out)

    def test_ignores_abbreviated_body_quote_after_real_marker(self):
        real = (
            f"🤖 ~~~~~~~~ Mon Handoff ({self.SID}) ~~~~~~\n"
            "## 本体\n上の marker (~~~~ … Handoff (5262c4b2…) ~~~~) 以降だけ"
        )
        out = _trim_before_handoff(self._mk("👤 q", "🤖 中間", real), self.SID)
        self.assertTrue(out.startswith("🤖 ~~~~~~~~ Mon Handoff"))
        self.assertNotIn("中間", out)

    def test_no_sid_marker_returns_full(self):
        text = self._mk("👤 q", "🤖 例 ~~~~ Handoff (other999) ~~~~", "🤖 結び")
        self.assertEqual(_trim_before_handoff(text, self.SID), text)

    def test_no_marker_returns_full(self):
        text = self._mk("👤 q", "🤖 ただの会話")
        self.assertEqual(_trim_before_handoff(text, self.SID), text)

    def test_rehandoff_picks_last(self):
        text = self._mk(
            "👤 q",
            f"🤖 ~~~~ Handoff ({self.SID}) ~~~~\n古い handoff",
            "👤 やり直し",
            f"🤖 ~~~~ Handoff ({self.SID}) ~~~~\n新しい handoff",
        )
        out = _trim_before_handoff(text, self.SID)
        self.assertIn("新しい handoff", out)
        self.assertNotIn("古い handoff", out)

    def test_empty_sid_returns_full(self):
        text = self._mk("👤 q", f"🤖 ~~~~ Handoff ({self.SID}) ~~~~\n本体")
        self.assertEqual(_trim_before_handoff(text, ""), text)

    def test_marker_at_text_start_returns_full(self):
        text = f"🤖 ~~~~ Handoff ({self.SID}) ~~~~\n本体"  # 先頭 = preceding \n\n 無し
        self.assertEqual(_trim_before_handoff(text, self.SID), text)


class TurnBoundaryTest(unittest.TestCase):
    """_is_turn_boundary: human-input turn のみ起点 (isMeta / tool_result 継続は非起点)。 窓選択の load-bearing 不変。"""

    def test_str_user_content_is_boundary(self):
        self.assertTrue(
            _is_turn_boundary({"type": "user", "message": {"content": "hi"}})
        )

    def test_meta_is_not_boundary(self):
        self.assertFalse(
            _is_turn_boundary(
                {"type": "user", "isMeta": True, "message": {"content": "x"}}
            )
        )

    def test_tool_result_only_list_is_not_boundary(self):
        obj = {"type": "user", "message": {"content": [{"type": "tool_result"}]}}
        self.assertFalse(_is_turn_boundary(obj))


class SelectPriorTest(unittest.TestCase):
    """_select_prior: registry 既知なら live sid を除外 (idle-alive も)、 不明 (None) なら最新で best-effort。"""

    @staticmethod
    def _p(sid: str) -> str:
        return f"/proj/{sid}.jsonl"

    def test_live_known_skips_live_returns_newest_dead(self):
        files = [self._p("A"), self._p("B"), self._p("C")]  # mtime 降順
        self.assertEqual(_select_prior(files, {"A"}), self._p("B"))

    def test_live_known_all_live_returns_none(self):
        files = [self._p("A"), self._p("B")]
        self.assertIsNone(_select_prior(files, {"A", "B"}))

    def test_live_known_none_live_returns_newest(self):
        files = [self._p("A"), self._p("B")]
        self.assertEqual(_select_prior(files, set()), self._p("A"))

    def test_registry_unknown_returns_newest(self):
        files = [self._p("A"), self._p("B")]
        self.assertEqual(_select_prior(files, None), self._p("A"))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
