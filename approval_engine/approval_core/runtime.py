# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Runtime hooks for documents governed by an approval workflow.

Registered on the `validate` event for all DocTypes; they no-op unless the
DocType is managed by an active `<DocType> Approval` workflow.

- block: refuse to save if no Approval Matrix band matches (company/department/amount)
- history: record every workflow state change into `Document Workflow Log` (full audit trail),
  with the approver's remarks (mandatory on Reject — see `remarks.py`)

Registered on `on_update` too: after a state change, retire the document's open
email links and queue the next tier's action-link emails (see `email_action/`).
"""

import frappe
from frappe import _
from frappe.utils import flt

from approval_engine.approval_core.generator import (
    workflow_name, amount_field_for, find_band_row,
    ADDITIONAL_APPROVAL_STATE, ADDITIONAL_HOLD_STATE,
)
from approval_engine.approval_core.doctype.additional_approver.additional_approver_utils import (
    mark_reviewer_completed, close_reviewer,
)
from approval_engine.approval_core.email_action.action_link import supersede_links
from approval_engine.approval_core.remarks import (
    add_timeline_comment, pop_transition_remarks, validate_reject_reason,
)

# States in which no one is emailed on entry: terminal, or the reviewer's own hold.
NO_EMAIL_STATES = ("Approved", "Rejected", ADDITIONAL_HOLD_STATE)


def _managed(doctype):
    """
    Whether `doctype` currently runs on an active engine-generated workflow.

    Parameters:
        doctype (str, required): DocType to check.

    Returns:
        bool: True when its `<DocType> Approval` workflow exists and is active.
    """
    return bool(frappe.db.get_value(
        "Workflow",
        {"document_type": doctype, "is_active": 1, "name": workflow_name(doctype)},
        "name",
    ))


def target_validate(doc, method=None):
    """
    `validate` hook for every DocType: band gate + transition history for managed ones.

    Parameters:
        doc (Document, required): Document being saved.
        method (str, optional): Hook event name passed by Frappe.

    Returns:
        None
    """
    if not _managed(doc.doctype):
        return
    _block_if_no_band(doc)
    _record_history(doc)


def target_on_update(doc, method=None):
    """
    `on_update` hook for every DocType: on a workflow state change of a managed document,
    retire its open email links and queue emails for whoever must act next.

    Links are retired synchronously (same transaction as the state change); emails go
    out from a job queued only after commit, so a rolled-back save never emails anyone.

    Parameters:
        doc (Document, required): Document that was saved.
        method (str, optional): Hook event name passed by Frappe.

    Returns:
        None
    """
    if not doc.get("workflow_state") or not doc.has_value_changed("workflow_state"):
        return
    if not _managed(doc.doctype):
        return
    supersede_links(doc.doctype, doc.name)
    _sync_additional_reviewer(doc)
    if doc.workflow_state in NO_EMAIL_STATES:
        return  # nobody to email (terminal, or the reviewer resumes from their own hold)
    frappe.enqueue(
        "approval_engine.approval_core.tasks.send_action_emails",
        queue="short",
        enqueue_after_commit=True,
        doctype=doc.doctype,
        name=doc.name,
        workflow_state=doc.workflow_state,
    )


def _sync_additional_reviewer(doc):
    """
    Keep the active `Additional Approver` record in step with the document's state.

    Marks the reviewer completed when the document enters `Additionally Approved` (they just
    approved), and retires the reviewer once the chain has moved past the review step or the
    document is rejected. Driven here because the state change lives on the target document,
    not on the reviewer record.

    Parameters:
        doc (Document, required): The governed document that changed state.

    Returns:
        None
    """
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    new_state = doc.workflow_state

    if new_state == ADDITIONAL_APPROVAL_STATE:
        mark_reviewer_completed(doc.doctype, doc.name)
    elif old_state == ADDITIONAL_APPROVAL_STATE or new_state == "Rejected":
        close_reviewer(doc.doctype, doc.name)


def _block_if_no_band(doc):
    """
    Refuse to save a governed document that no Approval Matrix band covers.

    Parameters:
        doc (Document, required): Document being saved.

    Returns:
        None
    """
    if not doc.get("department"):
        frappe.throw(_("Please set Department — it is required for approval routing."))
    amount = flt(doc.get(amount_field_for(doc.doctype)))
    row = find_band_row(doc.doctype, doc.company, doc.get("department"), amount)
    if not row:
        frappe.throw(_("No approval matrix band is defined for {0} / {1} at amount {2}. "
                       "Cannot process this document.")
                     .format(doc.company, doc.get("department"), amount))


def _record_history(doc):
    """Log every workflow state change (create/approve/hold/resume/reject) so the
    Document Workflow Log is a full audit trail — who moved the document from which
    state to which, and when (standard `creation`). This is what lets the dashboard
    attribute an on-hold document to the user who actually placed the hold."""
    new_state = doc.get("workflow_state")
    if not new_state:
        return
    # Skip on creation: the desk form sets workflow_state='Pending' on the new doc, but the
    # document isn't in the DB yet, so logging here would fail the log's reference_name
    # (Dynamic Link) validation. The create -> Pending event is intentionally not logged
    # anyway (DECISIONS #14a) — real transitions only ever happen on already-saved docs.
    if doc.is_new():
        return
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    if new_state == old_state:
        return
    # Skip if the latest logged state for this doc already matches — guards against
    # `validate` firing more than once within a single save/transition.
    last = frappe.get_all(
        "Document Workflow Log",
        filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
        fields=["workflow_state"], order_by="creation desc", limit=1,
    )
    if last and last[0].workflow_state == new_state:
        return

    # Popped only once we know this is a real, not-yet-logged transition, so a repeated
    # `validate` can't consume the remarks before the logging pass sees them.
    note = pop_transition_remarks(doc, new_state)
    validate_reject_reason(new_state, note.remarks)

    frappe.get_doc({
        "doctype": "Document Workflow Log",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "from_state": old_state,
        "workflow_state": new_state,
        "user": frappe.session.user,
        "remarks": note.remarks,
        "via_email_link": note.via_email_link,
    }).insert(ignore_permissions=True)

    if note.remarks:
        add_timeline_comment(doc, new_state, note.remarks)
