# GTM Container Audit: demo-store.in

- Public ID: GTM-DEMO123
- Export time: 2026-11-20 10:15:02
- Tags: 10 | Triggers: 4 | Variables: 7 | Folders: 1 | Custom templates: 1

## Summary

- **High** - Duplicate GA4 Event tags: GA4 purchase, GA4 - Event - purchase (copy)
- **High** - GA4 event 'purchase' sent by 2 active tags: GA4 purchase, GA4 - Event - purchase (copy)
- **High** - Meta event 'Purchase' sent by 2 active tags: Meta Purchase HTML, Meta - Pixel - Purchase
- **High** - Conversion-type tag fires on all pages: Google Ads Purchase (All Pages (built-in))
- **High** - Conversion-type tag fires on all pages: Meta Purchase HTML (All Pages (built-in))
- **Medium** - Custom HTML duplicates a native/gallery tag: Meta Pixel Base
- **Medium** - Custom HTML duplicates a native/gallery tag: Meta Purchase HTML
- **Medium** - Custom HTML uses document.write: Old affiliate pixel
- **Medium** - 3 non-Google tag(s) with no consent settings
- **Medium** - 5 hardcoded ID(s) in tags
- **Low** - 2 tag(s) with no firing trigger
- **Low** - 1 paused tag(s)
- **Low** - 3 unused trigger(s)
- **Low** - 3 unused variable(s)

## Tag inventory by type

| Type | Count |
|---|---|
| GA4 Event | 3 |
| Custom HTML | 3 |
| Google Tag | 1 |
| Google Ads Conversion | 1 |
| Conversion Linker | 1 |
| Custom template: Facebook Pixel | 1 |

## Duplicate tags (same type + same ID)

| Type | ID / event | Tags |
|---|---|---|
| GA4 Event | G-DEMO12345 / purchase | GA4 purchase, GA4 - Event - purchase (copy) |

## Same event sent by more than one active tag

| Platform | Event / label | Tags | Triggers |
|---|---|---|---|
| GA4 | purchase | GA4 purchase, GA4 - Event - purchase (copy) | CE - purchase |
| Meta | Purchase | Meta Purchase HTML, Meta - Pixel - Purchase | All Pages (built-in) / CE - purchase |

## Conversion-type tags firing on all pages

| Tag | Type | Trigger |
|---|---|---|
| Google Ads Purchase | Google Ads Conversion | All Pages (built-in) |
| Meta Purchase HTML | Custom HTML | All Pages (built-in) |

## Hardcoded IDs in tags

| Tag | ID type | Value | Note |
|---|---|---|---|
| Google Tag - GA4 | GA4 / Google tag ID | G-DEMO12345 | Constant exists: {{CONST - GA4 ID}} - replace the hardcoded value |
| GA4 - Event - purchase (copy) | GA4 / Google tag ID | G-DEMO12345 | Constant exists: {{CONST - GA4 ID}} - replace the hardcoded value |
| Google Ads Purchase | Google Ads conversion ID | 123456789 | No constant variable - create one |
| Meta Pixel Base | Meta pixel ID | 1234567890123456 | Constant exists: {{Meta Pixel ID}} - replace the hardcoded value |
| Meta - Pixel - Purchase | Pixel ID | 1234567890123456 | Constant exists: {{Meta Pixel ID}} - replace the hardcoded value |

## Custom HTML tags

| Tag | Paused | Triggers | Flags |
|---|---|---|---|
| Meta Pixel Base | no | All Pages (built-in) | Meta Pixel code - use the Facebook Pixel gallery template (or one tag type, not both) |
| Meta Purchase HTML | no | All Pages (built-in) | Meta Pixel code - use the Facebook Pixel gallery template (or one tag type, not both) |
| Old affiliate pixel | yes | none | uses document.write; 'Support document.write' enabled |

## Tags with no consent settings (consentStatus NOT_SET or missing)

| Tag | Type | Action |
|---|---|---|
| Google Tag - GA4 | Google Tag | Google tag - has built-in consent checks if Consent Mode is set up; verify |
| GA4 purchase | GA4 Event | Google tag - has built-in consent checks if Consent Mode is set up; verify |
| GA4 - Event - purchase (copy) | GA4 Event | Google tag - has built-in consent checks if Consent Mode is set up; verify |
| Google Ads Purchase | Google Ads Conversion | Google tag - has built-in consent checks if Consent Mode is set up; verify |
| Meta Pixel Base | Custom HTML | Set 'Require additional consent' (e.g. ad_storage / analytics_storage) or confirm your CMP blocks it |
| Meta Purchase HTML | Custom HTML | Set 'Require additional consent' (e.g. ad_storage / analytics_storage) or confirm your CMP blocks it |
| Old affiliate pixel | Custom HTML | Set 'Require additional consent' (e.g. ad_storage / analytics_storage) or confirm your CMP blocks it |
| Conversion Linker | Conversion Linker | Google tag - has built-in consent checks if Consent Mode is set up; verify |
| GA4 - Event - generate_lead | GA4 Event | Google tag - has built-in consent checks if Consent Mode is set up; verify |

## Paused tags

| Tag | Type |
|---|---|
| Old affiliate pixel | Custom HTML |

## Tags with no firing trigger

| Tag | Type |
|---|---|
| Old affiliate pixel | Custom HTML |
| GA4 - Event - generate_lead | GA4 Event |

## Unused triggers

| Trigger | Type |
|---|---|
| Thank You Page | PAGEVIEW |
| whatsapp click | LINK_CLICK |
| All Pages DOM | DOM_READY |

## Unused variables

| Variable | Type code |
|---|---|
| Old Cart Total JS | jsm |
| env lookup | smm |
| Meta Pixel ID | c |

_Notes: built-in variables are not listed in exports and are not checked. Tags fired only through tag sequencing are not counted as orphaned. Duplicate detection for GA4 Event tags uses measurement ID + event name._
