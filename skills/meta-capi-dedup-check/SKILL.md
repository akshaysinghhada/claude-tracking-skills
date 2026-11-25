---
name: meta-capi-dedup-check
description: Verifies that Meta Pixel and Conversions API events deduplicate correctly - matching event_name and event_id, timing inside Meta's 48-hour window, fbp/fbc passed server-side - by comparing browser and server event logs, and explains how to read Events Manager and the Test Events tool. Use when the user says "check CAPI deduplication", "purchases are double counted in Meta", "event_id not matching", "Received from Browser and Server", or shares Pixel and CAPI logs.
---

# Meta Pixel + CAPI Dedup Check

## What it needs

1. Two event logs for the same time period, as CSV, JSON array or JSON lines:
   - Browser (Pixel): `event_name, event_id, timestamp`. Sources: GTM preview export, a dataLayer log, Meta Pixel Helper notes, or a small logging script on the thank-you page.
   - Server (CAPI): `event_name, event_id, event_time` plus `fbp`, `fbc` if available (flat columns or inside `user_data`). Sources: your server/sGTM logs, the CAPI gateway or partner integration logs, or the payloads you send to the Graph API.
   Timestamps can be unix seconds, unix milliseconds or ISO 8601.
2. Which events matter for optimization (usually Purchase or Lead).
3. How each side is implemented: Pixel via GTM, Shopify/WooCommerce partner integration, sGTM, CAPI Gateway, or custom code. Many double-counting issues come from two integrations sending the same event.
4. Optional screenshots from Events Manager: Data sources > your dataset (pixel) > Overview, with an event opened.

## How deduplication works

- Meta deduplicates a browser event and a server event when both have the same `event_name` and the same event ID, and they arrive within 48 hours of each other.
- Pixel: the ID goes in the fourth argument as `eventID`:
  `fbq('track', 'Purchase', {value: 2499, currency: 'INR'}, {eventID: 'order-DS10021'});`
  In GTM Meta Pixel templates this is usually an "Event ID" field.
- CAPI: the same value goes in `event_id`, with `event_name` spelled identically (case matters: `Purchase` is not `purchase`).
- Use an ID both sides can know: the order ID for Purchase, a generated ID pushed to the dataLayer and passed to the server for other events.
- Meta also documents a method based on fbp/external_id, but event_id is the standard approach. Check current Meta docs if you rely on the other one.
- Server events need `event_time` in unix seconds and should be sent close to real time; Meta rejects server events with event_time older than 7 days.
- Send `fbp` (from the `_fbp` cookie) and `fbc` (from the `_fbc` cookie, or built from the `fbclid` URL parameter as `fb.1.<unix ms>.<fbclid>`) on server events, plus `client_ip_address` and `client_user_agent`. These do not drive dedup with event_id, but they raise match quality. `fbc` only exists for visits from a Meta ad click.

## Steps Claude follows

1. Get both logs and save them. Confirm they cover the same period. Unix times and ISO times with an offset are compared as absolute times; ISO times without an offset are read as UTC.
2. Run:
   `python3 scripts/dedup_check.py --browser browser_events.csv --server server_events.json`
   Add `--examples 10` to see more IDs per problem, `--json report.json` to save the full result.
3. Read the per-event table:
   - Match% (B): share of Pixel event IDs that have a server event with the same name and ID. For Purchase and Lead aim for near 100%.
   - Only B: Pixel fired, server did not (server integration gap or event not sent server-side).
   - Only S: server sent, Pixel did not. Normal at some level (ad blockers, browsers restricting the Pixel), and expected for offline events.
4. Go through the findings using the checks table below, worst first.
5. Ask the user to confirm in Events Manager (see below) after fixes go live.
6. Write the output in the template.

Sample inputs: `examples/browser_events.csv` and `examples/server_events.json` (fake demo-store events covering: a missing server event_id, a missing Pixel eventID, a case mismatch Purchase/purchase, a 62-hour gap, a malformed fbp, duplicate IDs on each side, and a server-only purchase).

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Server events missing event_id | ERROR in findings | Pass the same ID from the page to the server (dataLayer, form hidden field, or order ID). |
| Pixel events missing eventID | ERROR in findings | Add `{eventID: ...}` as the 4th fbq argument or fill the GTM template's Event ID field. |
| event_name mismatch | ERROR "browser ['Purchase'] vs server ['purchase']" | Use identical names on both sides, standard events in their documented casing. |
| Gap over 48 hours | ERROR with both timestamps | Send server events in real time, not in a nightly batch. Delayed events will double count. |
| Duplicate IDs on browser | WARN "sent more than once from the browser" | Thank-you page reloads or two Pixel tags. Fire once per transaction (GTM trigger, "once per page", order-ID check). |
| Duplicate IDs on server | WARN | Webhook retries or two integrations (e.g. Shopify app plus custom CAPI). Keep one sender. |
| Low match rate | WARN with missing IDs listed | Find where server events fail: check server logs for errors or missing event types. |
| Browser only | WARN (INFO for PageView) | Add the event server-side if it matters for optimization. |
| fbp/fbc format | ERROR | Pass cookie values as-is: `fb.1.<time>.<random>`. Do not strip the prefix. |
| Low fbp coverage | WARN under 80% | Read `_fbp` server-side or pass it from the browser with the event. |
| Two integrations | Same event appears from "Server" via two sources in Events Manager | Disable one (common: platform app plus GTM server container). |

## Reading Events Manager

- Data sources > dataset > Overview: each event row shows the integration it was "Received from" (Browser, Server, or both). Open an event to see details including deduplication and Event Match Quality.
- Event Match Quality: a 0 to 10 score for server events, showing which customer parameters are sent. Low scores point to missing email, phone, fbp, fbc, IP or user agent.
- Diagnostics tab: Meta flags deduplication problems here (for example, server events missing a dedup key or low overlap). Wording changes; read the message.
- Test Events tab: copy the test code, add `test_event_code` to the server payload, and open the site from the same tab. Each event shows its source (Browser or Server) and whether it was deduplicated. Remove `test_event_code` before going live.
- Numbers in Events Manager can lag; wait a day after a fix before judging.

## Output format

```
META DEDUP CHECK - <brand> - <period>
Browser events: <n> | Server events: <n>

KEY EVENTS
Purchase: match <x>% | only browser <n> | only server <n>
Lead: ...

PROBLEMS (fix in this order)
1. <issue> - <evidence: example IDs> - <fix with where to change it>

EXPECTED AFTER FIX
- Match rate for Purchase near 100% of Pixel events
- No gaps over 48 h, no case mismatches

VERIFY IN EVENTS MANAGER
- Test Events: <steps>
- Overview: Received from Browser and Server for <events>
```

## Limits

- The script only sees what is in the logs. If logs are sampled or cover different periods, match rates will look worse than they are.
- It does not call Meta's API or read Events Manager. Events Manager is the final check.
- "Only server" events are not always a problem: ad blockers and browser privacy features stop many Pixel events, which is why CAPI exists.
- Meta's documented rules (48-hour dedup window, 7-day event_time limit) are stable at the time of writing, but check current Meta developer docs if results contradict them.
