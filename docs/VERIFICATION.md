# VERIFICATION — End-to-End Test Plan (literal / band model)

Prereq: site `v16.dev` with `approval_engine`, a Company, and Departments.
Bootstrap: `bench --site v16.dev execute approval_engine.setup.demo.create_demo_matrix`.

## Generation (Milestone 1 — done)
1. **Generation** — submit an Approval Matrix for Purchase Invoice with a multi-band department
   (e.g. `[0,50000]`, `(50000,75000]`, `(75000,∞)`) + a catch-all department (`0/0`). Verify one
   Workflow with 10 states, correct `allow_edit` (Pending/Approved/Rejected = All; Approved N /
   On Hold N = Approver N), the 4 roles with union-of-tier users, and transitions carrying
   company + department + band + pool + no-repeat. (`demo.verify`.)
2. **Escalate/finalize** — a row with tiers 1,2,3 must end `Approved 2 → Approved` (finalize),
   not `Approved 3`.
3. **Band conditions** — `[0,50000]` → `<= 50000`; `(50000,75000]` → `> 50000 and <= 75000`;
   `(75000,∞)` → `> 75000`; `0/0` → no amount clause.
4. **Validations** — reject overlapping/gappy bands, a non-zero top-band Max, and non-contiguous
   tiers (Approver 3 without 2).

## Runtime (Milestone 2 — to test once hooks land)
5. **Department isolation** — an IT-band approver's action on an IT invoice succeeds; an Accounts
   approver (sharing the `- Approver 1` role) is blocked by the embedded pool clause.
6. **OR-pool** — either pool user advances a tier; the other's action then disappears.
7. **No-repeat** — a user who approved tier 1 is blocked at tier 2.
8. **Amount re-route** — edit a Pending invoice's amount across a band boundary; available
   transitions change accordingly (live evaluation, no snapshot).
9. **Hold** — Hold → On Hold by Approver N; from there Approve moves forward / Reject rejects.
10. **Reject / Approve terminal** — both land on docstatus 1.
11. **No matching band** — creating an invoice whose (company, department, amount) matches no band
    is blocked.

## Handy commands
```bash
cd /Users/dg/frappe-bench-v16 && nvm use 24
bench --site v16.dev execute approval_engine.setup.demo.verify
bench --site v16.dev console
bench --site v16.dev migrate
```
