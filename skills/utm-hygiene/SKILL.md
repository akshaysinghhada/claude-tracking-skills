---
name: utm-hygiene
description: Sets a lowercase UTM naming convention matched to GA4 default channel group rules, builds tagged URLs, and validates existing links so traffic stops landing in Unassigned or Paid Other. Use when the user says "build UTMs", "check my UTM links", "why is traffic Unassigned in GA4", "UTM naming convention", or pastes a list of campaign URLs.
---

# UTM Hygiene

## What it needs

- A list of URLs to check: CSV with a `url` column (also accepts `final url`, `landing page`, `link`) or a TXT file with one URL per line. Pasted URLs work too, Claude saves them to a file.
- Where links usually live:
  - Meta Ads Manager: ad level > Destination > URL parameters (or export ads with the "URL parameters" column).
  - Google Ads: Campaign or account settings > Final URL suffix / Tracking template. Usually empty if auto-tagging is on.
  - Email tool, WhatsApp broadcast tool, LinkedIn post links, influencer briefs, QR codes.
- To see the damage in GA4: Reports > Acquisition > Traffic acquisition, primary dimension "Session default channel group", then add secondary dimension "Session source / medium" and filter for Unassigned.

## The convention

| Parameter | Rule | Examples |
|---|---|---|
| utm_source | Where the click came from. Lowercase, one word or domain. Use names in GA4's source lists so channel rules match. | facebook, instagram, google, linkedin, newsletter, whatsapp |
| utm_medium | The channel type. Pick from the table below, nothing else. | paid_social, cpc, social, email, referral, affiliate |
| utm_campaign | Campaign name, lowercase, hyphens, no spaces. Avoid the words "shop"/"shopping" unless it is a shopping campaign (see checks). | diwali-sale-2026, b2b-demo-q4 |
| utm_content | Creative or placement variant. | ugc-video-01, carousel-3 |
| utm_term | Keyword or audience/ad set. | lookalike-1pc, crm-retarget |
| utm_id | Optional campaign ID, useful for GA4 cost data import. | 120210000000 |

Medium values that GA4 maps to a default channel (GA4 matching ignores case, but reports do not, so keep everything lowercase):

| Intended channel | Source | Medium |
|---|---|---|
| Paid Social | social site (facebook, instagram, linkedin...) | matches `^(.*cp.*\|ppc\|retargeting\|paid.*)$`, e.g. paid_social, cpc, cpm, ppc |
| Paid Search | search site (google, bing...) | same paid regex, e.g. cpc |
| Paid Video | video site (youtube, vimeo) | same paid regex |
| Display | any | display, banner, expandable, interstitial, cpm |
| Paid Other | source not in any list | paid regex. Usually a mistake. |
| Organic Social | social site, OR any source with medium social, social-network, social-media, sm, social network, social media | social |
| Email | source or medium email, e-mail, e_mail, e mail | email |
| Referral | any | referral, app, link |
| Affiliates | any | affiliate |
| SMS | sms (source or medium) | sms |
| Mobile Push Notifications | any | ends with push, or contains mobile or notification |

Gotchas from the rule order:
- Campaign name containing "cross-network" goes to Cross-network.
- Campaign name matching `^(.*(([^a-df-z]|^)shop|shopping).*)$` with a paid medium goes to Paid Shopping, even with source facebook. "festive-shop-now" triggers it, "workshop" does not.
- Source facebook with medium "ads" goes to Organic Social (social source, non-paid medium). Paid spend reported as organic.
- Medium "newsletter", "whatsapp", "influencer", "qr" with an unknown source goes to Unassigned.

The full social, search, video and shopping source lists are published by Google in the GA4 help article on default channel groups. Check there for any source not in the tables above.

## Platform notes

- Meta: put this in URL parameters, not the website URL:
  `utm_source=facebook&utm_medium=paid_social&utm_campaign={{campaign.name}}&utm_content={{ad.name}}&utm_term={{adset.name}}`
  Dynamic values copy your campaign, ad set and ad names as typed, so name them lowercase with hyphens. `{{site_source_name}}` returns short codes (fb, ig, msg, an). Check in GA4 Traffic acquisition that those land in Paid Social, or keep a static utm_source.
- Google Ads: keep auto-tagging on and GA4 linked (Google Ads > Admin > Linked accounts). The gclid sets google / cpc in GA4, so no UTMs are needed. Adding manual UTMs on top only adds a second, possibly conflicting, set of values.
- UTMs must sit before any `#` fragment. GA4 does not read parameters after `#`.
- Never put UTMs on internal links of your own site. It starts a new session with the wrong source.

## Steps Claude follows

1. Ask what the links are for (paid or organic, platform) if not obvious.
2. To build: run
   `python3 scripts/utm_check.py build --url <landing url> --source <source> --medium <medium> --campaign "<name>" [--content ...] [--term ...]`
   The builder lowercases values, replaces spaces with hyphens, keeps `{{...}}` placeholders, and prints the predicted GA4 channel.
3. To validate: save the URLs to a file and run
   `python3 scripts/utm_check.py check <file> --report utm_report.csv`
4. Read the output. Group findings by the checks table below. Count how many URLs land in Unassigned, Paid Other or the wrong channel.
5. Give fixed URLs for every ERROR and WARN line (the script prints a `suggested:` URL when it can build one; fill in the rest by hand).
6. If the user has historical Unassigned traffic, explain that old sessions will not be re-classified. Options: fix links going forward, and create a custom channel group in GA4 (Admin > Data display > Channel groups) to re-bucket known bad values in reports.

Sample input: `examples/urls.csv` (13 URLs covering clean links, uppercase, spaces, wrong medium, Meta dynamic params, gclid-only, UTMs after `#`).

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Missing source or medium | ERROR "missing utm_source/utm_medium" | Add both. Without medium, GA4 cannot apply channel rules. |
| Uppercase values | WARN "has uppercase" | Lowercase. "Facebook" and "facebook" show as two rows in reports. |
| Spaces or odd characters | WARN "contains spaces" | Use hyphens in campaign/content, underscore in paid_social. |
| Uppercase parameter name | ERROR "UTM_SOURCE is not lowercase" | Parameter names must be exactly utm_source etc. |
| Unassigned | ERROR "will land in Unassigned" | Use a mapped medium from the table. |
| Paid Other | WARN "lands in Paid Other" | Use a listed source (facebook, instagram, google, linkedin). |
| Paid traffic counted organic | WARN "counts as Organic Social only because..." | Use paid_social or cpc for paid ads. |
| Shop rule hijack | WARN "campaign name triggers Paid Shopping" | Remove "shop"/"shopping" from utm_campaign. |
| UTMs after # | ERROR "UTMs are after '#'" | Move the query string before the fragment. |
| gclid plus UTMs | INFO | Remove manual UTMs from Google Ads if GA4 is linked. |
| Unverified source | note "verify ... in Google's current source list" | Check Google's list or switch to a known source. |

## Output format

```
UTM AUDIT - <brand> - <date>
URLs checked: <n> | Errors: <n> | Warnings: <n>
Predicted channels: <channel=count, ...>

PROBLEMS (fix first)
1. <url short> -> lands in <channel>. Why: <rule>. Fixed URL: <url>
...

CONVENTION FOR THIS ACCOUNT
source: <allowed values>
medium: <allowed values>
campaign: <pattern, e.g. objective-offer-yyyymm>
content: <pattern>

META URL PARAMETERS (paste at ad level)
<string>

NEXT STEPS
- <e.g. update 4 Meta ads, rename campaigns to lowercase, build GA4 custom channel group>
```

## Limits

- Channel prediction is an approximation. The script holds a partial source list; sources marked "verify" need checking against Google's current list. Google can change the rules, so confirm in the GA4 help center if results look off.
- It does not see redirects. If a link shortener or redirect strips query strings, UTMs are lost; test the final landing URL in a browser.
- It cannot fix past data. GA4 does not re-process old sessions.
- Custom channel groups in GA4 change how your reports bucket traffic, but not the default channel group itself.
