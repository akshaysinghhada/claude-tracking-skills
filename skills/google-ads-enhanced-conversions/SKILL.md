---
name: google-ads-enhanced-conversions
description: Sets up and checks Google Ads enhanced conversions for web and for leads - GTM or Google tag method, which user fields to send, Google's normalization and SHA-256 hashing rules, consent, and how to verify in the Diagnostics tab - with a script that normalizes and hashes email and phone (E.164, India default). Use when the user says "set up enhanced conversions", "enhanced conversions needs attention", "hash emails for Google Ads", "user-provided data in GTM", or "enhanced conversions for leads".
---

# Google Ads Enhanced Conversions

## What it needs

- Which flavour:
  - Enhanced conversions for web: improves measurement of online conversions (purchase, form submit) by attaching hashed first-party data to the conversion tag.
  - Enhanced conversions for leads: captures hashed user data when a form is submitted, then you upload the later CRM outcome (qualified, won) with the same hashed email or phone. Pairs with the google-ads-offline-import skill.
- How tags are deployed: Google Tag Manager, gtag.js directly, or a platform integration (Shopify, WooCommerce plugin). Platform integrations often have their own toggle; check that first.
- Where the user data exists on the page at conversion time: dataLayer (best), form fields, or the thank-you page.
- Conversion action names (Goals > Conversions > Summary).
- Access: Google Ads admin or standard access, GTM publish access.
- Consent setup: whether Consent Mode is implemented, and whether the site has EEA/UK traffic.

## Fields and normalization

| Field | Format before hashing | Notes |
|---|---|---|
| Email | trim, lowercase. For gmail.com and googlemail.com, remove dots before the @ | Strongest match key. |
| Phone | E.164: `+` country code number, digits only, e.g. `+919876543210` | Indian numbers: drop leading 0, add +91. |
| First name, last name | trim, lowercase | Hash each separately. |
| Street | lowercase, trim | Hashed. |
| City, region, postal code, country | plain text, country as 2-letter code (IN) | Not hashed. If you send an address, send first name, last name, postal code and country together. |

Hashing: SHA-256, hex output. Send either plain values (the Google tag normalizes and hashes them in the browser) or pre-hashed values in the `sha256_` fields. Never hash something that is not normalized first, it will not match.

The dot-removal rule for Gmail is specific to Google. Do not apply it to Meta or other platforms.

## Setup steps Claude walks through

### 1. Turn it on in Google Ads
Goals > Conversions > Settings > Enhanced conversions for web (or open a conversion action and find the Enhanced conversions section). Turn it on, choose the method (Google Tag Manager, Google tag, or API), and accept the customer data terms. Menu placement changes; check your account.

### 2a. GTM method
1. Push user data to the dataLayer on the conversion page, before the conversion tag fires:
   ```js
   dataLayer.push({
     event: "purchase",
     user_data: { email: "riya.sharma@gmail.com", phone_number: "+919876543210",
                  first_name: "riya", last_name: "sharma", country: "IN", postal_code: "302001" }
   });
   ```
2. Create Data Layer Variables for each field (e.g. `user_data.email`).
3. Open the Google Ads Conversion Tracking tag > tick "Include user-provided data from your website" > new variable of type User-Provided Data > Manual configuration > map Email, Phone, Name, Address to the variables. "Automatic" collection exists but scrapes the page and is less reliable; "Code" lets a Custom JavaScript variable return the object.
4. If the site uses a Google tag in GTM, also allow user-provided data there if the option is present.
5. Preview in GTM, submit a real test order or form, check the tag fired with the user-provided data variable filled.

### 2b. Google tag (gtag.js) method
Before the conversion event:
```js
gtag('set', 'user_data', {
  email: 'riya.sharma@gmail.com',
  phone_number: '+919876543210',
  address: { first_name: 'riya', last_name: 'sharma', postal_code: '302001', country: 'IN' }
});
```
Pre-hashed alternative keys: `sha256_email_address`, `sha256_phone_number`, and `address.sha256_first_name`, `address.sha256_last_name`.

### 2c. Enhanced conversions for leads
1. Goals > Conversions > Settings > Enhanced conversions for leads: turn on.
2. Capture user data on the form submit (same GTM or gtag setup as above, on the lead conversion tag).
3. Store email and phone in the CRM with the lead.
4. Create an "Import" conversion action for each later stage, then upload hashed email/phone with conversion time (google-ads-offline-import skill builds the file).

### 3. Prepare or test data with the script
- Check what a value becomes after normalization and hashing:
  `python3 scripts/normalize_user_data.py --email " Riya.Sharma@GMail.com " --phone "098765 43210"`
- Clean a CRM export to plain normalized values (for testing a GTM variable or for a platform that hashes itself):
  `python3 scripts/normalize_user_data.py --in examples/leads.csv --out leads_clean.csv --no-hash --drop-pii`
- Hash a file for upload:
  `python3 scripts/normalize_user_data.py --in examples/leads.csv --out leads_hashed.csv --drop-pii`
- Other default country: `--country-code 971`.
The script flags invalid emails, phone numbers it cannot read, and Excel scientific notation (9.19876543210E+11).

### 4. Verify
- Tag Assistant or browser Network tab: the conversion request should carry an `em` parameter when user data is attached.
- Google Ads > the conversion action > Diagnostics tab: enhanced conversions status and coverage. Results take a few days after the first conversions.
- Statuses like "Needs attention" usually point to no user data, wrong format, or the terms not accepted. Read the message shown in the Diagnostics tab.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Terms not accepted | Diagnostics or settings prompt | Accept customer data terms in Conversions > Settings. |
| No user data sent | No `em` in request, low coverage in Diagnostics | Make sure dataLayer push happens before the tag fires; check variable mapping. |
| Phone without country code | Script output or GTM preview shows `98765...` | Format as `+91...` before it reaches the tag. |
| Email with spaces/uppercase pre-hashed | Hash does not match script output for the same email | Normalize first, then hash, or send plain and let the tag hash. |
| Gmail dots kept when pre-hashing | Hash of `riya.sharma@gmail.com` differs from `riyasharma@gmail.com` | Apply the Gmail rule before hashing. |
| Automatic collection picking wrong field | GTM preview shows a non-email value | Switch to Manual configuration. |
| Double tagging | Platform plugin and GTM both send the conversion | Use one implementation. |
| Consent blocking data | EEA/UK users with ad_user_data denied | Expected: data is not sent without consent. Confirm Consent Mode v2 signals are set correctly. |
| Leads: stage uploads not matching | Uploads show low match rate | Same normalization in CRM export as on the site; upload within the conversion window. |

## Consent and policy

- Follow Google's customer data policies for enhanced conversions; check the current version.
- EEA and UK traffic: Consent Mode v2 with `ad_user_data` controls whether user data can be sent. Without consent, do not send it.
- Disclose in the privacy policy that hashed contact data is shared with advertising partners for measurement. For India, check obligations under the DPDP Act with your legal adviser.
- Never send plain PII in URLs or GA4 event parameters.

## Output format

```
ENHANCED CONVERSIONS PLAN - <brand>
Type: web / leads | Method: GTM / Google tag / platform
Conversion actions: <list>

FIELDS
email: <source variable> | phone: <source variable, E.164 check> | name/address: <yes/no>

STEPS
1. ... (with menu paths and exact variable names)

TEST
- Test value: <email> -> normalized <..> -> sha256 <..>
- Expected in request: em parameter present

VERIFY BY <date>: Diagnostics tab status and coverage
RISKS: <consent, double tagging, data not on page>
```

## Limits

- The script follows Google's published rules for email and phone. Address and name handling is basic (trim, lowercase). Check Google's current docs for any added rules.
- It cannot see your site or GTM container. Claude needs screenshots or exported container JSON to check the actual setup.
- Diagnostics wording and menu locations change. Confirm in your account.
- Match rates vary by audience and data quality; there is no fixed "good" number.
