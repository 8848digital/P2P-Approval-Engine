<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# SETUP.md

The Approval Engine has no external integrations. It does require one piece
of in-app configuration before the engine can process documents: the
**Approval Settings** Single DocType.

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

## Migrating a Site from p2p_customization

The Settlement and Vendor Portal modules (BRN, KYC, vendor portal, etc.) used
to ship in the separate `p2p_customization` app. On a site that still has it
installed, follow this order — **never run `bench uninstall-app
p2p_customization` before step 2 has run**, or Frappe deletes the BRN and
other Settlement DocTypes together with their data. Take a database backup
(`bench --site <site> backup`) first.

1. Get and install this app:
   `bench get-app approval_engine` and
   `bench --site <site> install-app approval_engine`
   (or, if it is already installed, `bench --site <site> migrate`).
2. Confirm the modules now belong to this app — in **Module Def**,
   `Settlement` and `Vendor Portal` must show App Name `approval_engine`.
   This is done automatically by `after_install` and by the
   `repoint_p2p_customization_modules` patch.
3. Only then remove the old app from the site:
   `bench --site <site> uninstall-app p2p_customization`, and drop it from
   the bench with `bench remove-app p2p_customization`.
4. Run `bench --site <site> migrate` once more and check that existing BRNs
   still open.
