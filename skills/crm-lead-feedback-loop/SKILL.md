---
name: crm-lead-feedback-loop
description: Closes the lead-gen loop by mapping CRM stages (New, Contacted, Qualified, Meeting/Site visit, Won) to events sent back to Meta (Conversions API for CRM, conversion leads optimization) and Google Ads (offline click conversions, enhanced conversions for leads), so bidding learns from qualified leads instead of form fills. Use when someone says "Meta gives me junk leads", "optimize for qualified leads", "send CRM stages back to Meta", "offline conversion import", "upload GCLID conversions", or "lead quality is bad".
---

# CRM Lead Feedback Loop

Ad platforms optimize for whatever you tell them is a conversion. If that is a form fill, they find people who fill forms. This skill sends later CRM stages back so they can find people who qualify and buy. Works for real estate, B2B, SaaS, education and high-ticket D2C.

## What it needs

1. **CRM export (CSV)** with: `lead_id, source, gclid, fbclid, meta_lead_id, email, phone, stage, stage_updated_at, value`. Export from the CRM's leads/deals list with these columns (HubSpot, Zoho, LeadSquared, Salesforce, Pipedrive and sheets-based CRMs all export CSV). A stage history export (one row per stage change) is better than current stage only. See `examples/crm_export.csv`.
2. **How match keys are captured today**:
   - Meta Lead Ads (Instant Forms): the leadgen ID must reach the CRM (native CRM integration, Zapier/Make, or the Leads API). This is `meta_lead_id`.
   - Website forms: hidden fields for `gclid` (and `gbraid`/`wbraid` if used) and `fbclid` from the landing URL, stored with the lead.
   - Email and phone from the form.
3. **The CRM's stage list** and which stage means "real lead" for the business.
4. Meta dataset ID with Conversions API access, and Google Ads admin access to create conversion actions.

## Stage mapping by vertical

| Vertical | Typical stages to send | Usual optimization target |
|---|---|---|
| Real estate | New, Contacted, Qualified, Site Visit, Booking | Site Visit (enough volume) or Qualified |
| B2B services | New, MQL, SQL, Meeting, Won | SQL or Meeting |
| SaaS | Signup, Activated, Demo, Paid | Demo or Activated |
| Education | Enquiry, Counselling, Application, Enrolled | Counselling or Application |
| High-ticket D2C | Enquiry, Consultation, Order | Consultation |

Pick a target stage that happens often enough for the platform to learn and close enough to revenue to matter. Each platform lists its own volume guidance; check current docs.

Write the map as JSON (`examples/stage_map.json`): CRM stage -> Meta event_name and Google conversion action name. `"value": true` sends the row value for that stage. Stages mapped to null (for example Junk) are counted but not sent.

## Steps Claude follows

1. Agree on the stage map with the user. Keep CRM stage names stable; renaming later breaks history on the platform side.
2. Run the mapper:
   ```
   python3 scripts/stage_mapper.py examples/crm_export.csv --map examples/stage_map.json \
       --crm-name "LeadSquared" --out-dir out/
   ```
   Flags: `--currency INR`, `--tz-offset +05:30`, `--country-code 91`, `--meta-value` (send value to Meta on value stages), `--meta-scope meta` (only send Meta rows that came from Meta: lead ID, fbclid, or a Meta source).
3. Read `out/summary.txt`: rows per stage, events written, match key coverage, issues (no match key, Meta form leads without lead ID, Google leads without gclid, unmapped stages, old events).
4. **Meta setup** (conversion leads): Events Manager > Connect data sources > CRM, or follow Meta's "Conversions API for CRM" guide; check current Meta docs for the exact flow. Each event in `meta_crm_events.jsonl` has:
   - `event_name`: your mapped stage name
   - `event_time`: unix seconds when the lead entered the stage
   - `action_source`: `system_generated`
   - `custom_data.event_source`: `crm`, `custom_data.lead_event_source`: your CRM name
   - `user_data.lead_id` (from Lead Ads) plus hashed `em`/`ph`
   Send in batches as `{"data":[...]}` to `POST https://graph.facebook.com/v<VERSION>/<DATASET_ID>/events` with the access token (keep it in an env variable). Upload at least daily. Then, in the Lead ads ad set, choose the conversion leads performance goal once Meta shows the dataset as eligible.
5. **Google Ads setup**: Goals > Conversions > New conversion action > Import > CRMs, files, or other data sources > Track conversions from clicks. Create one action per stage you send, with names that exactly match the `Conversion Name` column. Upload `google_ads_offline.csv` via Goals > Uploads, or schedule it from Google Sheets/SFTP/HTTPS, or the API. The time column includes the offset (`+0530`).
6. **Enhanced conversions for leads** (for leads without gclid): turn it on in the Google Ads conversion settings, capture hashed email/phone on form submit with the Google tag, then upload stage conversions keyed by hashed email/phone. Column names and setup differ from the gclid file; check current Google Ads docs.
7. **Bidding**: once the qualified-stage action has steady volume, make it Primary and the raw form fill Secondary in Google Ads; in Meta, choose the target stage in conversion leads setup. Change one platform at a time and give it time to relearn.
8. Automate the export and upload daily (CRM workflow, Zapier/Make, a cron job running this script).

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Meta lead ID not in CRM | Summary: `meta_form_lead_without_meta_lead_id` | Fix the Lead Ads to CRM sync so it stores the leadgen ID |
| gclid not captured | Summary: `google_lead_without_gclid`; gclid coverage low | Enable auto-tagging, add a hidden gclid field, store on the lead |
| Events too old | Summary flags >7 days (Meta) or >90 days (Google) | Upload daily; Google rejects conversions outside the click window |
| Conversion before click | Google upload errors | Use the stage timestamp, not the lead creation date of an older lead |
| Conversion name mismatch | Google upload error "conversion action not found" | Names in the CSV must match the action names exactly |
| Wrong time zone | Conversions shift a day | Keep `--tz-offset` consistent with the CRM export |
| Unhashed PII | Plain email/phone in output | The script hashes em/ph; do not edit the output by hand |
| Unmapped stages | Summary: `unmapped_stage` | Add them to the map, or map to null deliberately |
| Duplicate stage rows | Summary: `duplicate_lead_stage_rows` | Export one row per lead per stage; event_id `<lead_id>_<stage>` helps dedup |
| Optimizing on too-rare stage | Platforms show learning limited / few conversions | Move the target one stage earlier |

## Output format

```
CRM FEEDBACK LOOP PLAN: <brand> (<vertical>)
CRM: <name>   Lead sources: <Meta Lead Ads / website / Google Search ...>

STAGE MAP
| CRM stage | Meta event_name | Google conversion action | Send value? | Target? |

DATA CHECK (scripts/stage_mapper.py)
Rows: <n>  Meta events: <n>  Google rows: <n>
Match key coverage: lead_id <n>, gclid <n>, fbclid <n>, email <n>, phone <n>
Issues: <list>

SETUP STEPS
Meta: <numbered steps>
Google Ads: <numbered steps>

AUTOMATION
<how the daily export + upload will run, owner>

BIDDING CHANGE (after volume builds)
<what to switch, when, how to judge>
```

## Limits

- Meta field names here follow Meta's conversion leads / Conversions API for CRM docs as known at writing. Requirements (eligibility, minimum volumes, event age limits) change; check current Meta docs before launch.
- Meta conversion leads optimization is built around Lead Ads with `lead_id`. Sending website-lead stages with fbc/email can help matching, but the optimization options differ; check current Meta docs.
- `fbc` built from fbclid uses the stage time because the click time is not in the export. Store fbc at landing for accuracy.
- The script prepares files; it does not upload them or call any API.
- Only send data you have consent to process, and follow the user's privacy policy and local law (DPDP Act in India).
