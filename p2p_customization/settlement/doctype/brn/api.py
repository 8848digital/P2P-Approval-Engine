import frappe
from frappe.utils import add_months, getdate, cint, add_days

from p2p_customization.settlement.doctype.brn.utils import (
	create_po_from_brn,
	_create_pi_from_brn
)

@frappe.whitelist()
def create_purchase_order_from_brn(source_name):
	# frappe.model.mapper.make_mapped_doc (behind open_mapped_doc client-side)
	# calls this as method(source_name) only -- the extra `args` passed from
	# brn.js land in frappe.flags.args instead of as a kwarg here.
	vendor = (frappe.flags.args or {}).get("vendor")
	return create_po_from_brn(source_name, vendor)

@frappe.whitelist()
def create_purchase_invoice_from_brn(source_name):
	vendor = (frappe.flags.args or {}).get("vendor")
	return _create_pi_from_brn(source_name, vendor)

@frappe.whitelist()
def get_expiry_date(date, months):
	return add_months(getdate(add_days(date, -1)), cint(months))