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
	Enforce the Comparision child table's row-count limits (exactly 1 for
	Single, at least 3 with no upper bound for Multi/RPT), the
	minimum-3-quotes rule for RPT/Related Party vendors, and the
	single-Preferred-row constraint.

	Parameters:
		doc (Document, required): The BRN document being validated.

	Returns:
		None
	"""
	rows = doc.comparision or []
	row_count = len(rows)

	if doc.get("single") and row_count > 1:
		frappe.throw(_("Only one row is allowed in the Comparision table when Single is checked."))

	validate_minimum_comparison_rows(doc, row_count)
	validate_minimum_quotes(doc, rows)
	validate_single_preferred_row(doc, rows)


def validate_minimum_comparison_rows(doc, row_count) -> None:
	"""Multi (and RPT, which drives Multi on the client) auto-populates 3
	empty Comparision rows for the user to fill in -- if rows were removed
	afterwards, block save instead of silently allowing fewer than the 3
	vendors that Multi/RPT requires. There is no upper limit -- a user can
	add more than 3 rows freely."""
	if not (doc.get("multi") or doc.get("rpt")):
		return

	if row_count < 3:
		frappe.throw(
			_("At least 3 rows are required in the Comparision table when Multi or RPT is checked, found {0}.").format(
				row_count
			)
		)


def validate_minimum_quotes(doc, rows) -> None:
	"""At least 3 quoted rows (Rate filled in) are required once RPT is
	checked, or once any vendor in the comparison is tagged a Related
	Party -- both cases need multiple quotes on record to justify the
	choice, not just a single vendor's rate."""
	is_related_party = any(row.related_party == "Yes" for row in rows)

	if not doc.get("rpt") and not is_related_party:
		return

	reason = _("RPT is checked") if doc.get("rpt") else _("a vendor is tagged Related Party")
	quoted_rows = [row for row in rows if row.rate]

	if len(quoted_rows) < 3:
		frappe.throw(
			_("At least 3 vendor quotes (Rate filled in) are required in the Comparision table since {0}.").format(
				reason
			)
		)


def validate_single_preferred_row(doc, rows):
	"""Preferred picks the one vendor (new or existing) this BRN moves
	forward with -- for onboarding (see add_onboard_vendor_button) and for
	PO/Invoice creation (see create_purchase_order_button) alike. Exactly
	one row marked Preferred is required once there's at least one row;
	zero would leave that choice unmade, more than one would make it
	ambiguous."""
	if not rows:
		return

	preferred_rows = [row for row in rows if row.preferred]

	if len(preferred_rows) == 0:
		frappe.throw(_("One row in the Comparision table must be marked Preferred."))

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
