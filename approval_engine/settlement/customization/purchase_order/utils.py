# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import json

from erpnext.buying.doctype.purchase_order.purchase_order import get_mapped_purchase_invoice

import frappe
from frappe import _
from frappe.utils import get_link_to_form, get_url_to_form

from approval_engine.settlement.customization.purchase_order.brn_balance import (
	POI_Fields,
	_sum_other_po_items,
)


def make_purchase_invoice(purchase_order_name, items, supplier_invoice_no, supplier_invoice_date):
	"""
	Create Purchase Invoice from Purchase Order (Portal)
	items: list of dicts [{item_code, qty, rate}]
	"""

	doc = get_mapped_purchase_invoice(purchase_order_name, ignore_permissions=True)

	if doc.contact_email != frappe.session.user:
		frappe.throw(_("Not Permitted"), frappe.PermissionError)

	if items:
		# Update item qty and rate
		items = json.loads(items) if isinstance(items, str) else items
		for inv_item in doc.items:
			for i in items:
				if inv_item.item_code == i["item_code"]:
					inv_item.qty = i["qty"]
					inv_item.rate = i["rate"]
	if supplier_invoice_no:
		doc.bill_no = supplier_invoice_no
	if supplier_invoice_date:
		doc.bill_date = supplier_invoice_date

	doc.save()

	create_portal_invoice_log(doc)

	frappe.db.commit()  # nosemgrep: frappe-manual-commit - durably persist the invoice immediately after this portal write

	return doc.name


def create_portal_invoice_log(purchase_invoice):
	"""Create Portal Invoice Log entry"""

	if frappe.db.exists("Portal Invoice Log", {"purchase_invoice": purchase_invoice.name}):
		return

	frappe.get_doc(
		{
			"doctype": "Portal Invoice Log",
			"purchase_invoice": purchase_invoice.name,
			"supplier": purchase_invoice.supplier,
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def send_po_mail_to_vendor(purchase_order: str):
	"""Send Purchase Order email with PDF attachment to vendor"""
	doc = frappe.get_doc("Purchase Order", purchase_order)

	# frappe.get_doc() does not check permissions on its own -- without this,
	# any logged-in user could pass an arbitrary Purchase Order name and
	# have its PDF emailed to that supplier, regardless of whether they can
	# actually see/print this document.
	if not doc.has_permission("email"):
		frappe.throw(
			_("You are not permitted to email this Purchase Order."),
			frappe.PermissionError,
		)

	# 1. Try to get email from Purchase Order contact person
	supplier_email = None
	if doc.supplier_address:
		supplier_email = frappe.db.get_value("Address", doc.supplier_address, "email_id")

	# 2. If not found, get from Supplier master
	if not supplier_email:
		supplier_email = frappe.db.get_value("Supplier", doc.supplier, "email_id")

	if not supplier_email:
		frappe.throw(_("Please set Vendor Email in Supplier or Address master"))

	# Email content
	subject = f"Purchase Order {doc.name}"
	message = f"""
		<p>Dear {doc.supplier_name},</p>
		<p>Please find attached Purchase Order <b>{doc.name}</b> for your reference.</p>
		<p>You can also view it online: <a href="{get_url_to_form("Purchase Order", doc.name)}">{doc.name}</a></p>
		<p>Regards,<br>{frappe.session.user}</p>
	"""

	# Send Email with PDF attachment
	frappe.sendmail(
		recipients=[supplier_email],
		sender=None,
		subject=subject,
		message=message,
		now=True,
		attachments=[
			frappe.attach_print(
				doctype="Purchase Order",
				name=doc.name,
				# print_format="PO-3",   # or your custom format
				file_name=f"{doc.name}.pdf",
			)
		],
	)

	return True


def backdated_po_validation(doc, method: str | None = None) -> None:
	"""
	Restrict how far back a Purchase Order's transaction date may be
	backdated: 7 days if the date falls outside the PO's own fiscal year,
	30 days if it falls within it.

	custom_fiscal_year is only ever populated by
	validate_fiscal_year_and_brn_dates, which itself opts out whenever
	JFS Settings isn't installed or the PO isn't BRN-linked -- so it's
	routinely empty, not just on a data-entry mistake. Skip rather than
	crash when there's no fiscal year to check against.

	Parameters:
	        doc (Document, required): The Purchase Order document being saved.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	if not doc.custom_fiscal_year:
		return

	current_date = frappe.utils.getdate(frappe.utils.nowdate())
	fiscal_year = frappe.db.get_value(
		"Fiscal Year", doc.custom_fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	fiscal_year_start = frappe.utils.getdate(fiscal_year["year_start_date"])
	fiscal_year_end = frappe.utils.getdate(fiscal_year["year_end_date"])
	transaction_date = frappe.utils.getdate(doc.transaction_date)
	days_difference = frappe.utils.date_diff(current_date, transaction_date)

	if fiscal_year_start <= transaction_date <= fiscal_year_end:
		if days_difference > 30:
			frappe.throw(
				_(
					"Backdate posting of Purchase Order is not allowed if the Posting Date "
					"is prior to 30 days from today."
				)
			)
	elif days_difference > 7:
		frappe.throw(
			_(
				"In case of change in FY, Backdate posting of Purchase Order is not allowed "
				"if the Posting Date is prior to 7 days."
			)
		)


def validate_item_rate_and_qty_with_brn(doc, method: str | None = None) -> None:
	"""
	Validate that a BRN-linked Purchase Order's item rates/quantities stay
	within the balance still available on that BRN (qty and rate for
	non-Service requisitions, amount always), accounting for what other
	non-cancelled POs against the same BRN have already consumed.

	Parameters:
	        doc (Document, required): The Purchase Order document being validated.
	        method (str, optional): The hook event name passed by Frappe.

	Returns:
	        None
	"""
	if not doc.brn:
		return

	brn_items = frappe.get_all(
		"BRN Item", filters={"parent": doc.brn}, fields=["item_code", "qty", "rate"]
	)
	brn_map = {d.item_code: d for d in brn_items}

	brn_link = get_link_to_form("BRN", doc.brn)

	for row in doc.items:
		if row.item_code not in brn_map:
			frappe.throw(
				_("Row {0}: Item {1} is not in {2}").format(row.idx, row.item_code, brn_link),
				title=_("Invalid Item"),
			)

		brn_item = brn_map[row.item_code]

		if doc.requisition_type != "Service":
			already_ordered_qty = _sum_other_po_items(doc, row.item_code, POI_Fields.qty)
			if already_ordered_qty + row.qty > brn_item.qty:
				frappe.throw(
					_("Row {0}: Qty {1} exceeds BRN balance. Available BRN Qty: {2} in {3}").format(
						row.idx, row.qty, brn_item.qty - already_ordered_qty, brn_link
					),
					title=_("Qty Exceeded"),
				)

			if row.rate != brn_item.rate:
				frappe.throw(
					_("Row {0}: Rate {1} must match BRN Rate {2} for Item {3} in {4}").format(
						row.idx, row.rate, brn_item.rate, row.item_code, brn_link
					),
					title=_("Rate Mismatch"),
				)

		brn_amount = brn_item.qty * brn_item.rate
		already_ordered_amount = _sum_other_po_items(doc, row.item_code, POI_Fields.amount)
		current_row_amount = row.qty * row.rate

		if already_ordered_amount + current_row_amount > brn_amount:
			frappe.throw(
				_("Row {0}: Amount {1} exceeds BRN balance amount. Available BRN Amount: {2} in {3}").format(
					row.idx, current_row_amount, brn_amount - already_ordered_amount, brn_link
				),
				title=_("Amount Exceeded"),
			)
