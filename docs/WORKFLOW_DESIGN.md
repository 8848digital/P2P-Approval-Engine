# WORKFLOW_DESIGN — State Machine, Conditions, Generation (literal model)

## 1. Generation overview

On `Approval Matrix` submit, `generator.setup_workflow(document_type)` runs (idempotent):
1. `ensure_actions()` — Workflow Action Masters: Approve, Hold, Reject.
2. `ensure_roles()` — `<DocType> - Approver 1..4`.
3. `ensure_amount_field()` — seed Approval Settings default (grand_total / paid_amount).
4. `ensure_history_field()` — add `custom_workflow_history` (Document Workflow Detail) to the target.
5. `build_workflow()` — one Workflow for the DocType: 10 states + literal transitions from **all
   submitted matrices** for that DocType (all companies).
6. `reconcile_roles()` — grant/remove `<DocType> - Approver N` per the union of tier users.

`on_cancel` → rebuild the workflow without the cancelled matrix, or deactivate it if none remain.

## 2. Condition building blocks (Excel-literal — per client requirements doc)

Conditions are written **exactly as the client's Excel**: `company + department + amount band`
only. "Who can approve" is gated purely by the transition **Role** (`<DocType> - Approver N`).
There is **no** embedded user-pool clause and **no** no-repeat clause (both removed at client
request — see DECISIONS #5, #13).

```
gate   = doc.company == '<C>' and doc.department == '<D>' [and <band>]
band   = ""                        # Min 0, Max 0  -> matches everything
       | doc.<amt> <= M            # Min 0, Max M
       | doc.<amt> >= N            # Min N, Max 0  (N and above; inclusive)
       | doc.<amt> >= N and doc.<amt> <= M   # Min N, Max M (both inclusive; bands start at prev.Max+1)

# runtime escalate check (Approve only): is the NEXT tier configured in the matrix row?
# readable-filter form identifies the row by matrix + department + band
next   = frappe.db.get_value('Approval Matrix Detail',
             {'parent': '<matrix>', 'department': '<D>', 'min_amount': <min>, 'max_amount': <max>},
             'approver_{N+1}_user_1')

Hold / Reject condition        = gate
Approve escalate  (-> Approved N)  = gate and next          # next tier user 1 present
Approve finalize  (-> Approved)    = gate and not next      # next tier user 1 blank
```

`<amt>` = the DocType's configured amount field (Approval Settings). The `get_value` filter
(matrix + department + band) pins the exact matched Approval Matrix Detail row — the Excel
writes this loosely as "get_value(doctype, company, department...)".

**Consequence of role-only gating:** the `<DocType> - Approver N` role is shared across
departments, so a same-tier approver from another department can act on this department's
document. Accepted per client. (Restore isolation later via department-specific roles if needed.)

## 3. Transitions generated per row × configured tier

For each configured tier L (acting from `Pending`, `Approved 1`, `Approved 2`, `Approved 3`):

| Action | Target | Condition | Emitted when |
|---|---|---|---|
| Approve (escalate) | `Approved L` | `gate and next` | always (L < 4) |
| Approve (finalize) | `Approved` | `gate and not next` | always (L < 4); top tier: `gate` only |
| Hold | `On Hold by Approver L` | `gate` | `Can Hold` set |
| Reject | `Rejected` | `gate` | `Can Reject` set |
| (from `On Hold by Approver L`) Approve escalate/finalize | as above | `gate and [not] next` | `Can Hold` set |
| (from `On Hold by Approver L`) Reject | `Rejected` | `gate` | `Can Hold` and `Can Reject` set |

- Both Approve transitions are always emitted (L<4); the runtime `next` check selects which fires.
- All transitions set `allow_self_approval = 1` (creator may act).
- **No "Release"** — from a hold, the tier's approver moves it forward (Approve) or Rejects.
- `On Hold`/`Reject` only exist where the tier permits them.

## 4. Worked example (from JFS Settlement Approval Matrix.xlsx)

Purchase Invoice @ 8848Digital. Dept "IT" bands: `[0,50000]`, `(50000,75000]`, `(75000,∞)` —
all with Approver 1 = {a,b} (hold+reject), Approver 2 = {c,d} (reject), Approver 3 = {e}.

IT band `<= 50000` produces (conditions Excel-literal — role gates who, condition gates when):
```
Pending    --Approve--> Approved 1  [PI-Approver 1]  company + dept + net_total<=50000 + get_value(...approver_2_user_1)
Pending    --Approve--> Approved    [PI-Approver 1]  company + dept + net_total<=50000 + not get_value(...approver_2_user_1)
Approved 1 --Approve--> Approved 2  [PI-Approver 2]  ... + get_value(...approver_3_user_1)
Approved 2 --Approve--> Approved    [PI-Approver 3]  ... + not get_value(...approver_4_user_1)   (finalize: tier 4 blank)
Pending    --Hold-->    On Hold by Approver 1 [PI-Approver 1]  company + dept + net_total<=50000
```
- **Who** can act = anyone holding the tier's role (`PI-Approver N`). Because that role is shared
  across departments, an Accounts Approver-1 could act on an IT invoice — accepted per client.
- `Approved 2 → Approved` because IT has no Approver 4 → the runtime `not get_value(approver_4_user_1)` is true.

## 5. Runtime lifecycle (Milestone 2 — hooks, done)
- **Block on create** — if no matrix band matches `(company, department, amount)`, throw
  (`runtime._block_if_no_band`).
- **History on approve** — append `{user, workflow_state}` to `custom_workflow_history`
  (`runtime._record_history`). Now an **audit log only** (no longer feeds any condition, since
  no-repeat was removed). Kept per the original spec's Document Workflow Detail requirement.
