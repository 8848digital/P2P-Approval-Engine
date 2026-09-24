# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Workflow generation engine (LITERAL model).

For a target DocType, (re)build ONE standard ERPNext Workflow from all submitted
Approval Matrix records. Transitions are generated PER (company, department, band,
tier, action) with company/department/amount-band/approver-pool/no-repeat conditions
written literally into each transition. Escalate-vs-finalize is baked in at
generation time (we know which tiers are configured per row).

Roles (`<DocType> - Approver N`) are a coarse gate; the exact per-row approver pool
is embedded in each condition so only that department/band's approvers can act.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MAX_LEVELS = 4

# state -> docstatus ("0" draft, "1" submitted)
STATE_DOCSTATUS = {
    "Pending": "0",
    "Approved 1": "0",
    "Approved 2": "0",
    "Approved 3": "0",
    "Approved": "1",
    "On Hold by Approver 1": "0",
    "On Hold by Approver 2": "0",
    "On Hold by Approver 3": "0",
    "On Hold by Approver 4": "0",
    "Additionally Approved": "0",
    "On Hold by Additional Approver": "0",
    "Rejected": "1",
}
STATE_ORDER = list(STATE_DOCSTATUS.keys())

# Ad-hoc reviewer states (see doctype/additional_approver). A document routes through
# `Additionally Approved` when an eligible approver injects an extra approver at the current
# juncture; the configured tier then resumes. `On Hold by Additional Approver` backs the
# reviewer's optional Hold.
ADDITIONAL_APPROVAL_STATE = "Additionally Approved"
ADDITIONAL_HOLD_STATE = "On Hold by Additional Approver"

# Workflow State master styles
WORKFLOW_STATE_STYLES = {
    "Pending": "Warning",
    "Approved 1": "Primary",
    "Approved 2": "Primary",
    "Approved 3": "Primary",
    "Approved": "Success",
    "On Hold by Approver 1": "Inverse",
    "On Hold by Approver 2": "Inverse",
    "On Hold by Approver 3": "Inverse",
    "On Hold by Approver 4": "Inverse",
    "Additionally Approved": "Warning",
    "On Hold by Additional Approver": "Inverse",
    "Rejected": "Danger",
}

# allow_edit role per state ("All" = built-in role held by everyone; int = Approver N)
ALLOW_EDIT = {
    "Pending": "All",
    "Approved 1": 1,
    "Approved 2": 2,
    "Approved 3": 3,
    "Approved": "All",
    "On Hold by Approver 1": 1,
    "On Hold by Approver 2": 2,
    "On Hold by Approver 3": 3,
    "On Hold by Approver 4": 4,
    "Additionally Approved": "All",
    "On Hold by Additional Approver": "All",
    "Rejected": "All",
}

# state a given tier acts FROM
STATE_FOR_TIER = {1: "Pending", 2: "Approved 1", 3: "Approved 2", 4: "Approved 3"}

ACTIONS = ["Approve", "Hold", "Reject"]

HOLD_STATE_PREFIX = "On Hold by Approver "

DEFAULT_AMOUNT_FIELDS = {
    "Purchase Order": "grand_total",
    "Purchase Invoice": "grand_total",
    "Payment Entry": "paid_amount",
}

# ---------------------------------------------------------------------------
# naming helpers
# ---------------------------------------------------------------------------

def role_name(document_type, level):
    """
    Name of the approver role for one tier of a DocType's generated workflow.

    Parameters:
        document_type (str, required): Target DocType.
        level (int, required): Approver tier, 1..MAX_LEVELS.

    Returns:
        str: e.g. "Purchase Order - Approver 2".
    """
    return f"{document_type} - Approver {level}"


def additional_role_name(document_type):
    """
    Name of the coarse role held by ad-hoc additional approvers of a DocType.

    Unlike the tier roles, this is granted/revoked per `Additional Approver` record
    (not by `reconcile_roles`), so a matrix rebuild never strips an ad-hoc reviewer.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        str: e.g. "Purchase Order - Additional Approver".
    """
    return f"{document_type} - Additional Approver"


def workflow_name(document_type):
    """
    Name of the single Workflow this engine generates for a DocType.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        str: e.g. "Purchase Order Approval".
    """
    return f"{document_type} Approval"


def acting_tier(state):
    """
    Approver tier that acts FROM `state` (inverse of STATE_FOR_TIER, plus hold states).

    Example: "Pending" -> 1, "Approved 2" -> 3, "On Hold by Approver 2" -> 2, "Approved" -> None.

    Parameters:
        state (str, optional): A workflow state of an engine-generated workflow.

    Returns:
        int | None: The tier, or None for terminal/unknown states.
    """
    if not state:
        return None
    for tier, tier_state in STATE_FOR_TIER.items():
        if tier_state == state:
            return tier
    if state.startswith(HOLD_STATE_PREFIX):
        suffix = state[len(HOLD_STATE_PREFIX):]
        return int(suffix) if suffix.isdigit() else None
    return None


# ---------------------------------------------------------------------------
# row helpers
# ---------------------------------------------------------------------------

def pool(row, level):
    """
    Users configured for one tier of one matrix row, in field order, blanks dropped.

    Parameters:
        row (Document, required): An Approval Matrix Detail row.
        level (int, required): Approver tier, 1..MAX_LEVELS.

    Returns:
        list[str]: User IDs; empty when the tier is not configured.
    """
    return [row.get(f"approver_{level}_user_{u}")
            for u in range(1, 6) if row.get(f"approver_{level}_user_{u}")]


def configured_levels(row):
    """
    Tiers of a matrix row that have at least one approver.

    Parameters:
        row (Document, required): An Approval Matrix Detail row.

    Returns:
        list[int]: Ascending tier numbers, e.g. [1, 2].
    """
    return [level for level in range(1, MAX_LEVELS + 1) if pool(row, level)]


def amount_field_for(document_type):
    """
    Fieldname whose value the amount bands compare against for a DocType.

    Prefers the explicit Approval Settings mapping, else a per-DocType default.
    See `resolve_amount_field` for the same answer with its provenance.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        str: Fieldname, e.g. "grand_total".
    """
    settings = frappe.get_single("Approval Settings")
    for r in settings.amount_fields:
        if r.document_type == document_type:
            return r.amount_field
    return DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total")


# Field types that can hold an amount to compare bands against.
AMOUNT_FIELDTYPES = ("Currency", "Float", "Int")


def resolve_amount_field(document_type):
    """Describe the amount field the bands WILL compare against for `document_type`, so it can be
    shown/validated before a matrix is submitted (the field gets baked into conditions at
    generation, and today is silently defaulted). Returns:
        amount_field : the resolved fieldname
        is_explicit  : True if it comes from an Approval Settings mapping, False if a fallback default
        exists       : True if that field actually exists as an amount field on the target DocType
        label        : the field's label (or the fieldname if unresolved)
    """
    settings = frappe.get_single("Approval Settings")
    explicit = next((r.amount_field for r in settings.amount_fields
                     if r.document_type == document_type), None)
    amount_field = explicit or DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total")

    df = frappe.get_meta(document_type).get_field(amount_field) if document_type else None
    exists = bool(df and df.fieldtype in AMOUNT_FIELDTYPES)
    return {
        "amount_field": amount_field,
        "is_explicit": bool(explicit),
        "exists": exists,
        "label": (df.label if df else None) or amount_field,
    }


def band_condition(amt_field, min_amount, max_amount):
    """Bake the amount band into a condition. Bounds are INCLUSIVE on both ends
    (Min <= amount <= Max); bands start at the previous band's Max + the smallest
    currency unit (e.g. 100000 -> next Min 100000.01) — enforced in
    approval_matrix.py's _validate_bands, not here (this just embeds the row's own values).
    Max=0 => unbounded above, Min=0 => no lower bound (from 0), both 0 => matches all."""
    minv = min_amount or 0
    maxv = max_amount or 0
    parts = []
    if minv:
        parts.append(f"doc.{amt_field} >= {minv}")
    if maxv:
        parts.append(f"doc.{amt_field} <= {maxv}")
    return " and ".join(parts)


# ---------------------------------------------------------------------------
# ensure masters
# ---------------------------------------------------------------------------

def ensure_roles(document_type):
    """
    Create the `<DocType> - Approver 1..N` roles if they don't exist yet (idempotent).

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        None
    """
    names = [role_name(document_type, level) for level in range(1, MAX_LEVELS + 1)]
    names.append(additional_role_name(document_type))
    for name in names:
        if not frappe.db.exists("Role", name):
            frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
                ignore_permissions=True)


def ensure_role_permissions(document_type):
    """Grant read/write/submit on the target DocType to each approver role,
    so approvers can open and act on the document."""
    from frappe.permissions import add_permission, update_permission_property
    roles = [role_name(document_type, level) for level in range(1, MAX_LEVELS + 1)]
    roles.append(additional_role_name(document_type))
    for role in roles:
        has_perm = frappe.db.exists(
            "Custom DocPerm", {"parent": document_type, "role": role, "permlevel": 0}
        )
        if not has_perm:
            add_permission(document_type, role, 0)
        for ptype in ("read", "write", "submit"):
            update_permission_property(document_type, role, 0, ptype, 1)


def _grant_read_to_flow_roles(target_doctype, document_type):
    """Grant read on `target_doctype` to every role that touches `document_type`'s flow: its
    approver roles, and any role that can already create the target document. A real,
    admin-visible/editable Custom DocPerm (shows up in Role Permission Manager like any other
    permission) -- deliberately NOT a permission bypass at the query/API layer, so the admin
    stays in control of it exactly like any other grant in the system.
    """
    from frappe.permissions import add_permission, update_permission_property

    roles = {role_name(document_type, level) for level in range(1, MAX_LEVELS + 1)}
    roles.add(additional_role_name(document_type))
    for perm_dt in ("DocPerm", "Custom DocPerm"):
        roles.update(frappe.get_all(
            perm_dt, filters={"parent": document_type, "create": 1, "permlevel": 0},
            pluck="role"))

    for role in roles:
        already = frappe.db.exists("Custom DocPerm",
                                   {"parent": target_doctype, "role": role, "permlevel": 0}) \
            or frappe.db.exists("DocPerm",
                                {"parent": target_doctype, "role": role, "permlevel": 0})
        if not already:
            add_permission(target_doctype, role, 0)
        update_permission_property(target_doctype, role, 0, "read", 1)


def ensure_department_read(document_type):
    """Grant read on `Department` to everyone who touches the flow.

    `Department` is HR-restricted by default. Since the engine adds a `department`
    field to the target DocType and requires it for routing, the document's
    creators (roles that can create the target) and the approver roles must be able
    to read Department, or saving/opening the document raises
    'Insufficient Permission for Department'. (Department names aren't sensitive;
    this grants READ only.)
    """
    _grant_read_to_flow_roles("Department", document_type)


def ensure_company_read(document_type):
    """Grant read on `Company` to everyone who touches the flow.

    `Company` is ERPNext-restricted to specific business roles (Accounts User, Employee,
    etc.) by default, but an approver needs to see company names regardless of their
    business-role footprint -- e.g. the Finance dashboard's company selector, which any
    approver should be able to use. Same reasoning as ensure_department_read. (Company
    name/abbr/tax_id aren't sensitive; this grants READ only.)
    """
    _grant_read_to_flow_roles("Company", document_type)


def ensure_actions():
    """
    Create the Workflow Action Masters the generated transitions use (Approve/Hold/Reject).

    Returns:
        None
    """
    for action in ACTIONS:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action,
            }).insert(ignore_permissions=True)


def ensure_workflow_states():
    """
    Create the Workflow State masters for every state in the engine's fixed state machine.

    Returns:
        None
    """
    for name in STATE_ORDER:
        if not frappe.db.exists("Workflow State", name):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": name,
                "style": WORKFLOW_STATE_STYLES.get(name, ""),
            }).insert(ignore_permissions=True)


def ensure_amount_field(document_type):
    """
    Seed an Approval Settings amount-field row for this DocType if none exists.

    Makes the resolved default visible and editable instead of leaving it implicit.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        None
    """
    settings = frappe.get_single("Approval Settings")
    if not any(r.document_type == document_type for r in settings.amount_fields):
        settings.append("amount_fields", {
            "document_type": document_type,
            "amount_field": DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total"),
        })
        settings.save(ignore_permissions=True)


LEGACY_HISTORY_FIELDS = ("ae_section", "custom_workflow_history")


def remove_legacy_history_field(document_type):
    """Drop the old per-DocType `custom_workflow_history` child-table field, if present.

    History now lives centrally in `Document Workflow Log` (reference_doctype/reference_name)
    instead of a Table field added to every target DocType — no per-DocType schema needed.
    """
    for fieldname in LEGACY_HISTORY_FIELDS:
        name = f"{document_type}-{fieldname}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True)


# A routing department must belong to the document's own company: the generated conditions pair
# `doc.company == X` with `doc.department == Y`, and Approval Matrix rows are restricted the same
# way. `eval:` is resolved client-side against the open document (see link.js parse_filters).
DEPARTMENT_LINK_FILTERS = json.dumps([
    ["Department", "company", "=", "eval:doc.company"],
    ["Department", "is_group", "=", 0],
])


def ensure_department_field(document_type):
    """Ensure the target DocType has a `department` field (routing needs it), with the picker
    scoped to the document's company."""
    if frappe.get_meta(document_type).get_field("department"):
        _backfill_department_link_filters(document_type)
        return
    create_custom_fields({document_type: [
        {"fieldname": "department", "fieldtype": "Link", "label": "Department",
         "options": "Department", "insert_after": "company",
         "link_filters": DEPARTMENT_LINK_FILTERS},
    ]}, ignore_validate=True)


def _backfill_department_link_filters(document_type):
    """Add the company filter to a `department` Custom Field created before the filter existed.

    Only OUR Custom Field is touched (a standard `department` field on the target DocType is left
    alone), and only when no filter is configured — so a filter someone tuned by hand survives.
    """
    name = frappe.db.exists("Custom Field", {"dt": document_type, "fieldname": "department"})
    if not name or frappe.db.get_value("Custom Field", name, "link_filters"):
        return
    frappe.db.set_value("Custom Field", name, "link_filters", DEPARTMENT_LINK_FILTERS)
    frappe.clear_cache(doctype=document_type)


def find_band_row(document_type, company, department, amount):
    """Return the matching Approval Matrix Detail row for (company, dept, amount), or None."""
    name = frappe.db.get_value(
        "Approval Matrix",
        {"document_type": document_type, "company": company, "docstatus": 1}, "name")
    if not name:
        return None
    m = frappe.get_doc("Approval Matrix", name)
    for row in m.detail:
        if row.department != department:
            continue
        mn = row.min_amount or 0
        mx = row.max_amount or 0
        if (mn == 0 or amount >= mn) and (mx == 0 or amount <= mx):
            return row
    return None


def resuming_tier(doc):
    """Tier that must act once the ad-hoc reviewer on `doc` has completed.

    Only meaningful while `doc` sits in `Additionally Approved` (the reviewer approved,
    the configured chain has not yet resumed). Read from the active reviewer's captured
    `insert_state`. Used by the email notifier to reach the right approver pool.

    Parameters:
        doc (Document, required): The governed document in the review state.

    Returns:
        int | None: The resuming approver tier, or None when no reviewer applies.
    """
    state = frappe.db.get_value("Additional Approver", {
        "reference_doctype": doc.doctype, "reference_name": doc.name,
        "active": 1, "completed": 1,
    }, "insert_state")
    return acting_tier(state) if state else None


# ---------------------------------------------------------------------------
# ad-hoc reviewer condition fragments (evaluated live against the document)
#
# Only `frappe.db.get_value`/`get_list` and `frappe.session` are exposed to workflow
# condition eval (see frappe.model.workflow.get_workflow_safe_globals), so every
# per-document reviewer check is a `get_value` returning the record name (truthy) or
# None (falsy) — the same technique the escalate/finalize `next` check already uses.
# ---------------------------------------------------------------------------

def _pending_reviewer_cond(state, extra=""):
    """
    Condition fragment: an active, not-yet-acted reviewer sits at `state` for this doc.

    Parameters:
        state (str, required): The reviewer's captured `insert_state`.
        extra (str, optional): Extra filter clause(s), e.g. pinning the approver.

    Returns:
        str: A `frappe.db.get_value(...)` expression usable in a transition condition.
    """
    return ("frappe.db.get_value('Additional Approver', "
            "{'reference_doctype': doc.doctype, 'reference_name': doc.name, "
            f"'insert_state': {state!r}, 'active': 1, 'completed': 0{extra}}}, 'name')")


def _reviewer_can_act_cond(state, flag=None):
    """
    Condition fragment: the session user is the pending reviewer at `state` (optionally
    only when their record permits `flag`, e.g. `can_reject`).

    Parameters:
        state (str, required): The reviewer's captured `insert_state`.
        flag (str, optional): A permission checkbox that must be set (`can_hold`/`can_reject`).

    Returns:
        str: A `frappe.db.get_value(...)` expression usable in a transition condition.
    """
    extra = ", 'approver': frappe.session.user"
    if flag:
        extra += f", {flag!r}: 1"
    return _pending_reviewer_cond(state, extra)


def _reviewer_done_cond(state):
    """
    Condition fragment: the reviewer inserted at `state` has approved and the chain may resume.

    Parameters:
        state (str, required): The reviewer's captured `insert_state`.

    Returns:
        str: A `frappe.db.get_value(...)` expression usable in a transition condition.
    """
    return ("frappe.db.get_value('Additional Approver', "
            "{'reference_doctype': doc.doctype, 'reference_name': doc.name, "
            f"'insert_state': {state!r}, 'active': 1, 'completed': 1}}, 'name')")


# ---------------------------------------------------------------------------
# transitions (literal, per row)
# ---------------------------------------------------------------------------

def _t(state, action, next_state, allowed, condition):
    """
    Build one Workflow Transition row.

    Parameters:
        state (str, required): State the transition acts from.
        action (str, required): Workflow action name.
        next_state (str, required): State the document moves to.
        allowed (str, required): Role allowed to perform it.
        condition (str, required): Python condition evaluated against the document.

    Returns:
        dict: Transition row for `Workflow.append("transitions", ...)`.
    """
    return {
        "state": state,
        "action": action,
        "next_state": next_state,
        "allowed": allowed,
        "condition": condition,
        "allow_self_approval": 1,
    }


def _approve_transitions(origin, guard, level, base, role, next_configured):
    """
    Approve transitions (escalate + finalize) from one origin state for a tier.

    Escalate vs finalize is chosen at runtime by the live `next_configured` check; the
    top tier always finalizes. `guard` is a reviewer-related condition suffix ("", the
    block suffix, or the resume suffix) appended to the tier's base condition.

    Parameters:
        origin (str, required): State the transition acts from.
        guard (str, required): Extra condition suffix (may be empty).
        level (int, required): Approver tier, 1..MAX_LEVELS.
        base (str, required): Company/department/band/pool condition for the tier.
        role (str, required): Tier approver role.
        next_configured (str | None, required): Live "next tier configured?" expression
            (None for the top tier).

    Returns:
        list[dict]: One or two transition rows.
    """
    if level < MAX_LEVELS:
        return [
            _t(origin, "Approve", f"Approved {level}", role, f"{base}{guard} and {next_configured}"),
            _t(origin, "Approve", "Approved", role, f"{base}{guard} and not {next_configured}"),
        ]
    return [_t(origin, "Approve", "Approved", role, f"{base}{guard}")]


def _hold_reject_transitions(origin, guard, base, role, hold_state, can_hold, can_reject):
    """
    Hold/Reject transitions from one origin state, only where the tier permits them.

    Parameters:
        origin (str, required): State the transition acts from.
        guard (str, required): Extra condition suffix (may be empty).
        base (str, required): Company/department/band/pool condition for the tier.
        role (str, required): Tier approver role.
        hold_state (str, required): The tier's On Hold state.
        can_hold (int, required): Whether the tier may hold.
        can_reject (int, required): Whether the tier may reject.

    Returns:
        list[dict]: Zero to two transition rows.
    """
    out = []
    if can_hold:
        out.append(_t(origin, "Hold", hold_state, role, f"{base}{guard}"))
    if can_reject:
        out.append(_t(origin, "Reject", "Rejected", role, f"{base}{guard}"))
    return out


def _reviewer_intercepts(document_type):
    """
    Generic transitions that let an inserted ad-hoc reviewer act on any governed document.

    Emitted once per DocType, independent of matrix rows: the reviewer is pinned by the
    `Additional Approver` record and the session user, not by any band/pool. Each per-record
    `can_hold`/`can_reject` flag is honoured live inside the condition, so the transition can
    exist yet stay unavailable when the record doesn't permit it.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        list[dict]: Reviewer intercept/resume transition rows.
    """
    role = additional_role_name(document_type)
    out = []
    for src in STATE_FOR_TIER.values():
        approve_cond = _reviewer_can_act_cond(src)
        reject_cond = _reviewer_can_act_cond(src, "can_reject")
        hold_cond = _reviewer_can_act_cond(src, "can_hold")
        # From the tier's waiting state: reviewer approves into review, or rejects/holds.
        out.append(_t(src, "Approve", ADDITIONAL_APPROVAL_STATE, role, approve_cond))
        out.append(_t(src, "Reject", "Rejected", role, reject_cond))
        out.append(_t(src, "Hold", ADDITIONAL_HOLD_STATE, role, hold_cond))
        # From the reviewer's own hold: resume into review, or reject.
        out.append(_t(ADDITIONAL_HOLD_STATE, "Approve", ADDITIONAL_APPROVAL_STATE, role, approve_cond))
        out.append(_t(ADDITIONAL_HOLD_STATE, "Reject", "Rejected", role, reject_cond))
    return out


def build_transitions(document_type):
    """
    Build every transition for a DocType from all submitted matrices (see module docstring).

    One set per (company, department, band, tier): Approve (escalate and finalize), plus
    Hold/Reject where that tier allows them.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        list[dict]: Transition rows in generation order.
    """
    amt = amount_field_for(document_type)
    transitions = []

    matrices = frappe.get_all(
        "Approval Matrix",
        filters={"document_type": document_type, "docstatus": 1},
        pluck="name",
    )
    for mname in matrices:
        m = frappe.get_doc("Approval Matrix", mname)
        for row in m.detail:
            levels = configured_levels(row)
            if not levels:
                continue
            band = band_condition(amt, row.min_amount, row.max_amount)
            gate = f"doc.company == {m.company!r} and doc.department == {row.department!r}"
            if band:
                gate = f"{gate} and {band}"

            for level in levels:
                role = role_name(document_type, level)
                # Condition = company + department + amount band + this row's tier pool.
                # The Role is still the coarse gate, but the embedded pool clause pins
                # eligibility to the specific approvers configured for THIS row/tier, so a
                # same-tier approver from another row/department can no longer act here
                # even though they hold the shared `<DocType> - Approver N` role.
                base = f"{gate} and frappe.session.user in {pool(row, level)!r}"
                src = STATE_FOR_TIER[level]
                can_hold = row.get(f"approver_{level}_can_hold")
                can_reject = row.get(f"approver_{level}_can_reject")
                hold_state = f"On Hold by Approver {level}"

                # Escalate vs finalize is decided at RUNTIME by reading the matrix row live
                # (is the NEXT approver tier configured?). Only defined below the top tier;
                # readable-filter form identifies the row by matrix + department + band.
                next_configured = None
                if level < MAX_LEVELS:
                    next_configured = (
                        "frappe.db.get_value('Approval Matrix Detail', "
                        f"{{'parent': {m.name!r}, 'department': {row.department!r}, "
                        f"'min_amount': {row.min_amount or 0}, 'max_amount': {row.max_amount or 0}}}, "
                        f"'approver_{level + 1}_user_1')"
                    )

                # An ad-hoc reviewer inserted at `src` blocks the tier from acting there until
                # it clears; the SAME tier transitions are mirrored FROM `Additionally Approved`
                # so the chain resumes once the reviewer has approved (see doctype/additional_approver).
                block_guard = f" and not {_pending_reviewer_cond(src)}"
                resume_guard = f" and {_reviewer_done_cond(src)}"

                # Normal path (blocked while a reviewer is pending) + resumed path (after review).
                transitions += _approve_transitions(src, block_guard, level, base, role, next_configured)
                transitions += _approve_transitions(
                    ADDITIONAL_APPROVAL_STATE, resume_guard, level, base, role, next_configured)
                transitions += _hold_reject_transitions(
                    src, block_guard, base, role, hold_state, can_hold, can_reject)
                transitions += _hold_reject_transitions(
                    ADDITIONAL_APPROVAL_STATE, resume_guard, base, role, hold_state, can_hold, can_reject)

                # Resume from the tier's OWN hold — unreachable while a reviewer is pending
                # (you cannot insert a reviewer once a document is on hold), so no reviewer guard.
                if can_hold:
                    transitions += _approve_transitions(hold_state, "", level, base, role, next_configured)
                    if can_reject:
                        transitions.append(_t(hold_state, "Reject", "Rejected", role, base))

    transitions += _reviewer_intercepts(document_type)
    return transitions


def _allow_edit(document_type, state):
    """
    Role allowed to edit a document sitting in `state`.

    Parameters:
        document_type (str, required): Target DocType.
        state (str, required): Workflow state.

    Returns:
        str: "All", or the tier's approver role.
    """
    v = ALLOW_EDIT[state]
    return "All" if v == "All" else role_name(document_type, v)


def build_workflow(document_type):
    """
    Create or refresh the single Workflow for a DocType: states + generated transitions.

    An existing workflow is rewritten in place (states and transitions cleared first), so
    the live workflow always reflects the currently submitted matrices.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        str: Name of the saved Workflow.
    """
    existing = frappe.db.get_value("Workflow", {"document_type": document_type}, "name")
    if existing:
        wf = frappe.get_doc("Workflow", existing)
        wf.states = []
        wf.transitions = []
    else:
        wf = frappe.new_doc("Workflow")
        wf.workflow_name = workflow_name(document_type)

    wf.document_type = document_type
    wf.is_active = 1
    wf.workflow_state_field = "workflow_state"
    wf.send_email_alert = 0
    wf.override_status = 0

    for state in STATE_ORDER:
        wf.append("states", {
            "state": state,
            "doc_status": STATE_DOCSTATUS[state],
            "allow_edit": _allow_edit(document_type, state),
        })
    for tr in build_transitions(document_type):
        wf.append("transitions", tr)

    wf.save(ignore_permissions=True)
    return wf.name


# ---------------------------------------------------------------------------
# role <-> user reconciliation
# ---------------------------------------------------------------------------

def reconcile_roles(document_type):
    """
    Align `<DocType> - Approver N` role holders with the users named in submitted matrices.

    Grants the role to users newly added to a tier and revokes it from users no longer in
    any row of that tier, so cancelling or editing a matrix cannot leave stale approvers.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        None
    """
    matrices = frappe.get_all(
        "Approval Matrix",
        filters={"document_type": document_type, "docstatus": 1},
        pluck="name",
    )
    desired = {level: set() for level in range(1, MAX_LEVELS + 1)}
    for mname in matrices:
        m = frappe.get_doc("Approval Matrix", mname)
        for row in m.detail:
            for level in range(1, MAX_LEVELS + 1):
                for user in pool(row, level):
                    desired[level].add(user)

    for level in range(1, MAX_LEVELS + 1):
        role = role_name(document_type, level)
        current = set(frappe.get_all(
            "Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"))
        for user in desired[level] - current:
            _grant_role(user, role)
        for user in current - desired[level]:
            _revoke_role(user, role)


def _grant_role(user, role):
    """
    Give a user an approver role, skipping Administrator/Guest and unknown users.

    Parameters:
        user (str, required): User ID.
        role (str, required): Role name.

    Returns:
        None
    """
    if user in ("Administrator", "Guest") or not frappe.db.exists("User", user):
        return
    frappe.get_doc("User", user).add_roles(role)


def _revoke_role(user, role):
    """
    Remove an approver role from a user, ignoring users that no longer exist.

    Parameters:
        user (str, required): User ID.
        role (str, required): Role name.

    Returns:
        None
    """
    if not frappe.db.exists("User", user):
        return
    frappe.get_doc("User", user).remove_roles(role)


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------

def setup_workflow(document_type):
    """
    Bring everything a governed DocType needs into line (idempotent; run on matrix submit).

    Ensures masters, roles and permissions, the routing department field, then rebuilds the
    workflow from all submitted matrices and reconciles role holders.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        None
    """
    ensure_workflow_states()
    ensure_actions()
    ensure_roles(document_type)
    ensure_role_permissions(document_type)
    ensure_department_read(document_type)
    ensure_company_read(document_type)
    ensure_amount_field(document_type)
    remove_legacy_history_field(document_type)
    ensure_department_field(document_type)
    build_workflow(document_type)
    reconcile_roles(document_type)
    frappe.clear_cache(doctype=document_type)


def on_matrix_cancel(document_type):
    """
    React to a cancelled matrix: rebuild the workflow without it, or deactivate it.

    The workflow is deactivated (never deleted) when no submitted matrix remains for the
    DocType, so in-flight documents keep their recorded state.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        None
    """
    reconcile_roles(document_type)
    remaining = frappe.db.count(
        "Approval Matrix", {"document_type": document_type, "docstatus": 1})
    wf = frappe.db.get_value("Workflow", {"document_type": document_type}, "name")
    if wf:
        if remaining:
            build_workflow(document_type)  # rebuild without the cancelled matrix
        else:
            frappe.db.set_value("Workflow", wf, "is_active", 0)
    frappe.clear_cache(doctype=document_type)
