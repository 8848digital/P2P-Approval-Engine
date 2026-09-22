# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""ITC reversal Journal Entry creation + notification. Split out of
purchase_invoice_itc_reversal.py to keep that file under the line-count
cap. Re-exported from there (see that file) so existing callers keep
working.
"""

import frappe
from frappe.utils import cint, flt, nowdate


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
