<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Mock Zithara server

A local fake of the Zithara POS API for testing the integration **without real
Zithara credentials**. Python standard library only; nothing to install. It is
repo tooling, not part of the app installed on sites.

Unlike **Test Mode** (which skips the network entirely), the app makes real HTTP
calls to the mock, so the token call, headers, retries, 401 refresh, 409
duplicates and payload checks are all exercised.

## Run

```bash
python3 scripts/mock_zithara/server.py                  # http://127.0.0.1:9099
python3 scripts/mock_zithara/server.py --store my-id:my-secret --token-ttl 600
```

Valid stores by default: `test-client-1` / `test-secret-1` and `test-client-2` / `test-secret-2`.
Every call is printed in the terminal, with errors and payload warnings.

## Point the app at it (developer-mode site only)

1. **Zithara Settings** → Enabled ✅, Test Mode ❌, **Base URL** `http://127.0.0.1:9099` → Save.
   Plain `http://` is accepted only for localhost / 127.0.0.1 on a developer-mode site.
2. **Zithara Store** → Client ID `test-client-1`, Client Secret `test-secret-1` → Save → **Test Connection** → Active.
   A wrong secret gives **Invalid Credentials**.
3. Submit a fully paid invoice → Zithara Sync Log **Success**; returns and cancels → Cancel Order logs.

Set the Base URL back to the Sandbox/Production URL when done.

## What it checks

| Endpoint | Behaviour |
| -------- | --------- |
| `GET /v1/generate-access-token` | `client_id` / `client_secret` headers → `{access_token, expires_in}`; wrong → 401 |
| any API call | raw token in `Authorization` (a `Bearer ` prefix → 401); expired token → 401 |
| `POST /v1/order` | 201 `{orderId}`; same `platform_order_id` again → 409; bad data → 200 `success:false` |
| `POST /v1/order/cancel` | `complete` or `partial` (line ids must belong to the order) |
| `GET /v1/order/{id}` | an array with the stored order, status and cancelled lines |
| `GET /v1/customer/loyalty-points` | balance (every customer starts at 5000) and redeem rule (100 points = ₹100, 100–5000 points) |
| `POST /v1/initiate-redemption` | checks limits and balance, returns a `sessionId` ("sends" the OTP) |
| `POST /v1/complete-redemption` | OTP must be `123456` (`--otp` to change); a wrong OTP uses up the session; deducts points and returns the rupee `amount` |

Order data rules: phone `91` + 10 digits, `created_at` as `YYYY-MM-DD HH:MM:SS`,
at least one line, `platform_line_item_id` a string unique across all orders,
integer `product_id`, quantity > 0. Warnings (not rejected): missing timezone,
subtotal + tax ≠ total, payments ≠ total, no transactions (real Zithara silently
drops such orders).

These rules follow Zithara's POS doc and the previous backend's live dev tests.
They are **not** a guarantee that real Zithara accepts a payload; confirm with
sandbox credentials before go-live.

## Control endpoints

```bash
curl http://127.0.0.1:9099/__mock/state                          # orders, loyalty balances + last 50 requests
curl -X POST "http://127.0.0.1:9099/__mock/fail?status=503&count=2" # next 2 calls fail (retry test)
curl -X POST http://127.0.0.1:9099/__mock/expire-tokens           # force 401 → token refresh
curl -X POST http://127.0.0.1:9099/__mock/reset                   # forget everything
```

State is in memory and lost when the server stops.
