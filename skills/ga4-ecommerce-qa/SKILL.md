---
name: ga4-ecommerce-qa
description: Step-by-step QA of the GA4 purchase funnel with DebugView and Tag Assistant, plus a reconciliation of GA4 transactions against backend orders to find missing, duplicate and test purchases, revenue gaps and COD vs prepaid differences. Use when someone says "GA4 revenue doesn't match Shopify", "test my purchase tracking", "GA4 is missing orders", "duplicate purchases in GA4" or "QA ecommerce tracking".
---

# GA4 Ecommerce QA

Two parts: a live test of each funnel step, and a reconciliation of what GA4 recorded against what the store actually sold. Do both; the live test explains the "why" behind the reconciliation numbers.

## What it needs

1. **Site access for a test order:** a test product or a coupon, and permission to place 1-2 real orders (one prepaid, one COD if offered). Ask the user to cancel them afterwards.
2. **GA4 transactions CSV.** GA4 > Explore > Free form. Dimension: Transaction ID. Metrics: Purchase revenue (or Total revenue) and Ecommerce purchases. Set the date range, set rows to show to the maximum, then Export (download icon) > CSV. Metric names can differ slightly, check in your account; the script accepts the common ones.
3. **Backend orders CSV for the same dates and time zone:** columns `order_id`, `amount`, optional `payment_method`, optional `status`. Shopify: Orders > Export. WooCommerce: Orders export or Analytics > Orders download. Make sure the GA4 property time zone and the store time zone match, or trim a day at each end.
4. Which value the site sends to GA4 (with or without shipping and tax), and whether orders are created before or after payment.

## Steps Claude follows

**Part A - live funnel test (user does this with Claude guiding):**

1. Open tagassistant.google.com (or GTM > Preview) and enter the site URL. In GA4 open Admin > Data display > DebugView. Using Preview mode marks hits as debug so they show in DebugView.
2. Walk the funnel and ask the user to screenshot each event's parameters in DebugView: `view_item` > `add_to_cart` > `begin_checkout` > `add_shipping_info` > `add_payment_info` > `purchase`.
3. On `purchase` check every row of the checks table below.
4. Refresh the thank-you page twice and reopen it from browser history. A second `purchase` with the same `transaction_id` is a duplicate risk. GA4 is documented to drop repeat purchases with the same transaction ID, but do not rely on it alone, and Google Ads and Meta tags on the same trigger will count again. The fix belongs on the site or in GTM.
5. Repeat for a prepaid order through the payment gateway. Watch the page the gateway returns to: if it is not the normal thank-you page, purchase may never fire.

**Part B - reconciliation:**

6. Run:
   ```
   python3 scripts/reconcile_orders.py <ga4_transactions.csv> <backend_orders.csv>
   python3 scripts/reconcile_orders.py <ga4.csv> <orders.csv> --tolerance 2
   ```
   `--tolerance` is the allowed per-order revenue difference in percent (default 1). Rows with a status containing cancel, fail, void or test are excluded from the backend side and reported separately.
7. Interpret the output:
   - Missing in GA4 concentrated in prepaid = gateway return flow, ad blockers or consent.
   - Extra in GA4 matching cancelled orders = purchase fires before payment is confirmed.
   - Duplicated IDs or Ecommerce purchases above 1 = thank-you page refresh or two tags.
   - Mismatches of a fixed amount = shipping or tax included on one side only. A mismatch of about 100x = value sent in paise.
   - (not set) transaction IDs = purchases sent without `transaction_id`.
8. Give a judgement on the gap, not a pass/fail statistic. As a rough guide: a small under-count (single-digit percent) is common because of blockers, consent and closed tabs; a gap well above that, or GA4 higher than backend, means a setup problem worth fixing. Say what is driving it.
9. Write the report in the output format.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| transaction_id present | DebugView purchase shows `transaction_id`; Explore shows no (not set) | Push the order ID in `ecommerce.transaction_id` |
| transaction_id unique and stable | Same ID format as backend (`1001` vs `#1001`), never reused, not a timestamp | Use the backend order ID / number customers see |
| Value correct | `value` equals order total by your chosen rule (with or without shipping/tax), sent as a number | Fix the dataLayer; send `1299.00` not `"₹1,299"` |
| Currency | `currency` is `INR` (ISO code) on every ecommerce event with value | Add `currency`; without it revenue is not recorded correctly |
| Items array | `items` has `item_id` or `item_name`, `price`, `quantity` | Build items from the order lines; prices per unit |
| Duplicate on refresh | Second purchase after refresh / back button | Fire only once per order: server flag, cookie or localStorage check with the order ID |
| Fires after payment only | Cancelled or failed prepaid orders appear in GA4 | Fire on the confirmed thank-you page, not on "Place order" click |
| Gateway return | Prepaid capture rate much lower than COD | Make the gateway return to the thank-you page; add the gateway to unwanted referrals |
| COD handling | COD orders included, flagged by a param | Send a custom param such as `payment_method_type: "cod"` / `"prepaid"` on purchase and register it as a custom dimension; handle cancellations with `refund` |
| ecommerce cleared | `dataLayer.push({ ecommerce: null })` before each ecommerce push | Prevents items from a previous event leaking into the next |
| Ads tags | Google Ads and Meta purchase tags use the same order ID and fire on the same event | Pass `transaction_id` as Ads order ID and Meta `eventID` for dedup |

## Output format

```
# GA4 ecommerce QA - <site>, <date range>

## Verdict
<2-3 sentences: how far GA4 is from the backend, the main cause, and whether ROAS reporting can be trusted>

## Live test results
| Step | Fired | Parameters OK | Notes |
|---|---|---|---|
| view_item | | | |
| add_to_cart | | | |
| begin_checkout | | | |
| add_shipping_info | | | |
| add_payment_info | | | |
| purchase (prepaid) | | | |
| purchase (COD) | | | |
| refresh test | | | |

## Reconciliation
| Metric | Backend | GA4 | Gap |
|---|---|---|---|
<from the script, plus COD vs prepaid table>

## Causes found
1. <cause> - evidence - fix - owner (developer / GTM / store admin)

## Retest plan
<what to re-run after fixes, and when to re-reconcile>
```

## Limits

- GA4 reports can take a day or more to settle; reconcile on dates at least 2-3 days old.
- Consent Mode, ad blockers and browser restrictions mean GA4 will not capture every order; the script cannot separate those from setup bugs, the live test can.
- Explore exports may be sampled or capped on large date ranges; use shorter ranges or the BigQuery export for big stores.
- The script matches on order ID only. If GA4 receives a different ID than the backend export (internal ID vs order number), everything shows as missing; fix the ID mapping first.
- It does not see refunds or RTO in GA4 unless the `refund` event is implemented.
