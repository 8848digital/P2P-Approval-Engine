# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints backing the "Workflow Activity" form sidebar.

Thin wrappers over ``approval_core.activity``; the reconstruction logic lives
there, these only expose it and shape the response envelope.
"""

import frappe

from approval_engine.approval_core import activity
from approval_engine.utils.api_handlers.response_formatter import api_response


@frappe.whitelist()
def get_managed_doctypes():
	"""Target DocTypes that currently have an active engine-generated workflow.

	Used by the client to register the sidebar renderer only where relevant.

	Path: approval_engine.approval_core.api.v1.activity.get_managed_doctypes
	Method: GET

	Parameters:
	    None

	Returns:
	    dict: Envelope whose ``data`` is a list of DocType names.
	"""
	return api_response(
		data=activity.managed_doctypes(),
		message="Managed DocTypes fetched successfully",
	)


@frappe.whitelist()
def get_workflow_activity(doctype, name):
	"""Approver chain + live status for a single target document.

	Path: approval_engine.approval_core.api.v1.activity.get_workflow_activity
	Method: GET

	Parameters:
	    doctype (str, required): Target document's DocType.
	    name (str, required): Target document's name.

	Returns:
	    dict: Envelope whose ``data`` is
	    ``{"managed": bool, "current_state": str, "steps": list}``.
	"""
	return api_response(
		data=activity.workflow_activity(doctype, name),
		message="Workflow activity fetched successfully",
	)
