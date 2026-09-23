<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# SETUP.md

The Approval Engine talks to external KYC providers (SurePass, FRSLab) and
needs a few Settings DocTypes filled in before its features work: **Approval
Settings**, **JFS Settings** (from the `jfs_report_customization` app),
**Payments Compliance Settings** and **Vendor Rate Comparison Settings**.

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

None.

### How to Test

1. Open **Approval Settings** and add a row mapping a target DocType (e.g.
   `Purchase Order`) to its amount field (e.g. `grand_total`).
2. Create and submit an **Approval Matrix** for that DocType and a company,
   with at least one amount band and an Approver 1 user.
3. Open a document of that DocType — the generated `<DocType> Approval`
   workflow should be active and the "Workflow Activity" sidebar should
   render on the form.

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
