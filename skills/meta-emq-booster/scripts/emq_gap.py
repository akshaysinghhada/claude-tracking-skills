#!/usr/bin/env python3
"""
emq_gap.py - audit a sample of Meta Conversions API (CAPI) server events for
Event Match Quality gaps.

Input: a JSON lines file. Each line can be either
  - a single CAPI event object: {"event_name": ..., "user_data": {...}, ...}
  - a full request body: {"data": [ {event}, {event} ], ...}
A plain JSON array of events, or one request body, also works.

Reports:
  - per-parameter coverage % (overall and per event_name)
  - plaintext PII sent in fields that must be SHA-256 hashed
  - fields that must NOT be hashed but look hashed (fbc, fbp, IP, user agent)
  - malformed plaintext emails / phones, bad fbc / fbp formats
  - hashes of empty strings or placeholder values
  - a ranked list of what to add or fix first

Usage:
  python3 emq_gap.py events.jsonl
  python3 emq_gap.py events.jsonl --json report.json
  python3 emq_gap.py events.jsonl --by-event

Standard library only. Python 3.8+.
"""
import argparse
import hashlib
import ipaddress
import json
import re
import sys
from collections import Counter, defaultdict

HASHED_FIELDS = ["em", "ph", "fn", "ln", "ct", "st", "zp", "country", "external_id", "ge", "db"]
UNHASHED_FIELDS = ["client_ip_address", "client_user_agent", "fbc", "fbp"]
# Order used for the report table.
REPORT_FIELDS = ["em", "ph", "fbc", "fbp", "external_id", "client_ip_address",
                 "client_user_agent", "fn", "ln", "ct", "st", "zp", "country"]

# Heuristic priority. Meta does not publish exact weights; these reflect the
# usual impact of each key on matching. Higher = add first.
PRIORITY = {
    "em": 10, "ph": 9, "fbc": 8, "external_id": 7, "fbp": 7,
    "client_ip_address": 6, "client_user_agent": 6,
    "fn": 4, "ln": 4, "zp": 3, "ct": 3, "st": 2, "country": 2,
}

HOW_TO_ADD = {
    "em": "Send the customer email from checkout/lead form, lowercased and trimmed, then SHA-256.",
    "ph": "Send phone as digits only with country code (India: 91XXXXXXXXXX, no +, no spaces), then SHA-256.",
    "fbc": "Capture fbclid from the landing URL, store it (first-party cookie _fbc or your DB), send as fb.1.<timestamp_ms>.<fbclid>, unhashed.",
    "fbp": "Read the _fbp cookie set by the Meta pixel and pass it to the server with the order, unhashed.",
    "external_id": "Send your stable customer/user ID (same value on pixel and CAPI), SHA-256 recommended.",
    "client_ip_address": "Send the end user's IP from the request (not your server IP, respect X-Forwarded-For), unhashed.",
    "client_user_agent": "Send the browser User-Agent header captured at event time, unhashed.",
    "fn": "Send first name lowercased, no punctuation, then SHA-256.",
    "ln": "Send last name lowercased, no punctuation, then SHA-256.",
    "ct": "Send city lowercased, no spaces or punctuation (e.g. jaipur), then SHA-256.",
    "st": "Send state lowercased, no spaces or punctuation (e.g. rajasthan), then SHA-256.",
    "zp": "Send postal code with no spaces (India PIN e.g. 302001), then SHA-256.",
    "country": "Send 2-letter ISO country code lowercased (in), then SHA-256.",
}

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
FBC_RE = re.compile(r"^fb\.\d\.\d{13}\.\S+$")
FBP_RE = re.compile(r"^fb\.\d\.\d{13}\.\d+$")

# Hashes of values that mean "no data" but get sent anyway.
PLACEHOLDERS = ["", "null", "none", "undefined", "nan", "n/a", "na", "0", "test", "test@test.com"]
PLACEHOLDER_HASHES = {hashlib.sha256(p.encode("utf-8")).hexdigest(): p for p in PLACEHOLDERS}


def load_events(path):
    events = []
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        return events
    chunks = []
    try:
        whole = json.loads(text)
        chunks = whole if isinstance(whole, list) else [whole]
    except json.JSONDecodeError:
        for n, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"warning: line {n} is not valid JSON, skipped ({exc})", file=sys.stderr)
    for obj in chunks:
        if isinstance(obj, dict) and isinstance(obj.get("data"), list):
            events.extend(e for e in obj["data"] if isinstance(e, dict))
        elif isinstance(obj, dict):
            events.append(obj)
    return events


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v not in (None, "")]
    if value == "":
        return []
    return [value]


def check_hashed_field(field, values, issues, idx):
    """Return True if the field has at least one usable value."""
    usable = False
    for raw in values:
        v = str(raw).strip()
        if HEX64.match(v):
            if v.lower() in PLACEHOLDER_HASHES:
                issues["placeholder_hash"][field] += 1
                continue
            if v != v.lower():
                issues["uppercase_hash"][field] += 1
            usable = True
            continue
        # Not a SHA-256 hex string: plaintext PII sent where hashing is required.
        issues["unhashed_pii"][field] += 1
        issues["examples"].setdefault(f"unhashed_{field}", idx)
        if field == "em" and not EMAIL_RE.match(v.lower()):
            issues["malformed"]["em"] += 1
        if field == "ph":
            digits = re.sub(r"\D", "", v)
            if v.startswith("+") or not v.isdigit():
                issues["malformed"]["ph_format (plus sign, spaces or symbols)"] += 1
            if len(digits) == 10 and digits[0] in "6789":
                issues["malformed"]["ph_missing_country_code (Indian 10-digit)"] += 1
            elif len(digits) < 8 or len(digits) > 15:
                issues["malformed"]["ph_length"] += 1
        if field == "country" and len(v) != 2:
            issues["malformed"]["country_not_2_letter_code"] += 1
        usable = True  # Meta may hash plaintext for some fields, but do not rely on it.
    return usable


def check_unhashed_field(field, values, issues, idx):
    usable = False
    for raw in values:
        v = str(raw).strip()
        if HEX64.match(v):
            issues["hashed_but_should_not_be"][field] += 1
            continue
        if field == "fbc" and not FBC_RE.match(v):
            issues["malformed"]["fbc_format (want fb.1.<13-digit ms>.<fbclid>)"] += 1
            issues["examples"].setdefault("bad_fbc", idx)
        if field == "fbp" and not FBP_RE.match(v):
            issues["malformed"]["fbp_format (want fb.1.<13-digit ms>.<random>)"] += 1
        if field == "client_ip_address":
            try:
                ip = ipaddress.ip_address(v)
                if ip.is_private or ip.is_loopback:
                    issues["malformed"]["client_ip_private_or_server (use the visitor IP)"] += 1
            except ValueError:
                issues["malformed"]["client_ip_invalid"] += 1
                continue
        usable = True
    return usable


def analyse(events):
    total = len(events)
    present = Counter()
    present_by_event = defaultdict(Counter)
    count_by_event = Counter()
    issues = {
        "unhashed_pii": Counter(),
        "hashed_but_should_not_be": Counter(),
        "malformed": Counter(),
        "placeholder_hash": Counter(),
        "uppercase_hash": Counter(),
        "examples": {},
    }
    other = Counter()
    for idx, ev in enumerate(events, 1):
        name = ev.get("event_name", "(missing event_name)")
        count_by_event[name] += 1
        ud = ev.get("user_data") or {}
        if not ev.get("user_data"):
            other["events_without_user_data"] += 1
        if not ev.get("event_id"):
            other["events_without_event_id (dedup with pixel will fail)"] += 1
        if ev.get("action_source") is None:
            other["events_without_action_source"] += 1
        for field in REPORT_FIELDS:
            values = as_list(ud.get(field))
            if not values:
                continue
            if field in HASHED_FIELDS:
                ok = check_hashed_field(field, values, issues, idx)
            else:
                ok = check_unhashed_field(field, values, issues, idx)
            if ok:
                present[field] += 1
                present_by_event[name][field] += 1
    return total, present, present_by_event, count_by_event, issues, other


def pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


def ranked_actions(total, present, issues):
    actions = []
    # Fix-first items: data that is actively wrong.
    for field, n in issues["unhashed_pii"].items():
        actions.append((100 + PRIORITY.get(field, 1),
                        f"FIX: {field} sent as plaintext in {n} event(s). Normalize then SHA-256 before sending."))
    for field, n in issues["hashed_but_should_not_be"].items():
        actions.append((95 + PRIORITY.get(field, 1),
                        f"FIX: {field} looks hashed in {n} event(s). Send {field} raw, never hashed."))
    for field, n in issues["placeholder_hash"].items():
        actions.append((90 + PRIORITY.get(field, 1),
                        f"FIX: {field} is a hash of an empty/placeholder value in {n} event(s). Omit the key when you have no data."))
    for label, n in issues["malformed"].items():
        actions.append((85, f"FIX: {label}: {n} value(s)."))
    for field, n in issues["uppercase_hash"].items():
        actions.append((80, f"FIX: {field} hash uses uppercase hex in {n} event(s). Use lowercase hex digest."))
    # Coverage gaps, weighted by missing share.
    for field in REPORT_FIELDS:
        cov = pct(present[field], total)
        if cov >= 95:
            continue
        missing_share = (100 - cov) / 100.0
        score = PRIORITY.get(field, 1) * missing_share * 10
        actions.append((score, f"ADD: {field} (coverage {cov}%). {HOW_TO_ADD[field]}"))
    actions.sort(key=lambda a: a[0], reverse=True)
    return [a[1] for a in actions]


def main():
    ap = argparse.ArgumentParser(description="Meta CAPI Event Match Quality gap report")
    ap.add_argument("file", help="JSON lines file of CAPI events or request bodies")
    ap.add_argument("--by-event", action="store_true", help="also print coverage per event_name")
    ap.add_argument("--json", metavar="OUT", help="write the full report as JSON to this path")
    args = ap.parse_args()

    events = load_events(args.file)
    if not events:
        print("No events found. Check the file format (JSON lines of CAPI events).")
        sys.exit(1)

    total, present, by_event, count_by_event, issues, other = analyse(events)

    print(f"EMQ gap report: {total} events")
    print("Events by name: " + ", ".join(f"{k}={v}" for k, v in count_by_event.most_common()))
    print()
    print(f"{'parameter':<20}{'hashed?':<10}{'coverage':>9}")
    print("-" * 39)
    for field in REPORT_FIELDS:
        kind = "SHA-256" if field in HASHED_FIELDS else "raw"
        print(f"{field:<20}{kind:<10}{pct(present[field], total):>8}%")

    if args.by_event:
        print()
        print("Coverage by event_name:")
        for name, n in count_by_event.most_common():
            cells = ", ".join(f"{f}={pct(by_event[name][f], n)}%" for f in REPORT_FIELDS)
            print(f"  {name} ({n}): {cells}")

    print()
    print("Problems found:")
    any_problem = False
    for key, title in [("unhashed_pii", "Plaintext PII in fields that need SHA-256"),
                       ("hashed_but_should_not_be", "Hashed values in fields that must be raw"),
                       ("placeholder_hash", "Hashes of empty/placeholder values"),
                       ("uppercase_hash", "Uppercase hex hashes"),
                       ("malformed", "Malformed values")]:
        if issues[key]:
            any_problem = True
            print(f"  {title}:")
            for k, v in issues[key].most_common():
                print(f"    - {k}: {v}")
    for k, v in other.most_common():
        any_problem = True
        print(f"  {k}: {v}")
    if not any_problem:
        print("  none")
    if issues["examples"]:
        print("  First offending event (1-based index): " +
              ", ".join(f"{k}=#{v}" for k, v in issues["examples"].items()))

    actions = ranked_actions(total, present, issues)
    print()
    print("Do this first (ranked):")
    for i, a in enumerate(actions[:12], 1):
        print(f"  {i}. {a}")
    if not actions:
        print("  Nothing major. Compare with Events Manager EMQ per event to confirm.")

    if args.json:
        report = {
            "total_events": total,
            "events_by_name": dict(count_by_event),
            "coverage_pct": {f: pct(present[f], total) for f in REPORT_FIELDS},
            "coverage_by_event": {n: {f: pct(by_event[n][f], c) for f in REPORT_FIELDS}
                                  for n, c in count_by_event.items()},
            "issues": {k: dict(v) for k, v in issues.items() if k != "examples"},
            "other": dict(other),
            "ranked_actions": actions,
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nJSON report written to {args.json}")


if __name__ == "__main__":
    main()
