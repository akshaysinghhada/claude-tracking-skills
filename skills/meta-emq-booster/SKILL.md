---
name: meta-emq-booster
description: Diagnoses and raises Meta Event Match Quality (EMQ) by checking which customer information parameters your pixel and Conversions API events send, how they are normalized and hashed, and what to add first. Use when someone says "my EMQ is low", "improve event match quality", "which user_data should I send to CAPI", "fbc fbp not passing", or shares CAPI payloads for review.
---

# Meta EMQ Booster

Event Match Quality is Meta's score for how well the customer information on an event can be matched to a Meta account. Better matching usually means more attributed conversions and better optimization. This skill finds the missing or broken parameters and gives a ranked fix list.

## What it needs

1. **EMQ per event from Events Manager.** Events Manager > Data sources > select the pixel/dataset > Overview > click an event (for example Purchase) > look for the Event Match Quality score and the list of customer information parameters with their coverage. Screenshot or copy the numbers for Purchase, Lead, InitiateCheckout, AddToCart. Menu labels move around; if a label differs, look for "Event match quality" on the event detail view.
2. **A sample of server event payloads** (20 to 500 events) as JSON lines, one CAPI event or one request body (`{"data":[...]}`) per line. Ways to get them:
   - Log the exact JSON your server POSTs to `/events` for a few hours (strip the access token).
   - Shopify, WooCommerce or a CAPI gateway: use the app's debug or event log export if it has one.
   - Server-side GTM: copy event data from Preview mode for the Meta CAPI tag.
3. **How events are sent today**: browser pixel only, CAPI only, or both (and whether `event_id` is shared for deduplication).
4. Optional: the landing page URL pattern and how the site stores cookies, to check fbclid capture.

## Parameter reference

| Key | Meaning | Hash? | Normalize before hashing |
|---|---|---|---|
| em | email | SHA-256 | trim, lowercase |
| ph | phone | SHA-256 | digits only, include country code, no +, no leading zeros (India: 919812345678) |
| fn / ln | first / last name | SHA-256 | lowercase, no punctuation, UTF-8 |
| ct | city | SHA-256 | lowercase, no spaces or punctuation (jaipur, newdelhi) |
| st | state | SHA-256 | lowercase, no spaces or punctuation; US uses 2-letter code. For India use one consistent form, for example rajasthan, and check current Meta docs |
| zp | postal code | SHA-256 | no spaces or dashes (302001) |
| country | country | SHA-256 | 2-letter ISO code, lowercase (in) |
| external_id | your customer/user ID | SHA-256 recommended | same value on pixel and CAPI |
| client_ip_address | visitor IP | NOT hashed | the visitor's IP, not your server or CDN IP |
| client_user_agent | browser user agent | NOT hashed | full header string captured at event time |
| fbc | click ID cookie | NOT hashed | `fb.1.<timestamp_ms>.<fbclid>` |
| fbp | browser ID cookie | NOT hashed | value of the `_fbp` cookie as set by the pixel |

Hashing is SHA-256 of the normalized UTF-8 string, output as lowercase hex. Values can be sent as a string or an array of strings. Never send a hash of an empty string; omit the key instead.

### fbc and fbclid capture

- When a visitor lands from a Meta ad, the URL has `?fbclid=...`. The Meta pixel sets the `_fbc` cookie automatically if it loads on that landing page.
- If the pixel is blocked, consent-gated, or the landing page differs from the checkout domain, capture it yourself: on landing, read `fbclid` from the URL, build `fb.1.<Date.now()>.<fbclid>`, store it in a first-party cookie (90 days is common) and in your order or lead record.
- The timestamp is milliseconds (13 digits), set when the click ID was first seen. Do not change the fbclid value (it is case sensitive) and do not regenerate fbc on every page.
- Send fbc and fbp with the server event, raw.

## Steps Claude follows

1. Ask for the Events Manager EMQ numbers and the payload sample if not provided.
2. Run the gap script on the sample:
   ```
   python3 scripts/emq_gap.py path/to/events.jsonl --by-event
   python3 scripts/emq_gap.py path/to/events.jsonl --json emq_report.json
   ```
   Sample input to try: `examples/sample_capi_events.jsonl`.
3. Read the output in this order: plaintext PII, hashed fields that must be raw, placeholder hashes, malformed values, then coverage gaps.
4. Compare script coverage with Events Manager coverage. A big difference usually means the sample is not representative, or the pixel and CAPI send different keys.
5. For each gap, find where the data exists (checkout form, CRM, login, cookies) and write the code or config change. Give the exact normalization in the user's stack (JavaScript, PHP, Python, GTM variable).
6. Check deduplication: pixel `eventID` and CAPI `event_id` must match per event, with the same `event_name`.
7. Produce the output below. Tell the user to recheck EMQ after a few days of new data, since the score is computed on recent events.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Email/phone sent in plaintext | Script "Plaintext PII" lists em or ph | Normalize, SHA-256, send lowercase hex |
| fbc/fbp/IP/UA hashed | Script "Hashed values in fields that must be raw" | Send raw strings |
| Phone missing country code | Script flags 10-digit Indian numbers | Prefix 91 after stripping spaces, +, leading 0 |
| Phone has + or spaces before hashing | Script `ph_format` | Strip all non-digits before hashing |
| Empty value hashed | Script "Hashes of empty/placeholder values" | Omit the key when there is no value |
| fbc wrong format | Script `fbc_format`, or seconds instead of ms | Build `fb.1.<13-digit ms>.<fbclid>` |
| fbc coverage low | Coverage under ~50% on ad traffic | Capture fbclid on landing, store, pass to server |
| Server IP sent as client IP | Script `client_ip_private_or_server`, or the same IP on every event | Read the visitor IP from the request or X-Forwarded-For |
| No external_id | Coverage 0% | Send hashed customer ID on both pixel and CAPI |
| Pixel and CAPI send different keys | Events Manager shows different coverage by source | Align user_data across both |
| No event_id | Script "events_without_event_id" | Send the same event_id on pixel and CAPI |
| Advanced matching off on pixel | Events Manager > dataset > Settings > Automatic advanced matching | Turn it on and select the fields you collect |

## Output format

```
EMQ REVIEW: <brand> / <dataset name>
Events reviewed: <n> server events, <dates>
Events Manager EMQ: Purchase <x>/10, Lead <x>/10, ... (as shared by user)

PARAMETER COVERAGE (from sample)
| Param | Coverage | Status (OK / Missing / Broken) | Note |

BROKEN DATA (fix before adding anything)
1. <issue> - <count> events - <exact fix>

ADD NEXT (ranked)
1. <param> - current <x>% - where to get it - code/config change
2. ...

DEDUP CHECK
<pixel eventID vs CAPI event_id status>

RECHECK
Re-run scripts/emq_gap.py on fresh payloads and compare EMQ in Events Manager after a few days.
```

## Limits

- Meta does not publish exact weights per parameter. The ranking in the script is a heuristic (email, phone and click ID first), not Meta's formula.
- The script counts plaintext values as present for coverage, then flags them separately. Fix them, do not rely on Meta to normalize.
- The script cannot verify that a hash was made from correctly normalized input. Check the hashing code itself.
- EMQ is computed by Meta on its side. A clean sample does not guarantee a specific score.
- Only send data the user has consented to share, and follow the user's privacy policy and local law (DPDP Act in India, GDPR in the EEA).
- Field rules and Events Manager menus change. Check current Meta Conversions API docs for customer information parameters.
