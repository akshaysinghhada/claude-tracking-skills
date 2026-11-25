// demo-store.in - reference dataLayer pushes (GA4 recommended events)
// Paste into a browser console on a test page, or run with: node examples/demo-store-datalayer.js
// Values are examples. Replace with real product and order data from the backend.

// "w" is the browser window; outside a browser (node) it is a plain object so the file can be tested.
var w = typeof window !== "undefined" ? window : {};
w.dataLayer = w.dataLayer || [];

var item = {
  item_id: "SKU-TEE-BLK-M",       // same ID as the product feed / catalog
  item_name: "Organic Cotton Tee",
  item_brand: "demo-store",
  item_category: "Men",
  item_category2: "T-Shirts",
  item_variant: "Black / M",
  price: 799.00,                  // unit price after item discount, number, INR
  discount: 200.00,               // per-unit discount, optional
  quantity: 1
};

// 1. Product page
w.dataLayer.push({ ecommerce: null });
w.dataLayer.push({
  event: "view_item",
  event_id: "vi_8f3a2c71",        // unique per event, reuse in Meta CAPI
  ecommerce: { currency: "INR", value: 799.00, items: [item] }
});

// 2. Add to cart
w.dataLayer.push({ ecommerce: null });
w.dataLayer.push({
  event: "add_to_cart",
  event_id: "atc_1b9d44e0",
  ecommerce: { currency: "INR", value: 799.00, items: [item] }
});

// 3. Checkout start
w.dataLayer.push({ ecommerce: null });
w.dataLayer.push({
  event: "begin_checkout",
  event_id: "bc_5c0e7a12",
  ecommerce: { currency: "INR", value: 799.00, coupon: "WELCOME10", items: [item] }
});

// 4. Shipping chosen
w.dataLayer.push({ ecommerce: null });
w.dataLayer.push({
  event: "add_shipping_info",
  event_id: "asi_77aa0c3d",
  ecommerce: { currency: "INR", value: 799.00, shipping_tier: "Standard", items: [item] }
});

// 5. Payment method chosen ("cod", "upi", "card", "netbanking", "wallet")
w.dataLayer.push({ ecommerce: null });
w.dataLayer.push({
  event: "add_payment_info",
  event_id: "api_0d2f9b88",
  ecommerce: { currency: "INR", value: 799.00, payment_type: "cod", items: [item] }
});

// 6. Thank-you page, once per order (guard against refresh)
var orderId = "DS-100482";
var firedKey = "purchase_sent_" + orderId;
var alreadySent = false;
try { alreadySent = !!(w.localStorage && w.localStorage.getItem(firedKey)); } catch (e) {}
if (!alreadySent) {
  w.dataLayer.push({ ecommerce: null });
  w.dataLayer.push({
    event: "purchase",
    event_id: "purchase_" + orderId,      // stable: same ID on browser pixel and CAPI
    payment_method_type: "cod",            // custom: "cod" or "prepaid"
    user_data: {                           // for enhanced conversions / advanced matching
      email: "customer@example.com",       // lowercase, trimmed
      phone_number: "+919812345678",       // E.164 with country code
      address: {
        first_name: "asha", last_name: "verma",
        city: "jaipur", region: "rajasthan", postal_code: "302001", country: "IN"
      }
    },
    ecommerce: {
      transaction_id: orderId,             // exactly as in the backend export
      currency: "INR",
      value: 799.00,                       // agreed rule: items total after discounts, excl. shipping
      tax: 121.88,
      shipping: 49.00,
      coupon: "WELCOME10",
      items: [item]
    }
  });
  try { w.localStorage && w.localStorage.setItem(firedKey, "1"); } catch (e) {}
}

// Lead gen form (non-ecommerce events: parameters at top level)
w.dataLayer.push({
  event: "generate_lead",
  event_id: "lead_2c81f0aa",
  currency: "INR",
  value: 0,                                // set an estimated lead value if you bid on value
  form_name: "contact_sales",              // custom
  user_data: { email: "lead@example.com", phone_number: "+919812345678" }
});

// SaaS sign-up
w.dataLayer.push({
  event: "sign_up",
  event_id: "su_93ad1e57",
  method: "google",                        // "email", "google", "otp"
  user_data: { email: "founder@example.com" }
});

if (typeof module !== "undefined") { module.exports = w.dataLayer; }
