import frappe
from frappe import _

def set_total_amount(doc):
	total_amount = 0
	for row in doc.items:
		total_amount += row.amount
	doc.set("total_amount", total_amount)

def validate_comparision_rows(doc):
	row_count = len(doc.comparision or [])

	if doc.get("single") and row_count > 1:
		frappe.throw(_("Only one row is allowed in the Comparision table when Single is checked."))

	if doc.get("multi") and row_count > 3:
		frappe.throw(_("Maximum three rows can be added to the Comparision table when Multi is checked."))

	validate_single_preferred_row(doc)

def validate_single_preferred_row(doc):
	"""Preferred picks the one vendor (new or existing) this BRN moves
	forward with -- for onboarding (see add_onboard_vendor_button) and for
	PO/Invoice creation (see create_purchase_order_button) alike. More
	than one row marked Preferred would make that choice ambiguous."""
	preferred_rows = [row for row in (doc.comparision or []) if row.preferred]

	if len(preferred_rows) > 1:
		frappe.throw(
			_("Only one row in the Comparision table can be marked Preferred, found {0}.")
			.format(len(preferred_rows))
		)

def block_requisition_id(doc):
	if doc.quotation_requisition_id:
		frappe.db.set_value(
			"Requisition ID",
			doc.quotation_requisition_id,
			{"block_id": 1, "brn_id": doc.name},
		)