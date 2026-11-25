#!/usr/bin/env python3
"""UTM hygiene checker and builder (python3 stdlib only).

Check a list of URLs:
    python3 utm_check.py check urls.csv
    python3 utm_check.py check urls.txt --report report.csv

Build one tagged URL:
    python3 utm_check.py build --url https://demo-store.in/sale \
        --source facebook --medium paid_social --campaign "Diwali Sale 2026"

The channel prediction is an approximation of GA4's default channel group.
It uses a partial list of social / search / video sources. Google publishes the
full source lists in the GA4 help center; check there when a source is marked
"verify".
"""

import argparse
import csv
import re
import sys
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote_plus

UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "utm_id"]

PAID_RE = re.compile(r"^(.*cp.*|ppc|retargeting|paid.*)$")
SHOP_CAMPAIGN_RE = re.compile(r"^(.*(([^a-df-z]|^)shop|shopping).*)$")
VIDEO_MEDIUM_RE = re.compile(r"^(.*video.*)$")

# Sources we are confident appear in Google's lists.
SOCIAL_SOURCES = {
    "facebook", "facebook.com", "m.facebook.com", "l.facebook.com", "lm.facebook.com",
    "instagram", "instagram.com", "l.instagram.com",
    "linkedin", "linkedin.com", "lnkd.in",
    "twitter", "twitter.com", "t.co",
    "pinterest", "pinterest.com", "reddit", "reddit.com", "quora", "quora.com",
}
# Plausible but not verified here: treat as social with a "verify" note.
SOCIAL_SOURCES_VERIFY = {"fb", "ig", "x", "x.com", "whatsapp", "whatsapp.com", "snapchat",
                         "tiktok", "tiktok.com", "threads", "threads.net", "meta", "an", "msg"}
SEARCH_SOURCES = {"google", "google.com", "bing", "bing.com", "yahoo", "yahoo.com",
                  "baidu", "baidu.com", "yandex", "yandex.ru", "duckduckgo", "duckduckgo.com"}
SEARCH_SOURCES_VERIFY = {"ecosia", "ecosia.org", "naver", "naver.com", "seznam"}
VIDEO_SOURCES = {"youtube", "youtube.com", "m.youtube.com", "vimeo", "vimeo.com"}

SOCIAL_MEDIUMS = {"social", "social-network", "social-media", "sm", "social network", "social media"}
EMAIL_VALUES = {"email", "e-mail", "e_mail", "e mail"}
REFERRAL_MEDIUMS = {"referral", "app", "link"}
DISPLAY_MEDIUMS = {"display", "banner", "expandable", "interstitial", "cpm"}

PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|\{[a-z_]+\}")
ALLOWED_CHARS_RE = re.compile(r"^[a-z0-9_\-.|]+$")

# Common wrong mediums and what to use instead.
MEDIUM_FIXES = {
    # wrong medium: (suggested medium or None, explanation)
    "ads": ("cpc", "cpc for search, paid_social for social"),
    "ad": ("cpc", "cpc for search, paid_social for social"),
    "facebook": ("paid_social", "paid_social (or social if organic), and put facebook in utm_source"),
    "instagram": ("paid_social", "paid_social (or social if organic), and put instagram in utm_source"),
    "meta": ("paid_social", "paid_social, with utm_source=facebook or instagram"),
    "newsletter": ("email", "email"),
    "mail": ("email", "email"),
    "edm": ("email", "email"),
    "whatsapp": ("social", "social for organic shares; for paid broadcasts use a custom channel group"),
    "influencer": ("affiliate", "affiliate for paid creators, social for organic"),
    "qr": ("referral", "referral, or a custom channel group for offline"),
    "offline": ("referral", "referral, or a custom channel group for offline"),
    "story": ("social", "social, or paid_social if paid"),
    "reel": ("social", "social, or paid_social if paid"),
    "post": ("social", "social"),
}


def norm_source_key(src):
    s = src.lower().strip()
    if s.startswith("www."):
        s = s[4:]
    return s


def predict_channel(source, medium, campaign):
    """Return (channel, note) using an approximation of GA4 default channel group order."""
    s = norm_source_key(source or "")
    m = (medium or "").lower().strip()
    c = (campaign or "").lower().strip()
    note = ""
    social_sure = s in SOCIAL_SOURCES
    social_maybe = s in SOCIAL_SOURCES_VERIFY
    search_sure = s in SEARCH_SOURCES
    search_maybe = s in SEARCH_SOURCES_VERIFY
    is_social = social_sure or social_maybe
    is_search = search_sure or search_maybe
    if social_maybe or search_maybe:
        note = f"verify '{s}' is in Google's current source list"
    paid = bool(PAID_RE.match(m))

    if s == "(direct)" and m in ("(none)", "(not set)"):
        return "Direct", ""
    if "cross-network" in c:
        return "Cross-network", "campaign name contains 'cross-network'"
    if SHOP_CAMPAIGN_RE.match(c) and paid:
        return "Paid Shopping", "campaign name matches GA4 'shop/shopping' rule"
    if is_search and paid:
        return "Paid Search", note
    if is_social and paid:
        return "Paid Social", note
    if s in VIDEO_SOURCES and paid:
        return "Paid Video", ""
    if m in DISPLAY_MEDIUMS:
        return "Display", ""
    if paid:
        return "Paid Other", "paid medium but source not in social/search/video list"
    if SHOP_CAMPAIGN_RE.match(c):
        return "Organic Shopping", "campaign name matches GA4 'shop/shopping' rule"
    if is_social or m in SOCIAL_MEDIUMS:
        return "Organic Social", note
    if s in VIDEO_SOURCES or VIDEO_MEDIUM_RE.match(m):
        return "Organic Video", ""
    if is_search or m == "organic":
        return "Organic Search", note
    if m in REFERRAL_MEDIUMS:
        return "Referral", ""
    if s in EMAIL_VALUES or m in EMAIL_VALUES:
        return "Email", ""
    if m == "affiliate":
        return "Affiliates", ""
    if m == "audio":
        return "Audio", ""
    if s == "sms" or m == "sms":
        return "SMS", ""
    if m.endswith("push") or "mobile" in m or "notification" in m or s == "firebase":
        return "Mobile Push Notifications", ""
    return "Unassigned", ""


def clean_value(v, sep="-"):
    v = v.strip().lower()
    v = re.sub(r"[\s+]+", sep, v)
    v = re.sub(r"[^a-z0-9_\-.|{}]", "", v)
    v = re.sub(r"-{2,}", "-", v)
    return v.strip("-")


def read_urls(path):
    urls = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    lines = text.splitlines()
    if path.lower().endswith(".csv"):
        reader = csv.reader(lines)
        rows = list(reader)
        if not rows:
            return urls
        header = [h.strip().lower() for h in rows[0]]
        col = None
        for name in ("url", "final url", "final_url", "landing page", "landing_page", "link", "website url"):
            if name in header:
                col = header.index(name)
                break
        start = 1
        if col is None:
            # no header match: find first column with http in first row
            start = 0
            for i, cell in enumerate(rows[0]):
                if "http" in cell.lower() or "?" in cell:
                    col = i
                    break
            if col is None:
                col, start = 0, 1
        for r in rows[start:]:
            if len(r) > col and r[col].strip():
                urls.append(r[col].strip())
    else:
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def check_url(url):
    issues = []   # (level, message)
    fixes = {}
    parts = urlsplit(url)
    if not parts.scheme:
        issues.append(("WARN", "no http/https scheme"))
    raw_pairs = parse_qsl(parts.query, keep_blank_values=True)
    pairs = [(k, v) for k, v in raw_pairs]
    utm = {}
    for k, v in pairs:
        kl = k.lower()
        if kl.startswith("utm_"):
            if k != kl:
                issues.append(("ERROR", f"parameter name '{k}' is not lowercase; GA4 expects '{kl}'"))
            if kl in utm:
                issues.append(("ERROR", f"'{kl}' appears more than once"))
            utm[kl] = v
    has_gclid = any(k.lower() == "gclid" for k, _ in pairs)
    has_fbclid = any(k.lower() == "fbclid" for k, _ in pairs)
    if "#" in url and parts.fragment and "utm_" in parts.fragment:
        issues.append(("ERROR", "UTMs are after '#', GA4 will not read them; move them before the fragment"))

    if not utm:
        if has_gclid:
            issues.append(("INFO", "no UTMs, gclid present: fine for Google Ads with auto-tagging and GA4 linked"))
        else:
            issues.append(("ERROR", "no UTM parameters"))
        return utm, issues, fixes, "n/a" if not has_gclid else "google / cpc (auto-tagging)", ""

    for key in ("utm_source", "utm_medium"):
        if not utm.get(key, "").strip():
            issues.append(("ERROR", f"missing {key}"))
    if not utm.get("utm_campaign", "").strip():
        issues.append(("WARN", "missing utm_campaign"))

    for key in UTM_KEYS:
        if key not in utm:
            continue
        val = utm[key]
        has_ph = bool(PLACEHOLDER_RE.search(val))
        if val != val.strip():
            issues.append(("WARN", f"{key} has leading/trailing whitespace"))
        if has_ph:
            static = PLACEHOLDER_RE.sub("", val)
        else:
            static = val
        if static != static.lower():
            issues.append(("WARN", f"{key}='{val}' has uppercase; GA4 reports will split it from the lowercase version"))
            fixes[key] = clean_value(val, "_" if key == "utm_medium" else "-")
        if re.search(r"\s", static):
            issues.append(("WARN", f"{key}='{val}' contains spaces; use - or _"))
            fixes[key] = clean_value(val, "_" if key == "utm_medium" else "-")
        elif static and not ALLOWED_CHARS_RE.match(static.lower().strip()):
            issues.append(("INFO", f"{key}='{val}' has characters outside a-z 0-9 _ - . |"))
            fixes.setdefault(key, clean_value(val))
        if has_ph:
            issues.append(("INFO", f"{key} uses a dynamic placeholder; final value comes from the ad platform, keep campaign/ad set/ad names lowercase without spaces"))

    src = utm.get("utm_source", "")
    med = utm.get("utm_medium", "")
    camp = utm.get("utm_campaign", "")
    src_ph = bool(PLACEHOLDER_RE.search(src))
    med_ph = bool(PLACEHOLDER_RE.search(med))
    if src_ph and "site_source_name" in src:
        src_eval = "fb"
    else:
        src_eval = unquote_plus(src)
    channel, note = ("unknown (dynamic medium)", "") if med_ph else predict_channel(src_eval, unquote_plus(med), unquote_plus(camp))
    if src_ph and "site_source_name" in src:
        note = ("{{site_source_name}} resolves to fb, ig, msg or an; confirm in GA4 these land in Paid Social, "
                "or use a static utm_source=facebook / instagram")

    ml = med.lower().strip()
    if channel == "Unassigned":
        value, hint = MEDIUM_FIXES.get(ml, (None, None))
        issues.append(("ERROR", f"medium '{med}' with source '{src}' will land in Unassigned"
                       + (f"; use {hint}" if hint else "; use a medium GA4 maps (cpc, paid_social, social, email, referral, affiliate)")))
        if value:
            fixes["utm_medium"] = value
    elif channel == "Paid Other":
        issues.append(("WARN", "lands in Paid Other: source is not in GA4's social/search/video lists; use a known source (facebook, instagram, google, linkedin) or a custom channel group"))
    elif channel in ("Paid Shopping", "Organic Shopping") and norm_source_key(src_eval) in SOCIAL_SOURCES | SOCIAL_SOURCES_VERIFY:
        issues.append(("WARN", f"social source but campaign name triggers {channel}; remove 'shop'/'shopping' from utm_campaign if you want Paid/Organic Social"))
    if channel == "Organic Social" and ml not in SOCIAL_MEDIUMS:
        issues.append(("WARN", f"medium '{med}' counts as Organic Social only because the source is a social site; "
                       "if this is a paid ad use utm_medium=paid_social, if organic use utm_medium=social"))
    if channel == "Paid Social" and norm_source_key(src_eval) in SOCIAL_SOURCES_VERIFY and not src_ph:
        issues.append(("WARN", f"source '{src}' is not a confirmed match in this script's list; utm_source=facebook or instagram is a safe match"))
    if ml in ("cpc", "ppc") and norm_source_key(src_eval) in SOCIAL_SOURCES:
        issues.append(("INFO", "cpc on a social source maps to Paid Social, but keep one convention (paid_social or cpc) across the account"))
    if has_gclid and utm:
        issues.append(("INFO", "gclid and UTMs on the same URL: with GA4 linked to Google Ads, gclid already sets google / cpc; manual UTMs are not needed"))
    if has_fbclid:
        issues.append(("INFO", "fbclid present: this is a click URL copied from a browser, not a template"))
    return utm, issues, fixes, channel, note


def build_fixed_url(url, fixes):
    if not fixes:
        return ""
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    out = []
    for k, v in pairs:
        kl = k.lower()
        if kl in fixes:
            out.append((kl, fixes[kl]))
        elif kl.startswith("utm_"):
            out.append((kl, v))
        else:
            out.append((k, v))
    q = urlencode(out, safe="{}|")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, q, parts.fragment))


def cmd_check(args):
    urls = read_urls(args.file)
    if not urls:
        print("No URLs found.")
        return 1
    totals = {"ERROR": 0, "WARN": 0, "INFO": 0}
    channels = {}
    report_rows = []
    for i, url in enumerate(urls, 1):
        utm, issues, fixes, channel, note = check_url(url)
        channels[channel] = channels.get(channel, 0) + 1
        for lvl, _ in issues:
            totals[lvl] += 1
        fixed = build_fixed_url(url, fixes)
        print(f"[{i}] {url}")
        print(f"    source={utm.get('utm_source','-')} medium={utm.get('utm_medium','-')} campaign={utm.get('utm_campaign','-')}")
        print(f"    predicted GA4 channel: {channel}" + (f"  ({note})" if note else ""))
        for lvl, msg in issues:
            print(f"    {lvl:5} {msg}")
        if fixed and fixed != url:
            print(f"    suggested: {fixed}")
        print()
        report_rows.append({
            "row": i, "url": url,
            "utm_source": utm.get("utm_source", ""), "utm_medium": utm.get("utm_medium", ""),
            "utm_campaign": utm.get("utm_campaign", ""), "predicted_channel": channel,
            "errors": sum(1 for l, _ in issues if l == "ERROR"),
            "warnings": sum(1 for l, _ in issues if l == "WARN"),
            "issues": " | ".join(f"{l}: {m}" for l, m in issues),
            "suggested_url": fixed if fixed != url else "",
        })
    print("Summary")
    print(f"  URLs checked: {len(urls)}")
    print(f"  Errors: {totals['ERROR']}  Warnings: {totals['WARN']}  Info: {totals['INFO']}")
    print("  Predicted channels: " + ", ".join(f"{k}={v}" for k, v in sorted(channels.items())))
    if args.report:
        with open(args.report, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
            w.writeheader()
            w.writerows(report_rows)
        print(f"  Report written: {args.report}")
    return 0


def cmd_build(args):
    vals = {
        "utm_source": args.source, "utm_medium": args.medium, "utm_campaign": args.campaign,
        "utm_content": args.content, "utm_term": args.term, "utm_id": args.id,
    }
    parts = urlsplit(args.url)
    existing = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    out = list(existing)
    for k in UTM_KEYS:
        v = vals.get(k)
        if v:
            out.append((k, v if PLACEHOLDER_RE.search(v) and args.keep_placeholders else clean_value(v)))
    q = urlencode(out, safe="{}|")
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, q, parts.fragment))
    utm, issues, _, channel, note = check_url(url)
    print(url)
    print(f"predicted GA4 channel: {channel}" + (f"  ({note})" if note else ""))
    for lvl, msg in issues:
        if lvl != "INFO" or "placeholder" not in msg:
            print(f"{lvl:5} {msg}")
    return 0


def main():
    p = argparse.ArgumentParser(description="UTM checker and builder")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check a CSV or TXT of URLs")
    c.add_argument("file")
    c.add_argument("--report", help="write a CSV report to this path")
    b = sub.add_parser("build", help="build one tagged URL")
    b.add_argument("--url", required=True)
    b.add_argument("--source", required=True)
    b.add_argument("--medium", required=True)
    b.add_argument("--campaign", required=True)
    b.add_argument("--content")
    b.add_argument("--term")
    b.add_argument("--id")
    b.add_argument("--keep-placeholders", action="store_true", default=True,
                   help="keep {{...}} placeholders as-is (default on)")
    args = p.parse_args()
    return cmd_check(args) if args.cmd == "check" else cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
