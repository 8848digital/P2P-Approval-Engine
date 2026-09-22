# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Purchase Invoice ITC reversal hook entrypoints (validate/on_submit,
plus the daily sweep). Fiscal-year/cut-off resolution and Journal Entry
creation live in the sibling itc_reversal_fiscal_year.py / itc_reversal_jv.py
modules - split out to keep this file under the line-count cap, and
re-exported below so existing import/mock.patch paths targeting this
module keep working.
"""

from datetime import date

import frappe
from frappe.utils import cint, getdate, nowdate

from approval_engine.settlement.doc_events.itc_reversal_fiscal_year import (
	classify_itc_requirement,
	get_current_fiscal_year_doc,
	get_cutoff_date,
	get_or_create_log,
	get_previous_fiscal_year_doc,
	is_prior_fiscal_year,
)
from approval_engine.settlement.doc_events.itc_reversal_fiscal_year import (
	get_fiscal_year_doc as _get_fiscal_year_doc,
)
from approval_engine.settlement.doc_events.itc_reversal_jv import create_itc_reversal_jv


def get_settings():
	"""Return the cached JFS Settings document, or None if JFS Settings
	isn't installed (jfs_report_customization isn't a required_apps
	dependency here) -- callers treat that the same as the feature being
	disabled, rather than crashing every Purchase Invoice save/submit."""
	if not frappe.db.exists("DocType", "JFS Settings"):
		return None
	return frappe.get_cached_doc("JFS Settings")


@frappe.whitelist()
def get_fiscal_year_doc(for_date: str | date, company: str | None = None):
	"""Returns the Fiscal Year document that contains the given date.

	for_date accepts both a date string (HTTP callers pass JSON) and a
	datetime.date (internal callers pass getdate(...) results directly) --
	@frappe.whitelist() enforces this type hint at runtime for EVERY
	caller, not just HTTP, so it must cover both shapes actually in use.
	"""
	return _get_fiscal_year_doc(for_date, company)


def set_itc_status(doc, method=None) -> None:
	"""
	Purchase Invoice on_update/after_insert hook: (re)classify this
	invoice's ITC reversal requirement against the current fiscal
	year/cut-off, and create/update its ITC Reversal Log accordingly.
	Does not itself create the reversal Journal Entry -- that happens on
	submit (see handle_itc_reversal_on_submit) or the daily sweep, once
	reversal_status has actually become due.

	Parameters:
		doc (Document, required): The Purchase Invoice document being saved.
		method (str, optional): The hook event name passed by Frappe.

	Returns:
		None
	"""
	settings = get_settings()
	if not settings or not cint(settings.enable_itc_reversal):
		return
	if not doc.bill_date:
		return

	invoice_fy = get_fiscal_year_doc(getdate(doc.bill_date), doc.company)
	current_fy = get_current_fiscal_year_doc()
	previous_fy = get_previous_fiscal_year_doc(current_fy)
	cutoff_date = get_cutoff_date(current_fy, settings)
	today = getdate(nowdate())

	log = get_or_create_log(doc)
	log.company = doc.company
	log.supplier = doc.supplier
	log.supplier_invoice_no = doc.bill_no
	log.supplier_invoice_date = doc.bill_date
	log.invoice_fiscal_year = invoice_fy.name
	log.current_fiscal_year_at_processing = current_fy.name

	criteria_status, reversal_required = classify_itc_requirement(
		invoice_fy, current_fy, previous_fy, today, cutoff_date
	)
	log.itc_criteria_status = criteria_status

	if invoice_fy.name == previous_fy.name:
		log.cutoff_date_applied = cutoff_date
	else:
		log.cutoff_date_applied = None
		if invoice_fy.name != current_fy.name:
			log.remarks = (
				(log.remarks + "\n" if log.remarks else "")
				+ f"Invoice FY ({invoice_fy.name}) is older than the immediately-previous "
				f"FY ({previous_fy.name}) - no cut-off check applies; reversal is required "
				f"unconditionally."
			)

	if log.reversal_status != "Reversed":
		log.reversal_status = "Pending" if reversal_required else "Not Required"

	log.flags.ignore_permissions = True
	log.save()


def handle_itc_reversal_on_submit(doc, method=None) -> None:
	"""
	Purchase Invoice on_submit hook: post the ITC reversal Journal Entry
	immediately if this invoice's log already says reversal is Pending
	(i.e. it was already past cut-off at save time). An invoice that's
	still within its cut-off grace period at submit time is left for the
	daily sweep to catch once that grace period actually expires.

	Parameters:
		doc (Document, required): The Purchase Invoice document being submitted.
		method (str, optional): The hook event name passed by Frappe.

	Returns:
		None
	"""
	settings = get_settings()
	if not settings or not cint(settings.enable_itc_reversal):
		return

	log_name = frappe.db.get_value("ITC Reversal Log", {"purchase_invoice": doc.name})
	if not log_name:
		return
	log = frappe.get_doc("ITC Reversal Log", log_name)

	if log.reversal_status == "Not Required":
		return  # current FY, or previous FY still within cut-off - nothing to do

	if log.reversal_status == "Reversed":
		return  # already reversed (defensive check)

	create_itc_reversal_jv(doc, log, settings, trigger="Real-Time (on submit)")


def run_daily_itc_reversal_sweep() -> None:
	"""
	Scheduled (daily) sweep: catch every ITC Reversal Log not yet Reversed
	and re-evaluate it against today's fiscal-year/cut-off state, posting
	the reversal JV for any that have now crossed the cut-off. Exists
	because handle_itc_reversal_on_submit only fires once, at submit time
	-- an invoice submitted while still within its grace period needs
	this sweep to catch it once that period actually expires. Each log is
	processed in its own try/except + commit/rollback so one failure
	doesn't abort the rest of the batch.

	Parameters:
		None.

	Returns:
		None
	"""
	settings = get_settings()
	if not settings or not cint(settings.enable_itc_reversal):
		return

	current_fy = get_current_fiscal_year_doc()
	previous_fy = get_previous_fiscal_year_doc(current_fy)
	cutoff_date = get_cutoff_date(current_fy, settings)
	today = getdate(nowdate())

	candidate_logs = frappe.get_all(
		"ITC Reversal Log",
		filters={"reversal_status": ["!=", "Reversed"]},
		pluck="name",
	)

	for log_name in candidate_logs:
		try:
			log = frappe.get_doc("ITC Reversal Log", log_name)
			pi_doc = frappe.get_doc("Purchase Invoice", log.purchase_invoice)
			if pi_doc.docstatus != 1:
				continue  # only submitted invoices get reversed

			invoice_fy = get_fiscal_year_doc(getdate(pi_doc.bill_date), pi_doc.company)
			criteria_status, reversal_required = classify_itc_requirement(
				invoice_fy, current_fy, previous_fy, today, cutoff_date
			)

			log.itc_criteria_status = criteria_status
			log.current_fiscal_year_at_processing = current_fy.name

			if invoice_fy.name == previous_fy.name:
				log.cutoff_date_applied = cutoff_date
			else:
				log.cutoff_date_applied = None

			if reversal_required:
				create_itc_reversal_jv(pi_doc, log, settings, trigger="Batch Sweep (post cut-off)")
			else:
				log.reversal_status = "Not Required"
				log.flags.ignore_permissions = True
				log.save()

			frappe.db.commit()  # nosemgrep: frappe-manual-commit - scheduled job, checkpoints progress per log so one failure doesn't roll back the whole batch
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"ITC Reversal batch failed for {log_name}",
				message=frappe.get_traceback(),
			)
