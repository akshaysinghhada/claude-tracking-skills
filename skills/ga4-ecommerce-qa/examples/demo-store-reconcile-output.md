# GA4 vs backend order reconciliation

- GA4 file: examples/demo-store-ga4-transactions.csv (29 rows, 28 unique transaction IDs)
- Backend file: examples/demo-store-backend-orders.csv (28 valid orders, 2 excluded by status)
- Per-order revenue tolerance: 1.0%

## Headline

| Metric | Backend | GA4 | Gap |
|---|---|---|---|
| Orders | 28 | 28 | 0.0% |
| Revenue | 32,722.00 | 33,951.00 | -3.8% |
| GA4 purchase events (Ecommerce purchases) | - | 30 | - |
| Revenue, matched orders only | 31,225.00 | 32,952.00 | -5.5% |

- Backend orders found in GA4: 25 of 28 (89.3%)
- Missing in GA4: 3 | Extra in GA4: 3 | Duplicated IDs in GA4: 2 | Revenue mismatches: 3
- GA4 rows with transaction ID (not set): 1, revenue 2,398.00 - purchases sent without transaction_id

_Gap = (backend - GA4) / backend. Positive means GA4 is under-reporting._

## COD vs prepaid

| Payment type | Backend orders | Found in GA4 | Capture rate | Backend revenue | GA4 revenue (matched) |
|---|---|---|---|---|---|
| Prepaid | 13 | 10 | 76.9% | 11,537.00 | 11,688.00 |
| COD | 15 | 15 | 100.0% | 21,185.00 | 21,264.00 |

_A much lower capture rate for one payment type points to a flow problem (for example prepaid orders that return from the gateway to a different page)._

## Missing in GA4 (in backend, not in GA4) (3)

| Order ID | Amount | Payment |
|---|---|---|
| 1004 | 499.00 | Prepaid |
| 1015 | 499.00 | Prepaid |
| 1018 | 499.00 | Prepaid |

## Extra in GA4, order cancelled/failed/test in backend (2)

| Transaction ID | GA4 revenue |
|---|---|
| 1007 | 499.00 |
| 1022 | 499.00 |

## Extra in GA4, not in backend (test orders, wrong ID format, or other store) (1)

| Transaction ID | GA4 revenue |
|---|---|
| TEST-001 | 1.00 |

## Duplicated transaction IDs in GA4 (2)

| Transaction ID | Rows | Ecommerce purchases | GA4 revenue |
|---|---|---|---|
| 1012 | 1 | 2 | 698.00 |
| 1020 | 1 | 2 | 2,598.00 |

## Revenue mismatches over tolerance (3)

| Order ID | Backend | GA4 | Diff % |
|---|---|---|---|
| 1012 | 349.00 | 698.00 | 100.0% |
| 1020 | 1,299.00 | 2,598.00 | 100.0% |
| 1009 | 499.00 | 578.00 | 15.8% |

## Reading the result

- Revenue mismatches where GA4 is higher often mean shipping or tax is counted differently, or value is sent in paise instead of rupees. Lower often means discounts applied after the event.
- If extra IDs look like `TEST-` or come from staff, filter internal traffic and exclude test orders.
- If IDs never match at all, check the ID format (Shopify `#1001` vs `1001`, order number vs internal ID).
