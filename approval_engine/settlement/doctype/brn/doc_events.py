# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _


def set_total_amount(doc) -> None:
	"""
	Recompute doc.total_amount as the sum of its BRN Item rows' amounts.

	Parameters:
		doc (Document, required): The BRN document being validated.

	Returns:
		None
	"""
	total_amount = 0
	for row in doc.items:
		total_amount += row.amount
	doc.set("total_amount", total_amount)


def validate_comparision_rows(doc) -> None:
	"""
	Enforce the Comparision child table's row-count limits (1 for Single,
	up to 3 for Multi) and the single-Preferred-row constraint.

	Parameters:
		doc (Document, required): The BRN document being validated.

	Returns:
		None
	"""
	row_count = len(doc.comparision or [])

	if doc.get("single") and row_count > 1:
		frappe.throw(_("Only one row is allowed in the Comparision table when Single is checked."))

	if doc.get("multi") and row_count > 3:
		frappe.throw(_("Maximum three rows can be added to the Comparision table when Multi is checked."))

	validate_single_preferred_row(doc)


def validate_single_preferred_row(doc):
	"""Preferred picks the one vendor (new or existing) this BRN moves
	forward with -- for onboarding (see add_onboard_vendor_button) and for
	PO/Invoice creation (see create_purchase_order_button) alike. More
	than one row marked Preferred would make that choice ambiguous."""
	preferred_rows = [row for row in (doc.comparision or []) if row.preferred]

	if len(preferred_rows) > 1:
		frappe.throw(
			_("Only one row in the Comparision table can be marked Preferred, found {0}.").format(
				len(preferred_rows)
			)
		)


def block_requisition_id(doc) -> None:
	"""
	Mark the source Requisition ID as consumed once its BRN is submitted,
	so it can't be reused by another BRN.

	Parameters:
		doc (Document, required): The BRN document being submitted.

	Returns:
		None
	"""
	if doc.quotation_requisition_id:
		frappe.db.set_value(
			"Requisition ID",
			doc.quotation_requisition_id,
			{"block_id": 1, "brn_id": doc.name},
		)
