#!/usr/bin/env python3
"""Reconcile GA4 purchases against backend orders.

Usage:
    python3 scripts/reconcile_orders.py ga4_transactions.csv backend_orders.csv
    python3 scripts/reconcile_orders.py ga4.csv orders.csv --tolerance 1.0

GA4 CSV:     transaction_id, revenue  (also accepts "Transaction ID",
             "Purchase revenue", "Total revenue"; optional "Ecommerce purchases")
Backend CSV: order_id, amount, optional payment_method, optional status
             (cancelled / failed / test rows are listed separately and excluded)

--tolerance  allowed per-order revenue difference in percent (default 1.0)

Standard library only. Prints markdown.
"""
import csv
import io
import re
import sys
from collections import defaultdict, Counter

GA4_ID_COLS = ["transaction_id", "transaction id", "transactionid"]
GA4_REV_COLS = ["revenue", "purchase_revenue", "purchase revenue", "total_revenue", "total revenue",
                "item_revenue", "item revenue"]
GA4_COUNT_COLS = ["ecommerce_purchases", "ecommerce purchases", "purchases", "transactions"]
BE_ID_COLS = ["order_id", "order id", "order_number", "order number", "id", "name"]
BE_AMT_COLS = ["amount", "total", "order_total", "order total", "grand_total", "total_price", "revenue"]
BE_PM_COLS = ["payment_method", "payment method", "payment_mode", "payment mode", "gateway", "payment_type"]
BE_STATUS_COLS = ["status", "order_status", "financial_status"]
EXCLUDE_STATUS = re.compile(r"cancel|fail|void|test|abandon|pending_payment", re.I)


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    # drop GA4 "#" comment lines above the header only; order IDs may start with "#"
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rows]


def pick(cols, options, path, required=True):
    for o in options:
        if o in cols:
            return o
    if required:
        sys.exit("%s: none of the columns %s found (have: %s)" % (path, options, ", ".join(cols)))
    return None


def money(s):
    s = re.sub(r"[^\d.\-]", "", s or "")
    try:
        return float(s) if s not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0


def norm_id(s):
    s = (s or "").strip().lstrip("#").strip()
    return s.upper()


def classify_pm(pm):
    p = (pm or "").lower()
    if not p:
        return "unknown"
    # "cash" alone would also match gateways like Cashfree, so match whole words
    if re.search(r"\bcod\b|cash[\s_-]*on[\s_-]*delivery|^cash$|\bpay on delivery\b", p):
        return "COD"
    return "Prepaid"


def fmt(x):
    return "{:,.2f}".format(x)


def main():
    args = sys.argv[1:]
    tol = 1.0
    if "--tolerance" in args:
        i = args.index("--tolerance")
        try:
            tol = float(args[i + 1])
        except (IndexError, ValueError):
            sys.exit("--tolerance needs a number")
        args = args[:i] + args[i + 2:]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    ga_path, be_path = args

    ga_rows, be_rows = read_csv(ga_path), read_csv(be_path)
    if not ga_rows or not be_rows:
        sys.exit("One of the files has no data rows.")
    ga_cols, be_cols = list(ga_rows[0]), list(be_rows[0])
    g_id = pick(ga_cols, GA4_ID_COLS, ga_path)
    g_rev = pick(ga_cols, GA4_REV_COLS, ga_path)
    g_cnt = pick(ga_cols, GA4_COUNT_COLS, ga_path, required=False)
    b_id = pick(be_cols, BE_ID_COLS, be_path)
    b_amt = pick(be_cols, BE_AMT_COLS, be_path)
    b_pm = pick(be_cols, BE_PM_COLS, be_path, required=False)
    b_st = pick(be_cols, BE_STATUS_COLS, be_path, required=False)

    # ---- GA4 ----
    ga = defaultdict(float)
    ga_rowcount = Counter()
    ga_reported_count = Counter()
    not_set_rev, not_set_rows = 0.0, 0
    for r in ga_rows:
        raw = r.get(g_id, "")
        tid = norm_id(raw)
        if not tid or tid in ("(NOT SET)", "NOT SET"):
            not_set_rows += 1
            not_set_rev += money(r.get(g_rev))
            continue
        if tid.lower() in ("total", "grand total", "totals"):
            continue
        ga[tid] += money(r.get(g_rev))
        ga_rowcount[tid] += 1
        if g_cnt:
            ga_reported_count[tid] += int(money(r.get(g_cnt)) or 0)
    dup_ids = sorted({t for t, c in ga_rowcount.items() if c > 1} |
                     {t for t, c in ga_reported_count.items() if c > 1})

    # ---- backend ----
    be, be_pm = {}, {}
    excluded = []
    be_dupes = []
    for r in be_rows:
        oid = norm_id(r.get(b_id))
        if not oid:
            continue
        status = r.get(b_st, "") if b_st else ""
        if status and EXCLUDE_STATUS.search(status):
            excluded.append((oid, status, money(r.get(b_amt))))
            continue
        if oid in be:
            be_dupes.append(oid)
            be[oid] += money(r.get(b_amt))
        else:
            be[oid] = money(r.get(b_amt))
        be_pm[oid] = classify_pm(r.get(b_pm)) if b_pm else "unknown"
    excluded_ids = {e[0] for e in excluded}

    matched = sorted(set(ga) & set(be))
    missing = sorted(set(be) - set(ga))
    extra = sorted(set(ga) - set(be))
    extra_cancelled = [t for t in extra if t in excluded_ids]
    extra_unknown = [t for t in extra if t not in excluded_ids]

    mismatched = []
    for t in matched:
        b, g = be[t], ga[t]
        if b == 0 and g == 0:
            continue
        diff_pct = abs(g - b) / b * 100 if b else 100.0
        if diff_pct > tol:
            mismatched.append((t, b, g, diff_pct))

    be_total, ga_total = sum(be.values()), sum(ga.values())
    gap_pct = (be_total - ga_total) / be_total * 100 if be_total else 0.0
    cnt_gap = (len(be) - len(ga)) / len(be) * 100 if be else 0.0
    capture = len(matched) / len(be) * 100 if be else 0.0

    p = print
    p("# GA4 vs backend order reconciliation")
    p("")
    p("- GA4 file: %s (%d rows, %d unique transaction IDs)" % (ga_path, len(ga_rows), len(ga)))
    p("- Backend file: %s (%d valid orders, %d excluded by status)" % (be_path, len(be), len(excluded)))
    p("- Per-order revenue tolerance: %.1f%%" % tol)
    p("")
    p("## Headline")
    p("")
    p("| Metric | Backend | GA4 | Gap |")
    p("|---|---|---|---|")
    p("| Orders | %d | %d | %.1f%% |" % (len(be), len(ga), cnt_gap))
    p("| Revenue | %s | %s | %.1f%% |" % (fmt(be_total), fmt(ga_total), gap_pct))
    if g_cnt:
        ev_total = sum(ga_reported_count.values())
        p("| GA4 purchase events (Ecommerce purchases) | - | %d | - |" % ev_total)
    m_be = sum(be[t] for t in matched)
    m_ga = sum(ga[t] for t in matched)
    if m_be:
        p("| Revenue, matched orders only | %s | %s | %.1f%% |" % (fmt(m_be), fmt(m_ga), (m_be - m_ga) / m_be * 100))
    p("")
    p("- Backend orders found in GA4: %d of %d (%.1f%%)" % (len(matched), len(be), capture))
    p("- Missing in GA4: %d | Extra in GA4: %d | Duplicated IDs in GA4: %d | Revenue mismatches: %d"
      % (len(missing), len(extra), len(dup_ids), len(mismatched)))
    if not_set_rows:
        p("- GA4 rows with transaction ID (not set): %d, revenue %s - purchases sent without transaction_id"
          % (not_set_rows, fmt(not_set_rev)))
    p("")
    p("_Gap = (backend - GA4) / backend. Positive means GA4 is under-reporting._")
    p("")

    if b_pm:
        p("## COD vs prepaid")
        p("")
        p("| Payment type | Backend orders | Found in GA4 | Capture rate | Backend revenue | GA4 revenue (matched) |")
        p("|---|---|---|---|---|---|")
        for k in ("Prepaid", "COD", "unknown"):
            ids = [t for t in be if be_pm.get(t) == k]
            if not ids:
                continue
            found = [t for t in ids if t in ga]
            p("| %s | %d | %d | %.1f%% | %s | %s |" % (
                k, len(ids), len(found), 100.0 * len(found) / len(ids),
                fmt(sum(be[t] for t in ids)), fmt(sum(ga[t] for t in found))))
        p("")
        p("_A much lower capture rate for one payment type points to a flow problem "
          "(for example prepaid orders that return from the gateway to a different page)._")
        p("")

    def table(title, header, rows, limit=50):
        p("## %s (%d)" % (title, len(rows)))
        p("")
        if not rows:
            p("None.")
            p("")
            return
        p("| " + " | ".join(header) + " |")
        p("|" + "---|" * len(header))
        for r in rows[:limit]:
            p("| " + " | ".join(str(c) for c in r) + " |")
        if len(rows) > limit:
            p("")
            p("_...and %d more. Use the full lists from your own export for follow-up._" % (len(rows) - limit))
        p("")

    table("Missing in GA4 (in backend, not in GA4)", ["Order ID", "Amount", "Payment"],
          [(t, fmt(be[t]), be_pm.get(t, "")) for t in missing])
    table("Extra in GA4, order cancelled/failed/test in backend", ["Transaction ID", "GA4 revenue"],
          [(t, fmt(ga[t])) for t in extra_cancelled])
    table("Extra in GA4, not in backend (test orders, wrong ID format, or other store)",
          ["Transaction ID", "GA4 revenue"], [(t, fmt(ga[t])) for t in extra_unknown])
    table("Duplicated transaction IDs in GA4", ["Transaction ID", "Rows", "Ecommerce purchases", "GA4 revenue"],
          [(t, ga_rowcount[t], ga_reported_count.get(t, "-") if g_cnt else "-", fmt(ga[t])) for t in dup_ids])
    table("Revenue mismatches over tolerance", ["Order ID", "Backend", "GA4", "Diff %"],
          [(t, fmt(b), fmt(g), "%.1f%%" % d) for t, b, g, d in sorted(mismatched, key=lambda x: -x[3])])
    if be_dupes:
        table("Order IDs repeated in backend file (amounts summed)", ["Order ID"], [(t,) for t in sorted(set(be_dupes))])

    p("## Reading the result")
    p("")
    p("- Revenue mismatches where GA4 is higher often mean shipping or tax is counted differently, "
      "or value is sent in paise instead of rupees. Lower often means discounts applied after the event.")
    p("- If extra IDs look like `TEST-` or come from staff, filter internal traffic and exclude test orders.")
    p("- If IDs never match at all, check the ID format (Shopify `#1001` vs `1001`, order number vs internal ID).")


if __name__ == "__main__":
    main()
