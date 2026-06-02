#!/usr/bin/env python3
r"""
Deterministic feature-research findings builder + SessionStart hook.

This single file both BUILDS the findings and IS the SessionStart hook —
there is no LLM and no `claude` subprocess in the build, so it cannot
re-trigger SessionStart and needs no recursion guard / reaper / staging /
in-flight machinery.

The official changelog (code.claude.com/docs/en/changelog.md) is structured
MDX — `<Update label="X.Y.Z" description="<Mon DD, YYYY>">` blocks of `  * `
bullets — so the build is a plain parse → keep post-cutoff (by the in-source
DATE, no model judgement) → keyword-bucket → emit verbatim. No summarization
means features can never be silently dropped.

(The RSS feed code.claude.com/docs/en/changelog/rss.xml is cleaner XML but only
carries ~15 recent items, too few for the post-cutoff range; the MDX page,
generated from the GitHub CHANGELOG, is the one source with full history.)

Cutoff: a bullet is kept when its version's date is >= CUTOFF_YM. The date is
in the source, so the boundary needs no subagent. Bump CUTOFF_YM when the
model's cutoff moves. Features/skills/deprecations are verbatim; fixes are
consolidated to the clean CLI/config identifiers they name (keyword-less fixes
dropped).

Modes:
  (no args)        SessionStart hook: fast local version-check; if findings.md
                   is missing or its top version != `claude --version`, detach
                   a `--force` child to rebuild. Never blocks/breaks startup.
  --force          fetch + rebuild + write FINDINGS_PATH atomically.
  --input F        build from a local changelog file instead of fetching.
  --stdout         print instead of writing (with --input, for tests).

canonical source: files/claude_managed-hooks/feature_findings_build.py
deploy: /etc/claude-code/hooks/ (copy_dir で自動)。両者を同 session で同内容に保つ。
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
import time
import urllib.request

SOURCE_URL = "https://code.claude.com/docs/en/changelog.md"
CUTOFF_YM = (2026, 1)   # assistant knowledge cutoff (year, month); keep dates >= this
FETCH_TIMEOUT_S = 30
CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "claude-code-feature-research")
FINDINGS_PATH = os.path.join(CACHE_DIR, "findings.md")
ERR_LOG = os.path.join(CACHE_DIR, "build-errors.log")

_UPDATE_RE = re.compile(r'<Update\s+label="([^"]+)"\s+description="([^"]+)"')
_BULLET_RE = re.compile(r"^\s*\*\s+(.*\S)\s*$")
_END_RE = re.compile(r"</Update>")
_ID_RE = re.compile(r"`[^`]+`")   # backtick token in a bullet
# A clean CLI/config identifier: flag (--x / -x), slash command (/x), env var,
# dotted setting, or a tool/command word. Rejects snippets with spaces, mid-path
# slashes, and bare version tokens (those start with a digit).
_IDENT_SHAPE_RE = re.compile(r"(--?|/)?[A-Za-z][A-Za-z0-9_.\-]*")
_TOP_VER_RE = re.compile(r"^## v(\d+\.\d+\.\d+)")
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
    # Keep when the version date is at/after the cutoff. Unparseable date is kept
    # (fail toward inclusion, never drop a real delta).
    return rec["ym"] is None or rec["ym"] >= CUTOFF_YM


def _fix_identifiers(fixes: list[dict]) -> list[tuple[str, str]]:
    """Consolidate fixes to the clean identifiers they name: identifier ->
    newest version. Drops keyword-less fixes and noisy tokens. Newest-first."""
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
        "> feature_findings_build.py --force. The SessionStart hook regenerates",
        f"> this on a version change. {len(versions)} versions ({lo}..{hi}); "
        + "buckets: " + ", ".join(f"{counts[k]} {k}" for k, _ in _SECTIONS)
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


def _write_atomic(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def cmd_force(output: str) -> int:
    """Fetch + rebuild + write. On failure, log (never silently swallow)."""
    try:
        text = _fetch(SOURCE_URL)
        _write_atomic(output, build(text, datetime.date.today().isoformat()))
        return 0
    except Exception as e:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(ERR_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%FT%TZ', time.gmtime())}] build failed: {e!r}\n")
        except OSError:
            pass
        sys.stderr.write(f"feature_findings_build: {e}\n")
        return 1


def _cli_version() -> str | None:
    try:
        r = subprocess.run(["claude", "--version"], capture_output=True,
                           text=True, timeout=5)
    except Exception:
        return None
    m = re.search(r"\d+\.\d+\.\d+", r.stdout or "")
    return m.group(0) if (r.returncode == 0 and m) else None


def _findings_version(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            m = _TOP_VER_RE.match(f.readline())
    except OSError:
        return None
    return m.group(1) if m else None


def cmd_hook(output: str) -> int:
    """SessionStart: local version-check, detach a --force rebuild on a miss.

    The rebuild child runs plain python (no `claude` spawn) so it cannot
    re-trigger SessionStart — no recursion guard needed. Always exits 0:
    a feature-cache refresh must never block or break session startup.
    """
    try:
        sys.stdin.read()   # drain the SessionStart payload (unused)
    except Exception:
        pass
    cur = _cli_version()
    if cur and os.path.exists(output) and _findings_version(output) == cur:
        return 0   # already current — no fetch
    try:
        subprocess.Popen(
            [sys.executable, os.path.realpath(__file__), "--force", "--output", output],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="read changelog from FILE instead of fetching")
    ap.add_argument("--output", default=FINDINGS_PATH)
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    ap.add_argument("--force", action="store_true", help="fetch + rebuild now")
    a = ap.parse_args()

    if a.input or a.stdout:
        text = open(a.input, encoding="utf-8").read() if a.input else _fetch(SOURCE_URL)
        findings = build(text, datetime.date.today().isoformat())
        if a.stdout:
            sys.stdout.write(findings)
        else:
            _write_atomic(a.output, findings)
        return 0
    if a.force:
        return cmd_force(a.output)
    return cmd_hook(a.output)   # default = SessionStart hook mode


if __name__ == "__main__":
    sys.exit(main())
