#!/usr/bin/env python3
"""
build_capi_payload.py - turn an order / lead record into a ready Meta
Conversions API request body, with normalized and SHA-256 hashed user_data,
plus a curl command to send it.

Input: a JSON file (one object, or a list of objects) or a CSV file (one row
per event). Recognised columns / keys (all optional except event time and an
identifier):

  event_name        Purchase | Lead | AddToCart | InitiateCheckout | CompleteRegistration
                    (or pass --event to set it for every row)
  order_id          used as event_id if event_id is empty
  event_id          dedup key, must match the pixel eventID for the same event
  event_time        unix seconds, unix ms, or ISO 8601 (2025-11-20T14:05:00+05:30)
  event_source_url  page where the event happened
  email, phone, first_name, last_name, city, state, zip, country, external_id
  client_ip_address, client_user_agent, fbc, fbp, fbclid
  value, currency   (currency defaults to INR)
  items             JSON list: [{"id": "SKU1", "quantity": 2, "item_price": 499}]
  content_ids       pipe separated SKUs if no items: SKU1|SKU2
  num_items         defaults to total quantity of items

Usage:
  python3 build_capi_payload.py order.json
  python3 build_capi_payload.py orders.csv --event Purchase --out payload.json
  python3 build_capi_payload.py lead.json --event Lead --test-event-code TEST12345
  python3 build_capi_payload.py order.json --pixel-id 123456789012345 --api-version v00.0

The access token is never stored in the output. The curl example reads it
from the META_CAPI_TOKEN environment variable.
Standard library only. Python 3.8+.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta

SUPPORTED = ["Purchase", "Lead", "AddToCart", "InitiateCheckout", "CompleteRegistration"]
NEEDS_VALUE = {"Purchase"}
COMMERCE = {"Purchase", "AddToCart", "InitiateCheckout"}
IST = timezone(timedelta(hours=5, minutes=30))


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_email(v):
    v = v.strip().lower()
    return v if re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", v) else None


def norm_phone(v, default_cc):
    digits = re.sub(r"\D", "", v)
    if not digits:
        return None
    digits = digits.lstrip("0")
    # Bare national number: add the default country code.
    if default_cc == "91" and len(digits) == 10 and digits[0] in "6789":
        digits = "91" + digits
    elif default_cc and len(digits) <= 10 and not digits.startswith(default_cc):
        digits = default_cc + digits
    return digits if 8 <= len(digits) <= 15 else None


def norm_name(v):
    v = strip_accents(v.strip().lower())
    v = re.sub(r"[^\w\s]", "", v, flags=re.UNICODE)
    return re.sub(r"\s+", " ", v).strip() or None


def norm_compact(v):
    """city / state: lowercase, no spaces, no punctuation."""
    v = strip_accents(v.strip().lower())
    v = re.sub(r"[^\w]", "", v, flags=re.UNICODE).replace("_", "")
    return v or None


def norm_zip(v):
    v = re.sub(r"[\s-]", "", v.strip().lower())
    return v or None


def norm_country(v):
    v = v.strip().lower()
    names = {"india": "in", "united states": "us", "usa": "us", "united kingdom": "gb", "uk": "gb",
             "united arab emirates": "ae", "uae": "ae", "singapore": "sg", "australia": "au", "canada": "ca"}
    v = names.get(v, v)
    return v if re.match(r"^[a-z]{2}$", v) else None


def parse_time(raw, warnings):
    if raw in (None, ""):
        warnings.append("event_time missing, using current time")
        return int(time.time())
    s = str(raw).strip()
    if re.match(r"^\d+(\.\d+)?$", s):
        t = float(s)
        if t > 1e12:  # milliseconds
            t = t / 1000.0
        return int(t)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            raise ValueError(f"cannot parse event_time '{s}'")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
        warnings.append(f"event_time '{s}' had no timezone, assumed IST (+05:30)")
    return int(dt.timestamp())


def build_fbc(fbc, fbclid, event_time):
    if fbc:
        return fbc.strip()
    if fbclid:
        # Best effort: use event time when the real click time was not stored.
        return f"fb.1.{event_time * 1000}.{fbclid.strip()}"
    return None


def g(rec, *keys):
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def build_event(rec, args):
    warnings = []
    name = args.event or g(rec, "event_name") or "Purchase"
    if name not in SUPPORTED:
        warnings.append(f"event_name '{name}' is not one of {SUPPORTED}; sent as given")
    event_time = parse_time(g(rec, "event_time", "created_at", "order_date"), warnings)
    now = int(time.time())
    if event_time > now + 60:
        warnings.append("event_time is in the future; Meta will reject it")
    elif now - event_time > 7 * 86400:
        warnings.append("event_time is older than 7 days; Meta rejects most website events this old")

    event_id = g(rec, "event_id") or (f"{name.lower()}_{g(rec, 'order_id')}" if g(rec, "order_id") else "")
    if not event_id:
        warnings.append("no event_id or order_id: pixel/CAPI deduplication is impossible")

    ud = {}
    hashed_inputs = [
        ("em", g(rec, "email", "em"), norm_email),
        ("ph", g(rec, "phone", "ph", "mobile"), lambda v: norm_phone(v, args.default_country_code)),
        ("fn", g(rec, "first_name", "fn"), norm_name),
        ("ln", g(rec, "last_name", "ln"), norm_name),
        ("ct", g(rec, "city", "ct"), norm_compact),
        ("st", g(rec, "state", "st"), norm_compact),
        ("zp", g(rec, "zip", "pincode", "postal_code", "zp"), norm_zip),
        ("country", g(rec, "country") or args.default_country, norm_country),
        ("external_id", g(rec, "external_id", "customer_id"), lambda v: v.strip() or None),
    ]
    for key, raw, fn in hashed_inputs:
        if not raw:
            continue
        normalized = fn(raw)
        if normalized is None:
            warnings.append(f"{key} value '{raw}' could not be normalized, omitted")
            continue
        ud[key] = [sha256(normalized)]

    for key, raw in [("client_ip_address", g(rec, "client_ip_address", "ip")),
                     ("client_user_agent", g(rec, "client_user_agent", "user_agent")),
                     ("fbp", g(rec, "fbp"))]:
        if raw:
            ud[key] = raw.strip()
    fbc = build_fbc(g(rec, "fbc"), g(rec, "fbclid"), event_time)
    if fbc:
        ud["fbc"] = fbc
        if not g(rec, "fbc"):
            warnings.append("fbc built from fbclid using event_time; store the real click time on landing for accuracy")

    if not any(k in ud for k in ("em", "ph", "external_id", "fbc", "fbp")) and not (
            "client_ip_address" in ud and "client_user_agent" in ud):
        warnings.append("user_data has too few match keys; Meta may reject or not match this event")
    if "client_user_agent" not in ud:
        warnings.append("client_user_agent missing; it is required for action_source 'website'")

    event = {
        "event_name": name,
        "event_time": event_time,
        "action_source": "website",
        "user_data": ud,
    }
    if event_id:
        event["event_id"] = event_id
    url = g(rec, "event_source_url", "page_url")
    if url:
        event["event_source_url"] = url
    else:
        warnings.append("event_source_url missing; required for action_source 'website'")

    cd = {}
    value = g(rec, "value", "order_total", "total")
    if value:
        try:
            cd["value"] = round(float(value), 2)
        except ValueError:
            warnings.append(f"value '{value}' is not a number, omitted")
    if cd.get("value") is not None or name in NEEDS_VALUE:
        cd["currency"] = (g(rec, "currency") or args.currency).upper()
    if name in NEEDS_VALUE and "value" not in cd:
        warnings.append("Purchase requires value and currency")

    if name in COMMERCE:
        items_raw = rec.get("items")
        items = []
        if isinstance(items_raw, str) and items_raw.strip():
            try:
                items_raw = json.loads(items_raw)
            except json.JSONDecodeError:
                warnings.append("items is not valid JSON, ignored")
                items_raw = None
        if isinstance(items_raw, list):
            for it in items_raw:
                if not isinstance(it, dict) or not it.get("id"):
                    continue
                item = {"id": str(it["id"]), "quantity": int(it.get("quantity", 1))}
                if it.get("item_price") not in (None, ""):
                    item["item_price"] = round(float(it["item_price"]), 2)
                items.append(item)
        if items:
            cd["contents"] = items
            cd["content_ids"] = [i["id"] for i in items]
            cd["num_items"] = sum(i["quantity"] for i in items)
        elif g(rec, "content_ids"):
            cd["content_ids"] = [c.strip() for c in g(rec, "content_ids").split("|") if c.strip()]
        if g(rec, "num_items"):
            cd["num_items"] = int(float(g(rec, "num_items")))
        if "content_ids" in cd:
            cd["content_type"] = g(rec, "content_type") or "product"
        else:
            warnings.append("no items/content_ids; catalog (Advantage+ catalog ads) matching needs content_ids")
    if cd:
        event["custom_data"] = cd
    return event, warnings


def load_records(path):
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else [data]


def main():
    ap = argparse.ArgumentParser(description="Build a Meta Conversions API payload from order/lead data")
    ap.add_argument("file", help="order JSON (object or list) or CSV")
    ap.add_argument("--event", choices=SUPPORTED, help="force event_name for all records")
    ap.add_argument("--currency", default="INR", help="default currency (ISO 4217), default INR")
    ap.add_argument("--default-country-code", default="91", help="phone country code for bare numbers, default 91")
    ap.add_argument("--default-country", default="", help="2-letter country to use when the record has none, e.g. in")
    ap.add_argument("--test-event-code", help="adds test_event_code so events show in Events Manager > Test events")
    ap.add_argument("--pixel-id", default="<PIXEL_ID>", help="pixel / dataset ID for the curl example")
    ap.add_argument("--api-version", default="v<VERSION>", help="Graph API version for the curl example, e.g. v00.0 (use the current one)")
    ap.add_argument("--out", help="write the payload JSON to this file")
    args = ap.parse_args()

    records = load_records(args.file)
    events, all_warnings = [], []
    for i, rec in enumerate(records, 1):
        try:
            ev, warns = build_event(rec, args)
        except ValueError as exc:
            print(f"record {i}: skipped ({exc})", file=sys.stderr)
            continue
        events.append(ev)
        all_warnings += [f"record {i}: {w}" for w in warns]

    payload = {"data": events}
    if args.test_event_code:
        payload["test_event_code"] = args.test_event_code
    text = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"Payload with {len(events)} event(s) written to {args.out}")
        body_ref = f"@{args.out}"
    else:
        print(text)
        body_ref = "@payload.json"

    print("\n# Send it (token from env var, never paste it into files you share):")
    print("# export META_CAPI_TOKEN='<ACCESS_TOKEN>'")
    print(f"curl -X POST \\\n  'https://graph.facebook.com/{args.api_version}/{args.pixel_id}/events?access_token='\"$META_CAPI_TOKEN\" \\\n"
          f"  -H 'Content-Type: application/json' \\\n  --data {body_ref}")
    if args.api_version == "v<VERSION>":
        print("# Replace v<VERSION> with the current Graph API version from Meta's changelog.")
    if not args.test_event_code:
        print("# Tip: add --test-event-code TESTxxxx (from Events Manager > Test events) for a dry run.")
    if all_warnings:
        print("\nWarnings:", file=sys.stderr)
        for w in all_warnings:
            print(f"  - {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
