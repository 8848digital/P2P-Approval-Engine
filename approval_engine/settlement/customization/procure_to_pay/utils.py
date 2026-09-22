# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Validation logic shared by Purchase Order and Purchase Invoice around
fiscal-year alignment and BRN service-period dates.

Relocated out of settlement/utils.py, which had become a catch-all for
PO/PI-specific validation despite its generic module-root name -- both
functions branch on or are called for either doctype, so they live here
under procure_to_pay/ rather than under just one of purchase_order/ or
purchase_invoice/.
"""

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import getdate


def get_fiscal_year_and_validity(posting_date: str, brn: str | None = None) -> dict:
	"""
	Resolve the fiscal year for a posting date, and (if a BRN is given)
	clamp its service period to that fiscal year's bounds.

	Parameters:
		posting_date (str, required): The transaction/posting date to resolve.
		brn (str, optional): A BRN document name whose service period should
			be validated against and clamped to the resolved fiscal year.

	Returns:
		dict: {"fiscal_year": str} always; plus "validity_start_date" and
			"validity_end_date" (date) when brn is given and has a service
			period that overlaps the fiscal year.
	"""
	if not posting_date:
		frappe.throw(_("Posting Date is required"))

	fiscal_year, fy_start, fy_end = get_fiscal_year(getdate(posting_date))

	result = {"fiscal_year": fiscal_year}

	if not brn:
		return result

	service_start_date, expiry_date = frappe.db.get_value("BRN", brn, ["service_start_date", "expiry_date"])

	if not (service_start_date and expiry_date):
		return result

	service_start = getdate(service_start_date)
	service_end = getdate(expiry_date)

	# No overlap between BRN service period and fiscal year at all
	if service_end < fy_start or service_start > fy_end:
		frappe.throw(
			_(
				"BRN service period ({0} to {1}) does not fall within fiscal year {2} "
				"({3} to {4}). Please correct the Posting Date."
			).format(service_start, service_end, fiscal_year, fy_start, fy_end),
			title=_("Invalid Validity Period"),
		)

	result["validity_start_date"] = fy_start if service_start < fy_start else service_start
	result["validity_end_date"] = fy_end if service_end > fy_end else service_end

	return result


def validate_fiscal_year_and_brn_dates(doc, method: str | None = None) -> None:
	"""
	doc_events hook body (Purchase Order/Purchase Invoice validate): sets
	doc.custom_fiscal_year and, when the linked BRN's service period is
	found, doc.validity_start_date/validity_end_date -- gated by the
	JFS Settings toggle so sites that don't use BRN validity can opt out.

	Parameters:
		doc (Document, required): The Purchase Order or Purchase Invoice
			document being validated.
		method (str, optional): The hook event name passed by Frappe.

	Returns:
		None
	"""
	if not frappe.db.get_single_value("JFS Settings", "validate_brn_service_dates_in_po_pi"):
		return

	if doc.doctype == "Purchase Order":
		date = doc.transaction_date
	elif doc.doctype == "Purchase Invoice":
		date = doc.posting_date
	else:
		return

	brn_data = get_fiscal_year_and_validity(date, doc.brn)

	if not brn_data:
		return

	doc.custom_fiscal_year = brn_data.get("fiscal_year")
	if brn_data.get("validity_start_date"):
		doc.validity_start_date = brn_data.get("validity_start_date")
		doc.validity_end_date = brn_data.get("validity_end_date")


def validate_brn_dates(brn: str, transaction_date: str) -> dict:
	"""
	Check a transaction date against a BRN's service start/expiry dates.
	Used by the PO/PI client scripts to warn before the date is even saved.

	Parameters:
		brn (str, required): The BRN document name.
		transaction_date (str, required): The date to check.

	Returns:
		dict: {"status": "valid" | "before_start" | "expired", plus
			"start_date"/"expiry_date" (str) when status isn't "valid"}
	"""
	start_date, expiry_date = frappe.db.get_value("BRN", brn, ["service_start_date", "expiry_date"])

	if not (start_date and expiry_date):
		return {"status": "valid"}

	transaction_date = getdate(transaction_date)

	if transaction_date < getdate(start_date):
		return {"status": "before_start", "start_date": str(start_date), "expiry_date": str(expiry_date)}

	if transaction_date > getdate(expiry_date):
		return {"status": "expired", "start_date": str(start_date), "expiry_date": str(expiry_date)}

	return {"status": "valid"}
