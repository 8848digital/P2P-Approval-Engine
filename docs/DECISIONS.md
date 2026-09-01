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
| 5 **(REMOVED by client)** | No-repeat | ~~A person may approve a document at most once.~~ **Removed** — the client's Excel requirements doc has no such clause. The `Document Workflow Detail` history is still *recorded* (audit), but no longer gates any transition. A person listed in multiple tiers CAN now approve multiple tiers. |
| 6 | Self-approval | Allowed (`allow_self_approval = 1`). |
| 7 **(revised — Excel-literal)** | Enforcement approach | **Literal transitions**, conditions **exactly as the client's Excel**: `company + department + amount band` (+ for Approve, a runtime escalate check — see #1c). "Who can approve" is gated **only by the transition Role** `<DocType> - Approver N`. The earlier embedded pool clause `frappe.session.user in [...]` was **removed** at client request (see #13). |
| 1c **(new — escalate check)** | How Approve chooses escalate vs finalize | At **runtime**, each Approve emits BOTH transitions; the condition reads the matrix live: `frappe.db.get_value('Approval Matrix Detail', <row>, 'approver_{N+1}_user_1')` (truthy → escalate to `Approved N`; blank → finalize to `Approved`). Matches the Excel's `frappe.get_value(... approver N+1 user 1 (not) blank)`. |
| 8 | No matching band for a document | **Block** (Milestone 2 create hook). |
| 9 **(revised)** | Matrix edit / cancel & in-flight docs | Regenerate the (single, live) workflow on submit; reconcile roles. Because conditions are evaluated live and there is **no snapshot**, an amount edit auto re-routes — ERPNext-native, no migration. Cancel → rebuild without this matrix, or deactivate if none remain. |
| 10 | Amount field | Configurable per DocType via **Approval Settings** (PO/PI → `grand_total`, Payment Entry → `paid_amount`; PI → `net_total` if desired). |
| 11 **(revised)** | State `allow_edit` | Pending / Approved / Rejected = **All**; Approved N = **Approver N**; On Hold by Approver N = **Approver N**. |
| 12 **(new)** | Tiers | Exactly 4 tiers × 5 users; tiers must be **contiguous** (Approver 3 requires 1 & 2). |
| 13 **(reverted by client)** | Department isolation blocker | The shared `- Approver N` role lets another department's same-tier approver act on this department's document. We had **fixed** this by embedding the per-row pool in the condition, but the client chose to **implement conditions exactly as their Excel** (role-only gating), so the pool clause was **removed** and this cross-department behavior is **accepted**. To restore isolation later without the pool clause, use department-specific roles (`<DocType> - <Dept> - Approver N`). |

## Environment
- **Separate v16 bench** (`frappe-bench-v16`) — one app-code copy per bench, so v16 can't coexist with the v15 bench.
- v16 requires **Python ≥ 3.14** and **Node ≥ 24**.
- App: `approval_engine`; site `v16.dev`.
