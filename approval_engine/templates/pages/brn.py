# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import json

import frappe
from frappe import _
from frappe.utils import today

from approval_engine.settlement.customization.purchase_order.utils import create_portal_invoice_log


def get_context(context) -> None:
	"""
	Page controller for the /brn/<name> portal detail page: loads the BRN,
	its public attachments, and whether the "Create Purchase Invoice"
	button should show (submitted BRNs only).

	Parameters:
		context (frappe._dict, required): The website render context.

	Returns:
		None
	"""
	context.no_cache = 1
	context.show_sidebar = True

	brn_name = frappe.form_dict.name

	context.doc = frappe.get_doc("BRN", brn_name)

	context.title = context.doc.name

	context.attachments = frappe.get_all(
		"File",
		fields=["name", "file_name", "file_url"],
		filters={
			"attached_to_doctype": "BRN",
			"attached_to_name": brn_name,
			"is_private": 0,
		},
	)

	context.show_make_pi_button = context.doc.docstatus == 1


@frappe.whitelist()
def make_purchase_invoice_from_brn(
	brn_name: str,
	items: str,
	supplier_invoice_no: str | None = None,
	supplier_invoice_date: str | None = None,
):
	"""
	Create and insert a Purchase Invoice mapped from a submitted BRN, from
	the vendor portal's BRN detail page.

	**Endpoint:** `/api/method/approval_engine.templates.pages.brn.make_purchase_invoice_from_brn`
	**HTTP Method:** POST
	**Parameters:**
		- brn_name (str, required): The BRN document name to map from
		- items (str, required): JSON-encoded list of {item_code, qty, rate}
		- supplier_invoice_no (str, optional): The supplier's own invoice number
		- supplier_invoice_date (str, optional): The supplier's own invoice date
	**Response:** The new Purchase Invoice's name (str), serialized as JSON.
	"""
	items = json.loads(items)

	brn = frappe.get_doc("BRN", brn_name)

	pi = frappe.new_doc("Purchase Invoice")
	pi.flags.ignore_permissions = True
	pi.company = brn.company
	pi.posting_date = today()

	if brn.supplier:
		pi.supplier = brn.supplier
	else:
		pi.supplier = brn.existing_vendor

	pi.po_type = "YEXP Proposal"
	pi.brn = brn_name
	pi.requisition_type = brn.requisition_type

	if supplier_invoice_no:
		pi.bill_no = supplier_invoice_no

	if supplier_invoice_date:
		pi.bill_date = supplier_invoice_date

	for item in items:
		# Find the matching BRN item row
		brn_item = next(
			(d for d in brn.items if d.item_code == item["item_code"]),
			None,
		)

		pi.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": item["qty"],
				"rate": item["rate"],
				"expense_account": brn_item.expense_gl if brn_item else None,
			},
		)

	pi.run_method("set_missing_values")
	pi.run_method("calculate_taxes_and_totals")

	pi.insert(ignore_mandatory=True)

	create_portal_invoice_log(pi)

	return pi.name
