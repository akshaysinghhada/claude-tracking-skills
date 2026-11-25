---
name: gtm-naming-cleanup
description: Applies a clear naming convention and folder structure to a Google Tag Manager container and produces a safe rename and cleanup plan from a container export. Use when someone says "my GTM is a mess", "rename my tags", "GTM naming convention", "organise GTM folders" or "clean up tag manager before handover".
---

# GTM Naming Cleanup

Gives every tag, trigger and variable a name that says what it is and where it sends data, groups them into folders, and plans the cleanup so nothing breaks. Renaming tags and triggers does not change how they fire. When you rename a variable, GTM updates `{{Variable}}` references to it, but confirm in Preview afterwards and check any code that mentions the old name as plain text.

## What it needs

1. **Container export (required):** GTM > Admin > Export Container > pick the latest published version > Export (`.json`).
2. Optional: the output of the `gtm-container-audit` skill, so duplicates and dead items are deleted instead of renamed.
3. Optional: the team's existing convention, if any. If they have one that is consistent, keep it and only fix outliers.

## The convention

**Tags:** `<Platform> - <Type> - <Detail>`

| Example | Notes |
|---|---|
| `GA4 - Google Tag - G-XXXXXXX` | One per GA4 property, All Pages / Initialization |
| `GA4 - Event - purchase` | Detail = exact GA4 event name, lowercase |
| `GAds - Conversion - Purchase` | Detail = conversion action name in Google Ads |
| `GAds - Conversion Linker - All Pages` | |
| `GAds - Remarketing - All Pages` | |
| `Meta - Pixel - Purchase` | Browser pixel via template; detail = Meta standard event |
| `Meta - CAPI - Purchase` | Server container tag sending Conversions API |
| `LinkedIn - Insight - All Pages` | |
| `HTML - Custom - <what it does>` | Custom HTML with no native option; review regularly |
| `Util - <Type> - <Detail>` | Helpers: cookie setters, dataLayer fixes |

Platform codes used by the script: GA4, GAds, Meta, LinkedIn, TikTok, Clarity, Hotjar, Bing, Snap, Pinterest, Floodlight, HTML, Util, CMP.

**Triggers:** `Trigger - <Code> - <Detail>`

| Code | Trigger type | Example |
|---|---|---|
| CE | Custom Event | `Trigger - CE - purchase` |
| PV / DOM / WL | Page View / DOM Ready / Window Loaded | `Trigger - PV - thank-you` |
| Click / Link | All Elements / Just Links click | `Trigger - Link - wa.me` |
| Form | Form Submission | `Trigger - Form - contact` |
| Hist, Timer, Scroll, Vis, YT, JSErr | History, Timer, Scroll Depth, Element Visibility, YouTube, JS Error | `Trigger - Scroll - 75` |
| Group | Trigger Group | `Trigger - Group - engaged visitor` |
| Init / Consent | Initialization / Consent Initialization | `Trigger - Consent - All Pages` |

**Variables:** `<Code> - <Detail>`

| Code | Variable type | Example |
|---|---|---|
| DLV | Data Layer Variable | `DLV - ecommerce.value` (detail = exact key) |
| CONST | Constant | `CONST - GA4 Measurement ID` |
| CJS | Custom JavaScript | `CJS - items to Meta contents` |
| URL, COOKIE, JSV, DOM, AEV | URL, 1st-party cookie, JS variable, DOM element, Auto-event | `COOKIE - _fbp` |
| LT / RT | Lookup / RegEx table | `LT - GA4 ID by hostname` |
| UPD | User-Provided Data | `UPD - checkout form` |

Rules: one separator style (` - `), GA4 event names stay exactly as sent, no "copy", "test", "new", "old" or dates in names (use version notes for history), and names are in English so any agency can read them.

**Folders:** GA4, Google Ads, Meta, LinkedIn (and other ad platforms), Consent, Utilities, Custom HTML - review, Triggers, Variables, Legacy - to delete. Folders by platform make it easy to hand one platform to a specialist.

## Steps Claude follows

1. Run the report:
   ```
   python3 scripts/naming_report.py <container.json> > naming-plan.md
   python3 scripts/naming_report.py <container.json> --csv > naming-plan.csv
   ```
   Markdown is for reading; CSV is a working sheet the user can tick off.
2. Review every proposed name. The script builds details from event names, dataLayer keys, trigger filters and the old name. Fix vague ones (for example `HTML - Custom - affiliate pixel` should name the affiliate network) and ask the user where the purpose is unknown.
3. Handle collisions first. Two tags proposing the same name usually means a duplicate tag. Mark one for deletion instead of numbering it.
4. Split the plan into phases:
   - Phase 1 Delete: paused tags that are not needed, orphan tags, unused triggers and variables, legacy UA tags. Do this in a workspace and publish separately so it is easy to roll back.
   - Phase 2 Rename and move into folders.
   - Phase 3 Replace hardcoded IDs with CONST variables.
5. Remind the user to export the current version as a backup before starting, and to name each published version (for example "Cleanup 1 - deletes").
6. Deliver the plan in the output format below.

## Checks

| Check | How to tell | Fix |
|---|---|---|
| Tag name pattern | Does not match `<Platform> - <Type> - <Detail>` | Rename to the proposed name |
| Trigger name pattern | Does not start with `Trigger - <Code> - ` | Rename; code comes from trigger type |
| Variable name pattern | Does not start with a type code | Rename; DLV detail must equal the dataLayer key |
| Leftover words | "copy", "test", "old", "temp" in a name | Usually a duplicate or a forgotten test; delete or rename |
| Name collisions | Two items get the same proposed name | Check for duplicate tags before renaming |
| GA4 event name drift | Tag name says one event, `eventName` sends another | Name after what is sent, and fix the event if it is wrong |
| Folder coverage | Items with no folder, or a catch-all folder like "old stuff" | Move to platform folders |
| Variable renames | Old variable name appears as plain text in code or notes | Search the export for the old name before renaming, then Preview |

## Output format

```
# GTM cleanup plan - <container name>

Backup: export version <n> saved before changes (yes/no)

## Phase 1 - delete (<count> items)
| Item | Kind | Reason |
|---|---|---|

## Phase 2 - rename and move (<count> items)
| Current name | New name | Folder |
|---|---|---|

## Phase 3 - replace hardcoded IDs
| ID | New constant | Tags to update |
|---|---|---|

## Folder structure
GA4 / Google Ads / Meta / ... (with item counts)

## Publish order
1. Phase 1 -> Preview -> publish "Cleanup 1 - deletes"
2. Phase 2 -> publish "Cleanup 2 - names"
3. Phase 3 -> Preview conversions -> publish "Cleanup 3 - constants"
```

## Limits

- The script judges names by pattern only. It cannot tell if a tag is still needed; pair it with `gtm-container-audit` or ask the user.
- Proposed details are guesses from configuration. Custom HTML tags without recognisable code get generic names.
- Built-in variables and folders' own names are not renamed.
- GTM has no bulk rename in the UI; renames are done one by one (or via the GTM API, which is outside this skill).
- Web containers only.
