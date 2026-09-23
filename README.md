<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Approval Engine

## Overview

Approval Engine turns a simple configuration table into a full approval
workflow for any submittable ERPNext document. Finance and procurement teams
define, per company and department, which amounts need which approvers — up to
four tiers, five people per tier — and the app generates and maintains the
matching ERPNext Workflow, roles and permissions automatically. Approvers act
either in the ERP or straight from their email, and every decision is recorded
with who acted, when, and why.

On top of the approval engine it runs the procure-to-pay (P2P) side: **BRN**
proposals that compare vendors before a Purchase Order or Invoice is raised,
vendor onboarding and KYC, MSA and TDS/ITC compliance checks, a vendor
self-service portal, and Procure to Pay dashboards. The Approval Settlement
and Approval Vendor Portal modules were merged in from the retired
`p2p_customization` app.

## Key DocTypes

| DocType | Owned by this app? | Purpose |
| ------- | ------------------ | ------- |
| Approval Matrix | Yes | Per company and document type: the amount bands and the approvers for each tier. Submitting it builds the workflow. |
| Approval Matrix Detail | Yes | One row of the matrix: a department, an amount band, and the approver pool for each tier, with what that tier may do (hold, reject, act via email). |
| Approval Settings | Yes (Single) | Which field holds the amount for each document type, and how long emailed approval links stay valid. See [SETUP.md](./SETUP.md). |
| Approval Amount Field Mapping | Yes (child) | One document type to amount field mapping inside Approval Settings. |
| Document Workflow Log | Yes | The audit trail: every state change, who made it, their remarks, and whether it came from an email link. |
| Approval Action Token | Yes | One emailed approval link: who it was issued to, its status, and how it was used. Tokens and codes are stored only as hashes. |
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
| Purchase Order, Purchase Invoice, Payment Entry and any other submittable DocType | No (ERPNext core, governed) | Can be placed under an Approval Matrix. The engine adds a `department` field where one is missing. |

## Features

- Define approvals as configuration: company, department, amount band and the
  people who approve at each tier, without writing workflow rules by hand.
- Generate and refresh the ERPNext Workflow, the approver roles and the
  document permissions automatically whenever a matrix is submitted or
  cancelled.
- Route each document to the right approvers by its own company, department and
  amount, and escalate tier by tier until the last configured tier approves.
- Allow a tier to hold or reject, where the matrix permits it.
- Block documents that no configured band covers, so nothing slips through
  unapproved.
- Capture approver remarks on every action, with a **mandatory reason for
  rejection**, enforced on the server whichever way the action is taken.
- Let approvers **act from email without signing in**: a personal single-use
  link plus the document PDF, confirmed with a one-time code sent separately to
  the approver's own mailbox. Links die on use, on expiry, or as soon as the
  document moves on.
- Show the approver chain and its live status in the sidebar of every governed
  document, including remarks and whether the action came from email.
- Keep a complete audit trail of every transition, plus a record of every
  emailed link and how it was used.
- Report on pending, on-hold and approved value per document type in the
  Finance Overview dashboard.
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

- **Email** — approval links and one-time codes need an outgoing Email Account
  and a correct site URL; see
  [SETUP.md](./SETUP.md#email-approvals-act-from-email-without-signing-in).
- **KYC providers** (GSTIN, PAN, MSME checks) — configured through KYC Vendor
  and KYC Credential records; see [SETUP.md](./SETUP.md).

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app approval_engine
```

Sites moving over from `p2p_customization` must follow the migration order in
[SETUP.md](./SETUP.md#migrating-a-site-from-p2p_customization).

## App Structure

See [CLAUDE.md](./CLAUDE.md) for internal module/folder layout and coding
conventions.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/approval_engine
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- black (Frappe fork) and isort
- flake8
- prettier and eslint
- check-max-lines (Python files at most 250 lines)

## Maintainers

8848 Digital LLP — dhaval@8848digital.com

## License

Proprietary — Copyright (c) 2026 8848 Digital LLP. All rights reserved.
See [license.txt](license.txt) for details.
