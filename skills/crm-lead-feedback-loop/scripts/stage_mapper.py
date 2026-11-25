#!/usr/bin/env python3
"""
stage_mapper.py - turn a CRM lead export into conversion feedback files for
Meta (Conversions API for CRM / conversion leads) and Google Ads (offline
click conversion import).

Input CSV columns (case-insensitive; extra columns ignored):
  lead_id            your CRM lead ID
  source             e.g. meta_lead_form, meta_website, google_search, organic
  gclid              Google click ID captured with the lead (optional)
  fbclid             Meta click ID captured on the landing page (optional)
  meta_lead_id       Meta Lead Ads leadgen ID, 15-17 digits (optional)
  email, phone
  stage              CRM stage name, e.g. New, Contacted, Qualified, Site Visit, Won
  stage_updated_at   when the lead entered this stage (ISO 8601 or "YYYY-MM-DD HH:MM:SS")
  value              deal / lead value (optional)

Stage map (JSON file, --map). Keys are CRM stage names (matched
case-insensitively). "meta" is the event_name sent to Meta (use null to skip),
"google" is the Google Ads conversion action name (null to skip):
  {
    "New":       {"meta": "Lead",       "google": null},
    "Qualified": {"meta": "Qualified",  "google": "CRM - Qualified Lead"},
    "Won":       {"meta": "Won",        "google": "CRM - Won", "value": true}
  }
"value": true sends the row value with that stage to Google (and to Meta with --meta-value).

Outputs (in --out-dir, default current directory):
  meta_crm_events.jsonl     one Meta CRM event per line; wrap in {"data": [...]} when POSTing
  google_ads_offline.csv    rows with a gclid and a mapped Google conversion
  summary.txt               counts per stage, match key coverage, skipped rows

Usage:
  python3 stage_mapper.py crm_export.csv --map stage_map.json --crm-name "LeadSquared" --out-dir out/
  python3 stage_mapper.py crm_export.csv --map stage_map.json --currency INR --tz-offset +05:30

Standard library only. Python 3.8+.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

DEFAULT_MAP = {
    "New": {"meta": "Lead", "google": None},
    "Contacted": {"meta": "Contacted", "google": None},
    "Qualified": {"meta": "Qualified", "google": "CRM - Qualified Lead"},
    "Meeting/Site visit": {"meta": "Meeting", "google": "CRM - Meeting"},
    "Won": {"meta": "Won", "google": "CRM - Won", "value": True},
}


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def norm_email(v):
    v = (v or "").strip().lower()
    return v if re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", v) else None


def norm_phone(v, cc):
    d = re.sub(r"\D", "", v or "").lstrip("0")
    if not d:
        return None
    if cc == "91" and len(d) == 10 and d[0] in "6789":
        d = "91" + d
    elif cc and len(d) <= 10 and not d.startswith(cc):
        d = cc + d
    return d if 8 <= len(d) <= 15 else None


def parse_tz(s):
    m = re.match(r"^([+-])(\d{2}):?(\d{2})$", s)
    if not m:
        raise SystemExit(f"bad --tz-offset '{s}', use like +05:30")
    sign = 1 if m.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


def parse_dt(s, tz):
    s = (s or "").strip()
    if not s:
        return None
    if re.match(r"^\d{10}$", s):
        return datetime.fromtimestamp(int(s), tz)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def google_time(dt, tz):
    local = dt.astimezone(tz)
    off = local.strftime("%z")  # +0530
    return local.strftime("%Y-%m-%d %H:%M:%S") + off


def load_map(path):
    if not path:
        return DEFAULT_MAP
    with open(path, encoding="utf-8") as fh:
        m = json.load(fh)
    if not isinstance(m, dict) or not m:
        raise SystemExit("stage map must be a JSON object of stage -> {meta, google}")
    return m


def main():
    ap = argparse.ArgumentParser(description="CRM stages -> Meta CRM events + Google Ads offline conversions")
    ap.add_argument("file", help="CRM export CSV")
    ap.add_argument("--map", help="stage map JSON (default: built-in New/Contacted/Qualified/Meeting/Won map)")
    ap.add_argument("--crm-name", default="CRM", help="value for custom_data.lead_event_source, e.g. HubSpot, Zoho CRM")
    ap.add_argument("--currency", default="INR", help="currency for values, default INR")
    ap.add_argument("--tz-offset", default="+05:30", help="timezone for naive timestamps and Google times, default +05:30")
    ap.add_argument("--country-code", default="91", help="phone country code for bare numbers, default 91")
    ap.add_argument("--meta-value", action="store_true", help="also send value/currency to Meta on stages with value: true")
    ap.add_argument("--meta-scope", choices=["all", "meta"], default="all",
                    help="'meta' sends to Meta only rows with a meta_lead_id, fbclid, or a source containing "
                         "meta/facebook/instagram; 'all' (default) sends every mapped row with a match key")
    ap.add_argument("--out-dir", default=".", help="output folder")
    args = ap.parse_args()

    tz = parse_tz(args.tz_offset)
    stage_map = {k.strip().lower(): v for k, v in load_map(args.map).items()}
    os.makedirs(args.out_dir, exist_ok=True)

    with open(args.file, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in reader]

    now = time.time()
    meta_events, google_rows = [], []
    stage_counts = Counter()
    meta_by_stage, google_by_stage = Counter(), Counter()
    issues = defaultdict(list)
    keys_cov = Counter()
    seen_meta_ids = set()

    for i, r in enumerate(rows, 2):  # row 1 is the header
        lid = r.get("lead_id") or f"row{i}"
        stage = r.get("stage", "")
        stage_counts[stage or "(blank)"] += 1
        m = stage_map.get(stage.lower())
        if m is None:
            issues["unmapped_stage"].append(f"{lid} ({stage or 'blank'})")
            continue
        dt = parse_dt(r.get("stage_updated_at"), tz)
        if dt is None:
            issues["bad_or_missing_stage_updated_at"].append(lid)
            continue

        meta_lead_id = re.sub(r"\D", "", r.get("meta_lead_id", ""))
        gclid = r.get("gclid", "")
        fbclid = r.get("fbclid", "")
        em = norm_email(r.get("email"))
        ph = norm_phone(r.get("phone"), args.country_code)
        if r.get("email") and not em:
            issues["invalid_email"].append(lid)
        if r.get("phone") and not ph:
            issues["invalid_phone"].append(lid)
        for k, present in (("meta_lead_id", meta_lead_id), ("gclid", gclid), ("fbclid", fbclid), ("email", em), ("phone", ph)):
            if present:
                keys_cov[k] += 1
        if not any([meta_lead_id, gclid, fbclid, em, ph]):
            issues["no_match_key_at_all"].append(lid)
            continue
        if "meta" in (r.get("source", "").lower()) and "form" in r.get("source", "").lower() and not meta_lead_id:
            issues["meta_form_lead_without_meta_lead_id"].append(lid)

        value = None
        if r.get("value"):
            try:
                value = round(float(r["value"].replace(",", "")), 2)
            except ValueError:
                issues["bad_value"].append(lid)

        # Meta CRM event.
        meta_name = m.get("meta")
        src = r.get("source", "").lower()
        is_meta_row = bool(meta_lead_id or fbclid or re.search(r"meta|facebook|instagram|\bfb\b|\big\b", src))
        if meta_name and args.meta_scope == "meta" and not is_meta_row:
            meta_name = None
        if meta_name:
            ud = {}
            if meta_lead_id:
                if not 15 <= len(meta_lead_id) <= 17:
                    issues["meta_lead_id_unexpected_length"].append(lid)
                ud["lead_id"] = int(meta_lead_id)
            if em:
                ud["em"] = [sha256(em)]
            if ph:
                ud["ph"] = [sha256(ph)]
            if fbclid and not meta_lead_id:
                # Click time is unknown here; stage time is a fallback. Store fbc at landing if you can.
                ud["fbc"] = f"fb.1.{int(dt.timestamp() * 1000)}.{fbclid}"
            if ud:
                ev = {
                    "event_name": meta_name,
                    "event_time": int(dt.timestamp()),
                    "action_source": "system_generated",
                    "event_id": f"{lid}_{re.sub(r'[^a-z0-9]+', '_', meta_name.lower())}",
                    "custom_data": {"event_source": "crm", "lead_event_source": args.crm_name},
                    "user_data": ud,
                }
                if args.meta_value and m.get("value") and value is not None:
                    ev["custom_data"]["value"] = value
                    ev["custom_data"]["currency"] = args.currency
                if ev["event_id"] in seen_meta_ids:
                    issues["duplicate_lead_stage_rows"].append(lid)
                    continue
                seen_meta_ids.add(ev["event_id"])
                if now - dt.timestamp() > 7 * 86400:
                    issues["meta_event_older_than_7_days (may be rejected, check current Meta docs)"].append(lid)
                meta_events.append(ev)
                meta_by_stage[meta_name] += 1

        # Google Ads offline conversion.
        g_name = m.get("google")
        if g_name:
            if gclid:
                row = {
                    "Google Click ID": gclid,
                    "Conversion Name": g_name,
                    "Conversion Time": google_time(dt, tz),
                    "Conversion Value": f"{value:.2f}" if (m.get("value") and value is not None) else "",
                    "Conversion Currency": args.currency if (m.get("value") and value is not None) else "",
                }
                google_rows.append(row)
                google_by_stage[g_name] += 1
                if now - dt.timestamp() > 90 * 86400:
                    issues["google_conversion_older_than_90_days (likely rejected)"].append(lid)
            elif "google" in r.get("source", "").lower():
                issues["google_lead_without_gclid"].append(lid)

    meta_path = os.path.join(args.out_dir, "meta_crm_events.jsonl")
    with open(meta_path, "w", encoding="utf-8") as fh:
        for ev in meta_events:
            fh.write(json.dumps(ev) + "\n")

    g_path = os.path.join(args.out_dir, "google_ads_offline.csv")
    with open(g_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["Google Click ID", "Conversion Name", "Conversion Time",
                                           "Conversion Value", "Conversion Currency"])
        w.writeheader()
        w.writerows(google_rows)

    total = len(rows)
    lines = [f"CRM feedback summary: {total} rows from {os.path.basename(args.file)}", "",
             "Rows per CRM stage:"]
    for s, n in stage_counts.most_common():
        mapped = stage_map.get(s.lower(), {})
        lines.append(f"  {s:<22}{n:>5}   -> Meta: {mapped.get('meta') or '-'} | Google: {mapped.get('google') or '-'}")
    lines += ["", f"Meta events written: {len(meta_events)} ({meta_path})"]
    lines += [f"  {k}: {v}" for k, v in meta_by_stage.most_common()]
    lines += [f"Google Ads rows written: {len(google_rows)} ({g_path})"]
    lines += [f"  {k}: {v}" for k, v in google_by_stage.most_common()]
    lines += ["", "Match key coverage (mapped rows with a valid date):"]
    lines += [f"  {k}: {keys_cov[k]}" for k in ("meta_lead_id", "gclid", "fbclid", "email", "phone")]
    lines += ["", "Issues:"]
    if not issues:
        lines.append("  none")
    for k, ids in issues.items():
        sample = ", ".join(ids[:8]) + (" ..." if len(ids) > 8 else "")
        lines.append(f"  {k}: {len(ids)} [{sample}]")
    lines += ["", "Next: send meta_crm_events.jsonl in batches as {\"data\": [...]} to the dataset /events endpoint; "
                  "upload google_ads_offline.csv in Google Ads (Goals > Conversions > Uploads; check the current menu). "
                  "Field names follow Meta's conversion leads docs at the time of writing; check current Meta docs."]
    text = "\n".join(lines)
    with open(os.path.join(args.out_dir, "summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
