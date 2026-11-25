#!/usr/bin/env python3
"""Check Meta Pixel + Conversions API deduplication from two event logs (python3 stdlib).

Usage:
  python3 dedup_check.py --browser browser_events.csv --server server_events.json
  python3 dedup_check.py --browser b.csv --server s.csv --json report.json --examples 5

Each log: CSV, JSON array, or JSON lines. Fields (aliases accepted):
  event_name (event, name)
  event_id   (eventID, eventId, id)
  timestamp  (event_time, time, ts)  unix seconds, unix ms, or ISO 8601
Optional on server rows: fbp, fbc (or user_data.fbp / user_data.fbc in JSON).

Meta deduplicates a browser and a server event when event_name and event_id
match and they arrive within 48 hours of each other.
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime, timezone

DEDUP_WINDOW_H = 48
NAME_KEYS = ["event_name", "event", "name", "eventname"]
ID_KEYS = ["event_id", "eventid", "eventID", "id"]
TIME_KEYS = ["timestamp", "event_time", "time", "ts", "datetime"]


def pick(d, keys):
    low = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def parse_ts(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = str(v).strip()
        if re.match(r"^\d+(\.\d+)?$", s):
            n = float(s)
        else:
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                return None
    if n > 1e11:  # milliseconds
        n /= 1000.0
    return n


def flatten(rec):
    """Pull fbp/fbc from nested user_data if present."""
    out = dict(rec)
    ud = rec.get("user_data") if isinstance(rec, dict) else None
    if isinstance(ud, dict):
        for k in ("fbp", "fbc"):
            if k in ud and k not in out:
                out[k] = ud[k]
    return out


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        text = f.read().strip()
    rows = []
    if path.lower().endswith(".json") or text.startswith("[") or text.startswith("{"):
        if text.startswith("["):
            rows = json.loads(text)
        elif text.startswith("{") and "\n" in text and text.count("\n{") > 0:
            rows = [json.loads(l) for l in text.splitlines() if l.strip()]
        else:
            obj = json.loads(text)
            rows = obj.get("data", [obj]) if isinstance(obj, dict) else obj
    else:
        rows = list(csv.DictReader(text.splitlines()))
    events = []
    for r in rows:
        r = flatten(r)
        name = pick(r, NAME_KEYS)
        eid = pick(r, ID_KEYS)
        ts = parse_ts(pick(r, TIME_KEYS))
        events.append({
            "event_name": str(name).strip() if name is not None else "",
            "event_id": str(eid).strip() if eid is not None else "",
            "ts": ts,
            "fbp": str(r.get("fbp") or "").strip(),
            "fbc": str(r.get("fbc") or "").strip(),
            "has_fbp_col": "fbp" in r,
            "has_fbc_col": "fbc" in r,
        })
    return events


def fmt_ts(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "?"


def main():
    ap = argparse.ArgumentParser(description="Meta Pixel + CAPI dedup check")
    ap.add_argument("--browser", required=True, help="browser (Pixel) event log")
    ap.add_argument("--server", required=True, help="server (Conversions API) event log")
    ap.add_argument("--examples", type=int, default=3, help="example IDs to print per problem")
    ap.add_argument("--json", help="write the full report as JSON")
    args = ap.parse_args()

    b = load(args.browser)
    s = load(args.server)
    report = {"browser_events": len(b), "server_events": len(s), "per_event": {}, "problems": []}

    def problem(sev, check, detail, examples=None):
        report["problems"].append({"severity": sev, "check": check, "detail": detail, "examples": (examples or [])[:args.examples]})

    # Missing event_id
    b_missing = [e for e in b if not e["event_id"]]
    s_missing = [e for e in s if not e["event_id"]]
    if s_missing:
        c = Counter(e["event_name"] for e in s_missing)
        problem("ERROR", "Server events missing event_id", f"{len(s_missing)} server events cannot be deduplicated: {dict(c)}")
    if b_missing:
        c = Counter(e["event_name"] for e in b_missing)
        problem("ERROR", "Browser events missing eventID", f"{len(b_missing)} Pixel events have no eventID: {dict(c)}")

    # Index by (name, id)
    def index(evts):
        idx = defaultdict(list)
        for e in evts:
            if e["event_id"]:
                idx[(e["event_name"], e["event_id"])].append(e)
        return idx

    bi, si = index(b), index(s)

    # Same-channel duplicates
    for label, idx in (("browser", bi), ("server", si)):
        dups = [(k, len(v)) for k, v in idx.items() if len(v) > 1]
        if dups:
            c = Counter(k[0] for k, _ in dups)
            problem("WARN", f"Duplicate IDs on {label}", f"{len(dups)} event IDs sent more than once from the {label}: {dict(c)}",
                    [f"{k[0]} {k[1]} x{n}" for k, n in dups])

    # event_name mismatch for same id (e.g. Purchase vs purchase)
    b_by_id = defaultdict(set)
    s_by_id = defaultdict(set)
    for (n, i) in bi:
        b_by_id[i].add(n)
    for (n, i) in si:
        s_by_id[i].add(n)
    mism = []
    for i in set(b_by_id) & set(s_by_id):
        if not (b_by_id[i] & s_by_id[i]):
            mism.append(f"id {i}: browser {sorted(b_by_id[i])} vs server {sorted(s_by_id[i])}")
    if mism:
        problem("ERROR", "event_name mismatch", f"{len(mism)} IDs exist on both sides with different event names (names must match exactly, including case)", mism)

    # Reused id across different events on same side
    reuse = [i for i, names in s_by_id.items() if len(names) > 1] + [i for i, names in b_by_id.items() if len(names) > 1]
    if reuse:
        problem("INFO", "Same event_id on different events", f"{len(set(reuse))} IDs are shared across event names (fine if intentional, e.g. order ID used for Purchase only)", sorted(set(reuse)))

    # Per event matching
    names = sorted({e["event_name"] for e in b + s if e["event_name"]})
    gaps = []
    for name in names:
        b_ids = {i for (n, i) in bi if n == name}
        s_ids = {i for (n, i) in si if n == name}
        matched = b_ids & s_ids
        only_b = b_ids - s_ids
        only_s = s_ids - b_ids
        for i in matched:
            tb = min((e["ts"] for e in bi[(name, i)] if e["ts"]), default=None)
            ts_ = min((e["ts"] for e in si[(name, i)] if e["ts"]), default=None)
            if tb and ts_ and abs(ts_ - tb) > DEDUP_WINDOW_H * 3600:
                gaps.append(f"{name} {i}: browser {fmt_ts(tb)}, server {fmt_ts(ts_)} ({abs(ts_ - tb)/3600:.0f} h apart)")
        bc = sum(1 for e in b if e["event_name"] == name)
        sc = sum(1 for e in s if e["event_name"] == name)
        rate_b = (len(matched) / len(b_ids) * 100) if b_ids else None
        rate_s = (len(matched) / len(s_ids) * 100) if s_ids else None
        report["per_event"][name] = {
            "browser_events": bc, "server_events": sc, "matched_ids": len(matched),
            "browser_match_rate_pct": round(rate_b, 1) if rate_b is not None else None,
            "server_match_rate_pct": round(rate_s, 1) if rate_s is not None else None,
            "only_browser": len(only_b), "only_server": len(only_s),
            "only_browser_examples": sorted(only_b)[:args.examples],
            "only_server_examples": sorted(only_s)[:args.examples],
        }
        if bc and not sc:
            sev = "INFO" if name == "PageView" else "WARN"
            problem(sev, "Browser only", f"{name}: {bc} Pixel events, none from the server")
        elif sc and not bc:
            problem("INFO", "Server only", f"{name}: {sc} server events, none from the Pixel (fine for offline/CRM events)")
        elif rate_b is not None and rate_b < 90:
            problem("WARN", "Low match rate", f"{name}: only {rate_b:.0f}% of Pixel event IDs have a matching server event",
                    sorted(only_b))
    if gaps:
        problem("ERROR", f"Gap over {DEDUP_WINDOW_H} hours", f"{len(gaps)} matched pairs arrive more than {DEDUP_WINDOW_H} h apart, outside Meta's dedup window; both will count", gaps)

    # fbp / fbc on server
    if s and any(e["has_fbp_col"] or e["has_fbc_col"] for e in s):
        web = s
        fbp_ok = sum(1 for e in web if e["fbp"])
        fbc_ok = sum(1 for e in web if e["fbc"])
        bad_fbp = [e["fbp"] for e in web if e["fbp"] and not e["fbp"].startswith("fb.")]
        bad_fbc = [e["fbc"] for e in web if e["fbc"] and not e["fbc"].startswith("fb.")]
        report["server_fbp_pct"] = round(fbp_ok / len(web) * 100, 1)
        report["server_fbc_pct"] = round(fbc_ok / len(web) * 100, 1)
        if fbp_ok / len(web) < 0.8:
            problem("WARN", "fbp coverage", f"fbp on {fbp_ok}/{len(web)} server events; read the _fbp cookie and send it")
        if bad_fbp or bad_fbc:
            problem("ERROR", "fbp/fbc format", "values not in fb.<subdomain>.<time>.<value> format", bad_fbp + bad_fbc)
        report["note_fbc"] = "fbc is only present for visits that came from a Meta ad click (fbclid); low coverage is normal"
    else:
        problem("INFO", "fbp/fbc not in server log", "Add fbp and fbc columns to check browser ID coverage")

    # Print
    print(f"Browser events: {len(b)} | Server events: {len(s)}")
    print()
    print(f"{'Event':<22}{'Browser':>8}{'Server':>8}{'Matched':>9}{'Match% (B)':>12}{'Only B':>8}{'Only S':>8}")
    for name, r in report["per_event"].items():
        rb = f"{r['browser_match_rate_pct']:.0f}%" if r["browser_match_rate_pct"] is not None else "-"
        print(f"{name:<22}{r['browser_events']:>8}{r['server_events']:>8}{r['matched_ids']:>9}{rb:>12}{r['only_browser']:>8}{r['only_server']:>8}")
    if "server_fbp_pct" in report:
        print(f"\nServer fbp coverage: {report['server_fbp_pct']}% | fbc coverage: {report['server_fbc_pct']}% ({report['note_fbc']})")
    print("\nFindings")
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    report["problems"].sort(key=lambda p: order[p["severity"]])
    if not report["problems"]:
        print("  No problems found.")
    for i, p in enumerate(report["problems"], 1):
        print(f"  {i}. [{p['severity']}] {p['check']}: {p['detail']}")
        for ex in p["examples"]:
            print(f"       - {ex}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nJSON written: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
