#!/usr/bin/env python3
"""Check a GA4 events export for naming problems, duplicate event names and
missing recommended events.

Usage:
    python3 scripts/ga4_events_check.py events.csv
    python3 scripts/ga4_events_check.py events.csv --type ecommerce   (or lead, saas)

Input: CSV with columns event_name and event_count. Also accepts the GA4 UI
export (Reports > Engagement > Events > Share > Download CSV), which has
"#" comment lines and "Event name" / "Event count" headers. Extra columns are
ignored. Standard library only. Prints markdown.
"""
import csv
import io
import re
import sys
from collections import defaultdict

AUTO_EVENTS = {
    "page_view", "session_start", "first_visit", "user_engagement", "scroll", "click",
    "view_search_results", "file_download", "form_start", "form_submit", "video_start",
    "video_progress", "video_complete",
}
RECOMMENDED = {
    "ecommerce": {
        "required": ["view_item", "add_to_cart", "begin_checkout", "add_shipping_info",
                     "add_payment_info", "purchase"],
        "useful": ["view_item_list", "select_item", "view_cart", "remove_from_cart", "refund",
                   "add_to_wishlist", "view_promotion", "select_promotion"],
    },
    "lead": {
        "required": ["generate_lead"],
        "useful": ["qualify_lead", "disqualify_lead", "working_lead", "close_convert_lead",
                   "close_unconvert_lead"],
    },
    "saas": {
        "required": ["sign_up", "login"],
        "useful": ["generate_lead", "purchase", "begin_checkout", "refund"],
    },
}
# common non-standard names -> recommended GA4 event
ALIASES = {
    "addtocart": "add_to_cart", "add_cart": "add_to_cart", "cart_add": "add_to_cart",
    "initiatecheckout": "begin_checkout", "checkout": "begin_checkout",
    "start_checkout": "begin_checkout", "checkout_started": "begin_checkout",
    "addpaymentinfo": "add_payment_info", "payment_info": "add_payment_info",
    "viewcontent": "view_item", "product_view": "view_item", "view_product": "view_item",
    "order_complete": "purchase", "order_completed": "purchase", "transaction": "purchase",
    "checkout_complete": "purchase", "purchased": "purchase", "order_placed": "purchase",
    "lead": "generate_lead", "lead_submit": "generate_lead", "form_submission": "generate_lead",
    "lead_form_submit": "generate_lead", "contact_form_submit": "generate_lead",
    "completeregistration": "sign_up", "signup": "sign_up", "register": "sign_up",
    "registration": "sign_up", "search": "search", "addtowishlist": "add_to_wishlist",
}
FUNNEL = ["view_item", "add_to_cart", "begin_checkout", "add_shipping_info",
          "add_payment_info", "purchase"]
RESERVED_PREFIXES = ("google_", "ga_", "firebase_")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def to_int(s):
    s = (s or "").strip().replace(",", "").replace(" ", "")
    try:
        return int(float(s))
    except ValueError:
        return None


def normalise(name):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip())   # camelCase -> snake
    s = re.sub(r"[\s\-\.]+", "_", s).lower()
    return re.sub(r"_+", "_", s).strip("_")


def squash(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def read_rows(path):
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.reader(io.StringIO("\n".join(lines)))
    header, rows = None, []
    for rec in reader:
        if header is None:
            low = [h.strip().lower().replace(" ", "_") for h in rec]
            if "event_name" in low:
                header = low
            continue
        if not rec:
            continue
        if header and len(rec) < len(header):
            rec += [""] * (len(header) - len(rec))
        rows.append(dict(zip(header, rec)))
        # GA4 sometimes appends a second table after a blank line; stop at a new header
    if header is None:
        sys.exit("No 'event_name' / 'Event name' column found.")
    if "event_count" not in header:
        sys.exit("No 'event_count' / 'Event count' column found.")
    out = defaultdict(int)
    for r in rows:
        name = (r.get("event_name") or "").strip()
        if not name or name.lower() in ("total", "grand total", "totals"):
            continue
        cnt = to_int(r.get("event_count"))
        if cnt is None:
            continue
        out[name] += cnt
    return out


def main():
    args = sys.argv[1:]
    site_type = None
    if "--type" in args:
        i = args.index("--type")
        site_type = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
        if site_type not in RECOMMENDED:
            sys.exit("--type must be one of: ecommerce, lead, saas")
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    events = read_rows(args[0])
    if not events:
        sys.exit("No event rows found.")

    names = set(events)
    norm_names = {normalise(n) for n in names}
    if site_type is None:
        ecom_hits = norm_names & set(RECOMMENDED["ecommerce"]["required"] + ["view_item_list"])
        site_type = "ecommerce" if ecom_hits else ("saas" if "sign_up" in norm_names else "lead")
        detected = True
    else:
        detected = False

    # naming issues
    naming = []
    for n in sorted(names):
        issues = []
        if not NAME_RE.match(n):
            issues.append("not lowercase snake_case")
        if " " in n:
            issues.append("contains spaces")
        if len(n) > 40:
            issues.append("longer than 40 characters (GA4 limit)")
        if n.lower().startswith(RESERVED_PREFIXES):
            issues.append("uses a reserved prefix (google_, ga_, firebase_)")
        if issues:
            naming.append((n, events[n], "; ".join(issues)))

    # duplicates differing by case / spacing / camelCase / separators
    groups = defaultdict(list)
    for n in names:
        groups[squash(normalise(n))].append(n)
    dupes = [sorted(g, key=lambda x: -events[x]) for g in groups.values() if len(g) > 1]

    # alias suggestions (non-standard names for a recommended event)
    alias = []
    for n in sorted(names):
        key = squash(n)
        target = ALIASES.get(key) or ALIASES.get(normalise(n))
        if target and target != n:
            alias.append((n, events[n], target))

    # missing recommended
    present = {normalise(n) for n in names}
    rec = RECOMMENDED[site_type]
    missing_req = [e for e in rec["required"] if e not in present]
    missing_use = [e for e in rec["useful"] if e not in present]

    # funnel sanity (exact recommended names only)
    funnel_rows, funnel_flags = [], []
    prev = None
    for e in FUNNEL:
        if e in events:
            funnel_rows.append((e, events[e]))
            if prev and events[e] > events[prev[0]]:
                funnel_flags.append("%s (%d) is higher than %s (%d) - check for duplicate firing "
                                    "or a step that does not fire on every path" %
                                    (e, events[e], prev[0], prev[1]))
            prev = (e, events[e])

    all_recommended = {e for v in RECOMMENDED.values() for e in v["required"] + v["useful"]}
    low_volume = [(n, c) for n, c in events.items()
                  if c < 10 and n not in AUTO_EVENTS and n not in all_recommended]

    # ---- output ----
    p = print
    p("# GA4 events check")
    p("")
    p("- File: %s" % args[0])
    p("- Distinct event names: %d | Total events: %s" % (len(events), "{:,}".format(sum(events.values()))))
    p("- Site type: %s%s" % (site_type, " (auto-detected, override with --type)" if detected else ""))
    p("")
    p("## Summary")
    p("")
    summary = []
    if dupes:
        summary.append("**High** - %d group(s) of duplicate event names that split reporting" % len(dupes))
    if missing_req:
        summary.append("**High** - missing recommended %s events: %s" % (site_type, ", ".join(missing_req)))
    if funnel_flags:
        summary.append("**High** - %d funnel step(s) out of order" % len(funnel_flags))
    if naming:
        summary.append("**Medium** - %d event name(s) break GA4 naming rules or convention" % len(naming))
    if alias:
        summary.append("**Medium** - %d custom name(s) that should use a recommended event name" % len(alias))
    if low_volume:
        summary.append("**Low** - %d custom event(s) with under 10 hits (tests or typos?)" % len(low_volume))
    for s in summary or ["No issues found by the automated checks."]:
        p("- " + s)
    p("")

    p("## Duplicate names (differ only by case, spacing or separators)")
    p("")
    if not dupes:
        p("None found.")
    else:
        p("| Variants (count) | Keep |")
        p("|---|---|")
        for g in dupes:
            keep = normalise(g[0])
            keep = ALIASES.get(squash(keep), keep)
            p("| %s | %s |" % (", ".join("`%s` (%s)" % (n, "{:,}".format(events[n])) for n in g), keep))
    p("")

    p("## Naming issues")
    p("")
    if not naming:
        p("None found.")
    else:
        p("| Event | Count | Issue |")
        p("|---|---|---|")
        for n, c, i in naming:
            p("| `%s` | %s | %s |" % (n, "{:,}".format(c), i))
    p("")

    p("## Non-standard names for recommended events")
    p("")
    if not alias:
        p("None found.")
    else:
        p("| Event | Count | Use instead | Recommended name already sent? |")
        p("|---|---|---|---|")
        for n, c, t in alias:
            also = ("yes, %s events - same action counted twice, keep one" % "{:,}".format(events[t])
                    if t in events else "no - rename at the source")
            p("| `%s` | %s | `%s` | %s |" % (n, "{:,}".format(c), t, also))
    p("")

    p("## Recommended events for %s" % site_type)
    p("")
    p("- Missing (core): %s" % (", ".join(missing_req) or "none"))
    p("- Missing (useful): %s" % (", ".join(missing_use) or "none"))
    p("")

    if funnel_rows:
        p("## Ecommerce funnel counts")
        p("")
        p("| Step | Events | % of previous |")
        p("|---|---|---|")
        last = None
        for e, c in funnel_rows:
            pct = "-" if not last else "%.1f%%" % (100.0 * c / last) if last else "-"
            p("| %s | %s | %s |" % (e, "{:,}".format(c), pct))
            last = c
        p("")
        for f in funnel_flags:
            p("- " + f)
        if funnel_flags:
            p("")

    if low_volume:
        p("## Low-volume custom events")
        p("")
        for n, c in sorted(low_volume, key=lambda x: x[1]):
            p("- `%s`: %d" % (n, c))
        p("")
    p("_Counts are event counts, not users. Funnel % compares event counts between steps, "
      "so repeat views inflate early steps. Use Explore > Funnel exploration for user-level rates._")


if __name__ == "__main__":
    main()
