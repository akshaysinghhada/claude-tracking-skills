#!/usr/bin/env python3
"""Build Google Ads offline conversion upload files from a CRM export (python3 stdlib).

Outputs:
  1. GCLID file  - click conversions:  Google Click ID, Conversion Name, Conversion Time,
                   Conversion Value, Conversion Currency
  2. Hashed file - rows with no GCLID but with email/phone, for enhanced conversions
                   for leads: Email, Phone Number (SHA-256, normalized), Conversion Name, ...
Both start with a Parameters:TimeZone=... row.

Usage:
  python3 build_offline_import.py crm.csv \
      --map "sql=Qualified Lead - CRM" --map "won=Closed Won - CRM" \
      --out-gclid gclid_upload.csv --out-hashed ec_leads_upload.csv

Options: --timezone Asia/Kolkata (default) or +0530, --default-currency INR,
--default-value 0, --upload-date 2026-11-25 (for testing; default now).

CRM columns (matched loosely): gclid, email, phone, lead_stage, stage_time, value,
currency, and optional click_time / lead_created_time used for the 90-day check.
"""

import argparse
import csv
import hashlib
import re
import sys
from datetime import datetime, timedelta, timezone

COLS = {
    "gclid": ["gclid", "google click id", "google_click_id", "click id"],
    "email": ["email", "e-mail", "email address", "email_address"],
    "phone": ["phone", "phone number", "phone_number", "mobile", "mobile number", "contact number"],
    "stage": ["lead_stage", "lead stage", "stage", "deal stage", "status", "lifecycle stage"],
    "stage_time": ["stage_time", "stage time", "stage_changed_at", "stage date", "converted_at", "conversion time",
                   "close date", "updated_at"],
    "value": ["value", "deal value", "amount", "revenue", "conversion value"],
    "currency": ["currency", "currency code", "conversion currency"],
    "click_time": ["click_time", "click time", "lead_created_time", "created_at", "lead created", "create date"],
}

TIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
]

GCLID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def parse_tz(tzname):
    """Return a tzinfo for an IANA name or +HHMM / +HH:MM offset."""
    m = re.match(r"^([+-])(\d{2}):?(\d{2})$", tzname.strip())
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tzname)
    except Exception:
        if tzname == "Asia/Kolkata":
            return timezone(timedelta(hours=5, minutes=30))
        sys.exit(f"Unknown time zone '{tzname}'. Use an IANA name (Asia/Kolkata) or an offset (+0530).")


def parse_time(raw, tz):
    """Parse a CRM time. Naive values are taken as already in tz. Returns aware datetime or None."""
    s = (raw or "").strip()
    if not s:
        return None
    iso = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    except ValueError:
        pass
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    if re.match(r"^\d{10}(\d{3})?$", s):  # unix seconds or ms
        n = int(s)
        if n > 10**11:
            n //= 1000
        return datetime.fromtimestamp(n, tz)
    return None


def norm_email(e):
    e = (e or "").strip().lower()
    if not e or "@" not in e:
        return ""
    local, domain = e.rsplit("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
    return f"{local}@{domain}"


def norm_phone(p, cc="91"):
    p = (p or "").strip()
    if not p or re.match(r"^\d(\.\d+)?[eE]\+\d+$", p):
        return ""
    plus = p.startswith("+")
    d = re.sub(r"\D", "", p)
    if not d:
        return ""
    if plus:
        out = "+" + d
    elif d.startswith("00"):
        out = "+" + d[2:]
    elif cc == "91" and len(d) == 10:
        out = "+91" + d
    elif cc == "91" and len(d) == 11 and d.startswith("0"):
        out = "+91" + d[1:]
    elif d.startswith(cc) and len(d) > 10:
        out = "+" + d
    else:
        out = "+" + cc + d.lstrip("0")
    return out if 8 <= len(out) - 1 <= 15 else ""


def sha256(v):
    return hashlib.sha256(v.encode("utf-8")).hexdigest() if v else ""


def find_cols(header):
    low = [h.strip().lower() for h in header]
    out = {}
    for k, aliases in COLS.items():
        for a in aliases:
            if a in low:
                out[k] = header[low.index(a)]
                break
    return out


def parse_map(items):
    m = {}
    for it in items or []:
        if "=" not in it:
            sys.exit(f"--map needs stage=Conversion Name, got '{it}'")
        k, v = it.split("=", 1)
        m[k.strip().lower()] = v.strip()
    return m


def main():
    ap = argparse.ArgumentParser(description="Build Google Ads offline conversion import files")
    ap.add_argument("crm_csv")
    ap.add_argument("--map", action="append", required=True,
                    help='CRM stage to conversion action name, e.g. --map "sql=Qualified Lead - CRM" (repeatable)')
    ap.add_argument("--out-gclid", default="gclid_upload.csv")
    ap.add_argument("--out-hashed", default="ec_leads_upload.csv")
    ap.add_argument("--timezone", default="Asia/Kolkata", help="IANA name or +HHMM (default Asia/Kolkata = +05:30)")
    ap.add_argument("--tz-param", choices=["name", "offset"], default="name",
                    help="write the Parameters row as the zone name or as an offset like +0530")
    ap.add_argument("--default-currency", default="INR")
    ap.add_argument("--default-value", default="")
    ap.add_argument("--country-code", default="91", help="for phones without a country code (default 91)")
    ap.add_argument("--max-age-days", type=int, default=90)
    ap.add_argument("--upload-date", help="treat this date as today (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    tz = parse_tz(args.timezone)
    stage_map = parse_map(args.map)
    now = parse_time(args.upload_date, tz) if args.upload_date else datetime.now(tz)
    if args.tz_param == "offset":
        off = now.utcoffset() or timedelta(0)
        mins = int(off.total_seconds() // 60)
        tz_param = f"{'+' if mins >= 0 else '-'}{abs(mins)//60:02d}{abs(mins)%60:02d}"
    else:
        tz_param = args.timezone
    param_row = [f"Parameters:TimeZone={tz_param}"]

    with open(args.crm_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        cols = find_cols(header)
        rows = list(reader)
    for need in ("stage", "stage_time"):
        if need not in cols:
            sys.exit(f"Missing column for {need}. Columns: {', '.join(header)}")
    if "gclid" not in cols and "email" not in cols and "phone" not in cols:
        sys.exit("Need at least one of gclid, email, phone columns.")

    def get(r, k):
        return (r.get(cols[k], "") if k in cols else "").strip()

    gclid_rows, hashed_rows, problems = [], [], []
    seen = set()
    gclid_names = {}
    stats = {"read": len(rows), "unmapped": 0, "gclid": 0, "hashed": 0, "skipped": 0, "old": 0, "dupes": 0}
    unmapped_stages = {}

    for i, r in enumerate(rows, 2):  # line numbers as in the file (header = 1)
        stage = get(r, "stage").lower()
        if stage not in stage_map:
            stats["unmapped"] += 1
            unmapped_stages[stage or "(blank)"] = unmapped_stages.get(stage or "(blank)", 0) + 1
            continue
        conv_name = stage_map[stage]
        t = parse_time(get(r, "stage_time"), tz)
        if not t:
            problems.append(("ERROR", i, f"cannot parse stage_time '{get(r, 'stage_time')}'"))
            stats["skipped"] += 1
            continue
        if t > now + timedelta(minutes=5):
            problems.append(("ERROR", i, f"stage_time {t:%Y-%m-%d %H:%M} is in the future"))
            stats["skipped"] += 1
            continue
        conv_time = t.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")

        value = get(r, "value") or args.default_value
        if value:
            v = value.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
            try:
                value = f"{float(v):.2f}"
            except ValueError:
                problems.append(("WARN", i, f"value '{value}' is not a number, left blank"))
                value = ""
        currency = (get(r, "currency") or args.default_currency).upper()
        if not re.match(r"^[A-Z]{3}$", currency):
            problems.append(("WARN", i, f"currency '{currency}' is not a 3-letter ISO code"))

        gclid = get(r, "gclid")
        click_t = parse_time(get(r, "click_time"), tz) if "click_time" in cols else None
        if gclid:
            if not GCLID_RE.match(gclid):
                problems.append(("ERROR", i, f"gclid '{gclid[:30]}' has spaces or invalid characters; row skipped, re-export the raw value"))
                stats["skipped"] += 1
                continue
            if len(gclid) < 20:
                problems.append(("WARN", i, f"gclid '{gclid[:30]}' is unusually short; check it was not truncated"))
            if click_t:
                age = (now - click_t).days
                if age > args.max_age_days:
                    problems.append(("ERROR", i, f"click on {click_t:%Y-%m-%d} is {age} days old; Google Ads rejects GCLIDs older than {args.max_age_days} days"))
                    stats["old"] += 1
                    stats["skipped"] += 1
                    continue
                if t < click_t:
                    problems.append(("ERROR", i, "conversion time is before the click/lead time"))
                    stats["skipped"] += 1
                    continue
                if age > 60:
                    problems.append(("WARN", i, f"click is {age} days old; upload soon and check the action's click-through window"))
            else:
                age = (now - t).days
                if age > args.max_age_days:
                    problems.append(("ERROR", i, f"stage_time is {age} days ago, so the click is older than {args.max_age_days} days; will be rejected"))
                    stats["old"] += 1
                    stats["skipped"] += 1
                    continue
            key = (gclid, conv_name, conv_time)
            if key in seen:
                problems.append(("WARN", i, "duplicate of an earlier row (same gclid, conversion, time), dropped"))
                stats["dupes"] += 1
                continue
            seen.add(key)
            gclid_names.setdefault((gclid, conv_name), []).append(i)
            gclid_rows.append([gclid, conv_name, conv_time, value, currency if value else ""])
            stats["gclid"] += 1
            continue

        email = norm_email(get(r, "email"))
        phone = norm_phone(get(r, "phone"), args.country_code)
        if not email and not phone:
            problems.append(("WARN", i, "no gclid, email or phone: cannot be uploaded"))
            stats["skipped"] += 1
            continue
        if (now - t).days > args.max_age_days:
            problems.append(("WARN", i, f"stage_time is over {args.max_age_days} days ago; likely outside the conversion window"))
        key = (email, phone, conv_name, conv_time)
        if key in seen:
            stats["dupes"] += 1
            continue
        seen.add(key)
        hashed_rows.append([sha256(email), sha256(phone), conv_name, conv_time, value, currency if value else ""])
        stats["hashed"] += 1

    for (g, name), lines in gclid_names.items():
        if len(lines) > 1:
            problems.append(("WARN", lines[-1], f"gclid has {len(lines)} '{name}' rows at different times (lines {lines}); if the action counts 'One', only the first is kept"))

    with open(args.out_gclid, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(param_row)
        w.writerow(["Google Click ID", "Conversion Name", "Conversion Time", "Conversion Value", "Conversion Currency"])
        w.writerows(gclid_rows)
    if hashed_rows:
        with open(args.out_hashed, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(param_row)
            w.writerow(["Email", "Phone Number", "Conversion Name", "Conversion Time", "Conversion Value", "Conversion Currency"])
            w.writerows(hashed_rows)

    print(f"Rows read: {stats['read']}")
    print(f"  GCLID conversions written: {stats['gclid']} -> {args.out_gclid}")
    print(f"  Hashed (no GCLID) conversions written: {stats['hashed']}" + (f" -> {args.out_hashed}" if hashed_rows else " (file not created)"))
    print(f"  Stage not mapped (ignored): {stats['unmapped']}" + (f"  {unmapped_stages}" if unmapped_stages else ""))
    print(f"  Skipped with errors/warnings: {stats['skipped']} | GCLIDs too old: {stats['old']} | duplicates dropped: {stats['dupes']}")
    print(f"  Time zone: {param_row[0]} | times written as yyyy-MM-dd HH:mm:ss")
    if problems:
        print("Issues:")
        for lvl, line, msg in sorted(problems, key=lambda x: (x[0] != "ERROR", x[1])):
            print(f"  {lvl:5} line {line}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
