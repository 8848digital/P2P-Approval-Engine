<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Approval Engine

## Overview

Approval Engine runs the procure-to-pay (P2P) approval and settlement process
on ERPNext v16. Finance sets up an **Approval Matrix** per document type and
company, and the app turns it into a standard ERPNext Workflow automatically.
On top of that it handles the procurement side: **BRN** proposals that compare
vendors before a Purchase Order or Invoice is raised, vendor onboarding and
KYC, MSA and TDS/ITC compliance checks, a vendor self-service portal, and
Procure to Pay dashboards.

The Settlement and Vendor Portal parts were merged in from the retired
`p2p_customization` app.

## Key DocTypes

| DocType | Owned by this app? | Purpose |
| ------- | ------------------ | ------- |
| Approval Matrix | Yes | Amount bands and approver tiers per document type and company; generates the approval Workflow. |
| Approval Settings | Yes | Which amount field each governed document type is banded on. |
| Document Workflow Log | Yes | Audit trail of every approval state change. |
| BRN | Yes | Business Requisition Note: a procurement proposal comparing vendors (Single, Multi or RPT), with one Preferred vendor. |
| Requisition ID | Yes | Requisition numbers a BRN is raised against; blocked from reuse once used. |
| KYC Vendor / KYC Validation Run | Yes | KYC checks (GSTIN, PAN, MSME, ...) run against a Supplier through external KYC providers. |
| TDS Reference | Yes | TDS rates per nature of service; drives Tax Withholding Categories. |
| ITC Reversal Log | Yes | Input Tax Credit reversal decisions on Purchase Invoices. |
| Payments Compliance Settings | Yes | Dashboard access, MSME ageing buckets and workflow-state mapping. |
| Vendor Portal Settings | Yes | Which documents vendors see on the portal and how. |
| Purchase Order | No (ERPNext, customized) | Linked to a BRN; blocked outside the BRN's validity window or against a draft, cancelled or closed BRN. |
| Purchase Invoice | No (ERPNext, customized) | Linked to a BRN; quantity/amount checks, TDS and ITC handling. |
| Supplier | No (ERPNext, customized) | Onboarding, FAQ answers, KYC status and MSA agreement. |
| Supplier Quotation | No (ERPNext, customized) | Vendor proposals, PDF import, and creating a BRN from a quotation. |
| Payment Entry | No (ERPNext, customized) | Payment blocked while a vendor's MSA attachment is missing. |

## Features

- Generate and keep ERPNext approval Workflows in sync from an Approval Matrix.
- Finance Overview dashboard of pending, on-hold and approved values.
- BRN vendor comparison: Single (one vendor) or Multi/RPT (at least three
  vendors, with three quotes when RPT or a related-party vendor is involved);
  exactly one Preferred vendor, whose email and justification are required
  on submit.
- Create a Purchase Order or Invoice from an approved BRN; POs are only
  allowed on a submitted, open BRN within its service dates.
- MSA tracking per BRN vendor: payment (including advances against a PO) is
  blocked until the MSA attachment is uploaded; the attachment can be added
  after the BRN is submitted.
- Vendor onboarding web form, onboarding FAQs, and KYC validation.
- TDS allowance and ITC reversal handling on Purchase Invoices.
- Vendor portal: approved proposals, orders and invoices, and invoice
  creation from a BRN within its approved quantities and rates.
- Procure to Pay dashboards for users and management.

## Integrations

- **KYC providers** (GSTIN, PAN, MSME checks) — configured through KYC Vendor
  and KYC Credential records; see [SETUP.md](./SETUP.md).

## Installation

    bench get-app approval_engine <repo_url> --branch develop
    bench --site <site_name> install-app approval_engine

Sites moving over from `p2p_customization` must follow the migration order in
[SETUP.md](./SETUP.md#migrating-a-site-from-p2p_customization).

## App Structure

See [CLAUDE.md](./CLAUDE.md) for internal module/folder layout and coding conventions.

## Maintainers

8848 Digital — dhaval@8848digital.com

## License

Proprietary — Copyright (c) 2026 8848 Digital LLP. All rights reserved.
See [license.txt](license.txt) for details.
