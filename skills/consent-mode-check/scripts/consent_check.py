#!/usr/bin/env python3
"""
consent_check.py - scan an exported Google Tag Manager container JSON for
Consent Mode v2 setup problems.

Export the container: GTM > Admin > Export Container > choose the live
(published) version or the workspace > Export. You get a .json file.

Checks:
  1. Is there a consent default source? (CMP template tag, a template that
     calls setDefaultConsentState, or Custom HTML with gtag('consent','default'))
  2. Does the consent default fire on Consent Initialization (the earliest stage)?
  3. Does the default cover all four v2 keys (ad_storage, analytics_storage,
     ad_user_data, ad_personalization)?
  4. Non-Google tags (Meta pixel, LinkedIn, TikTok, other Custom HTML) with no
     consent settings ("Additional consent checks" not configured).
  5. Google tags and Meta pixel tags that fire before or at the same stage as
     the consent default, or with no consent default at all.
  6. Paused tags are ignored.

Usage:
  python3 consent_check.py GTM-XXXXXXX_workspace.json
  python3 consent_check.py container.json --json findings.json

Standard library only. Python 3.8+.
"""
import argparse
import json
import re
import sys

# Built-in trigger IDs used in GTM exports.
BUILTIN_TRIGGERS = {
    "2147479572": ("Consent Initialization - All Pages", 0),
    "2147479573": ("Initialization - All Pages", 1),
    "2147479553": ("All Pages", 2),
}
# Stage order for trigger types (lower fires earlier).
TRIGGER_TYPE_STAGE = {
    "consentInit": 0, "consentinit": 0,
    "init": 1, "initialization": 1,
    "pageview": 2,
    "domReady": 3, "windowLoaded": 4,
}
STAGE_NAMES = {0: "Consent Initialization", 1: "Initialization", 2: "Page View",
               3: "DOM Ready", 4: "Window Loaded", 5: "Event/other"}

GOOGLE_TYPES = {
    "googtag": "Google tag", "gaawc": "GA4 config (legacy)", "gaawe": "GA4 event",
    "awct": "Google Ads conversion", "sp": "Google Ads remarketing", "gclidw": "Conversion Linker",
    "awcc": "Google Ads calls from website", "awud": "Google Ads user-provided data",
    "flc": "Floodlight counter", "fls": "Floodlight sales", "ua": "Universal Analytics",
}
V2_KEYS = ["ad_storage", "analytics_storage", "ad_user_data", "ad_personalization"]
CMP_HINTS = re.compile(r"cookiebot|onetrust|cookieyes|usercentrics|didomi|complianz|iubenda|termly|"
                       r"osano|quantcast|trustarc|consentmanager|cookie ?consent|consent mode|cmp\b",
                       re.I)
META_HINTS = re.compile(r"fbq\(|connect\.facebook\.net|fbevents\.js|facebook pixel|meta pixel", re.I)
VENDOR_HINTS = [
    ("LinkedIn Insight", re.compile(r"snap\.licdn\.com|_linkedin_partner_id|linkedin insight", re.I)),
    ("TikTok pixel", re.compile(r"analytics\.tiktok\.com|ttq\.|tiktok pixel", re.I)),
    ("Microsoft Clarity", re.compile(r"clarity\.ms|microsoft clarity", re.I)),
    ("Hotjar", re.compile(r"hotjar", re.I)),
    ("Microsoft UET", re.compile(r"bat\.bing\.com|uetq", re.I)),
]
CONSENT_DEFAULT_HTML = re.compile(r"""gtag\(\s*['"]consent['"]\s*,\s*['"]default['"]""", re.I)


def param(tag, key):
    for p in tag.get("parameter", []) or []:
        if p.get("key") == key:
            return p.get("value", "")
    return ""


def tag_text(tag, templates):
    """Searchable text for a tag: name, HTML, and its template name/code."""
    parts = [tag.get("name", ""), param(tag, "html")]
    tpl = templates.get(template_id_for(tag))
    if tpl:
        parts += [tpl.get("name", ""), tpl.get("templateData", "")]
    return "\n".join(parts)


def template_id_for(tag):
    t = tag.get("type", "")
    if t.startswith("cvt_"):
        return t.split("_")[-1]
    return None


def consent_status(tag):
    cs = tag.get("consentSettings") or {}
    status = cs.get("consentStatus", "notSet")
    types = []
    ct = cs.get("consentType") or {}
    for item in ct.get("list", []) or []:
        if item.get("value"):
            types.append(item["value"])
    return status, types


def stage_of(trigger_ids, triggers):
    """Earliest stage among the tag's firing triggers."""
    best = 5
    for tid in trigger_ids or []:
        tid = str(tid)
        if tid in BUILTIN_TRIGGERS:
            best = min(best, BUILTIN_TRIGGERS[tid][1])
            continue
        trg = triggers.get(tid)
        if trg:
            best = min(best, TRIGGER_TYPE_STAGE.get(trg.get("type", ""), 5))
    return best


def trigger_names(trigger_ids, triggers):
    out = []
    for tid in trigger_ids or []:
        tid = str(tid)
        if tid in BUILTIN_TRIGGERS:
            out.append(BUILTIN_TRIGGERS[tid][0])
        elif tid in triggers:
            out.append(triggers[tid].get("name", tid))
        else:
            out.append(f"trigger {tid}")
    return out


def classify(tag, templates):
    t = tag.get("type", "")
    text = tag_text(tag, templates)
    tpl = templates.get(template_id_for(tag)) or {}
    tpl_data = tpl.get("templateData", "")
    if "setDefaultConsentState" in tpl_data or (t == "html" and CONSENT_DEFAULT_HTML.search(text)):
        return "consent_default", "Consent default"
    if CMP_HINTS.search(tag.get("name", "") + " " + tpl.get("name", "")):
        return "cmp", "CMP / consent tag"
    if t in GOOGLE_TYPES:
        return "google", GOOGLE_TYPES[t]
    if META_HINTS.search(text):
        return "meta", "Meta pixel"
    for label, rx in VENDOR_HINTS:
        if rx.search(text):
            return "third_party", label
    if t == "html":
        return "third_party", "Custom HTML"
    if t == "img":
        return "third_party", "Custom Image"
    if t.startswith("cvt_"):
        return "third_party", f"Template: {tpl.get('name', t)}"
    return "other", t


def main():
    ap = argparse.ArgumentParser(description="Consent Mode v2 check for an exported GTM container")
    ap.add_argument("file", help="exported GTM container JSON")
    ap.add_argument("--json", metavar="OUT", help="write findings as JSON")
    args = ap.parse_args()

    with open(args.file, encoding="utf-8") as fh:
        data = json.load(fh)
    cv = data.get("containerVersion", data)
    container = cv.get("container", {})
    tags = cv.get("tag", []) or []
    triggers = {str(t.get("triggerId")): t for t in cv.get("trigger", []) or []}
    templates = {str(t.get("templateId")): t for t in cv.get("customTemplate", []) or []}

    findings = []  # (severity, message)
    rows = []

    active = [t for t in tags if not t.get("paused")]
    paused = len(tags) - len(active)

    defaults = []
    for tag in active:
        kind, label = classify(tag, templates)
        stage = stage_of(tag.get("firingTriggerId"), triggers)
        status, types = consent_status(tag)
        rows.append({"name": tag.get("name"), "type": tag.get("type"), "kind": kind, "label": label,
                     "stage": STAGE_NAMES[stage], "stage_num": stage,
                     "triggers": trigger_names(tag.get("firingTriggerId"), triggers),
                     "consent_status": status, "consent_types": types})
        if kind in ("consent_default", "cmp"):
            defaults.append((tag, kind, stage))

    # 1-3: consent default presence, timing, keys.
    true_defaults = [d for d in defaults if d[1] == "consent_default"]
    cmp_only = [d for d in defaults if d[1] == "cmp"]
    default_stage = None
    if not defaults:
        findings.append(("HIGH", "No consent default found (no CMP template, no setDefaultConsentState template, "
                                 "no Custom HTML gtag('consent','default')). Consent may be set in page code; "
                                 "confirm in Tag Assistant, otherwise add a CMP template on Consent Initialization."))
    else:
        use = true_defaults or cmp_only
        default_stage = min(d[2] for d in use)
        names = ", ".join(d[0].get("name", "?") for d in use)
        if not true_defaults:
            findings.append(("MEDIUM", f"CMP-like tag(s) found ({names}) but could not confirm they set a consent "
                                       "default. Check the template or CMP settings for Consent Mode."))
        if default_stage != 0:
            findings.append(("HIGH", f"Consent default ({names}) fires on {STAGE_NAMES[default_stage]}, not "
                                     "Consent Initialization. Move it to 'Consent Initialization - All Pages'."))
        else:
            findings.append(("OK", f"Consent default ({names}) fires on Consent Initialization."))
        for tag, kind, _ in true_defaults:
            text = tag_text(tag, templates)
            missing = [k for k in V2_KEYS if k not in text]
            if tag.get("type") == "html" and missing:
                findings.append(("HIGH", f"'{tag.get('name')}' default does not mention {', '.join(missing)}. "
                                         "Consent Mode v2 needs all four keys."))
            elif tag.get("type", "").startswith("cvt_") and missing:
                findings.append(("MEDIUM", f"Template for '{tag.get('name')}' does not reference {', '.join(missing)}. "
                                           "Update the CMP template to a v2-ready version and verify in Tag Assistant."))
            if tag.get("type") == "html" and "wait_for_update" not in text:
                findings.append(("LOW", f"'{tag.get('name')}' has no wait_for_update. Add it if your CMP loads "
                                        "asynchronously (for example wait_for_update: 500)."))

    # 4-5: per-tag checks.
    for r in rows:
        if r["kind"] in ("consent_default", "cmp", "other"):
            continue
        where = f"'{r['name']}' ({r['label']}, fires on {', '.join(r['triggers']) or 'no trigger'})"
        no_settings = r["consent_status"] in ("notSet", None) or (
            r["consent_status"] == "needed" and not r["consent_types"])
        if r["kind"] in ("meta", "third_party"):
            if no_settings:
                findings.append(("HIGH" if r["kind"] == "meta" else "MEDIUM",
                                 f"{where} has no additional consent checks. Set Consent Settings > Require "
                                 "additional consent (ad_storage for ads pixels, analytics_storage for analytics), "
                                 "or block it with a consent-based trigger."))
            elif r["consent_status"] == "notNeeded":
                findings.append(("LOW", f"{where} is marked 'No additional consent required'. Confirm that is intended."))
        if r["kind"] in ("google", "meta"):
            if default_stage is None:
                findings.append(("HIGH", f"{where} can fire with no consent default in GTM."))
            elif r["stage_num"] <= default_stage:
                if default_stage == 0:
                    fix = "Only consent default/CMP tags belong on Consent Initialization; move this tag later."
                elif r["stage_num"] < default_stage:
                    fix = "Move the consent default to Consent Initialization so it always runs first."
                else:
                    fix = ("Firing order within the same stage is not guaranteed. Move the consent default to "
                           "Consent Initialization so it always runs first.")
                findings.append(("HIGH", f"{where} fires at {r['stage']}, before or alongside the consent "
                                         f"default ({STAGE_NAMES[default_stage]}). {fix}"))
        if r["kind"] == "google" and r["consent_status"] == "notNeeded":
            findings.append(("LOW", f"{where} is set to 'No additional consent required'. Fine for Google tags, "
                                    "which have built-in consent checks."))

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "OK": 3}
    findings.sort(key=lambda f: order[f[0]])

    cid = container.get("publicId", "unknown container")
    print(f"Consent Mode check: {cid} ({len(active)} active tags, {paused} paused ignored, "
          f"{len(triggers)} custom triggers, {len(templates)} custom templates)")
    print()
    print(f"{'tag':<38}{'kind':<24}{'first stage':<24}{'consent settings'}")
    print("-" * 110)
    for r in sorted(rows, key=lambda r: (r["stage_num"], r["name"] or "")):
        cs = r["consent_status"] + (f" ({', '.join(r['consent_types'])})" if r["consent_types"] else "")
        print(f"{(r['name'] or '')[:36]:<38}{r['label'][:22]:<24}{r['stage']:<24}{cs}")
    print()
    counts = {k: sum(1 for f in findings if f[0] == k) for k in order}
    print(f"Findings: {counts['HIGH']} high, {counts['MEDIUM']} medium, {counts['LOW']} low")
    for sev, msg in findings:
        print(f"  [{sev}] {msg}")
    print()
    print("Next: run the browser checklist in SKILL.md (Tag Assistant > Consent tab) to confirm "
          "what actually happens on the live site.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"container": cid, "tags": rows,
                       "findings": [{"severity": s, "message": m} for s, m in findings]}, fh, indent=2)
        print(f"JSON written to {args.json}")


if __name__ == "__main__":
    main()
