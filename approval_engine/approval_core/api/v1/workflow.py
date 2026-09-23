# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for the Approval Matrix / workflow-generation UI.

Thin wrappers over ``approval_core.generator``; the resolution logic lives
there, these only expose it and shape the response envelope.
"""

import frappe

from approval_engine.approval_core import generator
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
