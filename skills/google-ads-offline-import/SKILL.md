---
name: google-ads-offline-import
description: Builds Google Ads offline conversion upload files from a CRM export - click conversions keyed on GCLID, plus a hashed email/phone file for enhanced conversions for leads - with the correct Parameters:TimeZone row, time format, stage-to-action mapping, and checks for GCLIDs older than 90 days. Use when the user says "upload CRM conversions to Google Ads", "offline conversion import", "send qualified leads back to Google", "GCLID upload file", or shares a CRM/lead export with stages.
---

# Google Ads Offline Conversion Import

## What it needs

1. A CRM export (CSV) with one row per stage change you want to report:
   `gclid, email, phone, lead_created_time, lead_stage, stage_time, value, currency`
   Column names can vary (the script matches common aliases like "Deal stage", "Amount", "Created at"). `lead_created_time` (or click time) is optional but makes the 90-day check exact.
   - HubSpot, Zoho, Salesforce, LeadSquared: export the deal/lead view with the GCLID field and stage change date.
   - Spreadsheet CRMs: make sure phone and GCLID columns are formatted as text, not numbers.
2. The stage mapping: which CRM stage becomes which Google Ads conversion action, e.g. `SQL -> Qualified Lead - CRM`, `Won -> Closed Won - CRM`. The names must match the conversion action names exactly.
3. The account time zone or the time zone your CRM exports in (default Asia/Kolkata, +05:30).
4. Prerequisites in Google Ads:
   - Auto-tagging on (Admin > Account settings > Auto-tagging).
   - The site captures the `gclid` URL parameter into a hidden form field (store it in a first-party cookie if the form is not on the landing page) and the CRM saves it with the lead.
   - One conversion action per stage: Goals > Conversions > New conversion action > Import > CRM, files or other data sources > Track conversions from clicks. Set the click-through window to cover your sales cycle (up to 90 days). Menu labels change; check your account.
   - For rows without GCLID: enhanced conversions for leads turned on (Goals > Conversions > Settings), with user data captured at form submit (see google-ads-enhanced-conversions skill).

## Rules the file must follow

- First row: `Parameters:TimeZone=Asia/Kolkata` (a zone name or an offset like `+0530`; match what the template downloaded from your account uses).
- Header row for click conversions: `Google Click ID,Conversion Name,Conversion Time,Conversion Value,Conversion Currency`
- Conversion Time: `yyyy-MM-dd HH:mm:ss` in the time zone of the Parameters row, and after the click time.
- Currency: 3-letter ISO code (INR, USD, AED).
- GCLIDs older than 90 days are rejected. Uploads must also fall inside the action's click-through window.
- Same GCLID + conversion name + time twice is a duplicate. Same GCLID with the same action at different times counts again only if the action counts "Every".
- New conversion actions may need a few hours before they accept uploads, and clicks that happened before the action was created can be rejected. Create actions before the campaign traffic you want to measure.
- The hashed file headers (`Email, Phone Number, ...`) follow the common template. Download the current template from the Uploads page and rename headers if they differ.

## Steps Claude follows

1. Look at the CRM columns and stage values (ask for 5 sample rows with PII masked if the user is cautious). Agree the stage mapping with the user. Only map stages that mean business value; MQLs usually stay out.
2. Run:
   ```
   python3 scripts/build_offline_import.py crm_export.csv \
     --map "sql=Qualified Lead - CRM" --map "won=Closed Won - CRM" \
     --out-gclid gclid_upload.csv --out-hashed ec_leads_upload.csv
   ```
   Options: `--timezone +0530` or another IANA zone, `--tz-param offset` to write `+0530` in the Parameters row, `--default-currency INR`, `--default-value 5000` for stages without a deal value, `--country-code 971` for non-Indian numbers, `--upload-date 2026-11-25` to test against a fixed date.
3. Read the summary: rows written, unmapped stages, rows skipped and why. Fix the source data where possible and re-run.
4. Tell the user how to upload: Goals > Uploads (also reachable from the conversions page) > upload the file, preview, then apply. For a recurring feed, schedule from Google Sheets, HTTPS or SFTP. Upload the GCLID file to the click-conversion actions and the hashed file through the enhanced conversions for leads flow.
5. After processing, check the upload history for errors per row and the conversion action status.
6. Suggest a cadence: daily or at least weekly uploads, so Smart Bidding gets timely signals and clicks do not age past 90 days.
7. If the user wants to bid on these actions, point to the google-ads-conversion-audit skill for primary/secondary choices.

Sample input: `examples/crm_export.csv` (10 fake leads: clean rows, Indian number formats, an aged GCLID, a duplicate, a malformed GCLID, a future date, a row with no identifiers, an unmapped MQL stage, a value written as "2,40,000"). Expected output for upload date 2026-11-25: `examples/expected_gclid_upload.csv` and `examples/expected_ec_leads_upload.csv`.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| GCLID too old | ERROR "older than 90 days" | Cannot be uploaded. Upload more often. |
| Malformed GCLID | ERROR "spaces or invalid characters" or WARN "unusually short" | Re-export the raw value; check spreadsheet formatting did not change it. |
| Conversion before click | ERROR "conversion time is before the click" | Fix CRM timestamps or the time zone setting. |
| Future time | ERROR "is in the future" | Wrong time zone or date format (dd/mm vs mm/dd). |
| Unmapped stages | "Stage not mapped" list | Add a `--map` if the stage should be reported, else ignore. |
| No identifiers | WARN "no gclid, email or phone" | Capture GCLID on forms; store email/phone for leads. |
| Low GCLID coverage | Many rows go to the hashed file | Check the hidden field works on every form and for every landing page. |
| Duplicate rows | WARN "duplicate ... dropped" | CRM exported the same stage twice; fine, already removed. |
| Value missing | Blank value | Use `--default-value` or set a default on the conversion action. |
| Scientific notation phones | Phone missing from hashed output | Re-export phone column as text. |
| Wrong action name | Upload error "conversion action not found" | Use the exact name from Goals > Conversions. |

## Output format

```
OFFLINE IMPORT - <brand> - <upload date>
Time zone: <param> | Source: <CRM>
Stage mapping: <stage> -> <action>, ...

FILES
gclid_upload.csv: <n> rows | ec_leads_upload.csv: <n> rows

SKIPPED
<n> too old | <n> malformed | <n> no identifiers | <n> unmapped stage

DATA FIXES FOR THE CRM TEAM
1. ...

UPLOAD STEPS
1. Goals > Uploads > ...

NEXT: cadence <daily/weekly>, review upload diagnostics on <date>
```

## Limits

- The script does not call the Google Ads API. It builds files for manual or scheduled upload.
- It does not handle gbraid/wbraid (some iOS clicks carry these instead of gclid) or conversion adjustments (retractions, restatements). Check current Google docs for those.
- Naive CRM times are taken as already in the chosen time zone. If the CRM exports UTC without a marker, pass `--timezone +0000` or convert first.
- Only a sample of Google's validation is reproduced. The upload preview in Google Ads is the final check.
- Hashed files contain no plain email or phone, but treat them as personal data anyway; delete after upload.
