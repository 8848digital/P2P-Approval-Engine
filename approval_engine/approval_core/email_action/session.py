# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Run a block of code as the approver who owns an emailed link.

Workflow transition conditions read `frappe.session.user` and the user's roles, so
the guest request must briefly *become* the approver for `get_transitions` /
`apply_workflow` to evaluate exactly as they would in Desk.
"""

from contextlib import contextmanager

import frappe


@contextmanager
def acting_as(user):
	"""
	Temporarily switch the request's session user, restoring it afterwards.

	`frappe.set_user` also resets the session id, session data and form_dict; all
	three are put back so the rest of the (guest) request is unaffected.

	Example:
	    with acting_as("approver@example.com"):
	        apply_workflow(doc, "Approve")

	Parameters:
	    user (str, required): User to act as.

	Returns:
	    Iterator[None]: Context manager; yields nothing.
	"""
	previous_session = frappe._dict(frappe.local.session)
	previous_form_dict = frappe.local.form_dict

	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(previous_session.user)
		frappe.local.session.update(previous_session)
		frappe.local.form_dict = previous_form_dict
