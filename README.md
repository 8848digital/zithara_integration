<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Zithara Integration

## Overview
Custom Frappe/ERPNext app by 8848 Digital LLP that connects an ERPNext site to
[Zithara](https://zithara.com), a loyalty and customer CRM platform. Every paid
sale is sent to Zithara with the customer, items, totals and payments; returns
and cancellations cancel it there. Zithara awards and tracks loyalty points in
its own CRM; customers can redeem their points on an invoice with an OTP. Generic: works for any client and any number of stores.

## Key DocTypes
- **Zithara Settings** — connection (sandbox / production / test mode), which ERPNext record is a store, what to send, and how store credentials are handled.
- **Zithara Store** — one per store (each store is its own Zithara merchant): linked ERPNext store, client id / secret, status.
- **Zithara Sync Log** — every call to Zithara with its payload, answer, status and retries.
- **Zithara Redemption** — every loyalty-points redemption: invoice, customer, points, rupee value, status (OTP Sent / Redeemed / Failed).

## Features
- **Paid sales go to Zithara** — Sales Invoice and POS Invoice are sent once fully paid (at submit, or when the settling Payment Entry or Journal Entry is submitted), with one transaction per payment mode. Zithara ignores orders without payments, so unpaid invoices wait.
- **Returns and cancellations** — a return cancels the returned lines (or the whole order when everything comes back); cancelling a sent invoice cancels the order.
- **Never blocks a sale** — calls run in the background; failures are logged, retried hourly (network / 5xx) and can be retried from the log.
- **Per-store credentials** — each store's client id / secret is kept encrypted on its Zithara Store and checked with **Test Connection**; tokens are cached per store.
- **No manual credential entry** — Zithara's credential emails are read automatically (allowed senders only), checked live with Zithara, saved on the right store, removed from the email, and held for one-click **Approve**.
- **Credential requests** — **Request Credentials** emails Zithara for a store; with automatic requests on, a new ERPNext store gets its Zithara Store and request email by itself. Zithara's reply is matched to the store through the email thread.
- **Loyalty points** — **Zithara → Loyalty Points** on an invoice shows the customer's balance and the redeem rule.
- **Redeem points with OTP** — **Zithara → Redeem Points** on a saved draft invoice: Zithara texts the customer an OTP, the cashier enters it, and the rupee value Zithara confirms is added to the invoice's additional discount. OTP calls are never retried (each sends an SMS), a new OTP waits a minute, and a wrong OTP needs a new one. Once redeemed, the discount can't be reduced, the customer can't change and the draft can't be deleted (the points are already spent). The order sent to Zithara is marked with the redeemed amount.
- **Test Mode** — fake Zithara replies for demos and training; nothing is sent (5000 points, OTP 123456).

## Integrations
- **Zithara POS API** — see [SETUP.md](./SETUP.md#zithara-loyalty--customer-crm)

## Installation

Requires Frappe v16 and ERPNext v16.

    bench get-app zithara_integration https://github.com/8848digital/zithara_integration --branch integration-master
    bench --site <site_name> install-app zithara_integration

## App Structure
See [CLAUDE.md](./CLAUDE.md) for internal module/folder layout and coding conventions.

## Contributing
This app uses `pre-commit` for formatting and linting and Conventional Commits:

    cd apps/zithara_integration
    pre-commit install
