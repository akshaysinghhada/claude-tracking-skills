---
name: google-ads-conversion-audit
description: Audits a Google Ads conversion setup from an exported or pasted conversion actions table - primary vs secondary goals, count settings, attribution model, click-through windows, double counting between Google Ads tags and GA4 imports, micro-conversions inflating Smart Bidding, enhanced conversions and values. Use when the user says "audit my Google Ads conversions", "conversions look too high", "ROAS in Google Ads does not match Shopify/CRM", "which conversions should be primary", or pastes a conversion actions list.
---

# Google Ads Conversion Audit

## What it needs

1. The conversion actions table. In Google Ads: Goals > Conversions > Summary (menu names move around between UI versions, check your account). Click the columns icon and add, if available: Action optimization, Source, Category (goal), Count, Click-through conversion window, Attribution model, Value, Status, Enhanced conversions. Set a date range of the last 30 days, then Download > CSV.
   A pasted table works too; Claude saves it as CSV. Column names do not need to match exactly.
2. Business type: ecommerce (D2C) or lead gen (B2B). The script guesses from categories if not given.
3. Answers Claude asks for, because they are not in the export:
   - Account-default goals vs campaign-specific goals: which campaigns override the account goals? (Campaign > Settings > Goals)
   - Conversion value rules in use? (Goals > Value rules)
   - Where is the GA4 property linked, and are GA4 key events imported?
   - The real numbers for the same period: orders and revenue from Shopify/WooCommerce, or leads and SQLs from the CRM.
   - Bid strategy per main campaign (Maximize conversions, tCPA, Maximize conversion value, tROAS).

## Background Claude applies

- Primary actions feed the "Conversions" column and Smart Bidding (when included in the campaign's goals). Secondary actions only show in "All conv." and are observation only.
- Count "Every" fits purchases. Count "One" fits leads (one lead per click, even if the form is submitted twice).
- Data-driven attribution is the default for most actions. Google retired the rule-based models (first click, linear, time decay, position-based); last click remains. Any action still showing a retired model needs a look.
- Click-through window default is 30 days, configurable up to 90.
- If the Google Ads purchase tag and the GA4 imported purchase key event are both primary, every order is counted twice and Smart Bidding sees double the conversions.

## Steps Claude follows

1. Save the table to a CSV and run:
   `python3 scripts/conversion_actions_check.py <file.csv> --business ecommerce|leadgen`
   Add `--json findings.json` if the user wants the findings in a file.
2. Check the "Columns not found" line. If key columns are missing, ask the user to add them and re-export, or note those checks as skipped.
3. Compare the primary conversions total with the source of truth (store orders or CRM leads). More than the real number: look for duplicates and micro-conversions. Much fewer: look for inactive tags, short windows, consent loss, missing enhanced conversions.
4. Go through the checks table below. The script covers the rows marked (script); Claude handles the rest from the user's answers.
5. Write the output in the template below. Order fixes by impact on bidding: duplicates and micro-conversions first, then counting and values, then attribution and windows.
6. Warn that changing primary actions changes what Smart Bidding optimizes for. Recommend changing one thing at a time and expecting a learning period, especially on tCPA/tROAS campaigns.

Sample inputs: `examples/conversion_actions_ecommerce.csv` (with title rows and a Total row, like a real export) and `examples/conversion_actions_leadgen.csv` (different column names).

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Duplicate purchase (script) | Two or more primary actions in category Purchase, often "Website" plus "Google Analytics 4" source | Keep one primary. Usually the Google Ads tag (supports enhanced conversions); set the GA4 import to secondary. |
| Duplicate lead actions (script) | Several primary actions in Submit lead form with similar names | Keep one per real user action. |
| Micro-conversions primary (script) | Page view, Add to cart, Begin checkout, outbound/WhatsApp click, scroll as primary | Set to secondary. If volume is too low to bid on purchases, use a campaign-specific goal on a single test campaign instead of account default. |
| Category "Other" primary (script) | Primary action with category Other | Confirm it is a business outcome. |
| Count setting (script) | Purchase on "One", lead on "Every" | Purchases Every, leads One. |
| Retired attribution model (script) | First click, linear, time decay, position-based | Data-driven, or last click if the user prefers. |
| Short click window (script) | Under 7 days | 30 days default; 90 for long B2B cycles. |
| CRM action window (script, leadgen) | Offline import action under 90 days | Increase so late-stage uploads are accepted. |
| Inactive primary (script) | Status Inactive, No recent conversions, Unverified, Needs attention | Fix the tag or upload schedule, or remove it from primary. |
| Enhanced conversions off (script) | Website purchase/lead with EC blank, Off, Not set up | Set up EC (see google-ads-enhanced-conversions skill). |
| Purchase without value (script) | "Don't use a value" or same value on a purchase | Pass the order value dynamically. Needed for tROAS. |
| Lead form assets (script, leadgen) | Lead form source set primary | Fine at first; move bidding to qualified leads once CRM import is running. |
| CRM stages secondary (script, leadgen) | Qualified/converted lead imports set secondary | Consider making them primary once they record steady volume. |
| Campaign-specific goals | User answer | Check that overrides are intentional; a campaign bidding on a micro-goal skews spend. |
| Conversion value rules | User answer | Rules change reported values and tROAS. Confirm each rule is documented and still wanted. |
| Lead gen on Maximize conversions with junk leads | CRM shows low SQL rate | Import qualified leads (see google-ads-offline-import skill). |
| Mismatch vs store/CRM | Primary conversions vs real orders | Expect Google Ads to differ (attribution, view-through, cross-device, modeled conversions). A large gap above real numbers means duplicates. |

## Output format

```
GOOGLE ADS CONVERSION AUDIT - <account> - <date range>
Business type: <ecommerce/leadgen> | Actions reviewed: <n> | Primary: <n>

Reality check
Google Ads primary conversions: <n> | Store/CRM: <n> | Gap: <+/- %> | Likely cause: <...>

CRITICAL (affects bidding now)
1. <action> - <issue> -> <exact fix with menu path>

IMPORTANT
1. ...

MINOR / HOUSEKEEPING
1. ...

RECOMMENDED PRIMARY SET
Primary: <action list>
Secondary: <action list>

CHANGE PLAN
Week 1: <one change>, watch <metric>
Week 2: <next change>
```

## Limits

- The export does not include campaign-specific goal settings, value rules or tag code. Claude asks for those.
- The script classifies by category, source and name keywords. A custom-named action may be misread; Claude reviews the action list it prints.
- It cannot see whether two actions fire on the same event. "Duplicate" means "likely"; confirm in Tag Assistant or by checking the trigger in GTM.
- UI labels and defaults change. Confirm attribution model options and window limits in your account before advising.
