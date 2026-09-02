# IMPLEMENTATION_PLAN — Phases & Status (literal model)

Legend: ✅ done · 🔜 next · ⬜ pending

## Environment ✅
- v16 bench `frappe-bench-v16` (Node 24, Python 3.14), site `v16.dev`, app `approval_engine`.
- Developer mode on.

## Milestone 1 — Approval Matrix submit → Workflow generated ✅
- ✅ DocTypes: `Approval Matrix` (+ `Approval Matrix Detail` with Min/Max band + 4 tiers),
  `Document Workflow Log` (global audit log — replaced the old `Document Workflow Detail`
  per-DocType child table 2026-09-01), `Approval Amount Field Mapping`, `Approval Settings`.
  (`Approval Level Snapshot` removed — unused in the literal model.)
- ✅ 10 `Workflow State` masters.
- ✅ `generator.py` — literal transition generation, roles, role reconciliation,
  `remove_legacy_history_field`, `ensure_amount_field`.
- ✅ `Approval Matrix` controller — validate (unique active, contiguous tiers, contiguous
  non-overlapping bands with one `Max = 0`), `on_submit` → generate, `on_cancel` → rebuild/deactivate.
- ✅ Verified end-to-end for **Purchase Invoice** against the JFS scenario (states/allow_edit,
  roles, 30 transitions with company+dept+band+pool+no-repeat, escalate/finalize).

## Milestone 2 — Runtime (a document actually flows) ✅
- ✅ **`department` field** ensured on target DocTypes (`generator.ensure_department_field`) —
  required for routing; PO/PI don't carry one by default.
- ✅ **Role permissions**: `generator.ensure_role_permissions` grants each
  `<DocType> - Approver N` role read/write/submit on the target DocType (needed because
  reaching `Approved`/`Rejected` is a submit, and approvers must be able to open + save).
- ✅ **Block hook** (`runtime.py` → `_block_if_no_band`, wired via `hooks.py` doc_events
  `validate`): refuses to save if no Approval Matrix band matches
  `(company, department, amount)`.
- ✅ **History hook** (`runtime.py` → `_record_history`): on **every** state change
  (approve/hold/resume/reject), inserts
  `{reference_doctype, reference_name, from_state, workflow_state, user}` into the global
  `Document Workflow Log` doctype — full audit trail (no-repeat was later removed, see
  DECISIONS #5; this hook no longer feeds any condition, but powers on-hold attribution).
- ✅ **Verified end-to-end on a real Purchase Order** (`setup/e2e.py`): created →
  `Pending` → tier 1 approve → `Approved 1` → tier 2 approve → `Approved 2` → tier 3
  approve → `Approved` (docstatus 1). No-repeat confirmed (the tier-1 approver had zero
  available actions at tier 2). Block-on-no-band confirmed (unconfigured department refused).
- ✅ Fixed a **site-setup gap** unrelated to our app: ERPNext's own
  `create_address_and_contact_custom_fields()` patch was logged as executed during the
  original `bench new-site` (which hit a Redis outage partway through) but its 3 custom
  fields (`Address.tax_category`, `Address.is_your_company_address`,
  `Contact.is_billing_contact`) never actually landed — this broke the stock
  Purchase Order supplier/party-details lookup for *any* PO, independent of our engine.
  Fixed by re-running ERPNext's own installer function (not a version mismatch — both
  frappe and erpnext were already at the tip of `version-16`). See `setup/diag.py`.

## Deployment gates (added 2026-09-01) 🔴
- ⬜ **Commit to git** — the engine is currently uncommitted (only "Initialize App" exists).
- ⬜ **Package for clean install** — `after_install` hook (pre-create Workflow States) / fixtures;
  quarantine dev/test scripts (`demo`, `e2e`, `test_po`, `diag`); delete one-off `revise.py`.
- ⬜ **Regenerate-all-workflows** command/patch for app upgrades.
- ⬜ Deployment prereqs doc (Python 3.14, Node 24, version-16; approver business roles).
- Design decisions to keep an eye on: cross-department role-only gating (accepted, may revisit);
  band scheme is now inclusive + `min = prev.max + 1` (whole-number amounts).

## Milestone 3 — Generalize & harden 🔜
- ✅ **UI walkthrough** — user manually logged in as 3 different approvers (A/B/C/D) and
  drove a real Purchase Order through the full cycle in the desk UI; everything worked.
- ⬜ Purchase Invoice, Payment Entry; BRN once its DocType (with company/department/amount) exists.
- ⬜ Seed Approval Settings defaults; UI to edit amount-field mapping.
- ⬜ Fixtures/packaging for Workflow States and standard config.
- ⬜ Automated tests (see VERIFICATION.md).

## Key files (app `approval_engine`)
```
approval_engine/
  generator.py                 # ✅ literal workflow generation, role reconcile,
                                #    ensure_department_field, ensure_role_permissions,
                                #    find_band_row
  runtime.py                   # ✅ block-on-create + history-on-approve (validate hook)
  hooks.py                     # ✅ doc_events: "*" -> validate -> runtime.target_validate
  setup/scaffold.py            # ✅ DocType + Workflow State creation (idempotent)
  setup/revise.py              # one-off migration to the band model
  setup/demo.py                # PI demo bootstrap + verify
  setup/simulate.py            # transition simulator (no real documents needed)
  setup/e2e.py                 # real Purchase Order walkthrough (creates PO, applies workflow)
  setup/diag.py                # check ERPNext Address/Contact custom fields exist
  approval_engine/doctype/approval_matrix/approval_matrix.py   # ✅ validate / on_submit / on_cancel
```

## Open items
- Amount field for **BRN** (custom DocType, not yet created).
- Whether PI should default to `net_total` vs `grand_total` (currently `grand_total`, configurable).
- Approvers need a business role (e.g. Purchase Manager) for master-data read during save —
  this is normal ERPNext deployment practice, not something the engine should grant.
