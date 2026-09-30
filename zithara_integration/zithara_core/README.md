<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Zithara Core

## Purpose
Sends ERPNext sales to Zithara (loyalty / CRM) per store, and manages each
store's Zithara credentials, including reading them from Zithara's emails.

## DocTypes

| DocType | Purpose |
| ------- | ------- |
| Zithara Settings | Single: connection, store mapping, what to send, customer fields, credential-email rules, credential requests. |
| Zithara Store | One per store: linked ERPNext store, client id / secret, status (Awaiting Credentials → Not Verified / Pending Approval → Active; Invalid Credentials; Disabled). |
| Zithara Sync Log | One record per Zithara call (Create / Cancel Order): payloads, status, attempts, retry. |
| Zithara Skipped Customer | Child table of Zithara Settings: customers never sent. |

## Customizations

| DocType | Owned by | What's customized |
| ------- | -------- | ------------------ |
| Sales Invoice, POS Invoice | ERPNext | on_submit / on_cancel: queue Create Order (fully paid) or Cancel Order (returns, cancellations). |
| Payment Entry, Journal Entry | ERPNext | on_submit: send invoices the payment settles. |
| Communication | Frappe | after_insert: read Zithara's credential emails. |
| All DocTypes | Any | after_insert: new Store DocType records get a Zithara Store + credential request (cached early exit). |

## Code layout
- `services/` — Zithara client + test mode, order payload, payments, order sync (queueing), sync runner, store resolver, store credentials, credential email reader, store onboarding, notifications.
- `customization/` — doc_events hook functions (one folder per DocType, `all/` for every DocType).
- `api/v1/store.py` — test_connection, approve, request_credentials.
- `api/v1/sync.py` — retry, check_order.
- `tasks.py` — background jobs and the hourly retry of failed syncs.
