"""Fiscal-year / cut-off resolution for ITC reversal. Split out of
purchase_invoice_itc_reversal.py to keep that file under the line-count
cap. Re-exported from there (see that file) so existing import/mock.patch
paths targeting that module keep working.
"""

from datetime import date, timedelta

import frappe
from frappe.utils import cint, getdate, nowdate


def get_fiscal_year_doc(for_date: str | date, company: str | None = None):
	"""Returns the Fiscal Year document that contains the given date."""
	for_date = getdate(for_date)
	fy_name = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ["<=", for_date], "year_end_date": [">=", for_date]},
		"name",
	)
	if not fy_name:
		frappe.throw(
			f"No Fiscal Year record found covering the date {for_date}. "
			f"Please create it under Accounts > Fiscal Year."
		)
	return frappe.get_doc("Fiscal Year", fy_name)


def get_current_fiscal_year_doc():
	"""The Fiscal Year that contains TODAY's system date."""
	return get_fiscal_year_doc(getdate(nowdate()))


def get_cutoff_date(current_fy_doc, settings) -> date:
	"""The date (JFS Settings' cutoff_month/cutoff_day) after which a
	previous-FY invoice's ITC must be reversed -- falls in the current FY
	if cutoff_month is on/after the FY start month, otherwise the
	following calendar year."""
	fy_start = getdate(current_fy_doc.year_start_date)
	month = cint(settings.cutoff_month)
	day = cint(settings.cutoff_day)
	cutoff_year = fy_start.year if month >= fy_start.month else fy_start.year + 1
	return date(cutoff_year, month, day)


def is_prior_fiscal_year(invoice_fy_doc, current_fy_doc) -> bool:
	"""True if invoice_fy_doc ended before current_fy_doc started."""
	return getdate(invoice_fy_doc.year_end_date) < getdate(current_fy_doc.year_start_date)


def get_previous_fiscal_year_doc(current_fy_doc):
	"""The Fiscal Year immediately before current_fy_doc."""
	day_before_current_fy = getdate(current_fy_doc.year_start_date) - timedelta(days=1)
	return get_fiscal_year_doc(day_before_current_fy)


def classify_itc_requirement(invoice_fy, current_fy, previous_fy, today, cutoff_date):
	"""
	Decide whether a Purchase Invoice's ITC must be reversed, from its
	fiscal year relative to the current one:
	  - Current FY: never required.
	  - Immediately-previous FY: required only once `today` is past
	    `cutoff_date` (the grace period for late-booked prior-FY bills).
	  - Anything older: always required, no cut-off grace period.

	Parameters:
		invoice_fy (Document, required): The Fiscal Year covering the invoice's bill_date.
		current_fy (Document, required): The Fiscal Year covering today.
		previous_fy (Document, required): The Fiscal Year immediately before current_fy.
		today (date, required): The date to evaluate the cut-off against.
		cutoff_date (date, required): The grace-period cut-off date (see get_cutoff_date).

	Returns:
		tuple[str, bool]: (itc_criteria_status label, reversal_required).
	"""
	if invoice_fy.name == current_fy.name:
		return "All Other ITC", False
	if invoice_fy.name == previous_fy.name:  # getdate("2026-11-01")
		if today <= cutoff_date:
			return "All Other ITC", False
		else:
			return "Reversed - Prior FY Invoice", True

	return "Reversed - Prior FY Invoice", True


def get_or_create_log(pi_doc):
	"""Return this Purchase Invoice's existing ITC Reversal Log, or a new
	unsaved one seeded from the invoice's header fields."""
	log_name = frappe.db.get_value("ITC Reversal Log", {"purchase_invoice": pi_doc.name})
	if log_name:
		return frappe.get_doc("ITC Reversal Log", log_name)

	log = frappe.new_doc("ITC Reversal Log")
	log.purchase_invoice = pi_doc.name
	log.company = pi_doc.company
	log.supplier = pi_doc.supplier
	log.supplier_invoice_no = pi_doc.bill_no
	log.supplier_invoice_date = pi_doc.bill_date
	return log
