---
name: consent-mode-check
description: Audits Google Consent Mode v2 (ad_storage, analytics_storage, ad_user_data, ad_personalization) in a GTM container and on the live site, checks that defaults are set before tags fire and updates happen on the user's choice, and flags Meta pixel and other tags with no consent gating. Use when someone says "check my consent mode", "is consent mode v2 set up", "CMP not working with GTM", "tags firing before consent", or asks about consent for EEA/UK or India DPDP.
---

# Consent Mode Check

Finds where consent is missing, late or incomplete: in the GTM container (script) and in the browser (manual checklist). Output is a ranked fix list.

## What it needs

1. **GTM container export**: GTM > Admin > Export Container > pick the published version (or the workspace you plan to publish) > Export. Save the .json file.
2. **The site URL** and a page with a conversion (thank-you page or form).
3. **The CMP in use** (Cookiebot, OneTrust, CookieYes, Usercentrics, Complianz, custom banner, or none) and whether it is loaded through GTM or hardcoded.
4. **Audience regions**: EEA/UK traffic, India only, or global. This decides how strict the defaults must be.
5. **Mode intended**: basic or advanced (see below). If unsure, Claude explains and the user decides with their legal/privacy owner.

## Key facts

- Consent Mode v2 has four main keys: `ad_storage`, `analytics_storage`, `ad_user_data`, `ad_personalization`. Each is `granted` or `denied`.
- **Default** must be set before any Google tag reads it: in GTM, a CMP template or consent tag on the **Consent Initialization - All Pages** trigger, or a `gtag('consent','default',{...})` call above the GTM snippet.
- **Update** is sent when the user makes a choice (`gtag('consent','update',{...})` or the CMP template's update call), and on later page loads from the stored choice.
- **Basic mode**: Google tags do not load until the user consents. No data reaches Google before consent.
- **Advanced mode**: Google tags load with denied defaults and send cookieless pings, which Google can use for modeling. Whether this is acceptable is a legal decision, not a tracking one.
- Google tags (Google tag, GA4, Google Ads, Floodlight, Conversion Linker) have **built-in consent checks**. Other tags (Meta pixel, LinkedIn, TikTok, Custom HTML) need **additional consent checks** in GTM or a consent-based trigger.
- For users in the EEA and UK, Google requires consent signals for its ads personalization and measurement features. Check Google's EU user consent policy for current requirements.
- **India**: the Digital Personal Data Protection Act, 2023 requires consent-based processing of personal data, with rules being phased in. Check the current status of the DPDP Rules and get legal advice before deciding defaults for Indian traffic.
- Meta pixel has its own consent API: `fbq('consent','revoke')` before `fbq('init',...)`, then `fbq('consent','grant')` after the user accepts. Or gate the tag in GTM.

## Steps Claude follows

1. Run the container scan:
   ```
   python3 scripts/consent_check.py path/to/GTM-XXXXXXX.json
   python3 scripts/consent_check.py path/to/GTM-XXXXXXX.json --json consent_findings.json
   ```
   Samples: `examples/gtm_container_needs_work.json` (problems) and `examples/gtm_container_ok.json` (clean).
2. Read the tag table (first firing stage and consent settings per tag) and the findings. HIGH items first.
3. Ask whether consent defaults are set in page code outside GTM; the script cannot see that.
4. Walk the user through the browser checklist below and record the results.
5. Combine both into the output template, with the exact GTM change for each fix.
6. After fixes, re-export and re-run the script, then repeat the browser checklist.

## Browser checklist (manual)

Use a fresh incognito window. For region-specific defaults, test from (or VPN to) each region.

1. **Tag Assistant**: open tagassistant.google.com > Add domain > connect. Click the first event in the left list (Consent) and open the **Consent** tab. Check: On-page Default shows all four keys, values match your policy (denied for EEA/UK).
2. Do not touch the banner. Click the Container Loaded / page view events: Google tags should show consent as denied; Meta pixel and other gated tags should be "Not fired".
3. Accept all on the banner. A new Consent event should appear with **On-page Update** = granted for the keys the user accepted. Gated tags should now fire.
4. Reload a page. The stored choice should apply on the Consent Initialization event, before other tags.
5. Reject all in a new incognito window. Update should stay denied; gated tags never fire.
6. **Network tab** (DevTools > Network, filter `collect`): GA4 requests carry `gcs=`. `G100` means ad_storage and analytics_storage denied, `G111` both granted, `G101` analytics only, `G110` ads only. A `gcd=` parameter should also be present.
7. **Cookies** (DevTools > Application > Cookies): before consent, with denied defaults, `_ga`, `_gcl_au` and `_fbp` should not be set. If they are, a tag is not respecting consent.
8. **GTM consent overview**: GTM > Admin > Container Settings > enable "Enable consent overview". Then in Tags, click the shield icon to see tags grouped by consent configuration.
9. Optional: GA4 and Google Ads show consent mode status in their admin/diagnostics screens. Locations change, check current docs.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| No consent default | Script HIGH "No consent default", Tag Assistant shows no On-page Default | Add CMP template (Community Template Gallery) on Consent Initialization - All Pages |
| Default set too late | Script says default fires on Page View/Initialization | Change the CMP/default tag trigger to Consent Initialization - All Pages |
| v1 only (missing ad_user_data, ad_personalization) | Script HIGH, Tag Assistant shows two keys | Update CMP template or add both keys to the default and update calls |
| No update on choice | Tag Assistant has no Consent update after clicking Accept | Fix CMP integration, enable its Google Consent Mode option |
| Meta pixel not gated | Script HIGH on Meta pixel tags; `_fbp` set before consent | Consent Settings > Require additional consent: ad_storage, or use Meta's fbq consent API |
| Other third-party tags not gated | Script MEDIUM on Custom HTML/LinkedIn/TikTok | Add additional consent checks per tag |
| Tags on Consent Initialization | Script HIGH "fires at Consent Initialization" | Keep only CMP/consent tags on that trigger |
| Hardcoded gtag before GTM ignores consent | Page source has gtag config above the default | Put the consent default first, or move the tag into GTM |
| No wait_for_update with async CMP | Script LOW; first hits sent as denied even for returning users | Add `wait_for_update: 500` to the default |
| Region defaults wrong | VPN test shows granted defaults in EEA | Use `region` in the default or the CMP's geo rules |

## Output format

```
CONSENT MODE AUDIT: <site> / <GTM container ID>
CMP: <name / none>   Mode: <basic / advanced / unclear>   Regions: <...>

CONTAINER SCAN (scripts/consent_check.py)
High: <n>  Medium: <n>  Low: <n>
<findings, one line each>

BROWSER CHECKS
| # | Check | Result (Pass/Fail/Not tested) | Evidence |

FIX LIST (in order)
1. <fix> - where in GTM - expected result in Tag Assistant
2. ...

LEGAL NOTES
- EEA/UK: Google consent requirements apply, confirm with current Google policy.
- India: DPDP Act 2023, rules phasing in. Confirm current status with legal counsel.
```

## Limits

- The script reads the GTM export only. It cannot see consent code in the page source, a hardcoded gtag, a CMP loaded outside GTM, or server-side GTM.
- Trigger stage detection uses built-in trigger IDs and trigger types. Unusual setups (tag sequencing, custom event names) may need manual review.
- CMP detection is name-based plus a check for `setDefaultConsentState` in templates. A CMP flagged MEDIUM may still be correct; verify in Tag Assistant.
- This is a technical audit, not legal advice. Consent requirements differ by country and change over time.
