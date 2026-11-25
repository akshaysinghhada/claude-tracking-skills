#!/usr/bin/env python3
"""List GTM tags, triggers and variables that break the naming convention and
propose new names and folders.

Usage:
    python3 scripts/naming_report.py container.json > naming-plan.md
    python3 scripts/naming_report.py container.json --csv > naming-plan.csv

Convention (see SKILL.md):
    Tags       <Platform> - <Type> - <Detail>     GA4 - Event - purchase
    Triggers   Trigger - <Code> - <Detail>        Trigger - CE - purchase
    Variables  <Code> - <Detail>                  DLV - ecommerce.value

Standard library only.
"""
import csv
import json
import re
import sys
from collections import Counter

TAG_RE = re.compile(r"^(GA4|GAds|Meta|LinkedIn|TikTok|Clarity|Hotjar|Bing|Snap|Pinterest|"
                    r"Floodlight|HTML|Util|CMP) - [A-Za-z][A-Za-z ]* - \S.*$")
TRIGGER_RE = re.compile(r"^Trigger - (CE|PV|DOM|WL|Click|Link|Form|Hist|Timer|Scroll|Vis|YT|JSErr|"
                        r"Group|Init|Consent) - \S.*$")
VAR_RE = re.compile(r"^(DLV|CONST|CJS|URL|COOKIE|JSV|DOM|AEV|LT|RT|CE|REF|RAND|UPD|GTES|GTCS) - \S.*$")

TRIGGER_CODES = {
    "CUSTOM_EVENT": "CE", "PAGEVIEW": "PV", "DOM_READY": "DOM", "WINDOW_LOADED": "WL",
    "CLICK": "Click", "LINK_CLICK": "Link", "FORM_SUBMISSION": "Form",
    "HISTORY_CHANGE": "Hist", "TIMER": "Timer", "SCROLL_DEPTH": "Scroll",
    "ELEMENT_VISIBILITY": "Vis", "YOU_TUBE_VIDEO": "YT", "JS_ERROR": "JSErr",
    "TRIGGER_GROUP": "Group", "INIT": "Init", "CONSENT_INIT": "Consent",
}
VAR_CODES = {
    "v": "DLV", "c": "CONST", "jsm": "CJS", "u": "URL", "k": "COOKIE", "j": "JSV",
    "d": "DOM", "aev": "AEV", "smm": "LT", "remm": "RT", "e": "CE", "f": "REF",
    "r": "RAND", "awec": "UPD", "gtes": "GTES", "gtcs": "GTCS",
}
FOLDER_BY_PLATFORM = {
    "GA4": "GA4", "GAds": "Google Ads", "Meta": "Meta", "LinkedIn": "LinkedIn",
    "TikTok": "TikTok", "Clarity": "Analytics - Other", "Hotjar": "Analytics - Other",
    "Bing": "Microsoft Ads", "Floodlight": "Floodlight", "HTML": "Custom HTML - review",
    "Util": "Utilities", "CMP": "Consent", "Snap": "Snap", "Pinterest": "Pinterest",
}


def param(obj, key):
    for p in obj.get("parameter", []) or []:
        if p.get("key") == key:
            return p.get("value", "")
    return ""


def clean(text):
    text = re.sub(r"\(copy\)|\bcopy\b|\bold\b|\btest\b|\bnew\b", "", text, flags=re.I)
    text = re.sub(r"[_\-|:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip() or "unnamed"


def custom_event_name(tr):
    for f in tr.get("customEventFilter", []) or []:
        for p in f.get("parameter", []) or []:
            if p.get("key") == "arg1":
                return p.get("value", "")
    return ""


def filter_summary(tr):
    parts = []
    for f in tr.get("filter", []) or []:
        a0 = a1 = ""
        for p in f.get("parameter", []) or []:
            if p.get("key") == "arg0":
                a0 = p.get("value", "").strip("{}")
            elif p.get("key") == "arg1":
                a1 = p.get("value", "")
        if a1:
            parts.append(a1.strip("/") or a0)
    return " ".join(parts)


def propose_tag(t, templates):
    ttype, name = t.get("type", ""), t.get("name", "")
    if ttype == "googtag":
        tid = param(t, "tagId")
        plat = "GAds" if tid.startswith("AW-") else "GA4"
        return "%s - Google Tag - %s" % (plat, "All Pages" if "{{" in tid or not tid else tid)
    if ttype == "gaawe":
        return "GA4 - Event - %s" % (param(t, "eventName") or clean(name))
    if ttype == "awct":
        return "GAds - Conversion - %s" % clean(re.sub(r"google|ads|adwords|conversion|gads", "", name, flags=re.I))
    if ttype == "sp":
        return "GAds - Remarketing - All Pages"
    if ttype == "gclidw":
        return "GAds - Conversion Linker - All Pages"
    if ttype == "awud":
        return "GAds - User Data - %s" % clean(name)
    if ttype in ("flc", "fls"):
        return "Floodlight - %s - %s" % ("Counter" if ttype == "flc" else "Sales", clean(name))
    if ttype == "bzi":
        return "LinkedIn - Insight - All Pages"
    if ttype == "hjtc":
        return "Hotjar - Tracking - All Pages"
    if ttype == "baut":
        return "Bing - UET - %s" % clean(name)
    if ttype.startswith("cvt_"):
        tmpl = templates.get(ttype.split("_")[-1], "").lower()
        if "facebook" in tmpl or "meta" in tmpl:
            ev = param(t, "standardEventName") or param(t, "customEventName") or clean(name)
            return "Meta - Pixel - %s" % ev
        if "tiktok" in tmpl:
            return "TikTok - Pixel - %s" % clean(name)
        if "clarity" in tmpl:
            return "Clarity - Tracking - All Pages"
        if "linkedin" in tmpl:
            return "LinkedIn - Conversion - %s" % clean(name)
        return "Util - Template - %s" % clean(name)
    if ttype == "html":
        html = param(t, "html")
        m = re.search(r"fbq\(\s*['\"]track(?:Custom)?['\"]\s*,\s*['\"]([A-Za-z_]+)", html)
        if "fbevents.js" in html or "fbq(" in html:
            return "Meta - Pixel HTML - %s" % (m.group(1) if m and "init" not in html else
                                               ("Base" if "init" in html else clean(name)))
        if "ttq." in html:
            return "TikTok - Pixel HTML - %s" % clean(name)
        if "clarity.ms" in html:
            return "Clarity - HTML - All Pages"
        return "HTML - Custom - %s" % clean(name)
    if ttype == "img":
        return "HTML - Image Pixel - %s" % clean(name)
    if ttype in ("ua", "gaawc"):
        return "DELETE - legacy %s - %s" % ("UA" if ttype == "ua" else "GA4 Config", clean(name))
    return "Util - %s - %s" % (ttype, clean(name))


def propose_trigger(tr):
    ttype = tr.get("type", "")
    code = TRIGGER_CODES.get(ttype, ttype.title())
    if ttype == "CUSTOM_EVENT":
        detail = custom_event_name(tr) or clean(tr.get("name", ""))
    elif ttype in ("PAGEVIEW", "DOM_READY", "WINDOW_LOADED") and not tr.get("filter"):
        detail = "All Pages"
    else:
        detail = filter_summary(tr) or clean(tr.get("name", ""))
    return "Trigger - %s - %s" % (code, detail)


def propose_variable(v):
    vtype, name = v.get("type", ""), v.get("name", "")
    code = VAR_CODES.get(vtype, vtype.upper())
    if vtype == "v":
        detail = param(v, "name") or clean(name)
    elif vtype == "k":
        detail = param(v, "name") or clean(name)
    elif vtype == "j":
        detail = param(v, "name") or clean(name)
    elif vtype == "u":
        detail = (param(v, "component") or "URL").lower()
        if param(v, "queryKey"):
            detail = "query " + param(v, "queryKey")
    elif vtype == "c":
        val = param(v, "value")
        if re.match(r"^G-", val):
            detail = "GA4 Measurement ID"
        elif re.match(r"^AW-", val):
            detail = "Google Ads ID"
        elif re.fullmatch(r"\d{14,17}", val):
            detail = "Meta Pixel ID"
        else:
            detail = clean(re.sub(r"\bconst(ant)?\b", "", name, flags=re.I))
    else:
        detail = clean(re.sub(r"\b(js|dlv|lookup|regex|cookie|const)\b", "", name, flags=re.I))
    return "%s - %s" % (code, detail)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_csv = "--csv" in sys.argv
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    try:
        with open(args[0], encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit("Could not read JSON: %s" % e)
    cv = data.get("containerVersion", data)
    templates = {t.get("templateId"): t.get("name", "") for t in cv.get("customTemplate", []) or []}
    folders = {f.get("folderId"): f.get("name", "") for f in cv.get("folder", []) or []}

    rows = []  # kind, current, proposed, folder_now, folder_proposed, ok
    for t in cv.get("tag", []) or []:
        prop = propose_tag(t, templates)
        plat = prop.split(" - ")[0]
        rows.append(["Tag", t.get("name", ""), prop, folders.get(t.get("parentFolderId"), ""),
                     FOLDER_BY_PLATFORM.get(plat, "Legacy - to delete" if plat == "DELETE" else "Utilities"),
                     bool(TAG_RE.match(t.get("name", ""))), t.get("paused", False)])
    for tr in cv.get("trigger", []) or []:
        rows.append(["Trigger", tr.get("name", ""), propose_trigger(tr),
                     folders.get(tr.get("parentFolderId"), ""), "Triggers",
                     bool(TRIGGER_RE.match(tr.get("name", ""))), False])
    for v in cv.get("variable", []) or []:
        rows.append(["Variable", v.get("name", ""), propose_variable(v),
                     folders.get(v.get("parentFolderId"), ""), "Variables",
                     bool(VAR_RE.match(v.get("name", ""))), False])

    # names that match the pattern but carry leftovers like "(copy)" still fail
    junk = re.compile(r"\(copy\)|\bcopy\b|\btest\b|\bold\b|\btemp\b", re.I)
    for r in rows:
        if r[5] and junk.search(r[1]):
            r[5] = False

    # make proposed names unique per kind; compliant names keep priority
    seen = Counter()
    for r in sorted(rows, key=lambda x: not x[5]):
        if r[5]:
            r[2] = r[1]
        key = (r[0], r[2].lower())
        seen[key] += 1
        if seen[key] > 1:
            r[2] = "%s (%d)" % (r[2], seen[key])
    collisions = [r for r in rows if re.search(r" \(\d+\)$", r[2])]

    bad = [r for r in rows if not r[5]]
    if as_csv:
        w = csv.writer(sys.stdout)
        w.writerow(["kind", "current_name", "proposed_name", "current_folder", "proposed_folder", "paused"])
        for r in bad:
            w.writerow([r[0], r[1], r[2], r[3], r[4], "yes" if r[6] else ""])
        return

    total = len(rows)
    print("# GTM naming report")
    print("")
    print("- Items checked: %d (tags %d, triggers %d, variables %d)" % (
        total, sum(r[0] == "Tag" for r in rows), sum(r[0] == "Trigger" for r in rows),
        sum(r[0] == "Variable" for r in rows)))
    print("- Breaking the convention: %d" % len(bad))
    print("- Existing folders: %s" % (", ".join(sorted(set(folders.values()))) or "none"))
    print("")
    for kind in ("Tag", "Trigger", "Variable"):
        items = [r for r in bad if r[0] == kind]
        print("## %ss to rename (%d)" % (kind, len(items)))
        print("")
        if not items:
            print("All follow the convention.")
            print("")
            continue
        print("| Current name | Proposed name | Current folder | Proposed folder |")
        print("|---|---|---|---|")
        for r in items:
            note = " (paused)" if r[6] else ""
            print("| %s%s | %s | %s | %s |" % (r[1].replace("|", "\\|"), note, r[2].replace("|", "\\|"),
                                              r[3] or "-", r[4]))
        print("")
    if collisions:
        print("## Name collisions")
        print("")
        print("These proposed names clashed with another item and got a number. "
              "A clash between two tags usually means a duplicate tag - check before renaming.")
        print("")
        for r in collisions:
            print("- %s: %s -> %s" % (r[0], r[1], r[2]))
        print("")
    print("_Proposed names are a starting point. Detail parts come from event names, "
          "dataLayer keys and trigger filters; edit them where the meaning is unclear._")


if __name__ == "__main__":
    main()
