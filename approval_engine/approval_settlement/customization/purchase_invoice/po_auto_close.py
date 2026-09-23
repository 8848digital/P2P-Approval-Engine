# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe.utils import flt, getdate, nowdate


def auto_close_purchase_orders():
	today = getdate(nowdate())
	pos = frappe.get_all(
		"Purchase Order",
		filters={
			"docstatus": 1,
			"status": ["not in", ["Closed", "Cancelled", "Completed"]],
		},
		pluck="name",
	)
	closed_count = 0
	for po_name in pos:
		try:
			if check_and_close_po(po_name, reference_date=today):
				closed_count += 1
		except Exception:
			frappe.log_error(
				title=f"Auto Close PO (scheduler) failed: {po_name}",
				message=frappe.get_traceback(),
			)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - scheduled job, not a web request; no auto-commit at the end
	frappe.logger().info(
		f"Auto Close PO (scheduler): closed {closed_count} of {len(pos)} eligible POs"
	)


def on_purchase_invoice_submit(doc, method=None):
	from approval_engine.approval_settlement.doctype.brn.brn_auto_close import (
		on_purchase_invoice_submit as brn_purchase_invoice_submit,
	)

	po_names = {row.purchase_order for row in doc.items if row.purchase_order}

	for po_name in po_names:
		try:
			check_and_close_po(po_name, reference_date=getdate(doc.posting_date))
		except Exception:
			frappe.log_error(
				title=f"Auto Close PO (on PI submit) failed: {po_name}",
				message=frappe.get_traceback(),
			)

	brn_purchase_invoice_submit(doc)


def check_and_close_po(po_name, reference_date):
	po = frappe.db.get_value(
		"Purchase Order",
		po_name,
		["name", "docstatus", "status", "validity_start_date", "validity_end_date", "requisition_type"],
		as_dict=True,
	)
	if not po or po.docstatus != 1 or po.status in ("Closed", "Cancelled", "Completed"):
		return False
	if _should_close(po, reference_date):
		_close_po(po.name)
		return True
	return False


def _should_close(po, reference_date):
	if po.validity_end_date and getdate(po.validity_end_date) < getdate(reference_date):
		return True
	req_type = (po.requisition_type or "").strip()
	if req_type in ("Material", "Fixed Asset"):
		return _material_fully_invoiced(po.name)
	elif req_type == "Service":
		return _service_fully_invoiced(po.name)
	else:
		frappe.logger().warning(
			f"Auto Close PO: {po.name} has no valid Requisition Type ('{req_type}'), "
			"skipping invoicing check."
		)
		return False


def _material_fully_invoiced(po_name):
	doc = frappe.get_doc("Purchase Order", po_name)
	for item in doc.items:
		ordered_qty = flt(item.qty)
		billed_qty = flt(
			frappe.db.sql(
				"""
				SELECT SUM(pii.qty)
				FROM `tabPurchase Invoice Item` pii
				INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pii.po_detail = %(po_detail)s
				  AND pii.item_code = %(item_code)s
				  AND pii.warehouse = %(warehouse)s
				  AND pi.docstatus = 1
				""",
				{
					"po_detail": item.name,
					"item_code": item.item_code,
					"warehouse": item.warehouse,
				},
			)[0][0]
			or 0
		)
		if billed_qty < ordered_qty:
			return False
	return True


def _service_fully_invoiced(po_name):
	doc = frappe.get_doc("Purchase Order", po_name)
	for item in doc.items:
		ordered_amount = flt(item.amount)
		billed_amount = flt(
			frappe.db.sql(
				"""
				SELECT SUM(pii.amount)
				FROM `tabPurchase Invoice Item` pii
				INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pii.po_detail = %(po_detail)s
				  AND pii.item_code = %(item_code)s
				  AND pi.docstatus = 1
				""",
				{
					"po_detail": item.name,
					"item_code": item.item_code,
				},
			)[0][0]
			or 0
		)
		if billed_amount < ordered_amount:
			return False
	return True


def _close_po(po_name):
	"""Set PO status to Closed, with a comment recording the reason."""
	doc = frappe.get_doc("Purchase Order", po_name)
	doc.db_set("status", "Closed")
	doc.add_comment(
		"Info",
		"Auto-closed by system: fully invoiced (per Requisition Type) or validity_end_date has passed.",
	)
