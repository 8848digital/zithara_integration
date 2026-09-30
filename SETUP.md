<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# SETUP.md

## Zithara (loyalty / customer CRM)

### Overview
Sends every paid sale (customer, items, totals, payments) to Zithara's POS API
and cancels it there when the sale is returned or cancelled. Zithara awards
and tracks loyalty points in its own CRM.

Every store is a separate Zithara merchant with its **own client id and
secret**. Zithara issues them by email when a store is opened.

- Sandbox: `https://dev-pos-api.zithara.com`
- Production: `https://pos-api.zithara.com`

### Required Credentials
| Credential | Where it's stored | Required? |
| ---------- | ------------------ | --------- |
| Client ID (per store) | Zithara Store → `client_id` | Yes, per store |
| Client Secret (per store) | Zithara Store → `client_secret` (encrypted) | Yes, per store |

### Settings DocType Fields
**Zithara Settings** — Connection tab

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| Enabled | Check | — | Master switch. |
| Environment | Select | — | Sandbox / Production; switches the Base URL. |
| Base URL | Data | Yes (when enabled) | Filled from the environment; can be overridden. |
| Test Mode | Check | — | Fake Zithara replies; nothing is sent. Demos/testing only. |
| Timeout (Seconds) | Int | — | Default 30. |
| Retries per Call | Int | — | Default 2. Only Zithara 5xx answers are retried. |
| Automatic Retry Attempts | Int | — | Default 5. Failed syncs (network, 429, 5xx) are retried hourly up to this many attempts. |
| Store DocType | Link | Yes | ERPNext record that represents a store. Default POS Profile (also e.g. Warehouse, Company). |
| Invoice Store Field | Data | Yes | Field on Sales Invoice / POS Invoice holding the store. Default `pos_profile`. |
| Default Store | Link | — | Zithara Store used when an invoice has no store (single-store setups). |
| Sales Invoice / POS Invoice | Check | — | Which invoice types are sent. Consolidated POS Sales Invoices are never sent twice. |
| Skip Customers | Table MultiSelect | — | e.g. the walk-in customer. |
| Phone Country Code | Data | — | Default 91; added to 10-digit mobile numbers. |
| Gender Field / Date of Birth Field | Data | — | Customer fields sent to Zithara. |

**Zithara Settings** — Store Credentials tab

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| Read Credentials from Zithara's Email → Enabled | Check | — | Reads Zithara's credential emails automatically. |
| Email Account | Link | — | Inbox that receives Zithara's emails (empty = any incoming account). |
| Allowed Senders | Small Text | Yes (when enabled) | One per line, e.g. `@zithara.com`. |
| Subject Pattern | Data | — | Optional regular expression. |
| Store / Client ID / Client Secret Pattern | Data | Client ID + Secret yes | Regular expressions; group 1 is the value. Defaults read lines like `Store Code: X`, `Client ID: X`, `Client Secret: X`. |
| Require Approval | Check | — | Default on. Checked credentials wait for an admin's **Approve**. |
| Remove Secret from Email | Check | — | Default on. The secret is blanked out of the saved email. |
| Notify Role | Link | — | Default System Manager. |
| Zithara Contact Email | Data | For requests | Where credential requests are sent. |
| Email Template | Link | — | Optional request template (the Zithara Store is `doc`). |
| Request for New Stores Automatically | Check | — | New Store DocType records get a Zithara Store and a request email. |

### Site Config / Environment Variables
None. Reading credential emails needs a normal ERPNext **Email Account** with
incoming mail enabled.

### Webhooks (if applicable)
None.

### How to Test
1. Zithara Settings → Enabled, Environment Sandbox (or **Test Mode** for no real calls) → Save.
2. Zithara Store → store code, link the POS Profile, Client ID + Secret → Save → **Test Connection** → Active.
3. Submit a POS Invoice / paid Sales Invoice → a Zithara Sync Log appears with status Success.
4. Return one item → a Cancel Order log (partial) appears.
5. Credential email: enable reading, send a test email from an allowed sender with
   `Store Code: <code>`, `Client ID: ...`, `Client Secret: ...` → the store becomes
   Pending Approval → **Approve**.
