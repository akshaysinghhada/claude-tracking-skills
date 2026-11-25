# GA4 events check

- File: examples/demo-store-events.csv
- Distinct event names: 18 | Total events: 524,803
- Site type: ecommerce (auto-detected, override with --type)

## Summary

- **High** - 2 group(s) of duplicate event names that split reporting
- **High** - missing recommended ecommerce events: add_shipping_info
- **High** - 1 funnel step(s) out of order
- **Medium** - 5 event name(s) break GA4 naming rules or convention
- **Medium** - 2 custom name(s) that should use a recommended event name
- **Low** - 1 custom event(s) with under 10 hits (tests or typos?)

## Duplicate names (differ only by case, spacing or separators)

| Variants (count) | Keep |
|---|---|
| `add_to_cart` (6,120), `AddToCart` (5,980), `add to cart` (44) | add_to_cart |
| `purchase` (1,902), `Purchase` (412) | purchase |

## Naming issues

| Event | Count | Issue |
|---|---|---|
| `AddToCart` | 5,980 | not lowercase snake_case |
| `Purchase` | 412 | not lowercase snake_case |
| `add to cart` | 44 | not lowercase snake_case; contains spaces |
| `ga_custom_test` | 3 | uses a reserved prefix (google_, ga_, firebase_) |
| `newsletter_popup_closed_without_subscribing_x` | 812 | longer than 40 characters (GA4 limit) |

## Non-standard names for recommended events

| Event | Count | Use instead | Recommended name already sent? |
|---|---|---|---|
| `AddToCart` | 5,980 | `add_to_cart` | yes, 6,120 events - same action counted twice, keep one |
| `add to cart` | 44 | `add_to_cart` | yes, 6,120 events - same action counted twice, keep one |

## Recommended events for ecommerce

- Missing (core): add_shipping_info
- Missing (useful): select_item, view_cart, remove_from_cart, refund, add_to_wishlist, view_promotion, select_promotion

## Ecommerce funnel counts

| Step | Events | % of previous |
|---|---|---|
| view_item | 52,310 | - |
| add_to_cart | 6,120 | 11.7% |
| begin_checkout | 2,980 | 48.7% |
| add_payment_info | 1,410 | 47.3% |
| purchase | 1,902 | 134.9% |

- purchase (1902) is higher than add_payment_info (1410) - check for duplicate firing or a step that does not fire on every path

## Low-volume custom events

- `ga_custom_test`: 3

_Counts are event counts, not users. Funnel % compares event counts between steps, so repeat views inflate early steps. Use Explore > Funnel exploration for user-level rates._
