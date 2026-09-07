# CCKAFWEARS \u2014 Online Shop + Admin Portal

A two-portal fashion e-commerce site built with Python (Flask):

- **Storefront** (`/`) \u2014 the public shop your customers browse and buy from.
- **Admin portal** (`/admin`) \u2014 where you add dresses, manage stock, set discounts/flash
  sales, and confirm payments/deliveries. No coding required after setup.

---

## 1. Install (one-time)

You need Python 3.10+ installed. Then, in Command Prompt / Terminal:

```
cd cckafwears
pip install -r requirements.txt
```

## 2. Run the site

```
python run.py
```

Then open in your browser:
- Shop: **http://localhost:5000/**
- Admin: **http://localhost:5000/admin**

**Default admin login:**
- Username: `admin`
- Password: `changeme123`

Log in and go to **Change password** immediately, then update **Settings** with your
real Mobile Money number, bank details, and shop address.

---

## 3. Adding dresses (no coding needed)

Admin \u2192 Products \u2192 **+ Add dress**. Fill in name, price, stock count, upload a photo,
optionally set a category, discount %, or flash sale. Click Save \u2014 it appears on the
shop instantly.

- **Stock** is only ever visible to you in the admin portal.
- The moment stock hits **0**, the dress automatically disappears from the shop.
- **Discount %** shows a strikethrough price on the shop automatically.
- **Flash sale** + an end date/time shows a "Flash sale" badge until it expires.

## 4. How orders flow

1. Customer checks out \u2192 order is created as **Pending payment**, and the delivery
   fee is calculated automatically from the distance between your shop address and
   the customer's typed address (using free OpenStreetMap geocoding \u2014 no paid API
   needed).
2. Customer sees your Mobile Money number or bank details and sends payment, then
   clicks "I've sent the payment" \u2192 status becomes **Payment review**.
3. You check your Mobile Money/bank account, and once the money has actually
   arrived, go to Admin \u2192 Orders \u2192 open the order \u2192 set status to **Paid**.
4. Arrange delivery. When the dress is handed over, set status to
   **Delivered / Sold**.

The customer can always re-check their order at `/order/<code>` or via **Track
order** in the shop nav.

---

## 5. Important limitations to know about (read this)

**Payment is currently manual-confirm.** There's no way for any website to
"see" money land in a personal Mobile Money or bank account automatically \u2014
that requires a registered **payment gateway** account. When you're ready:

- Sign up for **Paystack** or **Flutterwave** (both support MTN/Vodafone/AirtelTigo
  Mobile Money and cards, and both work in Ghana).
- They give you API keys and a webhook URL.
- I can then wire `report_payment` in `app/storefront/__init__.py` to call their
  API instead, so orders flip to "Paid" automatically the second money lands \u2014
  no manual step for you at all.

**Delivery fee is distance-based, not a live Bolt/Yango quote.** Bolt and Yango
don't offer a public API for outside websites to pull a delivery quote the way
Jumia's app does internally (Jumia uses its own private logistics system, not
Bolt/Yango's app). What this site does instead: it calculates the real straight-line
distance between your shop and the customer's address and applies your own
base fee + per-km rate (editable in Admin \u2192 Settings) \u2014 which produces the same
kind of result customers expect, without needing a courier company's private API.
If you want, once you're doing real delivery volume, we can look at Bolt for
Business or a local courier API that does support quote integration.

---

## 6. What's next

This is the first build. Natural next additions once you're ready:
- Real payment gateway (Paystack/Flutterwave) for instant auto-confirmation
- SMS/WhatsApp notifications to customers on status change
- Multiple product photos per dress, and size/color variants
- Sales analytics dashboard
- Customer accounts / order history

Just tell me which one to build next.
