import json

import frappe
from frappe import _
from frappe.utils import today

from p2p_customization.settlement.customization.purchase_order.utils import create_portal_invoice_log


def get_context(context):
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
	brn_name,
	items,
	supplier_invoice_no=None,
	supplier_invoice_date=None,
):
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