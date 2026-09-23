# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Background and scheduled jobs of the Approval Core module (targets of hooks.py / enqueue)."""

import frappe

from approval_engine.approval_core.email_action.action_link import expire_stale_links
from approval_engine.approval_core.email_action.notify import ActionRequestNotifier


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


def expire_action_links():
	"""
	Daily housekeeping: mark approval links past their validity window as Expired.

	Returns:
	    None
	"""
	expire_stale_links()
