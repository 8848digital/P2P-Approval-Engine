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


def _pending_condition():
    """Build the state/tier-pool OR-block of the WHERE clause."""
    clauses = []
    for state, prefix in STATE_TIER_POOL.items():
        pool = ", ".join(f"d.`{prefix}{i}`" for i in range(1, 6))
        clauses.append(f"(p.workflow_state = {frappe.db.escape(state)} AND %(user)s IN ({pool}))")
    return "\n     OR ".join(clauses)


def pending_for_doctype(document_type, company, user):
    """Return {records, amount} of docs of `document_type` pending on `user` in `company`."""
    amount_field = amount_field_for(document_type)
    if not amount_field:
        # No amount field configured -> DocType isn't set up for the engine; report zero.
        return {"records": 0, "amount": 0.0}

    query = """
        SELECT
            COUNT(*)                          AS records,
            COALESCE(SUM(p.`{amt}`), 0)       AS amount
        FROM `tab{dt}` p
        INNER JOIN `tabApproval Matrix` m
                ON m.document_type = %(doctype)s
               AND m.company       = p.company
               AND m.docstatus     = 1
        INNER JOIN `tabApproval Matrix Detail` d
                ON d.parent      = m.name
               AND d.department  = p.department
               AND p.`{amt}`    >= d.min_amount
               AND (d.max_amount = 0 OR p.`{amt}` <= d.max_amount)
        WHERE p.docstatus = 0
          AND p.company   = %(company)s
          AND (
                {pending_condition}
              )
    """.format(
        amt=amount_field,
        dt=document_type,
        pending_condition=_pending_condition(),
    )

    row = frappe.db.sql(
        query,
        {"doctype": document_type, "company": company, "user": user},
        as_dict=True,
    )[0]
    return {"records": int(row.records or 0), "amount": float(row.amount or 0)}


def on_hold_for_doctype(document_type, company, user):
    """Return {records, amount} of docs of `document_type` currently on hold by `user` in `company`.

    A doc counts if it is in an `On Hold by Approver N` state and the latest Document Workflow Log
    row for it was written by `user` (i.e. `user` placed the current hold)."""
    amount_field = amount_field_for(document_type)
    if not amount_field:
        return {"records": 0, "amount": 0.0}

    query = """
        SELECT
            COUNT(*)                          AS records,
            COALESCE(SUM(p.`{amt}`), 0)       AS amount
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
    """.format(amt=amount_field, dt=document_type)

    row = frappe.db.sql(
        query,
        {"doctype": document_type, "company": company, "user": user,
         "hold_like": HOLD_STATE_LIKE},
        as_dict=True,
    )[0]
    return {"records": int(row.records or 0), "amount": float(row.amount or 0)}


def approved_for_doctype(document_type, company, user, from_date=None, to_date=None):
    """Return {records, amount} of docs of `document_type` `user` approved in `company` within
    the date range. "Approved" = the user has any Document Workflow Log row moving the doc into
    an approval state (Approved 1/2/3 or final Approved); each doc is counted once even if the
    user approved it at more than one tier. `from_date`/`to_date` are inclusive dates (on the
    log row's creation); either may be omitted for an open bound."""
    amount_field = amount_field_for(document_type)
    if not amount_field:
        return {"records": 0, "amount": 0.0}

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
            COUNT(*)                          AS records,
            COALESCE(SUM(p.`{amt}`), 0)       AS amount
        FROM `tab{dt}` p
        WHERE p.company = %(company)s
          AND EXISTS (
                SELECT 1 FROM `tabDocument Workflow Log` l
                WHERE {exists_where}
              )
    """.format(amt=amount_field, dt=document_type, exists_where=" AND ".join(conditions))

    row = frappe.db.sql(query, params, as_dict=True)[0]
    return {"records": int(row.records or 0), "amount": float(row.amount or 0)}


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


def _resolve_user(user):
    """A caller may only request another user's summary if they are a System Manager."""
    if user and user != frappe.session.user:
        frappe.only_for("System Manager")
    return user or frappe.session.user


@frappe.whitelist()
def get_pending_summary(company, user=None):
    """API: per-DocType {records, amount} pending on `user` (default: session user) in `company`."""
    return pending_summary(company, _resolve_user(user))


@frappe.whitelist()
def get_on_hold_summary(company, user=None):
    """API: per-DocType {records, amount} on hold by `user` (default: session user) in `company`."""
    return on_hold_summary(company, _resolve_user(user))


@frappe.whitelist()
def get_approved_summary(company, from_date=None, to_date=None, user=None):
    """API: per-DocType {records, amount} approved by `user` (default: session user) in `company`
    within [from_date, to_date] (inclusive dates on when the approval happened)."""
    return approved_summary(company, _resolve_user(user), from_date, to_date)


@frappe.whitelist()
def get_dashboard_summary(company, user=None):
    """API: per-DocType {pending, on_hold} for `user` (default: session user) in `company`.

    The single call the dashboard needs — both rows per DocType column in one round trip."""
    return dashboard_summary(company, _resolve_user(user))
