#!/usr/local/lib/jev/bin/python -I
"""Backtest harness for the Jev context gate over the cases laid out by prepare.py.

  run.py calls <cases.jsonl> <run>                      what to send to the connected server's context_gate
  run.py judge <cases.jsonl> <log.jsonl> <run> [opts]   judge in this one process with a gate file
  run.py score <cases.jsonl> <log.jsonl> <run> [--json] false denials, misses, skips, margins, cost
  run.py diff  <cases.jsonl> <log.jsonl> <run-a> <run-b>

Records use the gate log format with session_id "backtest:<run>:<case>[#<n>]", so judgments from
the live server, this process or any other judge score the same way.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import importlib.machinery
import importlib.util
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GATE = ROOT / "files" / "jev_context_gate.py"
PREFIX = "backtest:"


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout


def load_jev():
    if "jev" not in sys.modules:
        loader = importlib.machinery.SourceFileLoader(
            "jev", str(ROOT / "files" / "jev")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        sys.modules["jev"] = module
    return sys.modules["jev"]


def load_gate(path):
    spec = importlib.util.spec_from_file_location("jev_context_gate_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def select(cases, kinds=None, origins=None, ids=None):
    if unknown := sorted(set(ids or ()) - {c["id"] for c in cases}):
        raise SystemExit(f"unknown case id(s): {', '.join(unknown)}")
    return [
        c
        for c in cases
        if (not kinds or c["kind"] in kinds)
        and (not origins or c.get("origin") in origins)
        and (not ids or c["id"] in ids)
    ]


def session(run_name, case_id):
    return f"{PREFIX}{run_name}:{case_id}"


def calls(cases_path, run_name, **only):
    return [
        {
            "cwd": c["cwd"],
            "command": c["command"],
            "session_id": session(run_name, c["id"]),
        }
        for c in select(read_jsonl(cases_path), **only)
    ]


def judge(cases_path, log_path, run_name, gate=GATE, evaluate=None, repeat=1, **only):
    """Judge each selected case in this process; cases already logged for the run are skipped."""
    module = load_gate(gate)
    setattr(module, "LOG", str(log_path))  # noqa: B010 - the gate module is loaded at run time
    done = {r.get("session_id") for r in read_jsonl(log_path)}
    if evaluate is None:
        evaluate = load_jev().JevSession().evaluate
    loop = asyncio.new_event_loop()

    def bridge(state, questions, seconds_left):
        try:
            return loop.run_until_complete(
                asyncio.wait_for(evaluate(state, questions), seconds_left)
            )
        except TimeoutError as exc:
            raise module.Skip("Jev の応答が時間内に返りませんでした") from exc
        # The server maps every Jev failure to a skip; so does the harness.
        except Exception as exc:
            raise module.Skip(str(exc)[:160] or type(exc).__name__) from exc

    try:
        for c in select(read_jsonl(cases_path), **only):
            for n in range(1, repeat + 1):
                sid = session(run_name, c["id"] if repeat == 1 else f"{c['id']}#{n}")
                if sid in done:
                    continue
                payload = {
                    "tool_name": "Bash",
                    "tool_input": {"command": c["command"]},
                    "cwd": c["cwd"],
                    "session_id": sid,
                }
                module.check(payload, bridge)
    finally:
        loop.close()


def _records(log_path, run_name):
    """Last record per (case, repeat) of the run, grouped by case id."""
    latest = {}
    for r in read_jsonl(log_path):
        sid = r.get("session_id") or ""
        if sid.startswith(session(run_name, "")):
            latest[sid[len(session(run_name, "")) :]] = r
    grouped = collections.defaultdict(list)
    for key, r in latest.items():
        grouped[key.split("#", 1)[0]].append(r)
    return grouped


def _score(record):
    values = (
        [p.get("fit") for p in record.get("pieces", [])]
        + [s.get("style") for s in record.get("new_sections", [])]
        + [f.get("placed") for f in record.get("new_files", [])]
    )
    values = [v for v in values if isinstance(v, (int, float))]
    return min(values) if values else None


def _decision(records):
    outcomes = [r.get("outcome") for r in records]
    if outcomes and all(o == "skip" for o in outcomes):
        return "skip"
    return (
        collections.Counter(o for o in outcomes if o != "skip").most_common(1)[0][0]
        if outcomes
        else None
    )


def _group():
    return {
        "good": {"n": 0, "denied": 0, "skipped": 0, "unjudged": 0},
        "bad": {"n": 0, "allowed": 0, "skipped": 0, "unjudged": 0},
        "scores": {"good": [], "bad": []},
    }


def _finish(group):
    scores = group.pop("scores")
    good, bad = scores["good"], scores["bad"]
    group["min_good"] = min(good) if good else None
    group["max_bad"] = max(bad) if bad else None
    group["margin"] = group["min_good"] - group["max_bad"] if good and bad else None
    points = sorted({0.0, 1.01, *good, *bad})
    best = max(
        (
            {
                "threshold": t,
                "correct": sum(s >= t for s in good) + sum(s < t for s in bad),
                "judged": len(good) + len(bad),
            }
            for t in points
        ),
        key=lambda b: (b["correct"], -abs(b["threshold"] - 0.5)),
    )
    group["best_threshold"] = best
    return group


def score(cases_path, log_path, run_name):
    records = _records(log_path, run_name)
    by_kind = collections.defaultdict(_group)
    by_origin = collections.defaultdict(_group)
    overall = _group()
    reasons = collections.Counter()
    cost = {"requests": 0, "input_tokens": 0, "latency_ms": 0}
    spreads, false_denials, misses = [], [], []
    for c in read_jsonl(cases_path):
        recs = records.get(c["id"], [])
        decision = _decision(recs)
        scores = [
            s
            for s in (_score(r) for r in recs if r.get("outcome") != "skip")
            if s is not None
        ]
        value = statistics.mean(scores) if scores else None
        if len(scores) > 1:
            spreads.append(max(scores) - min(scores))
        for r in recs:
            cost["requests"] += len(r.get("request_latency_ms") or [])
            cost["input_tokens"] += r.get("input_tokens") or 0
            cost["latency_ms"] += r.get("latency_ms") or 0
            if r.get("outcome") == "skip":
                reasons[r.get("skip_reason")] += 1
        failing = [
            p
            for r in recs
            for p in r.get("pieces", [])
            + r.get("new_sections", [])
            + r.get("new_files", [])
            if p.get("failed")
        ]
        for group in (by_kind[c["kind"]], by_origin[c.get("origin", "real")], overall):
            g = group[c["label"]]
            g["n"] += 1
            if decision is None:
                g["unjudged"] += 1
            elif decision == "skip":
                g["skipped"] += 1
            elif c["label"] == "good" and decision == "deny":
                g["denied"] += 1
            elif c["label"] == "bad" and decision == "allow":
                g["allowed"] += 1
            if value is not None:
                group["scores"][c["label"]].append(value)
        entry = {
            "id": c["id"],
            "kind": c["kind"],
            "origin": c.get("origin"),
            "score": value,
            "failing": failing,
        }
        if c["label"] == "good" and decision == "deny":
            false_denials.append(entry)
        elif c["label"] == "bad" and decision == "allow":
            misses.append(entry)
    overall = _finish(overall)
    overall["skip_reasons"] = dict(reasons)
    overall["cost"] = cost
    overall["max_spread"] = max(spreads) if spreads else None
    return {
        "kind": {k: _finish(v) for k, v in sorted(by_kind.items())},
        "origin": {k: _finish(v) for k, v in sorted(by_origin.items())},
        "all": overall,
        "false_denials": false_denials,
        "misses": misses,
    }


def diff(cases_path, log_path, run_a, run_b):
    a, b = _records(log_path, run_a), _records(log_path, run_b)
    changed = []
    for c in read_jsonl(cases_path):
        da, db = _decision(a.get(c["id"], [])), _decision(b.get(c["id"], []))
        if da != db:
            changed.append(
                {
                    "id": c["id"],
                    "label": c["label"],
                    "kind": c["kind"],
                    "a": da,
                    "b": db,
                }
            )
    return changed


def _table(report):
    fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
    lines = [
        "| 区分 | 良い n | 誤拒否 | 悪い n | 見逃し | 省略 | 良い最低点 | 悪い最高点 | 差 | 最適閾値 (正解/判定) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    rows = (
        [(f"kind:{k}", v) for k, v in report["kind"].items()]
        + [(f"origin:{k}", v) for k, v in report["origin"].items()]
        + [("all", report["all"])]
    )
    for name, g in rows:
        best = g["best_threshold"]
        lines.append(
            f"| {name} | {g['good']['n']} | {g['good']['denied']} | {g['bad']['n']} | {g['bad']['allowed']} | "
            f"{g['good']['skipped'] + g['bad']['skipped']} | {fmt(g['min_good'])} | {fmt(g['max_bad'])} | {fmt(g['margin'])} | "
            f"{best['threshold']:.2f} ({best['correct']}/{best['judged']}) |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("calls", "judge", "score", "diff"):
        p = sub.add_parser(name)
        p.add_argument("cases")
        if name != "calls":
            p.add_argument("log")
        p.add_argument("run")
        if name == "diff":
            p.add_argument("run_b")
        if name in ("calls", "judge"):
            p.add_argument("--kind", action="append")
            p.add_argument("--origin", action="append")
            p.add_argument("--id", action="append")
        if name == "judge":
            p.add_argument("--gate", default=str(GATE))
            p.add_argument("--repeat", type=int, default=1)
        if name == "score":
            p.add_argument("--json", action="store_true")
    args = parser.parse_args()
    only = {
        "kinds": getattr(args, "kind", None),
        "origins": getattr(args, "origin", None),
        "ids": getattr(args, "id", None),
    }
    if args.command == "calls":
        for call in calls(args.cases, args.run, **only):
            print(json.dumps(call, ensure_ascii=False))
    elif args.command == "judge":
        judge(
            args.cases,
            args.log,
            args.run,
            gate=Path(args.gate),
            repeat=args.repeat,
            **only,
        )
    elif args.command == "score":
        report = score(args.cases, args.log, args.run)
        print(
            json.dumps(report, ensure_ascii=False, indent=1)
            if args.json
            else _table(report)
        )
    else:
        for row in diff(args.cases, args.log, args.run, args.run_b):
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.exit(main())
