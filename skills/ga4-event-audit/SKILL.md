---
name: ga4-event-audit
description: Audits a GA4 property from an Events report CSV export and Admin screenshots or descriptions - duplicate and badly named events, missing recommended ecommerce or lead events, key event setup, missing purchase parameters, (not set) rates, high-cardinality custom dimensions, data retention and unwanted referrals such as payment gateways. Use when someone says "audit my GA4", "check my GA4 events", "is my GA4 set up right", "why is GA4 revenue wrong" or shares a GA4 events export.
---

# GA4 Event Audit

Finds the setup problems that make GA4 numbers unreliable for ad decisions. The script handles the events list; Claude checks the Admin settings from screenshots or the user's answers.

## What it needs

1. **Events export (required).** GA4 > Reports > Engagement > Events > set the date range (last 28-90 days) > Share this report (icon top right) > Download File > Download CSV. Any CSV with `event_name` and `event_count` columns also works; extra columns are ignored.
2. **Admin screenshots or answers (ask for these):**
   - Admin > Data display > Key events: which events are marked as key events.
   - Admin > Data display > Custom definitions: list of custom dimensions and metrics with scope.
   - Admin > Data collection and modification > Data retention: event data retention setting.
   - Admin > Data collection and modification > Data streams > web stream > Configure tag settings > Show more > List unwanted referrals, and Define internal traffic.
   - Admin > Data collection and modification > Data filters: internal traffic filter state (Testing / Active / Inactive).
   - Admin > Product links: Google Ads link status.
   Menu labels move occasionally; if a path does not match, check in your account using the Admin search box.
3. **Parameter check (for ecommerce):** a screenshot of a `purchase` event in Admin > Data display > DebugView, or Explore > Free form with dimension Transaction ID and metrics Ecommerce purchases and Purchase revenue.
4. Site type (ecommerce, lead gen, SaaS) and payment gateways used (Razorpay, PayU, Cashfree, CCAvenue, Stripe, PayPal, others).

## Steps Claude follows

1. Run the script on the CSV:
   ```
   python3 scripts/ga4_events_check.py <events.csv>
   python3 scripts/ga4_events_check.py <events.csv> --type ecommerce
   ```
   `--type` is `ecommerce`, `lead` or `saas`; without it the script guesses from the event names.
2. Read the output and decide what each duplicate group means: `purchase` + `Purchase` usually means two tags (often GTM plus a platform plugin or a hardcoded gtag). Ask where each is sent from before saying which to delete.
3. Check key events against the business goal. A key event should be an outcome (purchase, generate_lead, sign_up, qualified WhatsApp click), not page_view, scroll or session_start. If Google Ads imports GA4 key events, a noisy key event changes bidding.
4. Check parameters on purchase: `transaction_id`, `value`, `currency`, `items` (with `item_id` or `item_name`). Missing currency means revenue is not recorded correctly; missing transaction_id means GA4 cannot drop duplicate purchases with the same ID.
5. Check (not set): ask for a report or Explore table with the relevant dimension (Session source / medium, Item name, Transaction ID, Landing page). Judge the share; a small share is normal, a large or rising one points to a setup issue.
6. Review custom dimensions for high cardinality (IDs, timestamps, full URLs with query strings, email-like values). These push rows into "(other)" in reports and should not be registered as dimensions; keep them in BigQuery instead.
7. Check data retention: the default for event data is 2 months. Recommend the longest option available to the property (14 months on standard properties) so Explorations can compare year on year. It is not retroactive.
8. Check unwanted referrals and internal traffic (see table). Payment gateway redirects reassign the purchase session to the gateway domain and steal credit from ads.
9. Write the report in the output format.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Duplicate event names | Script: names that differ only by case, spaces, separators (`purchase` / `Purchase`) | Find both sources (GTM, plugin, hardcoded gtag), keep one, use the recommended lowercase name |
| Naming rules | Script: not snake_case, spaces, over 40 characters, reserved prefixes `google_`, `ga_`, `firebase_` | Rename at the source; GA4 does not merge old and new names |
| Non-standard names | Script: `AddToCart`, `checkout`, `Lead` instead of recommended names | Use `add_to_cart`, `begin_checkout`, `generate_lead`; recommended names fill the standard reports |
| Missing recommended events | Script: compares against GA4 recommended events for the site type | Add via dataLayer (see `gtm-datalayer-spec`) |
| Funnel order | Script: a later step has more events than an earlier one | Usually duplicate firing on the later step, or the earlier step only fires on some paths |
| Key events | Admin > Data display > Key events | Only outcome events; remove page_view / scroll / session_start style key events |
| Purchase parameters | DebugView or Explore on Transaction ID | Send `transaction_id`, `value` (number), `currency` (`INR`), `items` on every purchase |
| (not set) rates | Explore table with the dimension, compare (not set) share to total | Source / medium (not set): check tag order and consent; Item (not set): items array missing |
| High-cardinality dimensions | Custom definitions holding IDs, timestamps, raw URLs | Archive the dimension; use BigQuery export for row-level data |
| Data retention | Admin > Data retention shows 2 months | Set to the maximum available; note it only applies going forward |
| Unwanted referrals | Session source / medium shows `razorpay.com`, `payu.in`, `cashfree.com`, `stripe.com`, `paypal.com`, bank 3-D Secure domains | Add those domains to List unwanted referrals; check exact referral domains in your own source report |
| Internal traffic | No internal traffic rule, or Data filter left in Testing | Define office / agency IPs, set the filter to Active after checking in Testing |
| Google Ads link | Admin > Product links | Link the right Ads account so key events and audiences can be shared |

## Output format

```
# GA4 audit - <property name>, <date range>

## Verdict
<2-3 sentences: can this property be trusted for revenue and lead reporting today, and what breaks it most>

## Fix first
| # | Issue | Evidence | Fix | Where |
|---|---|---|---|---|

## Fix next
| # | Issue | Evidence | Fix |
|---|---|---|---|

## Settings snapshot
| Setting | Current | Recommended |
|---|---|---|
| Data retention | | Maximum available |
| Key events | | |
| Unwanted referrals | | |
| Internal traffic filter | | Active |
| Google Ads link | | |

## Events summary
<duplicates, missing recommended events, funnel counts from the script>

## Not checked
<anything you had no screenshot or data for>
```

## Limits

- The CSV only shows event names and counts. It cannot show parameters, which tag sent the event, or consent effects; ask for DebugView or Explore data for those.
- Admin settings are judged only from what the user shares; never assume a setting you have not seen.
- Thresholds for (not set) and funnel ratios are judgement calls, they vary by site and traffic mix.
- Changes in GA4 apply from the time they are made. Renamed events, new filters and retention changes do not fix past data.
- Consent Mode modelling and thresholding can change reported numbers; this skill does not measure those effects.
