# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Background and scheduled jobs of the Approval Core module (targets of hooks.py / enqueue)."""

import frappe

from approval_engine.approval_core.email_action.action_link import expire_stale_links
from approval_engine.approval_core.email_action.notify import (
    ActionRequestNotifier,
    send_reviewer_request,
)
from approval_engine.approval_core.doctype.additional_approver.additional_approver_utils import (
    pending_reviewer,
)


def send_action_emails(doctype, name, workflow_state):
    """
    Email action links to the approvers who must act on a document in `workflow_state`.

    Enqueued after commit by `runtime.target_on_update`. Skips quietly when the
    document has since been deleted or moved on: the newer state's own job emails
    the right people instead.

    Parameters:
        doctype (str, required): Target document's DocType.
        name (str, required): Target document's name.
        workflow_state (str, required): State the document entered when the job was queued.

    Returns:
        None
    """
    if not frappe.db.exists(doctype, name):
        return
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus != 0 or doc.get("workflow_state") != workflow_state:
        return
    ActionRequestNotifier(doc).run()


def send_reviewer_email(reference_doctype, reference_name, approver):
    """
    Email an ad-hoc additional approver their action link (enqueued after commit).

    Skips quietly when the reviewer is no longer the document's pending reviewer — e.g. the
    insertion was undone or already actioned before the job ran.

    Parameters:
        reference_doctype (str, required): Target document's DocType.
        reference_name (str, required): Target document's name.
        approver (str, required): The reviewer to email.

    Returns:
        None
    """
    if not pending_reviewer(reference_doctype, reference_name):
        return
    send_reviewer_request(reference_doctype, reference_name, approver)


def expire_action_links():
    """
    Daily housekeeping: mark approval links past their validity window as Expired.

    Returns:
        None
    """
    expire_stale_links()
