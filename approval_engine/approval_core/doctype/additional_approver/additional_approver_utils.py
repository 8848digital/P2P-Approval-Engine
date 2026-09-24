# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Business logic for the ad-hoc `Additional Approver` feature.

An `Additional Approver` record injects one extra sequential approver into a single
document's approval chain, at the juncture the document currently sits in — without
touching the shared Approval Matrix. The generic transitions that route a document
through the reviewer are baked into the generated workflow (see
`generator.build_transitions`); this module owns everything around those transitions:

- who may add a reviewer (an eligible approver of that document),
- the "one active reviewer per document" rule,
- granting/revoking the coarse `<DocType> - Additional Approver` role per record, and
- flipping the record's `completed` / `active` flags as the document moves through the
  `Additionally Approved` state (driven from `runtime.target_on_update`).
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from approval_engine.approval_core.generator import (
    STATE_FOR_TIER,
    additional_role_name,
    configured_levels,
    find_band_row,
    amount_field_for,
    pool,
    workflow_name,
)

DOCTYPE = "Additional Approver"

# States a document can sit in when a reviewer is inserted: the approve-chain
# waiting states, each of which has a configured tier that acts next.
INSERTABLE_STATES = set(STATE_FOR_TIER.values())

# Roles that may inject a reviewer even without being a configured approver.
MANAGER_ROLES = ("System Manager", "Approval Manager")


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------

def pending_reviewer(reference_doctype, reference_name):
    """
    The active reviewer that has NOT yet acted on a document, if any.

    Parameters:
        reference_doctype (str, required): Target document's DocType.
        reference_name (str, required): Target document's name.

    Returns:
        str | None: Name of the `Additional Approver` record, or None.
    """
    return frappe.db.get_value(DOCTYPE, {
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "active": 1,
        "completed": 0,
    }, "name")


def current_reviewer(reference_doctype, reference_name):
    """
    The active reviewer for a document regardless of whether they have acted yet.

    Used while the document sits in `Additionally Approved` (reviewer acted, chain not
    yet resumed) to know whose role to retire once it moves on.

    Parameters:
        reference_doctype (str, required): Target document's DocType.
        reference_name (str, required): Target document's name.

    Returns:
        str | None: Name of the `Additional Approver` record, or None.
    """
    return frappe.db.get_value(DOCTYPE, {
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "active": 1,
    }, "name")


def is_governed(document_type):
    """
    Whether a DocType runs on an active engine-generated workflow.

    Parameters:
        document_type (str, required): Target DocType.

    Returns:
        bool: True when its `<DocType> Approval` workflow exists and is active.
    """
    return bool(frappe.db.get_value(
        "Workflow",
        {"document_type": document_type, "is_active": 1, "name": workflow_name(document_type)},
        "name",
    ))


def is_eligible_approver(reference_doctype, reference_name, user):
    """
    Whether `user` may inject an additional approver into this document's chain.

    Eligible = a configured approver of the document (named in any tier of its matched
    Approval Matrix band row), or a manager role. Managers aside, this deliberately
    mirrors who can actually act on the document.

    Parameters:
        reference_doctype (str, required): Target document's DocType.
        reference_name (str, required): Target document's name.
        user (str, required): User attempting to add the reviewer.

    Returns:
        bool: True when the user is allowed to add a reviewer.
    """
    if set(MANAGER_ROLES) & set(frappe.get_roles(user)):
        return True

    doc = frappe.get_doc(reference_doctype, reference_name)
    amount = frappe.utils.flt(doc.get(amount_field_for(reference_doctype)))
    row = find_band_row(reference_doctype, doc.get("company"), doc.get("department"), amount)
    if not row:
        return False
    eligible = {approver for level in configured_levels(row) for approver in pool(row, level)}
    return user in eligible


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def add_additional_approver(reference_doctype, reference_name, approver,
                            can_hold=0, can_reject=0, action_via_email=0):
    """
    Insert one ad-hoc additional approver into a document's live approval chain.

    Authorises the caller, enforces the one-active-reviewer rule, captures the
    document's current workflow state as the insertion point, and creates the record.
    Plain business logic — the whitelisted wrapper lives under `api/v1/`.

    Parameters:
        reference_doctype (str, required): Target document's DocType.
        reference_name (str, required): Target document's name.
        approver (str, required): User to insert as the additional approver.
        can_hold (int, optional): Whether the reviewer may place the document on hold.
        can_reject (int, optional): Whether the reviewer may reject the document.
        action_via_email (int, optional): Whether to email the reviewer an action link.

    Returns:
        str: Name of the created `Additional Approver` record.
    """
    caller = frappe.session.user
    if not is_eligible_approver(reference_doctype, reference_name, caller):
        frappe.throw(_("Only an approver of this document can add an additional approver."),
                     frappe.PermissionError)

    doc = frappe.get_doc(reference_doctype, reference_name)
    insert_state = doc.get("workflow_state")
    if insert_state not in INSERTABLE_STATES:
        frappe.throw(_("An additional approver can only be added while the document is "
                       "awaiting a configured approver (current state: {0}).")
                     .format(_(insert_state or "—")))

    if pending_reviewer(reference_doctype, reference_name):
        frappe.throw(_("This document already has a pending additional approver. "
                       "It must be actioned before another can be added."))

    if approver == caller:
        frappe.throw(_("You cannot add yourself as the additional approver."))

    record = frappe.get_doc({
        "doctype": DOCTYPE,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "approver": approver,
        "insert_state": insert_state,
        "can_hold": can_hold,
        "can_reject": can_reject,
        "action_via_email": action_via_email,
        "active": 1,
        "completed": 0,
        "added_by": caller,
    })
    record.insert(ignore_permissions=True)
    return record.name


# ---------------------------------------------------------------------------
# validation (controller)
# ---------------------------------------------------------------------------

def validate_reviewer(doc):
    """
    Enforce the invariants of an `Additional Approver` record on save.

    Guards direct inserts as well as the API path: the target must be governed, the
    captured `insert_state` must be a real waiting state, and no other reviewer may be
    pending on the same document at the same time.

    Parameters:
        doc (Document, required): The `Additional Approver` being saved.

    Returns:
        None
    """
    if not is_governed(doc.reference_doctype):
        frappe.throw(_("{0} is not governed by an approval workflow.")
                     .format(_(doc.reference_doctype)))

    if doc.insert_state not in INSERTABLE_STATES:
        frappe.throw(_("Insert State {0} is not a valid approval-chain state.")
                     .format(doc.insert_state))

    other = frappe.db.get_value(DOCTYPE, {
        "reference_doctype": doc.reference_doctype,
        "reference_name": doc.reference_name,
        "active": 1,
        "completed": 0,
        "name": ("!=", doc.name),
    }, "name")
    if other:
        frappe.throw(_("This document already has a pending additional approver ({0}).")
                     .format(other))


# ---------------------------------------------------------------------------
# lifecycle driven from runtime (target document state changes)
# ---------------------------------------------------------------------------

def mark_reviewer_completed(reference_doctype, reference_name):
    """
    Flag the pending reviewer as completed when the document enters `Additionally Approved`.

    Called from `runtime.target_on_update` the moment the reviewer's Approve moves the
    document into the review state; the chain then resumes at the configured tier.

    Parameters:
        reference_doctype (str, required): Target document's DocType.
        reference_name (str, required): Target document's name.

    Returns:
        None
    """
    name = pending_reviewer(reference_doctype, reference_name)
    if not name:
        return
    frappe.db.set_value(DOCTYPE, name,
                        {"completed": 1, "acted_on": now_datetime()},
                        update_modified=False)


def close_reviewer(reference_doctype, reference_name):
    """
    Retire the active reviewer once the chain has moved past the review step.

    Sets `active = 0` and revokes the `<DocType> - Additional Approver` role from the
    reviewer unless they still hold another active assignment on the same DocType.
    Called when the document leaves `Additionally Approved` (tier resumed) or is rejected.

    Parameters:
        reference_doctype (str, required): Target document's DocType.
        reference_name (str, required): Target document's name.

    Returns:
        None
    """
    name = current_reviewer(reference_doctype, reference_name)
    if not name:
        return
    approver = frappe.db.get_value(DOCTYPE, name, "approver")
    frappe.db.set_value(DOCTYPE, name, "active", 0, update_modified=False)
    revoke_additional_role_if_last(reference_doctype, approver)


# ---------------------------------------------------------------------------
# notification
# ---------------------------------------------------------------------------

def notify_reviewer(record_name):
    """
    Queue the action-link email to a newly-added reviewer (after commit).

    Enqueued rather than sent inline so a rolled-back insertion never emails anyone.

    Parameters:
        record_name (str, required): Name of the `Additional Approver` record.

    Returns:
        None
    """
    reference_doctype, reference_name, approver = frappe.db.get_value(
        DOCTYPE, record_name, ["reference_doctype", "reference_name", "approver"])
    frappe.enqueue(
        "approval_engine.approval_core.tasks.send_reviewer_email",
        queue="short",
        enqueue_after_commit=True,
        reference_doctype=reference_doctype,
        reference_name=reference_name,
        approver=approver,
    )


# ---------------------------------------------------------------------------
# role grant / revoke (per record, dynamic — not part of reconcile_roles)
# ---------------------------------------------------------------------------

def grant_additional_role(document_type, approver):
    """
    Give a reviewer the coarse `<DocType> - Additional Approver` role (idempotent).

    Parameters:
        document_type (str, required): Target DocType the reviewer acts on.
        approver (str, required): Reviewer user ID.

    Returns:
        None
    """
    if approver in ("Administrator", "Guest") or not frappe.db.exists("User", approver):
        return
    # Saved with ignore_permissions: the grant is a system action triggered by an approver
    # who is authorised to add the reviewer but does not (and need not) hold write access to
    # the User doctype. Mirrors the engine's other ignore_permissions role operations.
    role = additional_role_name(document_type)
    user_doc = frappe.get_doc("User", approver)
    if role in {r.role for r in user_doc.get("roles")}:
        return
    user_doc.append_roles(role)
    user_doc.save(ignore_permissions=True)


def revoke_additional_role_if_last(document_type, approver):
    """
    Remove the additional-approver role from a reviewer once they have no active
    assignment left for this DocType.

    A user can be the live reviewer on more than one document at a time ("one at a
    time" is per document, not per user), so the role is stripped only when their last
    active assignment on this DocType closes — keeping least privilege without breaking
    a concurrent review.

    Parameters:
        document_type (str, required): Target DocType.
        approver (str, required): Reviewer user ID.

    Returns:
        None
    """
    if not frappe.db.exists("User", approver):
        return
    still_active = frappe.db.exists(DOCTYPE, {
        "reference_doctype": document_type,
        "approver": approver,
        "active": 1,
    })
    if still_active:
        return
    # ignore_permissions: revoke fires from the runtime state-change hook, running as whoever
    # acted (a tier approver / the reviewer), none of whom hold User write access.
    role = additional_role_name(document_type)
    user_doc = frappe.get_doc("User", approver)
    remaining = [r for r in user_doc.get("roles") if r.role != role]
    if len(remaining) == len(user_doc.get("roles")):
        return
    user_doc.set("roles", remaining)
    user_doc.save(ignore_permissions=True)
