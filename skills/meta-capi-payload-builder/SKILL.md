---
name: meta-capi-payload-builder
description: Builds correct Meta Conversions API payloads for Purchase, Lead, AddToCart, InitiateCheckout and CompleteRegistration from order or lead data, with normalized SHA-256 hashed user_data and a ready curl test command. Use when someone says "build a CAPI payload", "what JSON do I send to Conversions API", "test my server event", "send purchase to Meta from my backend", or "why is Meta rejecting my CAPI event".
---

# Meta CAPI Payload Builder

Turns one order, cart or lead record into a valid Conversions API request body, explains every field, and gives a curl command to test it against Events Manager > Test events before going live.

## What it needs

1. **The record**: one order/lead as JSON, or a CSV export with one row per event. Where to get it:
   - Shopify: Admin > Orders > Export (CSV), or the order JSON from the Admin API.
   - WooCommerce: WooCommerce > Orders > select > Export, or the order object in a webhook.
   - Custom backend / CRM: the row your thank-you page or webhook already writes.
   See `examples/sample_order.json` and `examples/sample_orders.csv` for the column names the script reads.
2. **Pixel (dataset) ID**: Events Manager > Data sources > select the dataset > Settings.
3. **Access token**: Events Manager > dataset > Settings > Conversions API > Generate access token. Keep it in an environment variable or secret manager. Never paste it into chat, code repos or shared files.
4. **Test event code** (optional, recommended): Events Manager > dataset > Test events > Confirm your server's events are set up correctly > copy the code (looks like TEST12345).
5. **Current Graph API version**: check Meta's Graph API changelog. The script keeps it as a placeholder `v<VERSION>`.
6. Whether the browser pixel fires the same event, and what it uses as `eventID`.

## Payload anatomy (comments are for reading only, JSON has no comments)

```
POST https://graph.facebook.com/v<VERSION>/<PIXEL_ID>/events?access_token=<ACCESS_TOKEN>
{
  "data": [{
    "event_name": "Purchase",
    "event_time": 1795529530,            // unix seconds, when the event happened
    "event_id": "purchase_KL-20931",     // same as pixel eventID for dedup
    "action_source": "website",
    "event_source_url": "https://shop.example/checkout/thank-you",
    "user_data": { "em": ["<sha256>"], "ph": ["<sha256>"], "client_ip_address": "...",
                   "client_user_agent": "...", "fbc": "fb.1.<ms>.<fbclid>", "fbp": "fb.1...." },
    "custom_data": { "value": 2148.0, "currency": "INR", "content_ids": ["SKU1"],
                     "content_type": "product", "contents": [{"id": "SKU1", "quantity": 2, "item_price": 649}],
                     "num_items": 2 }
  }],
  "test_event_code": "TEST12345"           // remove when going live
}
```

| Event | custom_data to include |
|---|---|
| Purchase | value and currency (required), contents, content_ids, content_type, num_items |
| InitiateCheckout | value, currency, contents, content_ids, num_items |
| AddToCart | value, currency, contents, content_ids, content_type |
| Lead | value and currency only if you assign a lead value |
| CompleteRegistration | value and currency if used, optionally status |

Rules the script applies:
- Hashed with SHA-256 after normalization: em, ph, fn, ln, ct, st, zp, country, external_id.
- Sent raw: client_ip_address, client_user_agent, fbc, fbp.
- Phone: digits only, country code added (91 by default for 10-digit Indian mobiles), no +, leading 0 removed.
- Email lowercased and trimmed; city/state lowercased with spaces removed; country mapped to 2-letter code.
- event_time accepts unix seconds, unix ms or ISO 8601. Naive timestamps are treated as IST and flagged.
- event_id defaults to `<event>_<order_id>`. Change the format to match whatever your pixel sends.

## Steps Claude follows

1. Confirm the event type, data source and whether the pixel sends the same event.
2. Map the user's fields to the script's column names (rename columns or tell the user which to add).
3. Run the builder:
   ```
   python3 scripts/build_capi_payload.py examples/sample_order.json --test-event-code TEST12345
   python3 scripts/build_capi_payload.py orders.csv --event Purchase --out payload.json \
       --pixel-id <PIXEL_ID> --api-version v<VERSION>
   ```
   Useful flags: `--currency INR`, `--default-country-code 91`, `--default-country in`.
4. Read the warnings on stderr and fix the source data (missing user agent, no event_id, old timestamps).
5. Give the user the curl command. They set the token locally: `export META_CAPI_TOKEN='...'`, then run curl.
6. Ask them to confirm the event appears in Test events with the expected parameters, then remove `test_event_code` for production.
7. If the response has an error, read the `error.message` and `error_user_msg` and fix the matching field.
8. For production, port the same logic to their backend or server-side GTM. Claude writes that code on request, keeping the same normalization.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| event_time in ms or wrong zone | 13-digit value, or the event shows hours off | Send unix seconds (10 digits); epoch time has no time zone |
| event_time too old | Error about event_time, or warning from script | Send in real time; website events older than 7 days are rejected |
| Missing user agent / source URL | Warning, or Meta error for website events | Capture `User-Agent` header and page URL at event time |
| No dedup | Pixel and CAPI both count; no event_id | Use the same event_id and event_name on both |
| PII sent unhashed | em/ph without 64-char hex | Hash after normalization (script does this) |
| fbc hashed or rebuilt each page | fbc is 64-char hex, or timestamp changes per event | Send raw, store once at landing |
| Currency wrong | "inr" vs "INR", or symbol | Use ISO 4217 code, for example INR |
| value is a string with commas | "2,148.00" | Send a number: 2148.00 |
| content_ids not matching catalog | Catalog diagnostics in Commerce Manager | Use the same IDs as your product feed |
| Token in code or shared doc | Token visible in repo or screenshot | Rotate the token, move it to a secret store |
| Test code left in production | Live events still go to Test events | Remove `test_event_code` |

## Output format

```
CAPI PAYLOAD: <event_name> for <brand>
Source: <file / system>
Events built: <n>

PAYLOAD
<JSON from the script>

FIELD NOTES
- event_id: <value> - pixel must send eventID '<same>'
- user_data keys sent: <list>  | missing: <list>
- custom_data: <summary>

TEST
export META_CAPI_TOKEN='<ACCESS_TOKEN>'
<curl command>
Expected: {"events_received": <n>, ...}. Then check Events Manager > Test events.

WARNINGS TO FIX
- <script warnings, plain language>

GO-LIVE CHANGES
- Remove test_event_code, set current API version, send in real time from <system>.
```

## Limits

- The script builds payloads; it does not send them. The user runs curl or their own backend.
- Field rules, required parameters and the API version change. Check current Meta Conversions API docs before going live.
- fbc built from fbclid uses event time when the real click time was not stored. Storing fbc at landing is more accurate.
- `action_source` is fixed to "website". For app, offline or CRM events use the matching action_source (see the crm-lead-feedback-loop skill).
- Only send data the customer has consented to share, and follow local privacy law.
