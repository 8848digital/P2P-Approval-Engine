import frappe
from frappe.utils import flt
from pypika import functions as fn


def auto_close_brns():
	"""Scheduler sweep: check all submitted, open BRNs regardless of PI activity."""
	brns = frappe.get_all(
		"BRN",
		filters={
			"docstatus": 1,
			"status": ["not in", ["Closed", "Cancelled"]],
		},
		pluck="name",
	)
	closed_count = 0
	for brn_name in brns:
		try:
			if check_and_close_brn(brn_name):
				closed_count += 1
		except Exception:
			frappe.log_error(
				title=f"Auto Close BRN (scheduler) failed: {brn_name}",
				message=frappe.get_traceback(),
			)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - scheduled job, not a web request; no auto-commit at the end
	frappe.logger().info(f"Auto Close BRN (scheduler): closed {closed_count} of {len(brns)} eligible BRNs")


def on_purchase_invoice_submit(doc):
	"""Doc event: check the single BRN referenced on this PI's header (if any)."""
	brn_name = doc.get("brn")
	if not brn_name:
		return
	try:
		check_and_close_brn(brn_name)
	except Exception:
		frappe.log_error(
			title=f"Auto Close BRN (on PI submit) failed: {brn_name}",
			message=frappe.get_traceback(),
		)


def check_and_close_brn(brn_name) -> bool:
	"""
	Close brn_name if it's still open and fully consumed. No-op (returns
	False) if it's already closed/cancelled or not yet submitted.

	Parameters:
		brn_name (str, required): The BRN document name.

	Returns:
		bool: True if this call closed the BRN, False otherwise.
	"""
	brn = frappe.db.get_value(
		"BRN",
		brn_name,
		["name", "docstatus", "status", "requisition_type"],
		as_dict=True,
	)
	if not brn or brn.docstatus != 1 or brn.status in ("Closed", "Cancelled"):
		return False
	if _should_close_brn(brn):
		_close_brn(brn.name)
		return True
	return False


def _should_close_brn(brn):
	"""Closure is decided purely by consumption: amount for Service, qty for Material/Fixed Asset."""
	req_type = (brn.requisition_type or "").strip()
	if req_type == "Service":
		return _brn_amount_fully_invoiced(brn.name)
	elif req_type in ("Material", "Fixed Asset"):
		return _brn_qty_fully_invoiced(brn.name)
	else:
		frappe.logger().warning(
			f"Auto Close BRN: {brn.name} has no valid Requisition Type ('{req_type}'), "
			"skipping invoicing check."
		)
		return False


def _billed_totals_by_item(brn_name: str, item_codes: list) -> dict:
	"""
	Batch-fetch billed qty/amount per item_code across every submitted PI
	linked to this BRN, in one query -- shared by both the amount- and
	qty-based closure checks below, instead of one query per BRN item.

	Parameters:
		brn_name (str, required): The BRN document name.
		item_codes (list, required): The item codes to sum for.

	Returns:
		dict: {item_code: {"billed_qty": float, "billed_amount": float}}.
			An item_code with no billed rows is simply absent.
	"""
	if not item_codes:
		return {}

	PII = frappe.qb.DocType("Purchase Invoice Item")
	PI = frappe.qb.DocType("Purchase Invoice")

	rows = (
		frappe.qb.from_(PII)
		.inner_join(PI)
		.on(PI.name == PII.parent)
		.select(
			PII.item_code,
			fn.Sum(PII.qty).as_("billed_qty"),
			fn.Sum(PII.amount).as_("billed_amount"),
		)
		.where(PI.brn == brn_name)
		.where(PI.docstatus == 1)
		.where(PII.item_code.isin(item_codes))
		.groupby(PII.item_code)
	).run(as_dict=True)

	return {r.item_code: r for r in rows}


def _brn_amount_fully_invoiced(brn_name: str) -> bool:
	"""
	Service BRN: a PI is raised against exactly one BRN item at a time, and BRN
	carries no taxes/charges, so compare item-wise net amount rather than the
	PI's header grand_total against the BRN's rolled-up total_amount.
	For each BRN item, sum billed amount by item_code across all submitted PIs
	linked to this BRN (via header `brn`), and compare against that item's
	sanctioned amount.
	"""
	doc = frappe.get_doc("BRN", brn_name)
	totals = _billed_totals_by_item(brn_name, [d.item_code for d in doc.items])

	for brn_item in doc.items:
		sanctioned_amount = flt(brn_item.amount)
		billed_amount = flt((totals.get(brn_item.item_code) or {}).get("billed_amount") or 0)
		if billed_amount < sanctioned_amount:
			return False
	return True


def _brn_qty_fully_invoiced(brn_name: str) -> bool:
	"""
	Material / Fixed Asset BRN: since `brn` sits on the PI header (not per item),
	sum billed qty per item_code across all submitted PIs linked to this BRN,
	and compare against each BRN Item's sanctioned qty.
	"""
	doc = frappe.get_doc("BRN", brn_name)
	totals = _billed_totals_by_item(brn_name, [d.item_code for d in doc.items])

	for brn_item in doc.items:
		ordered_qty = flt(brn_item.qty)
		billed_qty = flt((totals.get(brn_item.item_code) or {}).get("billed_qty") or 0)
		if billed_qty < ordered_qty:
			return False
	return True


def _close_brn(brn_name):
	"""Set BRN status to Closed, with a comment recording the reason."""
	doc = frappe.get_doc("BRN", brn_name)
	doc.db_set("status", "Closed")
	doc.add_comment(
		"Info",
		"Auto-closed by system: fully consumed (amount for Service, qty for Material/Fixed Asset).",
	)
