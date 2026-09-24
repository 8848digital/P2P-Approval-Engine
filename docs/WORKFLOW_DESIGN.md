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

## 6. Remarks on every transition (Milestone 3)

Frappe's `apply_workflow(doc, action)` has no slot for a note, so remarks travel beside it:
the caller stashes them in Redis (`remarks.stash_remarks`, keyed by user + document, 5 min
TTL), and `runtime._record_history` pops them while logging the transition.

```
Desk        : before_workflow_action dialog -> api/v1/workflow.stash_remarks -> apply_workflow
Email link  : link_actions.perform_action  -> stash_remarks(via_email_link=1) -> apply_workflow
both        -> runtime._record_history -> Document Workflow Log {remarks, via_email_link}
                                       -> doc.add_comment (timeline, authored by the approver)
```

- A stash made for a different action is discarded, not attached to the wrong transition.
- **Reject requires a reason**, enforced in `validate` (`remarks.validate_reject_reason`), so it
  holds for Desk, the email page and direct API calls. Bulk Reject from a list view therefore
  fails — it cannot collect a reason.
- The log row is the durable, tamper-resistant copy; the timeline comment is for visibility.

## 7. Acting from email (Milestone 3)

Per-tier **Action via Email** on the matrix row switches this on. It changes *who is notified*,
never *who may act* — the transition conditions of §2 are unchanged.

```
state change (on_update, managed doc)
  -> supersede open links for this doc       (same transaction: first approver wins)
  -> enqueue tasks.send_action_emails        (enqueue_after_commit -> never on a rolled-back save)
       -> ActionRequestNotifier: acting tier from the new state (generator.acting_tier),
          matched band row (find_band_row), tier's Action-via-Email flag
       -> one Approval Action Token + one email per approver of that tier (PDF deferred)
approver opens /approval_action?token=...    (GET renders only; scanners pre-fetch links)
  -> POST request_otp  -> 6-digit code emailed now=True to the approver's own address
  -> POST submit_action -> OTP verified -> acting_as(approver) -> apply_workflow
                        -> token Used, siblings superseded by the state change itself
```

A link is usable only while: status Active, before `expires_on` (Approval Settings, default 72h),
the document still a draft **in the exact state the link was issued for**, and the approver still
enabled. Anything else answers with a visitor-safe reason. Because the action runs as the
approver, §2's conditions, §5's band gate and the §6 audit trail all apply untouched — the email
channel adds no new way to approve, only a new way to reach the same one.

## 8. Ad-hoc additional approver (per document)

An eligible approver can inject ONE extra sequential approver into a single document's live chain
— e.g. `Dhaval → Karan → Atul(extra) → Ritik` for one PO — without touching the shared matrix or
any other document. Backed by the `Additional Approver` DocType (`reference_doctype/name`,
`approver`, captured `insert_state`, `can_hold`/`can_reject`/`action_via_email`, `active`/`completed`).

**One resting state, `Additionally Approved`**, plus `On Hold by Additional Approver`, and one coarse
role `<DocType> - Additional Approver` (granted/revoked **per record**, never by `reconcile_roles`,
so a matrix rebuild can't strip an ad-hoc reviewer). Insertion is auto-captured at the current
juncture: the reviewer's `insert_state` is the document's state when they were added, and at most
one reviewer may be active-and-incomplete per document.

For a document waiting at state `S` with a pending reviewer (all generic, baked at generation time,
gated by live `get_value` into `Additional Approver`):

```
# block: every tier transition FROM S gains  ... and not <pending reviewer at S>
# intercept (role <DocType> - Additional Approver, pinned to the reviewer):
S                              --Approve--> Additionally Approved          <pending reviewer at S, approver == session.user>
S                              --Reject-->  Rejected                     <... and can_reject>
S                              --Hold-->    On Hold by Additional Approver   <... and can_hold>
On Hold by Additional Approver --Approve--> Additionally Approved          <pending reviewer at S, approver == session.user>
On Hold by Additional Approver --Reject-->  Rejected                     <... and can_reject>
# resume: the tier that acts FROM S is mirrored FROM Additionally Approved, gated by the reviewer
# having completed, so the configured chain continues exactly as it would have:
Additionally Approved            --Approve--> Approved <tier> / Approved    <base tier cond and <reviewer done at S> [and next]>
```

Since only one reviewer is active per document, the completed reviewer's `insert_state` unambiguously
selects which tier resumes even though `Additionally Approved` is a single shared state. Lifecycle is
driven from `runtime.target_on_update` on the target document: entering `Additionally Approved` marks
the reviewer `completed`; leaving it (or `Rejected`) retires the reviewer (`active = 0`) and revokes
the role unless the user still has another active assignment on that DocType. The reviewer's
Approve/Reject reuses §5's audit log and §6's remarks dialog unchanged. Dashboard pending attribution
(`dashboard/finance_dashboard.py`) is adjusted additively: a blocked tier is not shown while a
reviewer is pending, the reviewer is shown instead, and the resuming tier is shown once the document
sits in `Additionally Approved`.

**Limitation:** you cannot insert after the final approval — once the top tier approves, the document
is submitted/terminal. The reviewer is always before the next pending tier.
