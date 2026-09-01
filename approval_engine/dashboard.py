"""Dashboard aggregation queries.

"Pending on me" — per target DocType, the count and total amount of in-flight documents
currently awaiting the logged-in user's approval, scoped to one company.

"Awaiting me" is matrix-designated: for a doc in an in-flight state, we look at the tier that
state is waiting on and check whether the user is named in that document's matched band-row
approver pool for that tier. This matches the engine's runtime gating: each transition's
condition embeds `frappe.session.user in [<this row's tier pool>]` (see generator.build_transitions),
so only the specific approvers configured for that row/tier can actually act on the document —
holding the shared `<DocType> - Approver N` role alone is not enough. Current state -> awaited tier:
    Pending -> 1, Approved 1 -> 2, Approved 2 -> 3, Approved 3 -> 4
"""

import frappe

# Current in-flight state -> the approver-pool column prefix that must contain the user.
STATE_TIER_POOL = {
    "Pending": "approver_1_user_",
    "Approved 1": "approver_2_user_",
    "Approved 2": "approver_3_user_",
    "Approved 3": "approver_4_user_",
}


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


def pending_summary(company, user=None):
    """Per-DocType pending summary for `user` (defaults to session user) in `company`."""
    user = user or frappe.session.user
    return {
        dt: pending_for_doctype(dt, company, user)
        for dt in target_doctypes()
    }


@frappe.whitelist()
def get_pending_summary(company, user=None):
    """API: per-DocType {records, amount} pending on `user` (default: session user) in `company`.

    `user` may only be overridden by System Manager; other callers always get their own summary.
    """
    if user and user != frappe.session.user:
        frappe.only_for("System Manager")
    return pending_summary(company, user)
