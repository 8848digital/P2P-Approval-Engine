# HANDOFF — read this first

Single entry-point to resume the **P2P Approval Engine** (ERPNext v16) in a fresh session.
For depth, follow the links to the other docs. Last updated: 2026-09-01.

---

## 1. What this is
A config-driven approval engine. An admin fills an **Approval Matrix** (per DocType + Company,
with per-department **amount bands** and up to 4 approver tiers) and **submits** it — that one
action auto-generates a complete ERPNext **Workflow** (states, roles, transitions, conditions),
grants permissions, adds needed fields, and wires runtime hooks. Generic across submittable
DocTypes. Client: 8848 Digital / JFS Settlement.

## 2. Status at a glance
- **Milestone 1 (generate workflow from matrix): ✅ done**
- **Milestone 2 (a real document flows through it): ✅ done & verified** — full comprehensive
  test passes 15/15 on **Purchase Order** (`setup/test_po.py`).
- **Milestone 3 (deployable + generalized): 🔜 not started** — see §7.

## 3. Environment & how to run
- Bench: **`/Users/dg/frappe-bench-v16`** — frappe 16.32, erpnext 16.33, app `approval_engine`
  (all at tip of `version-16`). Git remote for frappe/erpnext is named `upstream` (not `origin`).
- Requires **Node 24** (`nvm use 24`) and **Python 3.14** (v16 hard requirements). The old v15
  bench at `/Users/dg/frappe-bench` uses Node 18 — don't confuse them.
- Site: **`v16.dev`** (default) — **local dev only**. (Dev credentials for Administrator / MariaDB
  root are kept in the maintainer's local notes, intentionally NOT committed to this repo.)
- Run the site:  `cd /Users/dg/frappe-bench-v16 && nvm use 24 && bench start` → http://v16.dev:8000
- Run the full PO test:  `bench --site v16.dev execute approval_engine.setup.test_po.run`
- Simulate transitions (no real docs):  `bench --site v16.dev execute approval_engine.setup.simulate.run`
- **Important:** `System Manager` is NOT a superuser in Frappe — only the **Administrator user**
  bypasses permissions AND holds every role, so Administrator is the wrong user to test gating with.
  Test with real approver users (`a@example.com … f@example.com`).

## 4. The design in one screen (final, after all client changes)
- **One Workflow per DocType.** 10 states: Pending, Approved 1/2/3, Approved, On Hold by
  Approver 1-4, Rejected. `Approved` & `Rejected` = docstatus 1 (submitted); rest = draft.
- **`allow_edit`:** Pending / Approved / Rejected = `All`; Approved N / On Hold by Approver N = `Approver N`.
- **Transitions are LITERAL, one per (company, department, band, tier, action).** Condition =
  **exactly the client's Excel**: `company + department + amount band`. For **Approve**, plus a
  runtime escalate check reading the matrix live:
  `frappe.db.get_value('Approval Matrix Detail', {parent, department, min_amount, max_amount}, 'approver_{N+1}_user_1')`
  (truthy → escalate to `Approved N`; blank → finalize to `Approved`).
- **Who can approve = the transition Role, AND this row's tier pool** (`<DocType> - Approver N`
  role as a coarse gate, plus `frappe.session.user in [...]` pinned to the specific row that
  generated the transition). **Revised 2026-09-01** — role-only gating (no pool clause) was
  shipped per an earlier client request, but that let a same-tier approver from a *different*
  row/department act on documents they weren't assigned to, since the role is a union across
  every row for that tier. Confirmed live via `get_transitions()`, then fixed by restoring the
  pool clause. No-repeat is still not restored (removed at client request, unrelated).
- **Amount bands:** inclusive both ends (`Min <= amount <= Max`), `Max = 0` = unbounded, each band
  starts at **prev.Max + 1** (whole-number amounts, e.g. `0–100000` then `100001–200000`).
  Contiguous, non-overlapping, exactly one `Max=0` top band — all validated.
- **On Hold:** no "Release" — from a hold, the tier's approver **Approves** (moves forward) or
  **Rejects**. Hold/Reject only exist where the tier's Can Hold/Can Reject is set.
- **History:** `Document Workflow Log` — a global doctype (`reference_doctype` + `reference_name`,
  not a child table on the target) — records each approval (audit only; feeds no condition since
  no-repeat was removed). Replaced the old per-DocType `custom_workflow_history` Table field
  2026-09-01, so integrating a new DocType no longer means adding a schema field to it.

Full detail: [WORKFLOW_DESIGN.md](WORKFLOW_DESIGN.md) · rationale/reversals: [DECISIONS.md](DECISIONS.md)

## 5. What submitting an Approval Matrix does (`generator.setup_workflow`, idempotent)
ensure Workflow States → ensure Actions → ensure Roles → **grant roles read/write/submit on the
DocType** → **grant Department read** to approver + creator roles → seed Approval Settings amount
field → remove the legacy `custom_workflow_history` field if a prior version added it → **add
`department` field if missing** → build the Workflow (states + literal transitions) → reconcile
role↔user assignments. On cancel: rebuild without this matrix, or deactivate if none remain.

## 6. Key files
```
approval_engine/
  generator.py     # workflow generation, conditions, roles, perms, dept field, band matcher
  runtime.py       # doc_events(validate): block-if-no-band + record approval history
  hooks.py         # doc_events "*": validate -> runtime.target_validate
  approval_engine/doctype/approval_matrix/approval_matrix.py   # validate (bands/tiers) / on_submit / on_cancel
  approval_engine/doctype/<approval_matrix_detail | document_workflow_log |
                            approval_amount_field_mapping | approval_settings>/
  setup/scaffold.py  # idempotent DocType + Workflow State creation (dev)
  setup/simulate.py  # transition simulator, no real docs (dev/test)
  setup/e2e.py       # real PO walkthrough (dev/test)
  setup/test_po.py   # comprehensive PO scenarios, 15 checks (dev/test)
  setup/demo.py      # demo matrix bootstrap (dev)   setup/diag.py (dev)   setup/revise.py (one-off)
docs/  README SPEC DECISIONS WORKFLOW_DESIGN IMPLEMENTATION_PLAN VERIFICATION HANDOFF
```

## 7. What's pending (Milestone 3 / deployment) — see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- **Commit to git** — the whole engine is currently uncommitted (only "Initialize App" exists). ← do first
- **Package for clean install** — add an `after_install` hook (pre-create Workflow States) and/or
  fixtures; **quarantine dev/test scripts** so `demo/e2e/test_po/diag/revise` never run on prod;
  delete the one-off `revise.py`.
- **BRN** — the client's real custom DocType doesn't exist yet (needs company/department/amount fields).
- **Generalize & verify** on Purchase Invoice (`net_total`), Payment Entry (`paid_amount`), BRN.
- **Approval Settings** amount-field mapping must be set per DocType *before* submitting its matrix
  (it's baked into conditions at generation). Add a clean UI for it.
- **Regenerate-all-workflows** command/patch (so app upgrades re-emit workflows without manual resubmit).
- **Automated tests** — convert `test_po.py` / `simulate.py` into real Frappe unit tests.
- **Deployment prereqs doc**: Python 3.14, Node 24, version-16; approvers need a business role
  (e.g. Purchase Manager) for master-data reads during save.

## 8. Known gotchas (learned the hard way)
- **Cross-department/cross-row gating was open under role-only conditions** (a user could act on
  a document via a role granted by an unrelated row) — fixed 2026-09-01 by restoring the
  per-row pool clause (§4). No longer an open item.
- **Administrator** sees every action (superuser + all roles) — never test gating as Administrator.
- **PO/PI have no native `department`** field — the engine adds it; each document must set it.
- Approvers need a **business role** for the save-time re-validation (reads Supplier/Item/etc.).
- A prior **Redis outage during the original `bench new-site`** left ERPNext's Address/Contact
  custom fields uncreated; fixed by re-running ERPNext's own installer (see `setup/diag.py` history).
  A clean install won't have this.

## 9. To resume
Read this file → skim WORKFLOW_DESIGN + DECISIONS → run `test_po.run` to confirm the site is
healthy → pick a Milestone-3 item from §7.
