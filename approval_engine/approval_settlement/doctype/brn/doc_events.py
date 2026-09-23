# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _

# Fields a Preferred Comparision row must carry before submit (fieldname, label).
PREFERRED_ROW_FIELDS = (("email_id", "Email ID"), ("justification", "Justification"))


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
	Enforce the Comparision child table rules: exactly one of Single or
	Multi/RPT, exactly 1 row for Single, at least 3 rows (no upper bound)
	for Multi/RPT, the minimum-3-quotes rule, and exactly one Preferred row.

	Parameters:
	        doc (Document, required): The BRN document being validated.

	Returns:
	        None
	"""
	rows = doc.comparision or []
	row_count = len(rows)

	validate_single_or_multi(doc)

	if doc.get("single") and row_count > 1:
		frappe.throw(_("Only one row is allowed in the Comparision table when Single is checked."))

	validate_minimum_comparison_rows(doc, row_count)
	validate_minimum_quotes(doc, rows)
	validate_single_preferred_row(doc, rows)


def validate_preferred_row_details(doc) -> None:
	"""
	Require Email ID and Justification on the Preferred Comparision row.
	The form enforces this via mandatory_depends_on, but that is client-side
	only -- create_brn(), the REST API and data import bypass it. Runs on
	submit, so create_brn() can still save an incomplete draft.

	Parameters:
	        doc (Document, required): The BRN document being submitted.

	Returns:
	        None
	"""
	for row in doc.comparision or []:
		if not row.preferred:
			continue

		missing = [_(label) for fieldname, label in PREFERRED_ROW_FIELDS if not row.get(fieldname)]
		if missing:
			frappe.throw(
				_("Row #{0} of the Comparision table is marked Preferred, so {1} must be filled in.").format(
					row.idx, _(" and ").join(missing)
				),
				title=_("Preferred Vendor Details Missing"),
			)


def validate_single_or_multi(doc) -> None:
	"""
	Exactly one comparison mode must be chosen: Single, or Multi (RPT counts
	as Multi, since it drives Multi on the client). Both or neither leaves
	the row-count rule ambiguous.

	Parameters:
	        doc (Document, required): The BRN document being validated.

	Returns:
	        None
	"""
	is_multi = doc.get("multi") or doc.get("rpt")

	if doc.get("single") and is_multi:
		frappe.throw(_("Single cannot be combined with Multi or RPT. Please tick only one."))

	if not doc.get("single") and not is_multi:
		frappe.throw(_("Please tick either Single or Multi for the Comparision table."))


def validate_minimum_comparison_rows(doc, row_count: int) -> None:
	"""
	Multi/RPT needs at least 3 vendors to compare; there is no upper limit.

	Parameters:
	        doc (Document, required): The BRN document being validated.
	        row_count (int, required): Number of Comparision rows.

	Returns:
	        None
	"""
	if not (doc.get("multi") or doc.get("rpt")):
		return

	if row_count < 3:
		frappe.throw(
			_(
				"At least 3 rows are required in the Comparision table when Multi or RPT is checked, found {0}."
			).format(row_count)
		)


def validate_minimum_quotes(doc, rows: list) -> None:
	"""
	Require at least 3 quoted rows (Rate filled in) when RPT is checked, or
	when Multi is checked and any vendor is tagged Related Party. Under
	Single a Related Party vendor is allowed on its own -- Single only ever
	has one row, so the 3-quote rule can't apply there.

	Parameters:
	        doc (Document, required): The BRN document being validated.
	        rows (list, required): The BRN's Comparision rows.

	Returns:
	        None
	"""
	is_related_party = any(row.related_party == "Yes" for row in rows)
	related_party_under_multi = is_related_party and doc.get("multi")

	if not doc.get("rpt") and not related_party_under_multi:
		return

	reason = _("RPT is checked") if doc.get("rpt") else _("a vendor is tagged Related Party")
	quoted_rows = [row for row in rows if row.rate]

	if len(quoted_rows) < 3:
		frappe.throw(
			_(
				"At least 3 vendor quotes (Rate filled in) are required in the Comparision table since {0}."
			).format(reason)
		)


def validate_single_preferred_row(doc, rows: list) -> None:
	"""
	Exactly one row must be Preferred once there's at least one row: it's
	the vendor this BRN moves forward with (onboarding and PO/Invoice).
	Zero leaves the choice unmade; more than one makes it ambiguous.

	Parameters:
	        doc (Document, required): The BRN document being validated.
	        rows (list, required): The BRN's Comparision rows.

	Returns:
	        None
	"""
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
