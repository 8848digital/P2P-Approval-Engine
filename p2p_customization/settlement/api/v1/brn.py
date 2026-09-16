# Copyright (c) 2026, p2p_customization
"""Whitelisted endpoints for creating Purchase Order/Invoice from a BRN.

Thin wrappers only -- the actual mapping/calculation logic lives in
settlement/doctype/brn/utils.py.
"""

import frappe

from p2p_customization.settlement.doctype.brn.utils import (
	_create_pi_from_brn,
	calculate_brn_expiry_date,
	create_po_from_brn,
)


@frappe.whitelist(methods=["POST"])
def create_purchase_order_from_brn(source_name: str):
	"""
	Create a Purchase Order mapped from a BRN document.

	Invoked by frappe.model.open_mapped_doc (BRN's "Create Purchase Order"
	button), which calls this as method(source_name) only -- the extra
	`vendor` arg passed from brn.js lands in frappe.flags.args instead of
	as a kwarg here.

	**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.brn.create_purchase_order_from_brn`
	**HTTP Method:** POST
	**Parameters:**
		- source_name (str, required): The BRN document name to map from
	**Response:** The mapped (unsaved) Purchase Order document, serialized as JSON.
	"""
	vendor = (frappe.flags.args or {}).get("vendor")
	return create_po_from_brn(source_name, vendor)


@frappe.whitelist(methods=["POST"])
def create_purchase_invoice_from_brn(source_name: str):
	"""
	Create a Purchase Invoice mapped from a BRN document.

	Invoked by frappe.model.open_mapped_doc, same calling convention as
	create_purchase_order_from_brn above.

	**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.brn.create_purchase_invoice_from_brn`
	**HTTP Method:** POST
	**Parameters:**
		- source_name (str, required): The BRN document name to map from
	**Response:** The mapped (unsaved) Purchase Invoice document, serialized as JSON.
	"""
	vendor = (frappe.flags.args or {}).get("vendor")
	return _create_pi_from_brn(source_name, vendor)


@frappe.whitelist(methods=["GET", "POST"])
def get_expiry_date(date: str, months: int):
	"""
	Compute a BRN's service expiry date from its start date + duration.

	**Endpoint:** `/api/method/p2p_customization.settlement.api.v1.brn.get_expiry_date`
	**HTTP Method:** GET, POST
	**Parameters:**
		- date (str, required): The service start date
		- months (int, required): Duration of service, in months
	**Response:** The computed expiry date (ISO date string), serialized as JSON.
	"""
	return calculate_brn_expiry_date(date, months)
