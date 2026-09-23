<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# SETUP.md

The Approval Engine sends email (approval links and one-time codes), so it
needs a working **outgoing Email Account** and a correct **site URL**. It also
talks to external KYC providers (SurePass, FRSLab), and needs a few Settings
DocTypes filled in before its features work: **Approval Settings**, **JFS
Settings** (from the `jfs_report_customization` app), **Payments Compliance
Settings** and **Vendor Rate Comparison Settings**.

Required before go-live:

| # | What | Why |
| - | ---- | --- |
| 1 | [Approval Settings](#approval-settings) — amount field mapping | The engine cannot band amounts without it |
| 2 | [Outgoing Email Account](#email-approvals-act-from-email-without-signing-in) | Approval links and OTPs cannot be sent |
| 3 | [`host_name` in site config](#site-config--environment-variables) | Emailed links would point at an unreachable URL |
| 4 | [A business role per approver](#approver-roles-manual-step) | Approvers cannot save the document they approve |
| 5 | Background worker + scheduler running | Approval emails are queued and flushed by them |
| 6 | [KYC provider tokens](#kyc-providers-surepass-frslab) | Supplier KYC checks fail without them |

## Approval Settings

### Overview

Before an Approval Matrix can be submitted for a DocType, the engine needs to
know which field on that DocType holds the amount its bands compare against.
This mapping lives in the **Approval Settings** Single DocType. Without a
mapping the engine falls back to a per-DocType default (`grand_total` for
Purchase Order / Purchase Invoice, `paid_amount` for Payment Entry, else
`grand_total`); configure it explicitly for any other target DocType.

### Settings DocType Fields

Configure at **Approval Settings** (single, one per site):

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| Amount Field Mapping | Table (Approval Amount Field Mapping) | No¹ | One row per target DocType. |
| Email Link Validity (Hours) | Int | No | How long an emailed approval link stays usable, 1–720. Blank is stored as the default **72**. A link also dies as soon as it is used or the document moves state. |

Each **Amount Field Mapping** row:

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| DocType | Link (DocType) | Yes | The target DocType governed by an Approval Matrix. |
| Amount Fieldname | Data | Yes | Fieldname (not label) of the Currency/Float/Int field to band on, e.g. `grand_total`. Must exist on the DocType. |

¹ Optional only because of the built-in defaults above. A row **is** required
for any target DocType whose amount field is not one of those defaults —
submitting an Approval Matrix hard-blocks if the resolved amount field does
not exist on the DocType.

### Site Config / Environment Variables

| Key | Where | Required? | Notes |
| --- | ----- | --------- | ----- |
| `host_name` | `site_config.json` | **Yes**, when email approvals are used | Absolute public URL of the site, e.g. `https://erp.example.com`. Emailed links are built from it (`frappe.utils.get_url`). Without it Frappe falls back to the site name (`http://<site>:<port>`), which recipients cannot open. It also makes PDF rendering hang, because the renderer fetches the print's assets from that URL. |

```bash
bench --site <site> set-config host_name https://erp.example.com
```

### How to Test

1. Open **Approval Settings** and add a row mapping a target DocType (e.g.
   `Purchase Order`) to its amount field (e.g. `grand_total`).
2. Create and submit an **Approval Matrix** for that DocType and a company,
   with at least one amount band and an Approver 1 user.
3. Open a document of that DocType — the generated `<DocType> Approval`
   workflow should be active and the "Workflow Activity" sidebar should
   render on the form.


## Email approvals (act from email without signing in)

### Overview

When a tier has **Action via Email** ticked on its Approval Matrix row, each
approver of that tier is emailed a personal, single-use link plus the document
PDF. The link opens a public page where they approve, hold or reject after
confirming a one-time code sent separately to their own mailbox. No ERP login
is involved. See `README.md` for the flow.

### Required Credentials

| Credential | Where it's stored | Required? |
| ---------- | ----------------- | --------- |
| Outgoing SMTP account | **Email Account** DocType, with **Enable Outgoing** and **Default Outgoing** ticked | Yes |

Use a dedicated no-reply mailbox (e.g. `erp-noreply@example.com`), not a
personal one. Gmail/Google Workspace accounts need 2-Step Verification and an
**App Password** (`smtp.gmail.com`, port 587, TLS); Microsoft 365 mailboxes
need Authenticated SMTP enabled, or the account's **Method** set to OAuth.

Without a default outgoing account, approval emails and OTPs fail with
"Please setup default outgoing Email Account from Tools > Email Account".

### Background processes

| Process | Needed for |
| ------- | ---------- |
| Background worker (`bench worker`) | Runs the job that issues links and queues approval emails |
| Scheduler (`bench schedule`) | Flushes the Email Queue (every ~4 min by default) and expires old links daily |
| Redis queue | Carries the job from the web request to the worker |

OTP emails are sent synchronously in the web request, so they do not depend on
the worker or scheduler.

### Approver roles (manual step)

The engine grants each approver `<DocType> - Approver N`, which carries
read/write/submit on the governed DocType plus read on Department and Company.
That is **not enough on its own**: approving saves the document, and ERPNext
re-validates it as the approving user, reading linked master data.

Give every approver a normal business role for the DocType they approve:

| Approves | Role to assign manually |
| -------- | ----------------------- |
| Purchase Order | Purchase User (or Purchase Manager) |
| Purchase Invoice / Payment Entry | Accounts User (or Accounts Manager) |

Without it, the approver sees "Your ERP account is missing access to
&lt;DocType&gt;, which is needed to complete this approval" on the email page,
and the equivalent permission error in Desk.

### Email templates

`approval_engine/templates/emails/approval_action_request.html` and
`approval_action_otp.html` are plain placeholder layouts — restyle them to the
client's branding without changing the Jinja variables they use.

### How to Test

1. Tick **Approver 1 Action via Email** on an Approval Matrix row and submit
   the matrix.
2. Create a document matching that row (company, department, amount band). The
   approver should receive "Approval required: …" with the PDF attached,
   usually within a few minutes (Email Queue flush interval).
3. Open the link in a private window: the page must render without a login.
4. Request a verification code, enter it, and confirm the action.
5. Check the document: the new state, the remarks in the Workflow Activity
   sidebar and timeline, and a **Document Workflow Log** row with **Via Email
   Link** ticked.
6. Reopen the same link — it must report that it has already been used.

If nothing arrives, check **Email Queue** (row status and error), **Error Log**
(failed jobs) and **Approval Action Token** (whether links were issued at all).

## KYC Providers (SurePass, FRSLab)

### Overview

Supplier KYC checks (GSTIN, PAN, MSME, ...) call external KYC provider APIs
from the Supplier form's KYC Validation dialog; results are stored in **KYC
Validation Run**. Provider records are seeded by the `kyc_seed_records`
patch with **empty tokens** — the real tokens must be entered by hand.

### Required Credentials

| Credential | Where it's stored | Required? |
| ---------- | ------------------ | --------- |
| Provider API token | JFS Settings → Credentials (KYC Credential row) → `token` (Password) | Yes, per active credential |
| Base URL / Auth Type | JFS Settings → Credentials → `base_url`, `auth_type` (Bearer / Basic / None) | Yes |

### Settings DocType Fields

**JFS Settings → Credentials** (KYC Credential, one row per provider environment):

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| Credential Label | Data | Yes | e.g. `SurePass Sandbox`, `FRSLab Prod`. |
| Provider | Select | Yes | SurePass / FRSLab. |
| Is Active | Check | No | Only active credentials are called. Seeded rows start inactive. |
| Base URL | Data | Yes | No trailing slash. |
| Auth Type | Select | Yes | Bearer / Basic / None. |
| Header Key | Data | No | Custom auth header name, if the provider needs one. |
| Token | Password | Yes¹ | Paste the rotated provider token here — never in code. |

¹ Required whenever Auth Type is not None.

**KYC Vendor** (one record per provider + check type): `vendor_name`,
`kyc_type`, `vendor`, `http_method`, `request_style`, `endpoint_path` and
`success_path` are mandatory; `credential` links the JFS Settings credential
row to call. Its **Field Map** rows map Supplier fields to request
placeholders.

**JFS Settings** KYC behaviour: `default_kyc_vendors` (pre-checked in the
dialog), `block_supplier_on_failure_types`, `auto_hold_supplier_on_kyc_failure`,
`hold_type_to_apply`, `request_timeout_seconds`, `max_retry_attempts`,
`mask_sensitive_data_in_logs`.

### Site Config / Environment Variables

None.

### How to Test

1. In JFS Settings → Credentials, mark one sandbox credential active and
   paste its token.
2. Open a Supplier with a GSTIN or PAN, run **KYC Validation** and pick the
   matching KYC Vendor.
3. A **KYC Validation Run** is created with the provider's result.

## JFS Settings (feature toggles)

### Overview

`JFS Settings` is owned by the `jfs_report_customization` app, which must be
installed for KYC, onboarding FAQs and the vendor portal to work. It is not
yet listed in `required_apps`: BRN/PO date checks and custom-field setup
skip it when missing, but KYC needs it.

### Settings DocType Fields

| Field (fieldname) | Mandatory | Notes |
| ----------------- | --------- | ----- |
| Enable Vendor Portal (`enable_vendor_portal`) | No | Turns the vendor portal on (field added by this app). |
| Enable FAQ Section (`enable_faq_section`) | No | Shows onboarding FAQs on Supplier and the onboarding web form. |
| FAQ Manager Role (`faq_manager_role`) | No | Role allowed to manage FAQ Master. |
| Validate BRN Service Dates in PO/PI (`validate_brn_service_dates_in_po_pi`) | No | Fiscal-year check of PO/PI dates against the BRN. The hard BRN validity-window check on POs always runs. |

## Payments Compliance Settings

### Overview

Controls who can open the Procure to Pay Management dashboard, how its charts
look, and how workflow states map to dashboard buckets.

### Settings DocType Fields

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| Allowed Roles | Table (Payments Compliance Allowed Role) | Yes² | Roles that may view the management dashboard. |
| Period Closing Allowed Roles | Table (Payments Compliance Period Closing Role) | No | Roles that see "Update Account Closing". |
| Workflow State Mapping | Table (Payments Compliance Workflow State Mapping) | No | Maps each DocType's workflow states to Approved / Rejected / Pending. |
| Immediate Due Days, Bucket 2–4 End Days | Int | No | MSME ageing buckets. |
| Chart types, Auto Refresh Seconds | Select / Int | No | Display only. |

² Fail-closed: with no Allowed Roles, nobody can open the management
dashboard. The Error Log viewer on both dashboards is System Manager only.

## Vendor Rate Comparison Settings

| Field | Type | Mandatory | Notes |
| ----- | ---- | --------- | ----- |
| Allowed Role | Link (Role) | No | Only this role can open the Purchase Order rate-comparison popup. |
| Popup Trigger Mode | Select | No | Button Click Only / Auto Show on Load / Both. |

## Migrating a Site from p2p_customization

The Settlement and Vendor Portal modules (BRN, KYC, vendor portal, etc.) used
to ship in the separate `p2p_customization` app. In this app they are named
**Approval Settlement** and **Approval Vendor Portal**. On a site that still
has `p2p_customization` installed, follow this order — **never run `bench
uninstall-app p2p_customization` before step 2 has run**, or Frappe deletes
the BRN and other Settlement DocTypes together with their data. Take a
database backup (`bench --site <site> backup`) first.

1. Get and install this app:
   `bench get-app approval_engine` and
   `bench --site <site> install-app approval_engine`
   (or, if it is already installed, `bench --site <site> migrate`).
2. Confirm the modules were taken over — in **Module Def**, `Approval
   Settlement` and `Approval Vendor Portal` must show App Name
   `approval_engine`, and the old `Settlement` / `Vendor Portal` entries
   must be gone. This is done automatically by `after_install` and by the
   `repoint_p2p_customization_modules` and `rename_legacy_modules` patches.
3. Only then remove the old app from the site:
   `bench --site <site> uninstall-app p2p_customization`, and drop it from
   the bench with `bench remove-app p2p_customization`.
4. Run `bench --site <site> migrate` once more and check that existing BRNs
   still open.
