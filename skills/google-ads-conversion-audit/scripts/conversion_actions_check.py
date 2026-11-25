#!/usr/bin/env python3
"""Audit a Google Ads conversion actions export (python3 stdlib only).

Usage:
    python3 conversion_actions_check.py conversions.csv
    python3 conversion_actions_check.py conversions.csv --business leadgen
    python3 conversion_actions_check.py conversions.csv --json findings.json

Accepts the CSV downloaded from Goals > Conversions > Summary, or a hand-made
table. Column names are matched loosely (see COLUMN_ALIASES). Title rows above
the header and "Total" rows are skipped.
"""

import argparse
import csv
import io
import json
import re
import sys

COLUMN_ALIASES = {
    "name": ["conversion action", "conversion action name", "conversion name", "name", "action"],
    "source": ["source", "conversion source", "tracking source", "type"],
    "category": ["category", "goal category", "action category", "goal", "conversion category"],
    "optimization": ["action optimization", "action optimisation", "optimization", "optimisation",
                     "primary/secondary", "goal type", "include in \"conversions\"", "include in conversions",
                     "primary"],
    "count": ["count", "count type", "counting", "conversions count"],
    "attribution": ["attribution model", "attribution", "model"],
    "window": ["click-through conversion window", "click-through window", "click through window",
               "conversion window", "click-through"],
    "status": ["status", "tracking status", "conversion status"],
    "value": ["value", "value settings", "default value", "conversion value setting", "value setting"],
    "enhanced": ["enhanced conversions", "enhanced conversion", "enhanced conversions status", "ec status"],
    "conversions": ["conversions", "conv.", "all conv.", "all conversions"],
}

MICRO_CATEGORIES = {"page view", "add to cart", "begin checkout", "outbound click", "get directions",
                    "engagement", "view item", "download"}
MICRO_NAME_HINTS = ["page_view", "page view", "pageview", "scroll", "add_to_cart", "add to cart", "atc",
                    "view_item", "view item", "session_start", "first_visit", "engaged", "engagement",
                    "time on site", "video", "click", "begin_checkout", "initiate checkout", "initiatecheckout"]
PURCHASE_CATEGORIES = {"purchase", "store sale"}
LEAD_CATEGORIES = {"submit lead form", "contact", "request quote", "book appointment", "sign-up", "signup",
                   "phone call lead", "imported lead", "qualified lead", "converted lead", "lead", "subscribe"}
OFFLINE_HINTS = ["import", "crm", "salesforce", "hubspot", "upload", "offline", "zapier"]
GA4_HINTS = ["ga4", "google analytics", "analytics (ga4)", "firebase"]
LEADFORM_HINTS = ["lead form"]
BAD_STATUS_HINTS = ["inactive", "no recent", "unverified", "needs attention", "misconfigured", "not recording"]
DEPRECATED_MODELS = ["first click", "first-click", "linear", "time decay", "time-decay", "position-based",
                     "position based"]


def find_header(rows):
    for i, r in enumerate(rows[:15]):
        low = [c.strip().lower() for c in r]
        if any(c in COLUMN_ALIASES["name"] for c in low) and len([c for c in low if c]) >= 2:
            return i
    return 0


def map_columns(header):
    low = [h.strip().lower() for h in header]
    mapping = {}
    for key, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in low:
                mapping[key] = low.index(a)
                break
        if key not in mapping:
            for idx, h in enumerate(low):
                if any(h.startswith(a) for a in aliases if len(a) > 4):
                    if idx not in mapping.values():
                        mapping[key] = idx
                        break
    return mapping


def load(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        data = f.read()
    # Google Ads exports are sometimes tab separated (UTF-16 handled by user re-saving)
    delim = "\t" if data.count("\t") > data.count(",") else ","
    rows = list(csv.reader(io.StringIO(data), delimiter=delim))
    h = find_header(rows)
    header = rows[h]
    cmap = map_columns(header)
    if "name" not in cmap:
        sys.exit("Could not find a 'Conversion action' column. Columns seen: " + ", ".join(header))
    actions = []
    for r in rows[h + 1:]:
        if not r or not any(c.strip() for c in r):
            continue
        rec = {k: (r[i].strip() if i < len(r) else "") for k, i in cmap.items()}
        if rec["name"].lower().startswith("total"):
            continue
        actions.append(rec)
    return actions, cmap, header


def is_primary(a):
    v = a.get("optimization", "").lower()
    if not v:
        return None
    if "primary" in v or v in ("yes", "true", "y"):
        return True
    if "secondary" in v or v in ("no", "false", "n"):
        return False
    return None


def norm_name(n):
    n = n.lower()
    n = re.sub(r"\(.*?\)", "", n)
    for w in ["ga4", "google analytics", "web", "website", "tag", "gtag", "gtm", "-", "_", "  "]:
        n = n.replace(w, " ")
    return re.sub(r"\s+", " ", n).strip()


def has(text, hints):
    t = (text or "").lower()
    return any(h in t for h in hints)


def audit(actions, business):
    findings = []  # dict(severity, check, action, detail, fix)

    def add(sev, check, action, detail, fix):
        findings.append({"severity": sev, "check": check, "action": action, "detail": detail, "fix": fix})

    has_opt = any(is_primary(a) is not None for a in actions)
    if not has_opt:
        add("WARN", "Primary/secondary column", "-", "No Action optimization column found",
            "Add the 'Action optimization' column in Goals > Conversions > Summary and re-export")

    primaries = [a for a in actions if is_primary(a)]

    # 1. Duplicate counting: same category, more than one primary
    by_cat = {}
    for a in primaries:
        cat = a.get("category", "").lower() or "(no category)"
        by_cat.setdefault(cat, []).append(a)
    for cat, items in by_cat.items():
        if len(items) < 2:
            continue
        names = [i["name"] for i in items]
        srcs = [i.get("source", "") for i in items]
        ga4 = [i for i in items if has(i.get("source", "") + " " + i["name"], GA4_HINTS)]
        tag = [i for i in items if not has(i.get("source", "") + " " + i["name"], GA4_HINTS + OFFLINE_HINTS + LEADFORM_HINTS)]
        if cat in PURCHASE_CATEGORIES or "purchase" in cat:
            if ga4 and tag:
                add("ERROR", "Duplicate purchase counting", " + ".join(names),
                    f"{len(items)} primary purchase actions, including a Google Ads tag action and a GA4 import",
                    "Keep one as primary (usually the Google Ads tag with enhanced conversions), set the others to secondary")
            else:
                add("ERROR", "Duplicate purchase counting", " + ".join(names),
                    f"{len(items)} primary actions in category '{cat}' (sources: {', '.join(srcs)})",
                    "If they record the same order, set all but one to secondary")
        else:
            similar = {}
            for i in items:
                similar.setdefault(norm_name(i["name"]), []).append(i["name"])
            dup_groups = [v for v in similar.values() if len(v) > 1]
            sev = "ERROR" if (dup_groups or (ga4 and tag)) else "WARN"
            add(sev, "Multiple primary actions in one category", " + ".join(names),
                f"{len(items)} primary actions in '{cat}'" + (" with near-identical names" if dup_groups else ""),
                "Confirm they track different user actions; if the same form or event, keep one primary")

    for a in actions:
        name = a["name"]
        cat = a.get("category", "").lower()
        src = a.get("source", "")
        prim = is_primary(a)
        count = a.get("count", "").lower()
        attr = a.get("attribution", "").lower()
        status = a.get("status", "").lower()
        value = a.get("value", "").lower()
        enh = a.get("enhanced", "").lower()
        window = a.get("window", "")
        is_offline = has(src + " " + name, OFFLINE_HINTS)
        is_ga4 = has(src + " " + name, GA4_HINTS)
        is_leadform = has(src + " " + name, LEADFORM_HINTS)
        is_purchase = cat in PURCHASE_CATEGORIES or ("purchase" in cat)
        is_lead = cat in LEAD_CATEGORIES or "lead" in cat

        # 2. Micro-conversions as primary
        micro = cat in MICRO_CATEGORIES or (has(name, MICRO_NAME_HINTS) and not is_purchase and not is_lead)
        if prim and micro:
            add("ERROR", "Micro-conversion set as primary", name,
                f"category '{a.get('category','')}' is counted in Conversions and used by Smart Bidding",
                "Set to secondary; bid on purchases or qualified leads")
        elif prim and cat == "other":
            add("WARN", "Primary action with category Other", name,
                "Category 'Other' often hides micro-events", "Confirm it is a real business outcome, else set to secondary")

        # 3. Count setting
        if count:
            if is_purchase and count.startswith("one"):
                add("WARN", "Count setting", name, "Purchase counted 'One' per click",
                    "Use 'Every' for purchases so repeat orders are counted")
            if is_lead and count.startswith("every") and not is_offline:
                add("WARN", "Count setting", name, "Lead counted 'Every' per click",
                    "Use 'One' for leads so refreshes and double submits do not inflate counts")

        # 4. Attribution model
        if attr and not is_ga4:
            if any(m in attr for m in DEPRECATED_MODELS):
                add("ERROR", "Attribution model", name, f"'{a.get('attribution')}' is a rule-based model Google has retired",
                    "Switch to data-driven (or last click); check the action's settings in your account")
            elif "last" in attr and "click" in attr:
                add("INFO", "Attribution model", name, "Last click", "Data-driven is the default; consider switching if volume allows")

        # 5. Click-through window
        m = re.search(r"(\d+)", window or "")
        if m:
            days = int(m.group(1))
            if days < 7:
                add("WARN", "Click-through window", name, f"{days} days", "Short windows drop delayed conversions; 30 days is the default")
            if is_offline and days < 90 and business == "leadgen":
                add("WARN", "Click-through window", name, f"{days} days on an offline/CRM action",
                    "B2B sales cycles are long; set up to 90 days so late-stage imports are accepted")

        # 6. Status
        if status and has(status, BAD_STATUS_HINTS):
            add("ERROR" if prim else "WARN", "Tracking status", name, f"Status: {a.get('status')}",
                "Check tag firing with Tag Assistant, or upload schedule for imports")

        # 7. Enhanced conversions
        is_web_tag = (not src) or ("website" in src.lower()) or ("web" == src.lower())
        if "enhanced" in a and (is_purchase or is_lead) and is_web_tag and not is_ga4 and not is_offline:
            if not enh or any(x in enh for x in ["off", "not set", "no", "inactive", "needs attention", "unverified"]):
                add("WARN", "Enhanced conversions", name, f"Enhanced conversions: '{a.get('enhanced') or 'blank'}'",
                    "Turn on enhanced conversions and check the Diagnostics tab (see google-ads-enhanced-conversions skill)")

        # 8. Value
        if "value" in a and is_purchase:
            if not value or "don't use" in value or "no value" in value or value in ("0", "0.00"):
                add("ERROR", "Purchase value", name, "No value on a purchase action",
                    "Pass the transaction value dynamically; Target ROAS needs it")
            elif "same value" in value:
                add("WARN", "Purchase value", name, "Same value for each conversion",
                    "Use the actual order value for purchases")

        # 9. Lead forms
        if is_leadform and prim and business == "leadgen":
            add("INFO", "Lead form asset", name, "Lead form submits are primary",
                "Fine to start; once CRM import works, bid on qualified leads and set raw submits to secondary")

        # 10. GA4 import primary next to tag
    # 11. No primary purchase / lead
    if business == "ecommerce" and actions and has_opt:
        if not any(is_primary(a) and ((a.get("category", "").lower() in PURCHASE_CATEGORIES) or "purchase" in a.get("category", "").lower()) for a in actions):
            add("ERROR", "No primary purchase", "-", "No purchase action is primary",
                "Set one purchase action to primary or sales campaigns have no goal")
    if business == "leadgen" and actions and has_opt:
        offline_secondary = [a["name"] for a in actions if has(a.get("source", "") + " " + a["name"], OFFLINE_HINTS) and is_primary(a) is False]
        if offline_secondary:
            add("INFO", "Qualified-lead bidding", ", ".join(offline_secondary),
                "CRM/offline actions exist but are secondary",
                "When they record steady volume, consider making them primary (or use conversion value rules)")

    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    return findings


def main():
    p = argparse.ArgumentParser(description="Audit a Google Ads conversion actions export")
    p.add_argument("file")
    p.add_argument("--business", choices=["ecommerce", "leadgen", "auto"], default="auto",
                   help="tunes some checks; auto guesses from categories")
    p.add_argument("--json", help="also write findings as JSON")
    args = p.parse_args()

    actions, cmap, header = load(args.file)
    business = args.business
    if business == "auto":
        cats = " ".join(a.get("category", "").lower() for a in actions)
        business = "ecommerce" if "purchase" in cats else "leadgen"

    findings = audit(actions, business)
    missing = [k for k in ("source", "category", "optimization", "count", "attribution") if k not in cmap]

    print(f"Conversion actions read: {len(actions)}  (business type: {business})")
    print("Columns matched: " + ", ".join(f"{k}='{header[i]}'" for k, i in cmap.items()))
    if missing:
        print("Columns not found (checks skipped): " + ", ".join(missing))
    print()
    print("ACTIONS")
    for a in actions:
        prim = is_primary(a)
        tag = "PRIMARY  " if prim else ("secondary" if prim is False else "?        ")
        print(f"  {tag} | {a['name']} | {a.get('source','')} | {a.get('category','')} | count={a.get('count','')} | {a.get('attribution','')}")
    print()
    print("FINDINGS")
    if not findings:
        print("  No issues found by the script. Still review the manual checks in SKILL.md.")
    for i, f in enumerate(findings, 1):
        print(f"  {i}. [{f['severity']}] {f['check']}: {f['action']}")
        print(f"     {f['detail']}")
        print(f"     Fix: {f['fix']}")
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ("ERROR", "WARN", "INFO")}
    print()
    print(f"Summary: {counts['ERROR']} errors, {counts['WARN']} warnings, {counts['INFO']} info")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"business": business, "actions": actions, "findings": findings}, f, indent=2)
        print(f"JSON written: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
