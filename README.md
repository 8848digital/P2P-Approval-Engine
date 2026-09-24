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

## Key DocTypes

| DocType | Owned by this app? | Purpose |
| ------- | ------------------ | ------- |
| Approval Matrix | Yes | Per company and document type: the amount bands and the approvers for each tier. Submitting it builds the workflow. |
| Approval Matrix Detail | Yes | One row of the matrix: a department, an amount band, and the approver pool for each tier, with what that tier may do (hold, reject, act via email). |
| Approval Settings | Yes (Single) | Which field holds the amount for each document type, and how long emailed approval links stay valid. See [SETUP.md](./SETUP.md). |
| Approval Amount Field Mapping | Yes (child) | One document type to amount field mapping inside Approval Settings. |
| Document Workflow Log | Yes | The audit trail: every state change, who made it, their remarks, and whether it came from an email link. |
| Approval Action Token | Yes | One emailed approval link: who it was issued to, its status, and how it was used. Tokens and codes are stored only as hashes. |
| Additional Approver | Yes | One ad-hoc approver added to a single document's chain in-flight, before the next pending tier — without changing the matrix or any other document. |
| Purchase Order, Purchase Invoice, Payment Entry, … | No (ERPNext core, governed) | Any submittable DocType can be placed under an Approval Matrix. The engine adds a `department` field where one is missing. |

## Features

- Define approvals as configuration: company, department, amount band and the
  people who approve at each tier, without writing workflow rules by hand.
- Generate and refresh the ERPNext Workflow, the approver roles and the
  document permissions automatically whenever a matrix is submitted or
  cancelled.
- Route each document to the right approvers by its own company, department and
  amount, and escalate tier by tier until the last configured tier approves.
- Allow a tier to hold or reject, where the matrix permits it.
- Let an eligible approver insert a one-off **additional approver** into a single
  document's chain at the current step (before the next pending tier), with
  optional hold/reject and email action, without touching the shared matrix or
  affecting any other document.
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

## Integrations

No third-party services. The app does send email (approval links and one-time
codes), so it needs an outgoing Email Account and a correct site URL — see
[SETUP.md](./SETUP.md#email-approvals-act-from-email-without-signing-in).

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app approval_engine
```

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

- ruff
- eslint
- prettier
- pyupgrade

## Maintainers

8848 Digital LLP — dhaval@8848digital.com

## License

Proprietary — Copyright (c) 2026 8848 Digital LLP. All rights reserved.
See [license.txt](license.txt) for details.
