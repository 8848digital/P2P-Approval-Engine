<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Settlement

## Purpose
Owns the procure-to-pay settlement flow merged in from `p2p_customization`:
BRN (Business Requisition Note) proposals and their vendor comparison,
vendor KYC and onboarding, TDS/ITC compliance on Purchase Invoices, and the
Procure to Pay dashboards.

## DocTypes

| DocType | Purpose |
| ------- | ------- |
| BRN | Submittable procurement proposal comparing vendors; mapped into a Purchase Order/Invoice once approved. |
| BRN Comparision | Child of BRN: one candidate vendor (new or existing) with rate, Preferred flag, justification and MSA details. |
| BRN Item | Child of BRN: one item/service line with its sanctioned qty/rate/amount. |
| Requisition ID | Unique requisition numbers referenced by BRNs; blocked from reuse once the BRN is submitted. |
| FAQ Master | One onboarding FAQ question, synced onto the Supplier form and the vendor onboarding web form. |
| Supplier FAQ Answer | Child of Supplier: one onboarding question/answer pair. |
| Vendor FAQ Change Log | Child of Supplier: audit entry for one FAQ answer change. |
| Vendor Email | A vendor's onboarding email address(es) and the Supplier created from them. |
| Vendor Name | Master list of vendor names used as a selectable reference. |
| Portal Invoice Log | Purchase Invoice created by a supplier through the vendor portal, for async notifications. |
| KYC Type | KYC check category (e.g. GSTIN, PAN, MSME). |
| KYC Vendor | One KYC provider's configuration for one check type: credential, request template, response classification. |
| KYC Vendor Field Map | Child of KYC Vendor: maps a Supplier field to a request placeholder. |
| KYC Credential | Child of JFS Settings: a KYC provider's base URL and auth config. |
| KYC Settings Block Type | Child of JFS Settings: a KYC check that must succeed or the Supplier is put on hold. |
| KYC Settings Default Vendor | Child of JFS Settings: a KYC Vendor pre-checked in the Supplier KYC dialog. |
| KYC Validation Run | One KYC validation pass for a Supplier, with a rolled-up overall status. |
| KYC Validation Log | Child of KYC Validation Run: one vendor check attempt. |
| TDS Reference | TDS rates per Nature of Service / IT Act section; creates the matching Tax Withholding Categories. |
| Nature Of Transaction | Master list of transaction kinds (e.g. Advance, Settlement). |
| Nature of Service Reference | Child of Supplier: one selected Nature Of Transaction. |
| ITC Reversal Log | One Purchase Invoice's ITC (Input Tax Credit) reversal decision and outcome. |
| Payments Compliance Settings | Single: MSME ageing buckets, dashboard access roles, workflow-state mapping and chart settings. |
| Payments Compliance Allowed Role | Child of Payments Compliance Settings: role allowed to view the management dashboard. |
| Payments Compliance Period Closing Role | Child of Payments Compliance Settings: role allowed to run period-closing updates. |
| Payments Compliance Workflow State Mapping | Child of Payments Compliance Settings: maps a workflow state to a dashboard status bucket. |
| Vendor Rate Comparison Settings | Single: enables/configures the Purchase Order rate-comparison dialog. |

## Customizations

| DocType | Owned by | What's customized |
| ------- | -------- | ------------------ |
| Purchase Order | ERPNext | BRN link, BRN validity-window and balance checks, backdated-PO check, TDS, rate comparison, email PO to vendor. |
| Purchase Invoice | ERPNext | BRN link, BRN/PO quantity and amount checks, TDS allowance/return handling, ITC reversal status. |
| Supplier | ERPNext | Onboarding validation and workflow-based roles, FAQ answers and change log, KYC actions, MSA agreement, bank accounts/address from onboarding, link back to the BRN. |
| Supplier Quotation | ERPNext | Vendor proposal fields, requisition number, PDF import, create BRN from quotation. |
| Payment Entry | ERPNext | Blocks payment when a BRN vendor is marked "Has MSA" but no MSA attachment is uploaded. |
| Payment Request | ERPNext | MSA agreement check on the Supplier. |
| Tax Withholding Category / User | ERPNext / Frappe | Custom fields only (see `custom_fields/`). |

## Workspaces
- **Payments Compliance** — shortcut to the Payments Compliance dashboard.

## Print Formats
- **BRN** — printable BRN proposal.

## Web Forms
- **Vendor Onboarding Form** (`/vendor-onboarding-form`) — new-vendor self-registration that creates a Supplier.

## Dashboards
- **Procure To Pay** (`procure-to-pay` page) — the logged-in user's own BRN / PO / PI / Payment Order approval status and MSME ageing.
- **Procure To Pay Management** (`procure-to-pay-management` page) — company-wide view for Payments Compliance Allowed Roles, plus period-closing.
- Data for both lives in `customization/procure_to_pay/dashboard_data.py`.
