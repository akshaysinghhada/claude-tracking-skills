# GTM naming report

- Items checked: 21 (tags 10, triggers 4, variables 7)
- Breaking the convention: 16
- Existing folders: old stuff

## Tags to rename (8)

| Current name | Proposed name | Current folder | Proposed folder |
|---|---|---|---|
| Google Tag - GA4 | GA4 - Google Tag - G-DEMO12345 | - | GA4 |
| GA4 purchase | GA4 - Event - purchase | old stuff | GA4 |
| GA4 - Event - purchase (copy) | GA4 - Event - purchase (2) | - | GA4 |
| Google Ads Purchase | GAds - Conversion - Purchase | - | Google Ads |
| Meta Pixel Base | Meta - Pixel HTML - Base | - | Meta |
| Meta Purchase HTML | Meta - Pixel HTML - Purchase | - | Meta |
| Old affiliate pixel (paused) | HTML - Custom - affiliate pixel | old stuff | Custom HTML - review |
| Conversion Linker | GAds - Conversion Linker - All Pages | - | Google Ads |

## Triggers to rename (4)

| Current name | Proposed name | Current folder | Proposed folder |
|---|---|---|---|
| CE - purchase | Trigger - CE - purchase | - | Triggers |
| Thank You Page | Trigger - PV - thank-you | - | Triggers |
| whatsapp click | Trigger - Link - wa.me | - | Triggers |
| All Pages DOM | Trigger - DOM - All Pages | - | Triggers |

## Variables to rename (4)

| Current name | Proposed name | Current folder | Proposed folder |
|---|---|---|---|
| dlv transaction id | DLV - ecommerce.transaction_id | - | Variables |
| Old Cart Total JS | CJS - Cart Total | - | Variables |
| env lookup | LT - env | - | Variables |
| Meta Pixel ID | CONST - Meta Pixel ID | - | Variables |

## Name collisions

These proposed names clashed with another item and got a number. A clash between two tags usually means a duplicate tag - check before renaming.

- Tag: GA4 - Event - purchase (copy) -> GA4 - Event - purchase (2)

_Proposed names are a starting point. Detail parts come from event names, dataLayer keys and trigger filters; edit them where the meaning is unclear._
