from datetime import date, timedelta

import frappe
from frappe.utils import cint, flt, getdate, nowdate


def get_settings():
	"""Return the cached JFS Settings document."""
	return frappe.get_cached_doc("JFS Settings")


@frappe.whitelist()
def get_fiscal_year_doc(for_date, company=None):
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
	if not cint(settings.enable_itc_reversal):
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
	if not cint(settings.enable_itc_reversal):
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


def create_itc_reversal_jv(pi_doc, log, settings, trigger="Real-Time (on submit)"):
	"""
	Build and insert the ITC-reversal Journal Entry for pi_doc: mirrors
	each non-TDS tax row (credit for Add, debit for Deduct), then balances
	any shortfall between the two sides across the invoice's item-level
	Expense Accounts (weighted by each item's share of net_total).
	Updates log with the outcome; auto-submits the JV and emails
	notify_email_recipients if configured to.

	Parameters:
		pi_doc (Document, required): The submitted Purchase Invoice.
		log (Document, required): Its ITC Reversal Log (mutated and saved here).
		settings (Document, required): JFS Settings.
		trigger (str, optional): Recorded on the log for audit -- which
			code path triggered this reversal.

	Returns:
		str | None: The new Journal Entry's name, or None if pi_doc has no tax rows.
	"""
	if not pi_doc.taxes:
		frappe.log_error(f"PI {pi_doc.name}: no tax rows found, cannot build ITC reversal JV")
		return None

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Reversal Of ITC"
	je.posting_date = nowdate()
	je.company = pi_doc.company
	# india_compliance requires company_gstin whenever any GST account is
	# present (see gst_india/overrides/journal_entry.py::validate) and can
	# only auto-resolve it when the company has EXACTLY one registered
	# GSTIN -- otherwise it throws. Set it explicitly from the original
	# invoice's own company_gstin, which is the correct GSTIN context for
	# reversing THIS invoice's ITC regardless of how many GSTINs the
	# company is registered under.
	je.company_gstin = pi_doc.company_gstin
	je.user_remark = (
		f"Auto ITC Reversal for {pi_doc.name} "
		f"(Supplier Invoice Date {pi_doc.bill_date}, FY {log.invoice_fiscal_year}) [{trigger}]"
	)
	je.cheque_no = pi_doc.name
	je.cheque_date = pi_doc.bill_date

	cost_center = settings.itc_reversal_cost_center
	default_cc = pi_doc.items[0].cost_center if pi_doc.items else None
	credit_summary, debit_summary = [], []
	credit_total = 0.0
	debit_total = 0.0

	for t in pi_doc.taxes:
		if cint(t.is_tax_withholding_account):
			continue  # TDS - always skipped
		amount = flt(t.tax_amount)
		if not amount:
			continue

		if t.add_deduct_tax == "Add":
			je.append(
				"accounts",
				{
					"account": t.account_head,
					"credit_in_account_currency": amount,
					"cost_center": cost_center or default_cc,
					"state": pi_doc.state,
				},
			)
			credit_summary.append(f"{t.account_head}: {amount}")
			credit_total += amount

		elif t.add_deduct_tax == "Deduct":
			je.append(
				"accounts",
				{
					"account": t.account_head,
					"debit_in_account_currency": amount,
					"cost_center": cost_center or default_cc,
					"state": pi_doc.state,
				},
			)
			debit_summary.append(f"{t.account_head}: {amount}")
			debit_total += amount

	shortfall = flt(credit_total - debit_total, 2)

	if abs(shortfall) < 0.01:
		pass
	else:
		total_net = flt(pi_doc.net_total) or 1
		expense_allocation = {}
		for item in pi_doc.items:
			acct = item.expense_account or settings.default_expense_fallback_account
			if not acct:
				frappe.throw(
					f"Row {item.idx} in {pi_doc.name} has no Expense Account, "
					f"and no Fallback Expense Account is configured in JFS Settings (ITC Reversal Settings tab)."
				)
			weight = flt(item.base_net_amount) / total_net
			expense_allocation[acct] = expense_allocation.get(acct, 0) + weight

		for acct, weight in expense_allocation.items():
			amount = flt(abs(shortfall) * weight, 2)
			if not amount:
				continue
			row = {"account": acct, "cost_center": cost_center or default_cc, "state": pi_doc.state}
			if shortfall > 0:
				row["debit_in_account_currency"] = amount
				debit_summary.append(f"{acct}: {amount}")
			else:
				row["credit_in_account_currency"] = amount
				credit_summary.append(f"{acct}: {amount}")
			je.append("accounts", row)

	je.flags.ignore_permissions = True
	je.insert()
	if cint(settings.auto_submit_reversal_jv):
		je.submit()

	log.reversal_status = "Reversed"
	log.reversal_trigger = trigger
	log.reversal_date = nowdate()
	log.reversal_jv = je.name
	log.total_gst_amount = credit_total
	log.total_gst_reversed = abs(shortfall)
	log.credit_accounts_summary = "\n".join(credit_summary)
	log.debit_accounts_summary = "\n".join(debit_summary)
	if abs(shortfall) < 0.01:
		log.remarks = (
			log.remarks + "\n" if log.remarks else ""
		) + "Credit and Debit tax rows netted off exactly (e.g. RCM) - no Expense Account line was needed."
	log.flags.ignore_permissions = True
	log.save()
	frappe.db.set_value("Purchase Invoice", pi_doc.name, "is_itc_reversed", 1)

	if cint(settings.notify_users_on_reversal) and settings.notify_email_recipients:
		notify_reversal(pi_doc, je, settings)
	return je.name


def notify_reversal(pi_doc, je_doc, settings) -> None:
	"""Email JFS Settings' notify_email_recipients that an ITC reversal JV was posted."""
	recipients = [r.strip() for r in settings.notify_email_recipients.split(",") if r.strip()]
	if not recipients:
		return
	frappe.sendmail(
		recipients=recipients,
		subject=f"ITC Reversal posted for {pi_doc.name}",
		message=(
			f"An ITC reversal Journal Entry <b>{je_doc.name}</b> was auto-posted "
			f"against Purchase Invoice <b>{pi_doc.name}</b>. "
			f"Full details are in the ITC Reversal Log linked to that invoice."
		),
	)


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
	if not cint(settings.enable_itc_reversal):
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

			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"ITC Reversal batch failed for {log_name}",
				message=frappe.get_traceback(),
			)
