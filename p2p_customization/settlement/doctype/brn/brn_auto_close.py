import frappe
from frappe.utils import flt


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
	frappe.db.commit()
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


def check_and_close_brn(brn_name):
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


def _brn_amount_fully_invoiced(brn_name):
	"""
	Service BRN: a PI is raised against exactly one BRN item at a time, and BRN
	carries no taxes/charges, so compare item-wise net amount rather than the
	PI's header grand_total against the BRN's rolled-up total_amount.
	For each BRN item, sum billed amount by item_code across all submitted PIs
	linked to this BRN (via header `brn`), and compare against that item's
	sanctioned amount.
	"""
	doc = frappe.get_doc("BRN", brn_name)
	for brn_item in doc.items:
		sanctioned_amount = flt(brn_item.amount)
		billed_amount = flt(
			frappe.db.sql(
				"""
				SELECT SUM(pii.amount)
				FROM `tabPurchase Invoice Item` pii
				INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pi.brn = %(brn)s
				  AND pii.item_code = %(item_code)s
				  AND pi.docstatus = 1
				""",
				{"brn": brn_name, "item_code": brn_item.item_code},
			)[0][0]
			or 0
		)
		if billed_amount < sanctioned_amount:
			return False
	return True


def _brn_qty_fully_invoiced(brn_name):
	"""
	Material / Fixed Asset BRN: since `brn` sits on the PI header (not per item),
	sum billed qty per item_code across all submitted PIs linked to this BRN,
	and compare against each BRN Item's sanctioned qty.
	"""
	doc = frappe.get_doc("BRN", brn_name)
	for brn_item in doc.items:
		ordered_qty = flt(brn_item.qty)
		billed_qty = flt(
			frappe.db.sql(
				"""
				SELECT SUM(pii.qty)
				FROM `tabPurchase Invoice Item` pii
				INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pi.brn = %(brn)s
				  AND pii.item_code = %(item_code)s
				  AND pi.docstatus = 1
				""",
				{"brn": brn_name, "item_code": brn_item.item_code},
			)[0][0]
			or 0
		)
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