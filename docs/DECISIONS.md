# DECISIONS — Requirement Q&A Log

> Revised after the `JFS Settlement Approval Matrix.xlsx` scenario. Rows marked **(revised)**
> replace earlier choices.

| # | Question | Decision |
|---|----------|----------|
| 1 **(revised)** | How does amount decide approvers? | **Config-driven escalation.** The number of approvers = number of configured tiers in the matched row. **Amount selects the band/row, it does NOT decide how many approvers.** |
| 1a **(new)** | Amount model | Per-row **Min Amount + Max Amount** band (no per-approver amount). `Max = 0` = unbounded above; `Min 0 / Max 0` = matches everything. Lower bound exclusive, upper inclusive. |
| 1b **(new)** | Multiple rows per department? | **Yes — amount bands.** Must be contiguous, non-overlapping, start at 0, exactly one `Max = 0` top band (validated). |
| 2 | Terminal states | `Approved` **and** `Rejected` = docstatus 1 (submitted). Others = draft. |
| 3 **(revised)** | On Hold behaviour | **No "Release".** From `On Hold by Approver N`: **Approve → forward** (`Approved N`/`Approved`) or **Reject**. Any user in tier N's pool may act (not only the person who held it). |
| 4 | Tier = OR pool | Any one of a tier's ≤5 users satisfies that tier. |
| 5 **(REMOVED by client)** | No-repeat | ~~A person may approve a document at most once.~~ **Removed** — the client's Excel requirements doc has no such clause. History is still *recorded* (audit, now in the global `Document Workflow Log` doctype — see #14), but no longer gates any transition. A person listed in multiple tiers CAN now approve multiple tiers. |
| 6 | Self-approval | Allowed (`allow_self_approval = 1`). |
| 7 **(re-revised 2026-09-01, see #13)** | Enforcement approach | **Literal transitions**, conditions = `company + department + amount band + this row's tier pool` (+ for Approve, a runtime escalate check — see #1c). "Who can approve" is gated by the transition Role `<DocType> - Approver N` **AND** an embedded `frappe.session.user in [...]` pool clause pinned to the row that generated the transition. |
| 1c **(new — escalate check)** | How Approve chooses escalate vs finalize | At **runtime**, each Approve emits BOTH transitions; the condition reads the matrix live: `frappe.db.get_value('Approval Matrix Detail', <row>, 'approver_{N+1}_user_1')` (truthy → escalate to `Approved N`; blank → finalize to `Approved`). Matches the Excel's `frappe.get_value(... approver N+1 user 1 (not) blank)`. |
| 8 | No matching band for a document | **Block** (Milestone 2 create hook). |
| 9 **(revised)** | Matrix edit / cancel & in-flight docs | Regenerate the (single, live) workflow on submit; reconcile roles. Because conditions are evaluated live and there is **no snapshot**, an amount edit auto re-routes — ERPNext-native, no migration. Cancel → rebuild without this matrix, or deactivate if none remain. |
| 10 | Amount field | Configurable per DocType via **Approval Settings** (PO/PI → `grand_total`, Payment Entry → `paid_amount`; PI → `net_total` if desired). |
| 11 **(revised)** | State `allow_edit` | Pending / Approved / Rejected = **All**; Approved N = **Approver N**; On Hold by Approver N = **Approver N**. |
| 12 **(new)** | Tiers | Exactly 4 tiers × 5 users; tiers must be **contiguous** (Approver 3 requires 1 & 2). |
| 13 **(re-reverted 2026-09-01 — technical fix, needs client confirmation)** | Department isolation blocker | The shared `- Approver N` role lets another department's same-tier approver act on this department's document. This was originally **fixed** by embedding the per-row pool in the condition, then **removed** at client request to match their Excel literally (role-only gating, see #7). Role-only gating turned out to leak further than intended — because a tier's role is a *union* across every row for that DocType, a user could act on a document via a row they were never assigned to (confirmed live via `get_transitions()`, not just a theoretical cross-department case — could be any other row of the same tier, same department or not). The pool clause has been **restored** as a bug fix, since this exceeded what the client actually asked for. Flag to the client that gating is once again row-scoped, not purely role-scoped. |
| 14 **(new)** | History storage | **Moved off the target DocType** (2026-09-01). Previously a `custom_workflow_history` Table field (child doctype `Document Workflow Detail`) was added to every integrated DocType. Now a single global doctype `Document Workflow Log` (`reference_doctype` + `reference_name` + `from_state`/`workflow_state`/`user`, same pattern as Frappe's own `Version`) records history across every DocType — no schema change needed when integrating a new target. Trade-off: history no longer shows as an inline grid on the document form; it's reachable via the standard Frappe "Connections" sidebar link or by querying the log doctype directly. |
| 14a **(new)** | What history captures | **Every workflow state change** — approve, hold, resume, reject (not just approvals, as before). This makes the log a full audit trail AND lets the on-hold dashboard attribute a held document to the user who placed the hold. The initial `create → Pending` is intentionally **not** logged (redundant with the doc's own `owner`/`creation`, and would need an extra `after_insert` hook because the default state isn't set yet during our `validate` hook — client chose to leave it out 2026-09-02). |

## Environment
- **Separate v16 bench** (`frappe-bench-v16`) — one app-code copy per bench, so v16 can't coexist with the v15 bench.
- v16 requires **Python ≥ 3.14** and **Node ≥ 24**.
- App: `approval_engine`; site `v16.dev`.
