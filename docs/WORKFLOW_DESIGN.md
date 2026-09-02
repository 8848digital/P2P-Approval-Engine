# WORKFLOW_DESIGN — State Machine, Conditions, Generation (literal model)

## 1. Generation overview

On `Approval Matrix` submit, `generator.setup_workflow(document_type)` runs (idempotent):
1. `ensure_actions()` — Workflow Action Masters: Approve, Hold, Reject.
2. `ensure_roles()` — `<DocType> - Approver 1..4`.
3. `ensure_amount_field()` — seed Approval Settings default (grand_total / paid_amount).
4. `remove_legacy_history_field()` — drop the old per-DocType `custom_workflow_history` Table
   field if a prior version of the engine added it (history now lives centrally in
   `Document Workflow Log`, no per-DocType schema needed — see §5).
5. `build_workflow()` — one Workflow for the DocType: 10 states + literal transitions from **all
   submitted matrices** for that DocType (all companies).
6. `reconcile_roles()` — grant/remove `<DocType> - Approver N` per the union of tier users.

`on_cancel` → rebuild the workflow without the cancelled matrix, or deactivate it if none remain.

## 2. Condition building blocks

Conditions are `company + department + amount band + this row's tier pool`. "Who can approve"
is gated by BOTH the transition **Role** (`<DocType> - Approver N`, a coarse gate) AND an
embedded `frappe.session.user in [...]` clause naming exactly the users configured for **this
row's** tier — **(revised, see below)**.

```
gate   = doc.company == '<C>' and doc.department == '<D>' [and <band>]
       and frappe.session.user in ['<pool users for this row+tier>']
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

**Revision (2026-09-01):** the client originally asked for role-only gating (no embedded pool
clause — see DECISIONS #13), but this let a same-tier approver from a *different* row/department
act on a document they weren't actually assigned to (their Role is a union across every row for
that tier — see `generator.reconcile_roles`). Confirmed live via `get_transitions()`: a user
whose only listing was in a different department's band could still Approve a document in
another department, because the condition never checked *which* row granted them the role. The
pool clause has been **restored** to close this — the Role remains a coarse gate, but the
condition now also pins eligibility to the specific row that generated the transition. No-repeat
is still **not** restored (see DECISIONS #5) — a person listed in multiple tiers can still
approve at multiple tiers.

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

IT band `<= 50000` produces (role gates coarsely, condition pins to this row's pool):
```
Pending    --Approve--> Approved 1  [PI-Approver 1]  company + dept + net_total<=50000 + user in {a,b} + get_value(...approver_2_user_1)
Pending    --Approve--> Approved    [PI-Approver 1]  company + dept + net_total<=50000 + user in {a,b} + not get_value(...approver_2_user_1)
Approved 1 --Approve--> Approved 2  [PI-Approver 2]  ... + user in {c,d} + get_value(...approver_3_user_1)
Approved 2 --Approve--> Approved    [PI-Approver 3]  ... + user in {e} + not get_value(...approver_4_user_1)   (finalize: tier 4 blank)
Pending    --Hold-->    On Hold by Approver 1 [PI-Approver 1]  company + dept + net_total<=50000 + user in {a,b}
```
- **Who** can act = the pool named in this row's tier (`{a,b}` / `{c,d}` / `{e}`), gated
  additionally by the shared role (`PI-Approver N`). An Accounts Approver-1 whose only pool
  membership is in a different department can no longer act on this IT invoice — the row-level
  pool clause (§2 revision) closes that gap.
- `Approved 2 → Approved` because IT has no Approver 4 → the runtime `not get_value(approver_4_user_1)` is true.

## 5. Runtime lifecycle (Milestone 2 — hooks, done)
- **Block on create** — if no matrix band matches `(company, department, amount)`, throw
  (`runtime._block_if_no_band`).
- **History on every transition** — insert
  `{reference_doctype, reference_name, from_state, workflow_state, user}` into
  `Document Workflow Log` (`runtime._record_history`) on **each** state change (approve, hold,
  resume, reject — not just approvals). A central, global audit log (not a per-DocType child
  table — see SPEC §5.3) — audit only, feeds no condition, since no-repeat was removed. The
  initial `create → Pending` is intentionally not logged (see DECISIONS #14). This full trail is
  what lets the dashboard attribute an on-hold document to whoever placed the hold.
