#!/usr/bin/env python3
"""Normalize and SHA-256 hash user data for Google Ads enhanced conversions.

Rules applied (Google's documented normalization for enhanced conversions):
  email       trim, lowercase; for gmail.com / googlemail.com remove dots before the @
  phone       E.164: + country code + number, digits only (e.g. +919876543210)
  first/last  trim, lowercase
  hash        SHA-256, hex, lowercase

Usage:
  python3 normalize_user_data.py --email " Demo.User@GMail.com " --phone "098765 43210"
  python3 normalize_user_data.py --in leads.csv --out leads_hashed.csv
  python3 normalize_user_data.py --in leads.csv --out leads_clean.csv --no-hash
  python3 normalize_user_data.py --in leads.csv --out x.csv --country-code 971

CSV input: columns named email / phone (also e-mail, mobile, phone_number,
contact number) and optional first_name / last_name. Other columns are kept.
"""

import argparse
import csv
import hashlib
import re
import sys

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GOOGLE_EMAIL_DOMAINS = {"gmail.com", "googlemail.com"}

COLS = {
    "email": ["email", "e-mail", "email address", "email_address", "mail"],
    "phone": ["phone", "phone number", "phone_number", "mobile", "mobile number", "contact number", "whatsapp"],
    "first_name": ["first_name", "first name", "firstname", "fname"],
    "last_name": ["last_name", "last name", "lastname", "lname", "surname"],
}


def sha256(v):
    return hashlib.sha256(v.encode("utf-8")).hexdigest() if v else ""


def normalize_email(raw):
    """Return (normalized, warning)."""
    if raw is None:
        return "", ""
    e = raw.strip().lower()
    if not e:
        return "", ""
    if not EMAIL_RE.match(e):
        return "", f"invalid email '{raw.strip()}'"
    local, domain = e.rsplit("@", 1)
    if domain in GOOGLE_EMAIL_DOMAINS:
        local = local.replace(".", "")
    return f"{local}@{domain}", ""


def normalize_phone(raw, country_code="91"):
    """Return (e164, warning). Default country code is India (91)."""
    if raw is None:
        return "", ""
    p = raw.strip()
    if not p:
        return "", ""
    # Excel often turns 919876543210 into 9.19876543210E+11
    if re.match(r"^\d(\.\d+)?[eE]\+\d+$", p):
        return "", f"phone '{p}' is in scientific notation; re-export the column as text"
    has_plus = p.startswith("+")
    digits = re.sub(r"\D", "", p)
    if not digits:
        return "", f"invalid phone '{raw.strip()}'"
    cc = country_code.lstrip("+")
    if has_plus:
        e164 = "+" + digits
    elif digits.startswith("00"):
        e164 = "+" + digits[2:]
    elif cc == "91":
        if len(digits) == 10:
            e164 = "+91" + digits
        elif len(digits) == 11 and digits.startswith("0"):
            e164 = "+91" + digits[1:]
        elif len(digits) == 12 and digits.startswith("91"):
            e164 = "+" + digits
        else:
            return "", f"cannot read Indian phone '{raw.strip()}' ({len(digits)} digits)"
    else:
        local = digits[1:] if digits.startswith("0") else digits
        e164 = "+" + digits if digits.startswith(cc) and len(digits) > 10 else "+" + cc + local
    n = len(e164) - 1
    if n < 8 or n > 15:
        return "", f"phone '{raw.strip()}' is not a valid E.164 length"
    warn = ""
    if e164.startswith("+91") and (len(e164) != 13 or e164[3] not in "6789"):
        warn = f"phone '{raw.strip()}' -> {e164} does not look like an Indian mobile number"
    return e164, warn


def normalize_name(raw):
    return (raw or "").strip().lower()


def find_col(header, key):
    low = [h.strip().lower() for h in header]
    for alias in COLS[key]:
        if alias in low:
            return header[low.index(alias)]
    return None


def process_row(get, country_code, no_hash):
    out = {}
    warnings = []
    email, w = normalize_email(get("email"))
    if w:
        warnings.append(w)
    phone, w = normalize_phone(get("phone"), country_code)
    if w:
        warnings.append(w)
    fn = normalize_name(get("first_name"))
    ln = normalize_name(get("last_name"))
    if no_hash:
        out.update({"email_normalized": email, "phone_e164": phone, "first_name_normalized": fn,
                    "last_name_normalized": ln})
    else:
        out.update({"sha256_email_address": sha256(email), "sha256_phone_number": sha256(phone),
                    "sha256_first_name": sha256(fn), "sha256_last_name": sha256(ln)})
    if not email and not phone:
        warnings.append("no usable email or phone; this row cannot match")
    out["normalize_warnings"] = "; ".join(warnings)
    return out


def main():
    ap = argparse.ArgumentParser(description="Normalize and hash user data for Google enhanced conversions")
    ap.add_argument("--in", dest="infile", help="input CSV")
    ap.add_argument("--out", dest="outfile", help="output CSV (default: print)")
    ap.add_argument("--email")
    ap.add_argument("--phone")
    ap.add_argument("--first-name")
    ap.add_argument("--last-name")
    ap.add_argument("--country-code", default="91", help="default country code for numbers without one (default 91, India)")
    ap.add_argument("--no-hash", action="store_true",
                    help="output normalized plain values (for a GTM user-provided data variable, Google hashes them)")
    ap.add_argument("--drop-pii", action="store_true", help="remove the original email/phone/name columns from the output CSV")
    args = ap.parse_args()

    if not args.infile:
        vals = {"email": args.email, "phone": args.phone, "first_name": args.first_name, "last_name": args.last_name}
        if not any(vals.values()):
            ap.error("give --in FILE or at least --email / --phone")
        res = process_row(lambda k: vals.get(k), args.country_code, args.no_hash)
        for k, v in res.items():
            if v:
                print(f"{k}: {v}")
        if not args.no_hash:
            e, _ = normalize_email(args.email)
            p, _ = normalize_phone(args.phone, args.country_code)
            print(f"(normalized before hashing: email='{e}' phone='{p}')")
        return 0

    with open(args.infile, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        colmap = {k: find_col(header, k) for k in COLS}
        if not colmap["email"] and not colmap["phone"]:
            sys.exit("No email or phone column found. Columns: " + ", ".join(header))
        rows = list(reader)

    pii_cols = {c for c in colmap.values() if c}
    out_rows = []
    stats = {"rows": 0, "email": 0, "phone": 0, "unmatchable": 0, "warnings": 0}
    for r in rows:
        res = process_row(lambda k: r.get(colmap[k]) if colmap[k] else "", args.country_code, args.no_hash)
        base = {k: v for k, v in r.items() if not (args.drop_pii and k in pii_cols)}
        base.update(res)
        out_rows.append(base)
        stats["rows"] += 1
        stats["email"] += 1 if (res.get("sha256_email_address") or res.get("email_normalized")) else 0
        stats["phone"] += 1 if (res.get("sha256_phone_number") or res.get("phone_e164")) else 0
        stats["unmatchable"] += 1 if "cannot match" in res["normalize_warnings"] else 0
        stats["warnings"] += 1 if res["normalize_warnings"] else 0

    fields = list(out_rows[0].keys()) if out_rows else []
    if args.outfile:
        with open(args.outfile, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(out_rows)
    else:
        w = csv.DictWriter(sys.stdout, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    out = sys.stderr if not args.outfile else sys.stdout
    print(f"Rows: {stats['rows']} | with email: {stats['email']} | with phone: {stats['phone']} | "
          f"rows with warnings: {stats['warnings']} | unmatchable: {stats['unmatchable']}", file=out)
    for i, r in enumerate(out_rows, 1):
        if r["normalize_warnings"]:
            print(f"  row {i}: {r['normalize_warnings']}", file=out)
    if args.outfile:
        note = ""
        if not args.drop_pii:
            note = " (original email/phone/name columns kept; add --drop-pii before sharing the file)"
        print(f"Written: {args.outfile}{note}", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
