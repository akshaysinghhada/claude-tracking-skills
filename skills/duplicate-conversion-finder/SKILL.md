---
name: duplicate-conversion-finder
description: Finds double-counted conversions by comparing Meta, Google Ads and GA4 against backend orders day by day, then traces the cause (pixel plus CAPI without dedup, two primary Google Ads actions, thank-you page reloads, duplicate GTM or gtag, Shopify/WooCommerce app plus manual pixel). Use when someone says "Meta shows more purchases than Shopify", "conversions are double counting", "ROAS looks too good", "Google Ads conversions don't match orders", or "find duplicate conversions".
---

# Duplicate Conversion Finder

Two parts: a numbers check that shows which platform over-reports and since when, and a cause hunt that finds the duplicate source.

## What it needs

1. **Daily numbers for 14 to 60 days** in one CSV: `date, backend_orders, meta_purchases, google_ads_conversions, ga4_purchases`. Missing columns are fine. Where to pull them:
   - Backend: Shopify Admin > Analytics > Reports > orders over time, or WooCommerce > Reports/Analytics > Orders. Count paid orders, excluding test and cancelled orders.
   - Meta: Ads Manager > Reports or the campaigns table, breakdown By Time > Day, column Purchases (website). Note the attribution setting used.
   - Google Ads: Campaigns > segment by Day, column Conversions (primary actions only) or "All conv." filtered to the purchase action.
   - GA4: Reports > Monetization > Ecommerce purchases or Explore with Date and Transactions/purchase event count.
   See `examples/daily_conversions.csv` (full) and `examples/daily_conversions_partial.csv` (missing columns, blanks, zero day).
2. **Setup facts**: platform (Shopify, WooCommerce, custom), which apps/plugins send pixels, whether CAPI is on and how, GTM container IDs, and any recent changes with dates.
3. Access to the live site for browser checks (Meta Pixel Helper, Tag Assistant, DevTools).

## Steps Claude follows

1. Run the comparison:
   ```
   python3 scripts/compare_platforms.py path/to/daily.csv
   python3 scripts/compare_platforms.py path/to/daily.csv --threshold 1.3 --min-backend 5 --out ratios.csv
   ```
   `--threshold` sets the flag level (default 1.2 = platform reports 20% more than backend). `--min-backend` skips ratio flags on very low volume days.
2. Read the summary: overall ratio, flagged days, and any "median ratio jumped" line. A step change on a specific date is the strongest clue; ask what went live that day.
3. A ratio near 2.0x usually means every conversion fires twice. A ratio of 1.2 to 1.5x can be attribution differences or partial duplication.
4. Run the cause checks below for each platform flagged, starting with the one with the highest ratio.
5. Confirm a duplicate with one real test order (or a test transaction) and count how many events each platform receives for that order ID.
6. Write the fix list and tell the user to re-run the script on 7 to 14 days of post-fix data.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Meta pixel + CAPI without dedup | Meta about 2x backend, step on CAPI launch date; Events Manager shows browser and server events with no matching event_id | Send the same `eventID` (pixel) and `event_id` (CAPI) with the same event_name, for example the order ID |
| Two Meta integrations | Pixel Helper shows the same pixel firing Purchase twice; Shopify Meta channel app plus pixel code in theme or Customer events | Keep one integration, remove the other |
| GA4 import + Google Ads tag both primary | Google Ads > Goals > Conversions > Summary shows two purchase actions as Primary | Keep one as Primary, set the other to Secondary |
| Google Ads counting "Every" for leads | Lead action set to Every; repeat submits count | Set Count to One for leads; Every is normal for purchases |
| No transaction_id | Google Ads/GA4 events lack transaction_id; reloads count again | Send order ID as transaction_id; Google Ads dedups by transaction ID within a conversion action |
| Thank-you page reload | Test order, refresh the page, see a second event in Pixel Helper/Tag Assistant | Fire only once per order (server flag, or store fired order IDs in localStorage and check before firing) |
| Duplicate GTM containers | Page source has two `GTM-` IDs, or the same container twice | Remove the extra snippet |
| Hardcoded gtag + GTM | `gtag/js?id=` in source and a Google tag in GTM with the same ID | Pick one; remove the hardcoded config or the GTM tag |
| Shopify app + manual tags | Google & YouTube app or Meta channel connected and also custom pixels under Settings > Customer events or theme code | One source per platform |
| WooCommerce plugin overlap | Two plugins (for example an official Meta plugin and a pixel manager plugin) both active | Disable pixel output in one |
| Purchase on wrong trigger | Purchase tag fires on all pages containing "thank" or on page view of order status page with revisits | Trigger on a dataLayer purchase event with order ID |
| Sum of platforms > backend | Meta + Google + GA4 together exceed orders | Normal: each platform claims credit. Compare each platform to backend separately |

## Reading the ratios

- **Above threshold every day, near 2x**: systematic duplicate. Look for two integrations or missing dedup.
- **Jump on a date**: something shipped that day. Match it to app installs, theme changes, GTM publishes, CAPI launch.
- **Spiky days only**: reloads, a sale day with heavy view-through, or modeled conversions. Check those days in the platform with attribution set to click-only.
- **Below 0.7x**: under-reporting, not duplication. Usually missing tags on some checkout paths, consent, or ad blockers.
- Meta default attribution includes view-through. Google Ads may include modeled conversions and records conversions against the click date. GA4 uses its own attribution and session rules. Match date ranges and settings before concluding.

## Output format

```
DUPLICATE CONVERSION REVIEW: <brand>
Period: <start> to <end>   Threshold: <x>   Backend source: <...>

RATIOS (scripts/compare_platforms.py)
| Platform | Platform total | Backend total | Overall ratio | Flagged days | Verdict |
Step changes: <platform> jumped from <a>x to <b>x starting <date>

LIKELY CAUSES (ranked)
1. <cause> - evidence - confidence (high/medium/low)

CONFIRMATION TEST
Order <id>: Meta received <n> Purchase events, Google Ads <n>, GA4 <n>.

FIX LIST
1. <fix> - where - who
2. ...

RECHECK
Re-run compare_platforms.py after 7 to 14 days. Expected ratio after fix: <range>.
```

## Limits

- The script only compares counts. It cannot see event IDs or prove duplication; it shows where to look.
- Platforms attribute differently (view-through, modeled conversions, attribution windows, click date vs conversion date), so over-reporting is a signal to investigate, not proof.
- Backend data must be clean: exclude test, cancelled and fully refunded orders consistently.
- Low daily volume makes ratios noisy. Use `--min-backend` and a longer date range.
- Menu paths in Shopify, WooCommerce, Meta and Google change. Check current docs if a path differs.
