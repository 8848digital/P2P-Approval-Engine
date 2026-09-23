# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Guest page `/approval_action?token=...`: review a document and act on it from an email link.

Rendering is read-only on purpose: mail security scanners open every link in an
email, so nothing here may change state. Actions go through the POST endpoints in
`approval_core/api/v1/email_action.py`, which also require an emailed OTP.
"""

import frappe
from frappe import _

from approval_engine.approval_core.email_action.link_actions import get_link_summary

no_cache = 1
sitemap = 0


def get_context(context):
	"""
	Build the page context from the link token in the query string.

	Parameters:
	    context (frappe._dict, required): Page context supplied by Frappe's website renderer.

	Returns:
	    None
	"""
	context.no_header = 1
	context.no_breadcrumbs = 1
	context.token = frappe.form_dict.get("token") or ""
	context.summary = get_link_summary(context.token)
	context.title = (
		_("{0} · Approval request").format(context.summary["document"]["name"])
		if context.summary["valid"]
		else _("Approval request")
	)
