# SPEC — Approval Engine (revised: literal / band model)

## 1. Context & Objective

A **config-driven approval engine** for ERPNext v16. An administrator fills in an
**Approval Matrix** (per DocType + Company, with per-department **amount bands** and
approver tiers) and submits it. The system then **auto-generates / updates one standard
ERPNext Workflow** (states, roles, transitions, conditions) for that DocType and
**reconciles role→user assignments**. Generic — not hardcoded to specific DocTypes.

Initial targets: **BRN** (custom), **Purchase Order**, **Purchase Invoice**, **Payment Entry**.

## 2. Approach — LITERAL transitions (no snapshot)

Transitions are generated **per (Company, Department, amount band, tier, action)** with the
routing conditions written **literally** into each transition:

```
doc.company == '<Company>'  and  doc.department == '<Dept>'
  and <amount band condition>
  and frappe.session.user in ['<pool users for this row+tier>']
  and <no-repeat check>
```

- **Escalate-vs-finalize is baked in at generation time** — because we generate per row, we
  already know which tiers are configured, so `Approve` targets `Approved N` (escalate) or
  `Approved` (finalize) directly, with no runtime "is next approver configured?" lookup.
- **ERPNext evaluates conditions live** on the current document, so editing the amount while
  `Pending` automatically re-routes to the correct band — **no snapshot to freeze/re-sync.**
- **Conditions are Excel-literal** (client requirements doc): `company + department + amount
  band` only, plus a runtime escalate check on Approve. **No embedded user pool** and **no
  no-repeat** clause — both were removed at client request (see DECISIONS #5, #13).
- `<DocType> - Approver N` roles are the **sole gate** for "who can approve". The role is
  shared across departments, so a same-tier approver from another department can act on this
  department's document (accepted per client; restore isolation later via department-specific
  roles if needed).

## 3. Amount bands

Each Approval Matrix Detail row carries **one band**: `Min Amount` + `Max Amount`.

| Min | Max | Meaning | Baked condition |
|---|---|---|---|
| 0 | 0 | matches **everything** | *(no amount clause)* |
| 0 | N | 0 → N | `doc.<amt> <= N` |
| N | 0 | **N and above** (unbounded) | `doc.<amt> >= N` |
| N | M | N → M | `doc.<amt> >= N and doc.<amt> <= M` |

**Both bounds inclusive** (`Min <= amount <= Max`); `Max = 0` = unbounded above. A department
may have **multiple rows = bands**. Bands must be **contiguous, non-overlapping, start at 0,
with exactly one `Max = 0` top band**, and **each band starts at the previous band's Max + 1**
(assumes whole-number amounts — e.g. `0–100000`, then `100001–200000`). Validated.

## 4. Escalation (config-driven)

The number of approvers a document needs = the number of **configured tiers** in the matched
row (Approver N has a User 1). Amount only selects the band. From tier N, `Approve` →
`Approved N` if tier N+1 is configured, else `Approved`. Tiers must be **contiguous**
(Approver 3 requires 1 & 2).

## 5. Data Model

### 5.1 Approval Matrix (parent, submittable) — `AM-.#####`
- `company` — Link → Company
- `document_type` — Link → DocType (the target)
- `detail` — Table → **Approval Matrix Detail**
- `on_submit` → generate/refresh workflow + reconcile roles; `on_cancel` → rebuild without this
  matrix (or deactivate the workflow if none remain).
- **Validations:** one active matrix per (DocType, Company); contiguous tiers; contiguous
  non-overlapping bands with one `Max = 0` top band.

### 5.2 Approval Matrix Detail (child)
- `department` — Link → Department
- `min_amount`, `max_amount` — Currency (the band)
- For **N = 1..4**: `approver_{N}_user_1..5` (Link User, OR pool), `approver_{N}_can_hold`,
  `approver_{N}_can_reject`. *(No per-approver amount.)*

### 5.3 Document Workflow Log (global, audit only)
- `reference_doctype` (Link DocType), `reference_name` (Dynamic Link), `from_state` (Link
  Workflow State, blank on the first logged transition), `workflow_state` (Link Workflow State
  — the "to" state), `user` (Link User), `created_on` = standard `creation`.
- **Not a child table on the target DocType** — one central log doctype for every managed
  DocType, keyed by `reference_doctype` + `reference_name` (same pattern as Frappe's own
  `Version`/`Comment`). One row inserted per **workflow state change** — approve, hold, resume,
  reject — so it's a full audit trail (who moved the doc from which state to which, and when).
  The one event not logged is the initial `create → Pending` (redundant with the doc's own
  `owner`/`creation`; see DECISIONS #14). No condition reads this log — it's audit-only
  (no-repeat was removed, see DECISIONS #5) — but the on-hold dashboard query attributes a held
  document to the user of its most recent `On Hold by Approver N` row.

### 5.4 Approval Settings (Single) + Approval Amount Field Mapping (child)
- Per-DocType `amount_field` (e.g. PO/PI → `grand_total`, Payment Entry → `paid_amount`;
  set PI → `net_total` if desired). Baked into band conditions at generation.

### 5.5 Target-DocType custom fields (added by the engine)
- `workflow_state` (auto-created by Frappe on workflow save)
- `department` (Link → Department, if not already present)
- *(History no longer needs a field on the target — it lives in `Document Workflow Log`. The
  literal model needs no snapshot fields either.)*

### 5.6 Workflow States (10) & allow_edit
| State | docstatus | allow_edit |
|---|:--:|---|
| Pending | 0 | **All** |
| Approved 1 / 2 / 3 | 0 | Approver 1 / 2 / 3 |
| Approved | **1** | **All** |
| On Hold by Approver 1..4 | 0 | Approver 1..4 |
| Rejected | **1** | **All** |

### 5.7 Roles
`<DocType> - Approver 1..4` — auto-created, union of that tier's users across all rows; coarse gate only.
