import frappe
from frappe.utils import add_days, add_months, cint, getdate

from p2p_customization.settlement.doctype.brn.utils import _create_pi_from_brn, create_po_from_brn


@frappe.whitelist()
def create_purchase_order_from_brn(source_name):
	"""
	Create a Purchase Order mapped from a BRN document.

	Invoked by frappe.model.open_mapped_doc (BRN's "Create Purchase Order"
	button), which calls this as method(source_name) only -- the extra
	`vendor` arg passed from brn.js lands in frappe.flags.args instead of
	as a kwarg here.

	**Endpoint:** `/api/method/p2p_customization.settlement.doctype.brn.api.create_purchase_order_from_brn`
	**HTTP Method:** POST
	**Parameters:**
		- source_name (str, required): The BRN document name to map from
	**Response:** The mapped (unsaved) Purchase Order document, serialized as JSON.
	"""
	vendor = (frappe.flags.args or {}).get("vendor")
	return create_po_from_brn(source_name, vendor)


@frappe.whitelist()
def create_purchase_invoice_from_brn(source_name):
	"""
	Create a Purchase Invoice mapped from a BRN document.

	Invoked by frappe.model.open_mapped_doc, same calling convention as
	create_purchase_order_from_brn above.

	**Endpoint:** `/api/method/p2p_customization.settlement.doctype.brn.api.create_purchase_invoice_from_brn`
	**HTTP Method:** POST
	**Parameters:**
		- source_name (str, required): The BRN document name to map from
	**Response:** The mapped (unsaved) Purchase Invoice document, serialized as JSON.
	"""
	vendor = (frappe.flags.args or {}).get("vendor")
	return _create_pi_from_brn(source_name, vendor)


@frappe.whitelist()
def get_expiry_date(date, months):
	"""
	Compute a BRN's service expiry date from its start date + duration.

	**Endpoint:** `/api/method/p2p_customization.settlement.doctype.brn.api.get_expiry_date`
	**HTTP Method:** GET, POST
	**Parameters:**
		- date (str, required): The service start date
		- months (int, required): Duration of service, in months
	**Response:** The computed expiry date (ISO date string), serialized as JSON.
	"""
	return add_months(getdate(add_days(date, -1)), cint(months))
