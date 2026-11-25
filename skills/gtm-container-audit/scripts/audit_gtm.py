#!/usr/bin/env python3
"""Audit a Google Tag Manager web container export (Admin > Export Container).

Usage:
    python3 scripts/audit_gtm.py container.json > gtm-audit.md

Standard library only. Prints a markdown report to stdout.
"""
import json
import re
import sys
from collections import defaultdict

ALL_PAGES_ID = "2147479553"          # built-in "All Pages" trigger
BUILT_IN_TRIGGERS = {
    "2147479553": "All Pages (built-in)",
    "2147479572": "Consent Initialization - All Pages (built-in)",
    "2147479573": "Initialization - All Pages (built-in)",
}
PAGE_LEVEL_TYPES = {"PAGEVIEW", "DOM_READY", "WINDOW_LOADED"}

TAG_TYPE_NAMES = {
    "googtag": "Google Tag",
    "gaawe": "GA4 Event",
    "gaawc": "GA4 Configuration (legacy)",
    "ua": "Universal Analytics (retired)",
    "awct": "Google Ads Conversion",
    "sp": "Google Ads Remarketing",
    "gclidw": "Conversion Linker",
    "awcc": "Google Ads Calls from Website",
    "awud": "Google Ads User-Provided Data",
    "flc": "Floodlight Counter",
    "fls": "Floodlight Sales",
    "html": "Custom HTML",
    "img": "Custom Image",
    "bzi": "LinkedIn Insight",
    "hjtc": "Hotjar",
    "baut": "Microsoft Ads UET",
}
GOOGLE_TAG_TYPES = {"googtag", "gaawe", "gaawc", "ua", "awct", "sp", "gclidw",
                    "awcc", "awud", "flc", "fls"}
CONVERSION_EVENTS = {"purchase", "generate_lead", "sign_up", "begin_checkout",
                     "add_payment_info", "close_convert_lead", "qualify_lead"}
CONVERSION_NAME_RE = re.compile(
    r"purchase|conversion|convert|lead|thank|order|sign.?up|registration|checkout",
    re.I)

ID_PATTERNS = [
    ("GA4 / Google tag ID", re.compile(r"\bG-[A-Z0-9]{6,12}\b")),
    ("Google Ads ID", re.compile(r"\bAW-\d{6,12}\b")),
    ("GTM container ID", re.compile(r"\bGTM-[A-Z0-9]{4,10}\b")),
    ("Meta pixel ID", re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{10,20})['\"]")),
    ("TikTok pixel ID", re.compile(r"ttq\.load\(\s*['\"]([A-Z0-9]{15,25})['\"]")),
    ("LinkedIn partner ID", re.compile(r"_linkedin_partner_id\s*=\s*['\"]?(\d{4,10})")),
]
# parameter keys whose plain value is an ID even without a prefix
ID_PARAM_KEYS = {
    "conversionid": "Google Ads conversion ID",
    "pixelid": "Pixel ID", "pixelids": "Pixel ID",
    "partnerid": "LinkedIn partner ID",
    "tagid": "Google tag ID",
    "measurementid": "GA4 measurement ID",
    "measurementidoverride": "GA4 measurement ID",
}

NATIVE_TEMPLATE_HINTS = [
    (re.compile(r"connect\.facebook\.net/[^'\"]*fbevents\.js|fbq\(", re.I),
     "Meta Pixel code - use the Facebook Pixel gallery template (or one tag type, not both)"),
    (re.compile(r"googletagmanager\.com/gtag/js|gtag\(\s*['\"]config", re.I),
     "gtag.js code - use the native Google Tag / GA4 Event / Google Ads tags"),
    (re.compile(r"analytics\.tiktok\.com|ttq\.", re.I),
     "TikTok Pixel code - a gallery template exists"),
    (re.compile(r"snap\.licdn\.com|_linkedin_partner_id", re.I),
     "LinkedIn Insight code - native LinkedIn Insight tag exists"),
    (re.compile(r"clarity\.ms", re.I), "Microsoft Clarity code - a gallery template exists"),
    (re.compile(r"static\.hotjar\.com", re.I), "Hotjar code - native Hotjar tag exists"),
    (re.compile(r"bat\.bing\.com", re.I), "Microsoft UET code - native UET tag exists"),
    (re.compile(r"googletagmanager\.com/gtm\.js", re.I),
     "A second GTM container loaded from inside this container"),
]
VAR_REF_RE = re.compile(r"\{\{([^{}]+)\}\}")


def walk_values(params, out, key_path=""):
    """Collect (key, value) string pairs from GTM parameter structures."""
    if isinstance(params, list):
        for p in params:
            walk_values(p, out, key_path)
    elif isinstance(params, dict):
        key = params.get("key", key_path)
        if "value" in params and isinstance(params["value"], str):
            out.append((key, params["value"]))
        for sub in ("list", "map"):
            if sub in params:
                walk_values(params[sub], out, key)


def tag_values(tag):
    vals = []
    walk_values(tag.get("parameter", []), vals)
    return vals


def param(tag, key):
    for p in tag.get("parameter", []):
        if p.get("key") == key:
            return p.get("value", "")
    return ""


def type_label(t, templates):
    if t.startswith("cvt_"):
        tid = t.split("_")[-1]
        return "Custom template: " + templates.get(tid, t)
    return TAG_TYPE_NAMES.get(t, t)


def md_escape(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit("Could not read JSON: %s" % e)

    cv = data.get("containerVersion", data)
    tags = cv.get("tag", []) or []
    triggers = cv.get("trigger", []) or []
    variables = cv.get("variable", []) or []
    folders = cv.get("folder", []) or []
    templates = {t.get("templateId"): t.get("name", "") for t in cv.get("customTemplate", []) or []}
    container = cv.get("container", {})

    trig_by_id = {t.get("triggerId"): t for t in triggers}
    trig_name = dict(BUILT_IN_TRIGGERS)
    trig_name.update({t.get("triggerId"): t.get("name", "") for t in triggers})

    findings = defaultdict(list)   # severity -> list of strings for the summary

    # ---------- references ----------
    used_trigger_ids = set()
    for t in tags:
        used_trigger_ids.update(t.get("firingTriggerId", []) or [])
        used_trigger_ids.update(t.get("blockingTriggerId", []) or [])
    for tr in triggers:  # trigger groups reference other triggers
        stack = list(tr.get("parameter", []) or [])
        while stack:
            p = stack.pop()
            if p.get("type") == "triggerReference":
                used_trigger_ids.add(p.get("value"))
            stack.extend(p.get("list", []) or [])
            stack.extend(p.get("map", []) or [])

    sequenced_tags = set()
    for t in tags:
        for k in ("setupTag", "teardownTag"):
            for s in t.get(k, []) or []:
                sequenced_tags.add(s.get("tagName"))

    referenced_vars = set()
    for obj in tags + triggers:
        referenced_vars.update(VAR_REF_RE.findall(json.dumps(obj)))
    var_refs_from_vars = defaultdict(set)
    for v in variables:
        for r in VAR_REF_RE.findall(json.dumps(v.get("parameter", []))):
            var_refs_from_vars[r].add(v.get("name"))
    # a variable used only by an unused variable is still counted as used here;
    # the report notes this.
    referenced_by_vars = set(var_refs_from_vars)

    # ---------- per-tag analysis ----------
    paused, no_trigger, all_pages_conv, html_tags = [], [], [], []
    consent_rows, hardcoded = [], []
    dup_keys = defaultdict(list)

    const_values = {}
    for v in variables:
        if v.get("type") == "c":
            const_values.setdefault(param(v, "value").strip(), []).append(v.get("name"))

    const_by_name = {v.get("name"): param(v, "value").strip()
                     for v in variables if v.get("type") == "c"}

    def resolve(val):
        """Replace {{Constant}} references with their value for comparison."""
        return VAR_REF_RE.sub(lambda m: const_by_name.get(m.group(1), m.group(0)), val or "")

    platform_events = defaultdict(list)   # (platform, event) -> tags

    def is_all_pages(tid):
        if tid == ALL_PAGES_ID:
            return True
        tr = trig_by_id.get(tid)
        return bool(tr) and tr.get("type") in PAGE_LEVEL_TYPES and not tr.get("filter")

    for t in tags:
        name, ttype = t.get("name", ""), t.get("type", "")
        vals = tag_values(t)
        blob = "\n".join(v for _, v in vals)
        firing = t.get("firingTriggerId", []) or []

        if t.get("paused"):
            paused.append(t)
        if not firing and name not in sequenced_tags:
            no_trigger.append(t)

        # hardcoded IDs
        found = set()
        for key, val in vals:
            if VAR_REF_RE.fullmatch(val.strip() or "x"):
                continue
            for label, rx in ID_PATTERNS:
                for m in rx.finditer(val):
                    found.add((label, m.group(1) if rx.groups else m.group(0)))
            kl = key.lower()
            if kl in ID_PARAM_KEYS and val.strip() and "{{" not in val:
                for piece in re.split(r"[,\s]+", val.strip()):
                    if piece:
                        found.add((ID_PARAM_KEYS[kl], piece))
        seen_ids = set()
        for label, ident in sorted(found):
            if ident in seen_ids:
                continue
            seen_ids.add(ident)
            consts = const_values.get(ident)
            if consts:
                note = "Constant exists: {{%s}} - replace the hardcoded value" % consts[0]
            else:
                note = "No constant variable - create one"
            hardcoded.append((name, label, ident, note))

        # duplicate detection key
        dkey = None
        if ttype == "googtag":
            dkey = (ttype, param(t, "tagId"))
        elif ttype == "gaawe":
            dkey = (ttype, param(t, "measurementIdOverride") or param(t, "measurementId"),
                    param(t, "eventName"))
        elif ttype == "awct":
            dkey = (ttype, param(t, "conversionId"), param(t, "conversionLabel"))
        elif ttype == "sp":
            dkey = (ttype, param(t, "conversionId"))
        elif ttype.startswith("cvt_"):
            dkey = (ttype, param(t, "pixelIds") or param(t, "pixelId"),
                    param(t, "standardEventName") or param(t, "eventName"))
        if dkey and any(dkey[1:]):
            dkey = tuple(resolve(x) for x in dkey)
            dup_keys[dkey].append(t)

        # same platform event sent by several active tags (any tag type)
        if not t.get("paused") and firing:
            if ttype == "gaawe" and param(t, "eventName"):
                platform_events[("GA4", param(t, "eventName"))].append(t)
            if ttype == "awct":
                platform_events[("Google Ads", resolve(param(t, "conversionLabel")))].append(t)
            evs = set(re.findall(r"fbq\(\s*['\"]track(?:Custom)?['\"]\s*,\s*['\"]([A-Za-z_]+)", blob))
            if ttype.startswith("cvt_") and "facebook" in templates.get(ttype.split("_")[-1], "").lower():
                ev = param(t, "standardEventName") or param(t, "customEventName") or param(t, "eventName")
                if ev:
                    evs.add(ev)
            for ev in evs:
                platform_events[("Meta", ev)].append(t)

        # conversion-looking tag on all pages
        conv = (ttype in ("awct", "fls")
                or (ttype == "gaawe" and param(t, "eventName") in CONVERSION_EVENTS)
                or re.search(r"fbq\(\s*['\"]track['\"]\s*,\s*['\"](Purchase|Lead|CompleteRegistration|Subscribe|StartTrial)", blob)
                or (ttype.startswith("cvt_") and re.search(r"Purchase|Lead|CompleteRegistration", blob))
                or (ttype not in ("googtag", "gclidw") and CONVERSION_NAME_RE.search(name)))
        ap = [x for x in firing if is_all_pages(x)]
        if conv and ap:
            all_pages_conv.append((t, ", ".join(trig_name.get(x, x) for x in ap)))

        # custom HTML
        if ttype == "html":
            html = param(t, "html")
            flags = []
            if "document.write" in html:
                flags.append("uses document.write")
            if param(t, "supportDocumentWrite") == "true":
                flags.append("'Support document.write' enabled")
            for rx, msg in NATIVE_TEMPLATE_HINTS:
                if rx.search(html):
                    flags.append(msg)
            html_tags.append((t, flags))

        # consent
        cs = (t.get("consentSettings") or {}).get("consentStatus", "NOT_SET")
        if cs == "NOT_SET":
            consent_rows.append((t, ttype in GOOGLE_TAG_TYPES))

    duplicates = [(k, v) for k, v in dup_keys.items() if len(v) > 1]
    multi_event = [(k, v) for k, v in platform_events.items() if len(v) > 1]
    unused_triggers = [tr for tr in triggers if tr.get("triggerId") not in used_trigger_ids]
    unused_vars = [v for v in variables
                   if v.get("name") not in referenced_vars and v.get("name") not in referenced_by_vars]
    var_only_by_vars = [v for v in variables
                        if v.get("name") not in referenced_vars and v.get("name") in referenced_by_vars]

    # ---------- summary findings ----------
    for k, v in duplicates:
        findings["High"].append("Duplicate %s tags: %s" % (
            type_label(k[0], templates), ", ".join(x["name"] for x in v)))
    for k, v in multi_event:
        findings["High"].append("%s event '%s' sent by %d active tags: %s" % (
            k[0], k[1], len(v), ", ".join(x["name"] for x in v)))
    for t, trg in all_pages_conv:
        findings["High"].append("Conversion-type tag fires on all pages: %s (%s)" % (t["name"], trg))
    for t, flags in html_tags:
        if any("document.write" in f for f in flags):
            findings["Medium"].append("Custom HTML uses document.write: %s" % t["name"])
        if any("template" in f or "native" in f or "second GTM" in f for f in flags):
            findings["Medium"].append("Custom HTML duplicates a native/gallery tag: %s" % t["name"])
    non_google_consent = [t for t, g in consent_rows if not g]
    if non_google_consent:
        findings["Medium"].append("%d non-Google tag(s) with no consent settings" % len(non_google_consent))
    if hardcoded:
        findings["Medium"].append("%d hardcoded ID(s) in tags" % len(hardcoded))
    if no_trigger:
        findings["Low"].append("%d tag(s) with no firing trigger" % len(no_trigger))
    if paused:
        findings["Low"].append("%d paused tag(s)" % len(paused))
    if unused_triggers:
        findings["Low"].append("%d unused trigger(s)" % len(unused_triggers))
    if unused_vars:
        findings["Low"].append("%d unused variable(s)" % len(unused_vars))
    legacy = [t for t in tags if t.get("type") in ("ua", "gaawc")]
    if legacy:
        findings["Medium"].append("Legacy tag types present (UA / GA4 Configuration): %s" %
                                  ", ".join(t["name"] for t in legacy))

    # ---------- output ----------
    out = []
    w = out.append
    w("# GTM Container Audit: %s" % (container.get("name") or "container"))
    w("")
    w("- Public ID: %s" % container.get("publicId", "n/a"))
    w("- Export time: %s" % data.get("exportTime", "n/a"))
    w("- Tags: %d | Triggers: %d | Variables: %d | Folders: %d | Custom templates: %d"
      % (len(tags), len(triggers), len(variables), len(folders), len(templates)))
    w("")
    w("## Summary")
    w("")
    if not any(findings.values()):
        w("No issues found by the automated checks.")
    for sev in ("High", "Medium", "Low"):
        for f in findings.get(sev, []):
            w("- **%s** - %s" % (sev, f))
    w("")

    w("## Tag inventory by type")
    w("")
    w("| Type | Count |")
    w("|---|---|")
    counts = defaultdict(int)
    for t in tags:
        counts[type_label(t.get("type", ""), templates)] += 1
    for k in sorted(counts, key=lambda x: -counts[x]):
        w("| %s | %d |" % (md_escape(k), counts[k]))
    w("")

    def section(title, rows, header, empty="None found."):
        w("## " + title)
        w("")
        if not rows:
            w(empty)
        else:
            w("| " + " | ".join(header) + " |")
            w("|" + "---|" * len(header))
            for r in rows:
                w("| " + " | ".join(md_escape(c) for c in r) + " |")
        w("")

    section("Duplicate tags (same type + same ID)",
            [(type_label(k[0], templates), " / ".join(x for x in k[1:] if x),
              ", ".join(x["name"] for x in v)) for k, v in duplicates],
            ["Type", "ID / event", "Tags"])
    section("Same event sent by more than one active tag",
            [(k[0], k[1], ", ".join(x["name"] for x in v),
              " / ".join(sorted({", ".join(trig_name.get(i, i) for i in x.get("firingTriggerId", [])) for x in v})))
             for k, v in multi_event],
            ["Platform", "Event / label", "Tags", "Triggers"],
            empty="None found. (A GA4 event sent to two different properties on purpose will also show here.)")
    section("Conversion-type tags firing on all pages",
            [(t["name"], type_label(t["type"], templates), trg) for t, trg in all_pages_conv],
            ["Tag", "Type", "Trigger"])
    section("Hardcoded IDs in tags", hardcoded, ["Tag", "ID type", "Value", "Note"])
    section("Custom HTML tags",
            [(t["name"], "yes" if t.get("paused") else "no",
              ", ".join(trig_name.get(x, x) for x in t.get("firingTriggerId", []) or []) or "none",
              "; ".join(fl) or "-") for t, fl in html_tags],
            ["Tag", "Paused", "Triggers", "Flags"])
    section("Tags with no consent settings (consentStatus NOT_SET or missing)",
            [(t["name"], type_label(t["type"], templates),
              "Google tag - has built-in consent checks if Consent Mode is set up; verify" if g
              else "Set 'Require additional consent' (e.g. ad_storage / analytics_storage) or confirm your CMP blocks it")
             for t, g in consent_rows],
            ["Tag", "Type", "Action"])
    section("Paused tags",
            [(t["name"], type_label(t["type"], templates)) for t in paused],
            ["Tag", "Type"])
    section("Tags with no firing trigger",
            [(t["name"], type_label(t["type"], templates)) for t in no_trigger],
            ["Tag", "Type"])
    section("Unused triggers",
            [(tr.get("name"), tr.get("type")) for tr in unused_triggers],
            ["Trigger", "Type"])
    section("Unused variables",
            [(v.get("name"), v.get("type")) for v in unused_vars],
            ["Variable", "Type code"])
    if var_only_by_vars:
        section("Variables only referenced by other variables (check the parent is used)",
                [(v.get("name"), ", ".join(sorted(var_refs_from_vars[v.get("name")])))
                 for v in var_only_by_vars],
                ["Variable", "Referenced by"])
    w("_Notes: built-in variables are not listed in exports and are not checked. "
      "Tags fired only through tag sequencing are not counted as orphaned. "
      "Duplicate detection for GA4 Event tags uses measurement ID + event name._")
    print("\n".join(out))


if __name__ == "__main__":
    main()
