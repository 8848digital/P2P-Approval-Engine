# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _
from frappe.model.document import Document


class RequisitionID(Document):
	"""
	Master doctype storing unique Requisition IDs referenced by BRN
	records, with an optional flag (`block_id`) to block reuse once the
	related BRN is submitted.

	Carries no custom validation of its own; uniqueness of
	`requisition_no` is enforced by the DocType schema.
	"""

	pass


def block_requisition_id(doc: Document, method: str) -> None:
	"""
	Doc event handler that prevents a document from being saved when its
	`requisition_id` value is already used by another Requisition ID
	document.

	Parameters:
	        doc (Document, required): The document being validated.
	        method (str, required): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	if doc.requisition_id:
		existing_doc = frappe.get_all(
			"Requisition ID",
			filters={"requisition_id": doc.requisition_id, "name": ["!=", doc.name]},
		)
		if existing_doc:
			frappe.throw(
				_("Requisition ID '{0}' already exists in another document.").format(doc.requisition_id)
			)
