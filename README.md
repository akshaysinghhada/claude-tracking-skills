<p align="center">
  <img src="https://akshaysinghhada.com/wp-content/uploads/2026/11/conversion-tracking-audit-claude-skills.png" alt="Conversion tracking audit: 15 free Claude skills for GTM, GA4, Google Ads, Meta CAPI and CRM" width="100%">
</p>

# 15 Claude Skills for Tracking

Free pack by **[Akshay Singh Hada](https://akshaysinghhada.com/akshay-singh-hada/)** ([akshaysinghhada.com](https://akshaysinghhada.com)). Check the signal before you scale.

Each folder in `skills/` is a Claude Skill: a `SKILL.md` that tells Claude exactly how to run the check, plus a Python script (standard library only) and sample files to try it on.

Full walkthrough with real outputs from every script: **[Conversion Tracking Audit: 15 Free Claude Skills](https://akshaysinghhada.com/conversion-tracking-audit/)**

## The 15 skills

| # | Skill | What it does |
|---|-------|--------------|
| 1 | [gtm-container-audit](skills/gtm-container-audit/SKILL.md) | Audits a GTM container export: paused and orphan tags, unused triggers, hardcoded IDs, duplicate tags, missing consent settings |
| 2 | [gtm-datalayer-spec](skills/gtm-datalayer-spec/SKILL.md) | Writes a developer-ready dataLayer spec (GA4 ecommerce + lead events, event_id for Meta dedup, user_data, COD notes) |
| 3 | [gtm-naming-cleanup](skills/gtm-naming-cleanup/SKILL.md) | Naming convention, folders and a rename plan for a messy container |
| 4 | [ga4-event-audit](skills/ga4-event-audit/SKILL.md) | Audits GA4 events: naming issues, duplicates, missing recommended events, retention, unwanted referrals |
| 5 | [ga4-ecommerce-qa](skills/ga4-ecommerce-qa/SKILL.md) | Funnel QA in DebugView plus GA4 vs backend order reconciliation (COD vs prepaid) |
| 6 | [utm-hygiene](skills/utm-hygiene/SKILL.md) | UTM convention matched to GA4 channel rules, a URL checker and a builder |
| 7 | [google-ads-conversion-audit](skills/google-ads-conversion-audit/SKILL.md) | Primary vs secondary, counting, attribution, double counting between Ads tag and GA4 import |
| 8 | [google-ads-enhanced-conversions](skills/google-ads-enhanced-conversions/SKILL.md) | Enhanced conversions setup (GTM or Google tag) with a normalize + hash script |
| 9 | [google-ads-offline-import](skills/google-ads-offline-import/SKILL.md) | Builds GCLID and enhanced-conversions-for-leads upload files from a CRM export |
| 10 | [meta-capi-dedup-check](skills/meta-capi-dedup-check/SKILL.md) | Checks Pixel + CAPI deduplication from browser and server event logs |
| 11 | [meta-emq-booster](skills/meta-emq-booster/SKILL.md) | Finds which customer parameters are missing or malformed and ranks the fixes for Event Match Quality |
| 12 | [meta-capi-payload-builder](skills/meta-capi-payload-builder/SKILL.md) | Builds correct, hashed Conversions API payloads from order data |
| 13 | [consent-mode-check](skills/consent-mode-check/SKILL.md) | Consent Mode v2 audit of a GTM export plus a browser checklist |
| 14 | [duplicate-conversion-finder](skills/duplicate-conversion-finder/SKILL.md) | Compares Meta, Google Ads and GA4 numbers against backend orders day by day |
| 15 | [crm-lead-feedback-loop](skills/crm-lead-feedback-loop/SKILL.md) | Maps CRM stages to Meta CRM events and Google offline conversions so bidding learns from qualified leads |

## How to install

**Claude Code (plugin, all 15 at once):**

```
/plugin marketplace add akshaysinghhada/claude-tracking-skills
/plugin install tracking-audit@claude-tracking-skills
```

**Claude Code (manual):** copy the folders into `~/.claude/skills/` (personal) or `.claude/skills/` in a project. Claude picks the right skill from your request.

**Claude app (claude.ai or desktop):** zip a single skill folder (for example `skills/gtm-container-audit`) and upload it under Settings > Capabilities > Skills, if your plan and organization allow custom skills. Then just ask, for example "audit my GTM container" and attach the export.

**No skills support?** Open any `SKILL.md`, paste it into a chat as instructions, and attach your export.

## Running the scripts yourself

Every script runs with plain Python 3, no installs:

```
cd skills/ga4-ecommerce-qa
python3 scripts/reconcile_orders.py examples/demo-store-ga4-transactions.csv examples/demo-store-backend-orders.csv
```

Each SKILL.md lists the exact command and the export it needs.

## Notes

- Sample data is fake (demo-store, demo-b2b). Never paste real access tokens into a chat.
- Ad platforms change menus and defaults often. Each skill says where to check current docs.
- Hashing scripts run locally. Customer data is not sent anywhere by these scripts.

## More free skills

- [D2C Performance Marketing Claude Skills](https://github.com/akshaysinghhada/d2c-performance-marketing-claude-skills): true break-even ROAS after COD, RTO and GST, daily Meta ads verdicts, ROAS drop diagnosis and more.
- [Free break even ROAS calculator](https://akshaysinghhada.com/break-even-roas-calculator/)

Questions or want a tracking audit? akshay@akshaysinghhada.com

## License

MIT. See [LICENSE](LICENSE).
