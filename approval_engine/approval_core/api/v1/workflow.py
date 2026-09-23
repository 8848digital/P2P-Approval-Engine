# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for the Approval Matrix / workflow-generation UI and Desk workflow actions.

Thin wrappers over ``approval_core.generator`` and ``approval_core.remarks``; the logic lives
there, these only expose it and shape the response envelope.
"""

import frappe

from approval_engine.approval_core import generator
from approval_engine.approval_core import remarks as remarks_service
from approval_engine.utils.api_handlers.response_formatter import api_response


@frappe.whitelist()
def get_amount_field_info(document_type):
	"""Which amount field a DocType's bands will compare against, and its source.

	Reports the resolved amount field for the Approval Matrix form, and whether
	it comes from an explicit Approval Settings mapping or a fallback default.

	Path: approval_engine.approval_core.api.v1.workflow.get_amount_field_info
	Method: GET

	Parameters:
	    document_type (str, required): Target DocType to resolve the amount
	        field for.

	Returns:
	    dict: Envelope whose ``data`` is
	    ``{amount_field, is_explicit, exists, label}`` (or ``{}`` when
	    ``document_type`` is empty).
	"""
	if not document_type:
		return api_response(data={}, message="No document type provided")
	return api_response(
		data=generator.resolve_amount_field(document_type),
		message="Amount field info fetched successfully",
	)


@frappe.whitelist(methods=["POST"])
def stash_remarks(doctype: str, name: str, action: str, remarks: str | None = None):
	"""Hold the approver's remarks for the workflow action they are about to apply.

	    Called by the Desk workflow-action dialog just before Frappe's standard
	    `apply_workflow`; the transition log picks the remarks up and a Reject without
	    one is refused server-side.

	    **Endpoint:** `/api/method/approval_engine.approval_core.api.v1.workflow.stash_remarks`
	    **HTTP Method:** POST
	    **Parameters:**
	        - doctype (str, required): Target document's DocType
	        - name (str, required): Target document's name
	        - action (str, required): Workflow action about to be applied (Approve/Hold/Reject)
	        - remarks (str, optional): Approver's note; mandatory when action is Reject
	    **Response:**
	```json
	        {
	            "status": true,
	            "status_code": 200,
	            "message": "Remarks saved",
	            "data": null,
	            "errors": null
	        }
	```
	"""
	remarks_service.stash_remarks(doctype, name, action, remarks)
	return api_response(message="Remarks saved")
