"""Runtime hooks for documents governed by an approval workflow.

Registered on the `validate` event for all DocTypes; they no-op unless the
DocType is managed by an active `<DocType> Approval` workflow.

- block: refuse to save if no Approval Matrix band matches (company/department/amount)
- history: record each approval into `custom_workflow_history` (powers no-repeat)
"""

import frappe
from frappe import _
from frappe.utils import flt

from approval_engine.generator import (
    workflow_name, amount_field_for, find_band_row,
)

APPROVAL_STATES = {"Approved 1", "Approved 2", "Approved 3", "Approved"}


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
    new_state = doc.get("workflow_state")
    if new_state not in APPROVAL_STATES:
        return
    before = doc.get_doc_before_save()
    old_state = before.get("workflow_state") if before else None
    if new_state == old_state:
        return
    # avoid duplicate rows if validate runs twice for the same transition
    for r in (doc.get("custom_workflow_history") or []):
        if r.user == frappe.session.user and r.workflow_state == new_state:
            return
    doc.append("custom_workflow_history", {
        "user": frappe.session.user,
        "workflow_state": new_state,
    })
