#!/usr/bin/env python3
r"""
Deterministic feature-research findings builder for Claude Code.

Legacy: org CLAUDE.md §開発 (deterministic transform は LLM でなく code に)。

Replaces the former LLM background-research path. The official changelog
(code.claude.com/docs/en/changelog.md) is structured MDX —
`<Update label="X.Y.Z" description="<Mon DD, YYYY>">` blocks of `  * bullet`
lines — so the whole pipeline is deterministic: parse → keep post-cutoff
(by the in-source DATE, no model judgement) → keyword-bucket → emit verbatim.
No LLM means no summarization, so features can never be silently compressed
away (the bug that made the old findings untrustworthy), and a rebuild is a
single fast script run.

(The RSS feed code.claude.com/docs/en/changelog/rss.xml is cleaner XML but only
carries ~15 recent items, so it cannot cover the full post-cutoff range — the
MDX page, generated from the GitHub CHANGELOG, is the one source with history.)

Cutoff: a bullet is kept when its version's date is >= CUTOFF_YM (the assistant
knowledge cutoff). The date lives in the changelog, so the boundary needs no
subagent. Bump CUTOFF_YM when the model's cutoff moves.

Buckets are a keyword heuristic (scan aid, not load-bearing): deprecations,
skill/hook/agent items, fixes, else feature/change. Bug fixes are NOT listed
verbatim — they are consolidated to the clean CLI/config identifiers they name
(`--flag` / `/command` / env / dotted-setting), newest version each. A fix that
names no such identifier carries no spec signal a reader would query and is
dropped.

Usage:
  feature_findings_build.py [--input FILE] [--output FILE] [--stdout]
  default: fetch the official changelog, write FINDINGS_PATH atomically.

canonical source: files/claude_managed-hooks/feature_findings_build.py
deploy: /etc/claude-code/hooks/ (copy_dir で自動)。両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import urllib.request

SOURCE_URL = "https://code.claude.com/docs/en/changelog.md"
CUTOFF_YM = (2026, 1)   # assistant knowledge cutoff (year, month); keep dates >= this
FETCH_TIMEOUT_S = 30
FINDINGS_PATH = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "claude-code-feature-research", "findings.md",
)

_UPDATE_RE = re.compile(r'<Update\s+label="([^"]+)"\s+description="([^"]+)"')
_BULLET_RE = re.compile(r"^\s*\*\s+(.*\S)\s*$")
_END_RE = re.compile(r"</Update>")
_ID_RE = re.compile(r"`[^`]+`")   # backtick token in a bullet
# A clean CLI/config identifier: flag (--x / -x), slash command (/x), env var,
# dotted setting, or a tool/command word. Rejects snippets with spaces, mid-path
# slashes, and bare version tokens (those start with a digit).
_IDENT_SHAPE_RE = re.compile(r"(--?|/)?[A-Za-z][A-Za-z0-9_.\-]*")
_MONTHS = {m: i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}


def _vkey(version: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", version)][:3]
    return tuple(nums) + (0,) * (3 - len(nums))


def _parse_date(desc: str) -> tuple[int, int] | None:
    """`May 30, 2026` -> (2026, 5). None when unparseable (caller keeps it)."""
    m = re.search(r"([A-Za-z]+)\s+\d{1,2},\s*(\d{4})", desc)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).capitalize())
    return (int(m.group(2)), mon) if mon else None


def _bucket(text: str) -> str:
    low = text.lower()
    if low.startswith("fix"):
        return "fix"
    if re.search(r"\b(deprecat\w*|removed?|no longer|dropped|retired)\b", low):
        return "deprecated"
    if re.search(r"\b(skills?|hooks?|subagents?|plugins?|marketplace)\b|skill\.md", low):
        return "skill_hook_agent"
    return "feature"


def parse(text: str) -> list[dict]:
    """Return [{version, date(str), ym, bullet}] for every bullet in every Update."""
    out: list[dict] = []
    cur_v = cur_d = None
    cur_ym: tuple[int, int] | None = None
    for line in text.splitlines():
        mu = _UPDATE_RE.search(line)
        if mu:
            cur_v, cur_d = mu.group(1).strip(), mu.group(2).strip()
            cur_ym = _parse_date(cur_d)
            continue
        if _END_RE.search(line):
            cur_v = cur_d = cur_ym = None
            continue
        mb = _BULLET_RE.match(line)
        if mb and cur_v:
            out.append({"version": cur_v, "date": cur_d, "ym": cur_ym,
                        "bullet": mb.group(1)})
    return out


def _post_cutoff(rec: dict) -> bool:
    # Keep when the version date is at/after the cutoff. Unparseable date or a
    # version-less recent label is kept (fail toward inclusion, never drop).
    return rec["ym"] is None or rec["ym"] >= CUTOFF_YM


def _fix_identifiers(fixes: list[dict]) -> list[tuple[str, str]]:
    """Consolidate fixes to the clean identifiers they name: identifier ->
    newest version. Drops keyword-less fixes and noisy tokens. Returns
    [(identifier, version)] newest-first."""
    best: dict[str, str] = {}
    for r in fixes:
        for tok in _ID_RE.findall(r["bullet"]):
            ident = tok.strip("`").strip().split("=", 1)[0].strip()
            if not _IDENT_SHAPE_RE.fullmatch(ident):
                continue
            if ident not in best or _vkey(r["version"]) > _vkey(best[ident]):
                best[ident] = r["version"]
    return sorted(best.items(), key=lambda kv: (_vkey(kv[1]), kv[0].lower()), reverse=True)


_SECTIONS = [
    ("feature", "New features / changes"),
    ("skill_hook_agent", "New skills / hooks / agents"),
    ("deprecated", "Deprecated / removed"),
]


def build(text: str, today: str) -> str:
    recs = [r for r in parse(text) if _post_cutoff(r)]
    for r in recs:
        r["_b"] = _bucket(r["bullet"])
    recs.sort(key=lambda r: _vkey(r["version"]), reverse=True)
    versions = sorted({r["version"] for r in recs}, key=_vkey)
    lo = versions[0] if versions else "?"
    hi = versions[-1] if versions else "?"

    fixes_all = [r for r in recs if r["_b"] == "fix"]
    fix_ids = _fix_identifiers(fixes_all)
    counts = {k: sum(1 for r in recs if r["_b"] == k) for k, _ in _SECTIONS}

    lines = [
        f"## v{hi} (built {today} from official changelog, post-cutoff "
        f">= {CUTOFF_YM[0]}-{CUTOFF_YM[1]:02d}, deterministic)",
        "",
        "> Generated deterministically from the official Claude Code changelog",
        f"> ({SOURCE_URL}) — every post-cutoff feature bullet verbatim,",
        "> keyword-bucketed, no LLM so nothing is summarized away. Rebuild: run",
        "> feature_findings_build.py. The SessionStart hook regenerates this on a",
        f"> version change. {len(versions)} versions ({lo}..{hi}); buckets: "
        + ", ".join(f"{counts[k]} {k}" for k, _ in _SECTIONS)
        + f". Fixes consolidated to the {len(fix_ids)} CLI/config identifiers "
        + f"they name (from {len(fixes_all)} fix bullets); keyword-less fixes dropped.",
    ]
    for key, title in _SECTIONS:
        lines += ["", f"### {title}", ""]
        rs = [r for r in recs if r["_b"] == key]
        lines += [f"- {r['bullet']} (v{r['version']}, {r['date']})" for r in rs] or ["- なし"]
    lines += ["", "### Fixes — identifiers touched (consolidated, for reference)", ""]
    lines += [f"- `{ident}` (v{ver})" for ident, ver in fix_ids] or ["- なし"]
    return "\n".join(lines) + "\n"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "claude-code-hook"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        return resp.read().decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="read changelog from FILE instead of fetching")
    ap.add_argument("--output", default=FINDINGS_PATH)
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    a = ap.parse_args()

    if a.input:
        with open(a.input, encoding="utf-8") as f:
            text = f.read()
    else:
        text = _fetch(SOURCE_URL)   # raises (exit 1) on failure — never write a stale file

    findings = build(text, datetime.date.today().isoformat())

    if a.stdout:
        sys.stdout.write(findings)
        return 0
    os.makedirs(os.path.dirname(a.output), exist_ok=True)
    tmp = a.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(findings)
    os.replace(tmp, a.output)   # atomic
    sys.stderr.write(f"wrote {a.output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
