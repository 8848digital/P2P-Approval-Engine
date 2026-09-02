"""Runtime hooks for documents governed by an approval workflow.

Registered on the `validate` event for all DocTypes; they no-op unless the
DocType is managed by an active `<DocType> Approval` workflow.

- block: refuse to save if no Approval Matrix band matches (company/department/amount)
- history: record every workflow state change into `Document Workflow Log` (full audit trail)
"""

import frappe
from frappe import _
from frappe.utils import flt

from approval_engine.generator import (
    workflow_name, amount_field_for, find_band_row,
)


def _managed(doctype):
    return bool(frappe.db.get_value(
        "Workflow",
        {"document_type": doctype, "is_active": 1, "name": workflow_name(doctype)},
        "name",
    ))


def target_validate(doc, method=None):
    if not _managed(doc.doctype):
        return
    _block_if_no_band(doc)
    _record_history(doc)


def _block_if_no_band(doc):
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
    frappe.get_doc({
        "doctype": "Document Workflow Log",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "from_state": old_state,
        "workflow_state": new_state,
        "user": frappe.session.user,
    }).insert(ignore_permissions=True)
