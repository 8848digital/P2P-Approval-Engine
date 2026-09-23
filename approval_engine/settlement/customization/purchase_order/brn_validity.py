# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from approval_engine.settlement.customization.procure_to_pay.utils import validate_brn_dates


def validate_transaction_date_within_brn_validity(doc, method: str | None = None) -> None:
	"""
	Purchase Order validate hook: block save if the linked BRN is not a
	submitted, open BRN, or if Transaction Date falls outside its Service
	Start Date/Expiry Date window.

	Unlike validate_fiscal_year_and_brn_dates (gated behind JFS Settings'
	validate_brn_service_dates_in_po_pi toggle, and only checks fiscal-year
	overlap, not the exact BRN window), this always runs and is a hard
	stop, not a dismissible warning -- a PO must not be raised for a date
	the BRN doesn't actually cover.

	Parameters:
	        doc (Document, required): The Purchase Order document being validated.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	if not doc.brn:
		return

	brn_link = get_link_to_form("BRN", doc.brn)
	validate_brn_is_usable(doc.brn, brn_link)

	result = validate_brn_dates(doc.brn, doc.transaction_date)

	if result["status"] == "before_start":
		frappe.throw(
			_("Transaction Date {0} is before {1}'s Service Start Date ({2}).").format(
				doc.transaction_date, brn_link, result["start_date"]
			),
			title=_("Invalid Transaction Date"),
		)

	if result["status"] == "expired":
		frappe.throw(
			_(
				"Transaction Date {0} is after {1}'s Expiry Date ({2}). "
				"A Purchase Order cannot be created against this BRN for that date."
			).format(doc.transaction_date, brn_link, result["expiry_date"]),
			title=_("Invalid Transaction Date"),
		)


def validate_brn_is_usable(brn: str, brn_link: str) -> None:
	"""
	Block a Purchase Order against a BRN that isn't submitted (draft or
	cancelled) or whose status is Closed -- only an approved, open BRN may
	have POs raised against it.

	Parameters:
	        brn (str, required): The BRN document name.
	        brn_link (str, required): HTML link to the BRN, for the error message.

	Returns:
	        None
	"""
	values = frappe.db.get_value("BRN", brn, ["docstatus", "status"], as_dict=True)
	if not values:
		frappe.throw(_("BRN {0} not found.").format(brn), title=_("Invalid BRN"))

	if values.docstatus == 0:
		frappe.throw(
			_("{0} is still a draft. Submit the BRN before raising a Purchase Order against it.").format(
				brn_link
			),
			title=_("BRN Not Submitted"),
		)

	if values.docstatus == 2:
		frappe.throw(
			_("{0} is cancelled. A Purchase Order cannot be raised against it.").format(brn_link),
			title=_("BRN Cancelled"),
		)

	if values.status == "Closed":
		frappe.throw(
			_("{0} is Closed. A Purchase Order cannot be raised against it.").format(brn_link),
			title=_("BRN Closed"),
		)
