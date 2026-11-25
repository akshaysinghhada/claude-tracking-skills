---
name: gtm-datalayer-spec
description: Writes a developer-ready dataLayer specification for an ecommerce, lead gen or SaaS site using GA4 recommended events, with exact object shapes, ecommerce clearing, event_id for Meta deduplication, user_data for enhanced conversions, India COD rules and a QA checklist. Use when someone says "write a dataLayer spec", "what should my developer push", "tracking plan for my store", "dataLayer for GA4 and Meta" or "brief for my developer".
---

# GTM dataLayer Spec

Produces a spec a developer can implement without a call: which event, when it fires, the exact object, where each value comes from, and how to test it. GTM then maps these pushes to GA4, Google Ads and Meta tags.

## What it needs

Ask for anything missing, in one message:

1. Site type: ecommerce, lead gen, SaaS (or a mix) and platform (Shopify, WooCommerce, custom, Webflow, etc.).
2. Conversion points: checkout steps, forms, WhatsApp / call buttons, sign-up, trial, demo booking.
3. Payment options: prepaid gateways (Razorpay, PayU, Cashfree, Stripe, others) and whether COD is offered.
4. The value rule: does order value include shipping and tax? Pick one and keep it the same in GA4, Google Ads and Meta.
5. Which ad platforms will use the data (Google Ads, Meta, others) and whether Meta CAPI or server-side GTM is used or planned.
6. Consent setup (CMP or not) and whether customer email/phone are available on the confirmation page.

Reference file: `examples/demo-store-datalayer.js` holds a full set of tested pushes (run `node examples/demo-store-datalayer.js` or paste into a console). Use it as the shape reference.

## Steps Claude follows

1. Pick the event list for the site type:
   - Ecommerce: `view_item_list` (optional), `view_item`, `add_to_cart`, `view_cart` (optional), `begin_checkout`, `add_shipping_info`, `add_payment_info`, `purchase`, `refund` (backend or Measurement Protocol).
   - Lead gen: `generate_lead` on confirmed submission (thank-you state, not button click), plus custom events for WhatsApp / call clicks if needed. Later stages (`qualify_lead`, `close_convert_lead`) come from the CRM, not the website.
   - SaaS: `sign_up`, `login`, `generate_lead` (demo request), `begin_checkout` and `purchase` for paid plans. Trials have no GA4 recommended event; use a custom name such as `trial_start` and say so in the spec.
2. Write one block per event using the template below. Object shapes must match `examples/demo-store-datalayer.js`:
   - Ecommerce events put `currency`, `value`, `items` (and `transaction_id`, `tax`, `shipping`, `coupon`, `shipping_tier`, `payment_type` where they apply) inside `ecommerce`.
   - Non-ecommerce events (`generate_lead`, `sign_up`) put parameters at the top level.
   - Push `{ ecommerce: null }` immediately before every ecommerce push so old items do not merge into the new event.
3. Add `event_id` to every event that goes to Meta. Rules: unique per event instance, generated on the page, and sent with the same value and same event name from the browser pixel (`eventID`) and from CAPI so Meta can deduplicate. For purchase use a value built from the order ID (for example `purchase_DS-100482`) so a refresh produces the same ID.
4. Add `user_data` on purchase, generate_lead and sign_up when the user has given the data: `email`, `phone_number` (E.164, for example `+919812345678`), `address` (`first_name`, `last_name`, `city`, `region`, `postal_code`, `country`). Send normalised plain values over HTTPS and let the Google tag / GTM User-Provided Data variable hash them, or pre-hash with SHA-256 exactly as Google's enhanced conversions documentation describes. Enhanced conversions must also be turned on in Google Ads, and user-provided data collection in GA4; check in your account. Do not put personal data in any other parameter or in URLs.
5. Write the India / COD section (below) with the user's chosen option.
6. Add the GTM mapping table (dataLayer key > GTM variable > tag field) so whoever builds GTM can follow it.
7. Finish with the QA checklist.

## India notes: COD and payment gateways

- **When to fire purchase:** on the order confirmation page after the order is created in the backend, for both COD and prepaid. For prepaid, only after the gateway returns success; never on the "Pay" click.
- **Mark the payment method:** send a custom param such as `payment_method_type: "cod" | "prepaid"` on purchase (register it as a custom dimension in GA4). `payment_type` on `add_payment_info` is the GA4 recommended param for the method chosen.
- **COD choices for ad platforms (pick one, write it in the spec):**
  a) Send all orders as purchase and accept that some COD orders will be cancelled or returned.
  b) Send prepaid as Purchase to Meta and COD as a separate custom event, so campaigns can optimise on prepaid.
  c) Send delivered COD orders later from the backend (Meta CAPI, Google Ads offline conversion import) and use them for value reporting.
  Which works best depends on COD share and RTO rate; test, do not assume.
- **Cancellations and RTO:** send GA4 `refund` with the `transaction_id` from the backend (Measurement Protocol) so GA4 revenue can be corrected. Google Ads supports conversion adjustments for retractions; check in your account.
- **Gateway return page:** confirm every gateway returns to the same thank-you URL, and add gateway domains to GA4 unwanted referrals.
- **Currency:** always `"INR"`; values as numbers in rupees (`1299.00`), not paise, not strings with the rupee symbol.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Event names | Exact GA4 recommended names, lowercase | Rename at source; no `Purchase` / `AddToCart` |
| ecommerce cleared | `{ ecommerce: null }` pushed right before each ecommerce event | Add the clearing push |
| value matches items | `value` equals sum of `price * quantity` (minus order-level discount if that is the rule) | Fix the calculation; document the rule |
| Types | `value`, `price`, `quantity` are numbers | Cast on the server side |
| transaction_id | Present, equals the backend order ID shown in exports | Use the same field the finance team exports |
| Purchase once | Refresh / back button does not push again | Server flag or localStorage guard keyed on order ID |
| event_id | Present on Meta-bound events; purchase ID stable per order | Generate per event; reuse in CAPI |
| user_data | Only on events where the user supplied data; phone in E.164 | Normalise (trim, lowercase email) before pushing |
| Push timing | Push happens before or with the page view, not after a redirect | Push on the confirmation page load |

## Output format

```
# dataLayer spec - <site>, v1.0, <date>

## Summary
Site type, platforms, value rule (incl./excl. shipping and tax), COD option chosen.

## Events
### <event_name>
- Fires when: <exact user action / page state>
- Page / component: <URL pattern or component>
- Push:
  <code block, exact object>
- Field sources: | Key | Type | Example | Source in backend |
- Notes: <dedup, consent, edge cases>

## GTM mapping
| dataLayer key | GTM variable | Used in tags |
|---|---|---|

## India / COD rules
<chosen option and refund handling>

## QA checklist
- [ ] Every event appears in GTM Preview with the exact shape above
- [ ] ecommerce: null pushed before each ecommerce event
- [ ] purchase value, currency INR, transaction_id match the backend order
- [ ] Refreshing the thank-you page does not push purchase again
- [ ] Prepaid order through each gateway reaches the thank-you page and pushes purchase
- [ ] COD order pushes purchase with payment_method_type "cod"
- [ ] event_id on browser and CAPI purchase are identical (Events Manager > Test events)
- [ ] user_data present only after the user entered it; phone in E.164
- [ ] Events show in GA4 DebugView with items and currency
- [ ] No personal data in URLs or custom parameters
```

## Limits

- The spec defines what the website pushes. It does not build the GTM tags or CAPI setup; hand it to the `gtm-naming-cleanup` / container build step after implementation.
- Shopify checkout pages run in a restricted environment (customer events / web pixels), so standard dataLayer pushes may not run there; check your Shopify plan and app setup.
- Consent rules decide whether tags may use these values; the spec assumes the CMP gates the tags.
- Field names in `user_data` follow Google's user-provided data format; Meta CAPI uses its own keys (`em`, `ph`, etc.) mapped in the server tag.
