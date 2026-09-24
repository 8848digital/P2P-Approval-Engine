# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Dashboard aggregation queries — per target DocType, count + total amount of documents
that are **pending on** or **on hold by** the logged-in user, scoped to one company.

Pending ("awaiting me") is matrix-designated: for a doc in an in-flight state, we look at the
tier that state is waiting on and check whether the user is named in that document's matched
band-row approver pool for that tier. This matches the engine's runtime gating: each transition's
condition embeds `frappe.session.user in [<this row's tier pool>]` (see generator.build_transitions),
so only the specific approvers configured for that row/tier can actually act on the document —
holding the shared `<DocType> - Approver N` role alone is not enough. Current state -> awaited tier:
    Pending -> 1, Approved 1 -> 2, Approved 2 -> 3, Approved 3 -> 4

On hold ("held by me") is attributed from the audit trail: a doc counts if its current state is
an `On Hold by Approver N` state AND the most recent `Document Workflow Log` row for it (the row
that moved it into hold) was written by the user. This needs the full-transition logging added
in the Document Workflow Log work — approvals-only history could not attribute a hold.
"""

import frappe
from frappe.utils import add_days, getdate

from approval_engine.approval_core.generator import ADDITIONAL_APPROVAL_STATE

# Current in-flight state -> the approver-pool column prefix that must contain the user.
STATE_TIER_POOL = {
    "Pending": "approver_1_user_",
    "Approved 1": "approver_2_user_",
    "Approved 2": "approver_3_user_",
    "Approved 3": "approver_4_user_",
}

# All hold states share this prefix (On Hold by Approver 1..4).
HOLD_STATE_LIKE = "On Hold by Approver%"

# States an Approve action moves a document INTO — an escalation (Approved 1/2/3) is still an
# approval by the acting tier, as is the final Approved. "Approved by me" counts any of these.
APPROVED_STATES = ("Approved 1", "Approved 2", "Approved 3", "Approved")


def target_doctypes():
    """DocTypes that have a submitted (active) Approval Matrix."""
    return frappe.get_all(
        "Approval Matrix",
        filters={"docstatus": 1},
        distinct=True,
        pluck="document_type",
    )


def amount_field_for(document_type):
    """Resolve the configured amount field for a DocType from Approval Settings."""
    return frappe.db.get_value(
        "Approval Amount Field Mapping",
        {"parent": "Approval Settings", "document_type": document_type},
        "amount_field",
    )


def _pool_condition(state_column):
    """Build the state/tier-pool OR-block of a WHERE clause, keyed on `state_column`.

    `state_column` is the SQL expression holding the state to map to a tier — the document's
    own `p.workflow_state` (normal pending), or an inserted reviewer's captured
    `r.insert_state` (the tier resuming after an ad-hoc review).

    Parameters:
        state_column (str, required): SQL column/expression holding the waiting state.

    Returns:
        str: An OR-joined SQL boolean block.
    """
    clauses = []
    for state, prefix in STATE_TIER_POOL.items():
        pool = ", ".join(f"d.`{prefix}{i}`" for i in range(1, 6))
        clauses.append(f"({state_column} = {frappe.db.escape(state)} AND %(user)s IN ({pool}))")
    return "\n     OR ".join(clauses)


def _matrix_join(amount_field):
    """The band-matching join onto the Approval Matrix for a target document `p`.

    Parameters:
        amount_field (str, required): The DocType's amount fieldname (already validated).

    Returns:
        str: SQL join clause matching `p` to its Approval Matrix Detail band row (`d`).
    """
    return f"""
        INNER JOIN `tabApproval Matrix` m
                ON m.document_type = %(doctype)s
               AND m.company       = p.company
               AND m.docstatus     = 1
        INNER JOIN `tabApproval Matrix Detail` d
                ON d.parent      = m.name
               AND d.department  = p.department
               AND p.`{amount_field}` >= d.min_amount
               AND (d.max_amount = 0 OR p.`{amount_field}` <= d.max_amount)
    """


def _aggregate(rows):
    """Collapse per-document rows [{name, amount}] into a cell payload. Returning `names`
    lets the dashboard link each cell straight to a list view filtered to exactly these
    documents, so the list always matches the count/amount shown."""
    names = [r.name for r in rows]
    amount = sum(float(r.amount or 0) for r in rows)
    return {"records": len(names), "amount": amount, "names": names}


def _dedupe_by_name(rows):
    """Keep one row per document name — the pending sources can, in principle, overlap.

    Parameters:
        rows (list, required): Row dicts each carrying at least `name`.

    Returns:
        list: One row per distinct name (first occurrence wins).
    """
    seen = {}
    for row in rows:
        seen.setdefault(row.name, row)
    return list(seen.values())


def pending_for_doctype(document_type, company, user):
    """Return {records, amount, names} of docs of `document_type` pending on `user` in `company`.

    "Pending on me" spans three cases, unioned and de-duplicated by document:
    - the document's current tier awaits me (and it is not paused for an ad-hoc reviewer),
    - I am the ad-hoc reviewer currently inserted into the chain, or
    - the document is in `Additionally Approved` and I am the tier resuming after that review.
    """
    amount_field = amount_field_for(document_type)
    if not amount_field:
        # No amount field configured -> DocType isn't set up for the engine; report zero.
        return {"records": 0, "amount": 0.0, "names": []}

    params = {"doctype": document_type, "company": company, "user": user}
    rows = (
        _pending_tier_rows(document_type, amount_field, params)
        + _pending_resume_rows(document_type, amount_field, params)
        + _pending_reviewer_rows(document_type, amount_field, params)
    )
    return _aggregate(_dedupe_by_name(rows))


def _pending_tier_rows(document_type, amount_field, params):
    """Docs whose current tier awaits the user — excluding any paused for an ad-hoc reviewer
    (those are attributed to the reviewer, who must act first).

    Parameters:
        document_type (str, required): Target DocType.
        amount_field (str, required): The DocType's amount fieldname.
        params (dict, required): Bind values {doctype, company, user}.

    Returns:
        list: Row dicts {name, amount}.
    """
    # GROUP BY p.name collapses overlapping bands so a doc is never double-counted.
    query = f"""
        SELECT p.name AS name, p.`{amount_field}` AS amount
        FROM `tab{document_type}` p
        {_matrix_join(amount_field)}
        WHERE p.docstatus = 0
          AND p.company   = %(company)s
          AND ({_pool_condition("p.workflow_state")})
          AND NOT EXISTS (
                SELECT 1 FROM `tabAdditional Approver` r
                 WHERE r.reference_doctype = %(doctype)s
                   AND r.reference_name    = p.name
                   AND r.active = 1 AND r.completed = 0
              )
        GROUP BY p.name, p.`{amount_field}`
    """
    return frappe.db.sql(query, params, as_dict=True)


def _pending_resume_rows(document_type, amount_field, params):
    """Docs in `Additionally Approved` (reviewer done) awaiting the resuming tier's pool member.

    The resuming tier is derived from the reviewer's captured `insert_state`.

    Parameters:
        document_type (str, required): Target DocType.
        amount_field (str, required): The DocType's amount fieldname.
        params (dict, required): Bind values {doctype, company, user}.

    Returns:
        list: Row dicts {name, amount}.
    """
    query = f"""
        SELECT p.name AS name, p.`{amount_field}` AS amount
        FROM `tab{document_type}` p
        {_matrix_join(amount_field)}
        INNER JOIN `tabAdditional Approver` r
                ON r.reference_doctype = %(doctype)s
               AND r.reference_name    = p.name
               AND r.active = 1 AND r.completed = 1
        WHERE p.docstatus = 0
          AND p.company   = %(company)s
          AND p.workflow_state = {frappe.db.escape(ADDITIONAL_APPROVAL_STATE)}
          AND ({_pool_condition("r.insert_state")})
        GROUP BY p.name, p.`{amount_field}`
    """
    return frappe.db.sql(query, params, as_dict=True)


def _pending_reviewer_rows(document_type, amount_field, params):
    """Docs paused for an ad-hoc reviewer who is the user (their turn, before the tier resumes).

    Parameters:
        document_type (str, required): Target DocType.
        amount_field (str, required): The DocType's amount fieldname.
        params (dict, required): Bind values {doctype, company, user}.

    Returns:
        list: Row dicts {name, amount}.
    """
    query = f"""
        SELECT p.name AS name, p.`{amount_field}` AS amount
        FROM `tab{document_type}` p
        INNER JOIN `tabAdditional Approver` r
                ON r.reference_doctype = %(doctype)s
               AND r.reference_name    = p.name
               AND r.active = 1 AND r.completed = 0
               AND r.approver = %(user)s
        WHERE p.docstatus = 0
          AND p.company   = %(company)s
        GROUP BY p.name, p.`{amount_field}`
    """
    return frappe.db.sql(query, params, as_dict=True)


def on_hold_for_doctype(document_type, company, user):
    """Return {records, amount} of docs of `document_type` currently on hold by `user` in `company`.

    A doc counts if it is in an `On Hold by Approver N` state and the latest Document Workflow Log
    row for it was written by `user` (i.e. `user` placed the current hold)."""
    amount_field = amount_field_for(document_type)
    if not amount_field:
        return {"records": 0, "amount": 0.0, "names": []}

    query = """
        SELECT
            p.name         AS name,
            p.`{amt}`      AS amount
        FROM `tab{dt}` p
        INNER JOIN `tabDocument Workflow Log` l
                ON l.reference_doctype = %(doctype)s
               AND l.reference_name    = p.name
               AND l.user             = %(user)s
               AND l.workflow_state    = p.workflow_state
               AND l.creation = (
                     SELECT MAX(l2.creation)
                     FROM `tabDocument Workflow Log` l2
                     WHERE l2.reference_doctype = %(doctype)s
                       AND l2.reference_name    = p.name
                   )
        WHERE p.docstatus     = 0
          AND p.company       = %(company)s
          AND p.workflow_state LIKE %(hold_like)s
        GROUP BY p.name, p.`{amt}`
    """.format(amt=amount_field, dt=document_type)

    rows = frappe.db.sql(
        query,
        {"doctype": document_type, "company": company, "user": user,
         "hold_like": HOLD_STATE_LIKE},
        as_dict=True,
    )
    return _aggregate(rows)


def approved_for_doctype(document_type, company, user, from_date=None, to_date=None):
    """Return {records, amount} of docs of `document_type` `user` approved in `company` within
    the date range. "Approved" = the user has any Document Workflow Log row moving the doc into
    an approval state (Approved 1/2/3 or final Approved); each doc is counted once even if the
    user approved it at more than one tier. `from_date`/`to_date` are inclusive dates (on the
    log row's creation); either may be omitted for an open bound."""
    amount_field = amount_field_for(document_type)
    if not amount_field:
        return {"records": 0, "amount": 0.0, "names": []}

    conditions = [
        "l.reference_doctype = %(doctype)s",
        "l.reference_name    = p.name",
        "l.user             = %(user)s",
        "l.workflow_state    IN %(states)s",
    ]
    params = {"doctype": document_type, "company": company, "user": user,
              "states": APPROVED_STATES}
    if from_date:
        conditions.append("l.creation >= %(from_dt)s")
        params["from_dt"] = getdate(from_date)               # start of that day
    if to_date:
        conditions.append("l.creation < %(to_dt)s")
        params["to_dt"] = add_days(getdate(to_date), 1)      # exclusive: whole to_date included

    query = """
        SELECT
            p.name         AS name,
            p.`{amt}`      AS amount
        FROM `tab{dt}` p
        WHERE p.company = %(company)s
          AND EXISTS (
                SELECT 1 FROM `tabDocument Workflow Log` l
                WHERE {exists_where}
              )
    """.format(amt=amount_field, dt=document_type, exists_where=" AND ".join(conditions))

    rows = frappe.db.sql(query, params, as_dict=True)
    return _aggregate(rows)


def pending_summary(company, user=None):
    """Per-DocType pending summary for `user` (defaults to session user) in `company`."""
    user = user or frappe.session.user
    return {dt: pending_for_doctype(dt, company, user) for dt in target_doctypes()}


def on_hold_summary(company, user=None):
    """Per-DocType on-hold summary for `user` (defaults to session user) in `company`."""
    user = user or frappe.session.user
    return {dt: on_hold_for_doctype(dt, company, user) for dt in target_doctypes()}


def approved_summary(company, user=None, from_date=None, to_date=None):
    """Per-DocType approved-by-`user` summary in `company`, over the given date range."""
    user = user or frappe.session.user
    return {
        dt: approved_for_doctype(dt, company, user, from_date, to_date)
        for dt in target_doctypes()
    }


def dashboard_summary(company, user=None):
    """Per-DocType {pending, on_hold} summary for `user` in `company` (single pass over targets)."""
    user = user or frappe.session.user
    return {
        dt: {
            "pending": pending_for_doctype(dt, company, user),
            "on_hold": on_hold_for_doctype(dt, company, user),
        }
        for dt in target_doctypes()
    }
