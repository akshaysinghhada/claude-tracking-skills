#!/usr/bin/env python3
"""
compare_platforms.py - compare daily conversions reported by ad/analytics
platforms against backend (source of truth) orders, to spot double counting.

Input CSV columns (header names are matched case-insensitively; any platform
column can be missing):
  date, backend_orders, meta_purchases, google_ads_conversions, ga4_purchases
Extra numeric columns (for example tiktok_purchases) are compared too.

Output:
  - per-day table: backend, each platform, ratio platform / backend
  - flags for days where platform > backend * threshold (default 1.2)
  - summary per platform: totals, overall ratio, days flagged, median ratio
  - optional CSV with the per-day ratios

Usage:
  python3 compare_platforms.py daily.csv
  python3 compare_platforms.py daily.csv --threshold 1.3 --min-backend 5 --out ratios.csv

Platforms attribute differently (view-through, modeled conversions,
attribution windows, conversion date vs click date), so a high ratio is a
signal to investigate, not proof of duplication.
Standard library only. Python 3.8+.
"""
import argparse
import csv
import statistics
import sys
from datetime import datetime

KNOWN = ["meta_purchases", "google_ads_conversions", "ga4_purchases"]
ALIASES = {
    "backend_orders": ["backend_orders", "orders", "backend", "shopify_orders", "crm_orders"],
    "date": ["date", "day"],
}


def to_num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "" or s.lower() in ("na", "n/a", "null", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d %b %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description="Platform vs backend conversion comparison")
    ap.add_argument("file", help="CSV with date, backend_orders and platform columns")
    ap.add_argument("--threshold", type=float, default=1.2, help="flag when platform/backend exceeds this (default 1.2)")
    ap.add_argument("--min-backend", type=float, default=1, help="skip ratio flags on days with fewer backend orders (default 1)")
    ap.add_argument("--out", help="write per-day ratios to this CSV")
    args = ap.parse_args()

    with open(args.file, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            sys.exit("CSV has no header row.")
        header = {h.strip().lower(): h for h in reader.fieldnames if h}
        rows = list(reader)

    def find(col):
        for name in ALIASES.get(col, [col]):
            if name in header:
                return header[name]
        return None

    date_col, backend_col = find("date"), find("backend_orders")
    if not date_col or not backend_col:
        sys.exit("Need at least 'date' and 'backend_orders' columns. Found: " + ", ".join(reader.fieldnames))

    used = {date_col, backend_col}
    platforms = []
    for p in KNOWN:
        if p in header:
            platforms.append((p, header[p]))
            used.add(header[p])
    # Any other mostly-numeric column is treated as a platform.
    for low, orig in header.items():
        if orig in used:
            continue
        nums = [to_num(r.get(orig)) for r in rows]
        if rows and sum(n is not None for n in nums) >= max(1, len(rows) // 2):
            platforms.append((low, orig))
    missing = [p for p in KNOWN if p not in header]
    if not platforms:
        sys.exit("No platform columns found (expected one of: " + ", ".join(KNOWN) + ").")

    days = []
    for r in rows:
        d = parse_date(r.get(date_col, "") or "")
        if d is None:
            print(f"warning: skipped row with unreadable date '{r.get(date_col)}'", file=sys.stderr)
            continue
        days.append((d, to_num(r.get(backend_col)), {p: to_num(r.get(c)) for p, c in platforms}))
    days.sort(key=lambda x: x[0])
    if not days:
        sys.exit("No usable rows.")

    # Per-day table.
    names = [p for p, _ in platforms]
    head = f"{'date':<12}{'backend':>9}" + "".join(f"{p[:16]:>18}{'ratio':>7}" for p in names) + "  flags"
    print(f"Platform vs backend, {days[0][0]} to {days[-1][0]}, threshold {args.threshold}x")
    if missing:
        print("Missing columns (skipped): " + ", ".join(missing))
    print()
    print(head)
    print("-" * len(head))

    stats = {p: {"total": 0.0, "backend": 0.0, "ratios": [], "flags": [], "days": 0, "under": []} for p in names}
    out_rows = []
    for d, backend, vals in days:
        line = f"{d.isoformat():<12}{(f'{backend:.0f}' if backend is not None else '-'):>9}"
        flags = []
        out = {"date": d.isoformat(), "backend_orders": backend}
        for p in names:
            v = vals[p]
            ratio = None
            if v is not None and backend is not None:
                stats[p]["total"] += v
                stats[p]["backend"] += backend
                stats[p]["days"] += 1
                if backend >= args.min_backend and backend > 0:
                    ratio = v / backend
                    stats[p]["ratios"].append(ratio)
                    if ratio > args.threshold:
                        flags.append(f"{p} {ratio:.2f}x")
                        stats[p]["flags"].append((d, ratio))
                    elif ratio < 0.5:
                        stats[p]["under"].append((d, ratio))
                elif backend == 0 and v > 0:
                    flags.append(f"{p} {v:.0f} vs 0 backend")
                    stats[p]["flags"].append((d, float("inf")))
            line += f"{(f'{v:.0f}' if v is not None else '-'):>18}{(f'{ratio:.2f}' if ratio is not None else '-'):>7}"
            out[p] = v
            out[f"{p}_ratio"] = round(ratio, 3) if ratio is not None else ""
        out["flags"] = "; ".join(flags)
        out_rows.append(out)
        print(line + ("  " + "; ".join(flags) if flags else ""))

    print()
    print("Summary")
    for p in names:
        s = stats[p]
        if not s["days"]:
            print(f"  {p}: no overlapping data")
            continue
        overall = s["total"] / s["backend"] if s["backend"] else float("nan")
        med = statistics.median(s["ratios"]) if s["ratios"] else float("nan")
        verdict = "investigate" if (overall > args.threshold or len(s["flags"]) >= max(2, s["days"] // 4)) else (
            "under-reporting, check tag coverage" if overall < 0.7 else "within range")
        print(f"  {p}: total {s['total']:.0f} vs backend {s['backend']:.0f} -> overall {overall:.2f}x, "
              f"median daily {med:.2f}x, flagged days {len(s['flags'])}/{s['days']} -> {verdict}")
        if s["flags"]:
            worst = sorted(s["flags"], key=lambda x: x[1], reverse=True)[:3]
            print("     worst days: " + ", ".join(
                f"{d} ({'no backend' if r == float('inf') else f'{r:.2f}x'})" for d, r in worst))
    # Step change detection: a sudden jump often means a new tag/app went live.
    for p in names:
        r = [(d, v / b) for d, b, vals in days for v in [vals[p]] if v is not None and b and b >= args.min_backend]
        if len(r) >= 6:
            # Single change point: the split (3+ days each side) that minimises squared error.
            vals_r = [x[1] for x in r]

            def sse(seg):
                m = sum(seg) / len(seg)
                return sum((v - m) ** 2 for v in seg)

            best_k = min(range(3, len(r) - 2), key=lambda k: sse(vals_r[:k]) + sse(vals_r[k:]))
            first = statistics.median(vals_r[:best_k])
            second = statistics.median(vals_r[best_k:])
            if first > 0 and second / first >= 1.4:
                k = best_k
                print(f"  {p}: median ratio jumped from {first:.2f}x to {second:.2f}x starting {r[k][0]}. "
                      "Check what changed that day (new app, theme, GTM publish, CAPI launch).")
    print()
    print("Note: view-through, modeled conversions, attribution windows and conversion-date rules make platforms "
          "differ from backend. Treat flags as leads to investigate, not proof of duplicates.")

    if args.out:
        fields = ["date", "backend_orders"] + [x for p in names for x in (p, f"{p}_ratio")] + ["flags"]
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(out_rows)
        print(f"Per-day ratios written to {args.out}")


if __name__ == "__main__":
    main()
