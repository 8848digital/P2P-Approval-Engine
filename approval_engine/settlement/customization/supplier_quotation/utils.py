# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Business logic for Supplier Quotation customization hooks."""

import frappe


def ensure_requisition_number(doc) -> None:
	"""
	Auto-generate and persist a Requisition ID for a Supplier Quotation
	created against "New Requisition" that hasn't been assigned one yet.

	Parameters:
	        doc (Document, required): The Supplier Quotation document.

	Returns:
	        None
	"""
	if doc.custom_requisition_id != "New Requisition" or doc.custom_requisition_no:
		return

	requisition_id = frappe.model.naming.make_autoname("REQ-.YYYY.-.###")
	requisition_doc = frappe.get_doc(
		{
			"doctype": "Requisition ID",
			"requisition_no": requisition_id,
		}
	)
	requisition_doc.insert(ignore_permissions=True, ignore_mandatory=True)

	doc.custom_requisition_no = requisition_doc.requisition_no
	doc.flags.ignore_mandatory = True
	doc.save()
