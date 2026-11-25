---
name: gtm-container-audit
description: Audits an exported Google Tag Manager web container (JSON from Admin > Export Container) and returns a prioritised fix list - duplicate tags, conversion tags firing on every page, hardcoded IDs, risky Custom HTML, missing consent settings and dead triggers or variables. Use when someone says "audit my GTM", "check my tag manager container", "why are my conversions doubled", "clean up GTM" or uploads a GTM export JSON.
---

# GTM Container Audit

Turns a GTM container export into a ranked list of problems with a fix for each. The script does the mechanical checks; Claude adds judgement (which duplicates are real, what to fix first, what to ask the user).

## What it needs

1. **The container export (required).** In GTM: Admin > Container > Export Container > choose the published version (or the current workspace if that is what you want audited) > Export. You get a `.json` file. Ask the user which one they exported, because unpublished workspace changes are not live.
2. **Context (ask if not given):**
   - Business type: ecommerce, lead gen or SaaS, and the main conversion (purchase, lead form, WhatsApp click, call).
   - Platforms they advertise on (Meta, Google Ads, LinkedIn, others).
   - Whether a consent banner / CMP is used and if Consent Mode is set up.
   - Whether there is a server-side container or Meta CAPI running (affects dedup advice).
3. Optional: a screenshot of GTM Preview (Tag Assistant) on the thank-you page, to confirm what fires.

The export contains IDs (pixel, conversion, measurement) but no personal data. Still, tell the user to remove anything sensitive in Custom HTML (API keys) before sharing.

## Steps Claude follows

1. Save the uploaded file and run:
   ```
   python3 scripts/audit_gtm.py <container.json> > gtm-audit.md
   ```
   The script is Python 3 standard library only. It accepts the full export (`containerVersion` wrapper) or a bare container version object.
2. Read the script output. Do not paste it raw. Confirm each High item by looking at the relevant tag in the JSON (triggers, exceptions, tag sequencing) before calling it a bug.
3. Judge the duplicates:
   - Two GA4 Event tags with the same event name and same measurement ID on the same trigger = real double counting.
   - Same event to two different GA4 properties = probably intentional, ask.
   - A Custom HTML Meta tag and a Meta template tag sending the same event = double counting in Meta unless both carry the same `eventID` (and even then it is wasteful). Recommend keeping one.
4. Judge "conversion tags on all pages": a Google Ads conversion or Meta Purchase on All Pages inflates conversions and breaks bidding. Fix is a Custom Event trigger on the dataLayer event (for example `purchase`) or a thank-you page trigger with a filter. Some tags named "lead" are only remarketing; check the tag type before flagging.
5. Check consent: non-Google tags (Custom HTML, Meta, TikTok, LinkedIn, Clarity) with no consent settings will fire before consent unless the CMP blocks them another way. Google tags have built-in consent checks when Consent Mode is implemented, so ask whether it is.
6. Write the report using the template below, ordered by impact on ad optimisation and reporting, not by section order.
7. Offer next steps: a rename plan (see the `gtm-naming-cleanup` skill) and a dataLayer spec if events come from fragile triggers like CSS-selector clicks.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Counts | Tags / triggers / variables / folders in header | Large counts with no folders usually mean no ownership; plan a cleanup |
| Paused tags | `"paused": true` | Delete if not needed in the last few months, or document why paused |
| Tags with no firing trigger | No `firingTriggerId` and not used as a setup/teardown tag | Delete, or attach the intended trigger |
| Unused triggers | Trigger ID not referenced by any tag or trigger group | Delete |
| Unused variables | `{{Name}}` not referenced in any tag, trigger or variable | Delete (built-in variables are not checked) |
| Hardcoded IDs | `G-`, `AW-`, `GTM-`, Meta `fbq('init')`, TikTok, LinkedIn IDs, Ads conversion ID typed directly into tags | Create a Constant variable (or use the existing one the script names) and reference it |
| Duplicate tags | Same tag type + same ID (constants resolved), GA4 adds event name, Ads adds label | Keep one, pause the other, publish, then delete after checking reports |
| Same event from several tags | Same GA4 event name, Ads label or Meta event in more than one active tag | Keep one tag per platform event; if browser + server both send Meta events, share one `event_id` |
| Conversion tag on all pages | Ads conversion, GA4 key event, Meta Purchase/Lead fired by All Pages or an unfiltered Page View / DOM Ready / Window Loaded trigger | Move to a Custom Event or filtered thank-you trigger; add a once-per-order guard |
| Custom HTML with document.write | `document.write` in code or "Support document.write" enabled | Rewrite with a native tag or Custom Image tag; document.write can block page rendering |
| Custom HTML duplicating a native tag | fbevents.js, gtag.js, TikTok, LinkedIn, Clarity, Hotjar, UET or a second gtm.js inside Custom HTML | Replace with the native tag or gallery template so consent and IDs are managed in one place |
| Consent settings missing | `consentSettings.consentStatus` is `NOT_SET` or missing | For non-Google tags set "Require additional consent" with the right consent types, or confirm the CMP blocks them |
| Legacy tags | Type `ua` (Universal Analytics) or `gaawc` (old GA4 Configuration) | Delete UA tags; GA4 Configuration tags are migrated to Google Tag in GTM, check in your container |

## Output format

```
# GTM audit - <container name> (<GTM-ID>), <date>

## Verdict
<2-3 sentences: is conversion data trustworthy for bidding right now, and the single biggest problem>

## Fix first (High)
| # | Problem | Tags involved | Impact | Fix | Effort |
|---|---|---|---|---|---|

## Fix next (Medium)
| # | Problem | Tags involved | Fix |
|---|---|---|---|

## Cleanup (Low)
- Paused tags to delete: ...
- Orphan tags: ...
- Unused triggers: ...
- Unused variables: ...

## Questions for you
- <only things the export cannot answer, e.g. "Is the GA4 tag to G-XXXX a second property on purpose?">

## After you fix
1. Preview in GTM, place a test order / lead, check each conversion fires once.
2. Publish with a version name and notes.
3. Watch platform conversion counts for a few days against backend numbers.
```

Keep the report under two screens. Group repeated items (for example "7 hardcoded IDs") instead of listing each in prose; the script tables can go in an appendix if the user wants them.

## Limits

- Sees configuration only, not what actually fires. A tag can look fine and still fail (wrong dataLayer key, blocked by CMP). Confirm with GTM Preview.
- Cannot see code on the website itself: hardcoded gtag.js or Meta pixel in the theme, Shopify/WooCommerce plugins, or server-side containers can create duplicates the export will not show.
- Gallery template parameter names vary by template author; the Meta event detection is tuned to the common Facebook Pixel template, check others manually.
- Variables used only by other unused variables are listed separately, not as unused.
- Web containers only. Server, AMP and app containers use different tag types.
- "Conversion-like" detection uses tag type, event names and tag name keywords; expect a few false positives.
