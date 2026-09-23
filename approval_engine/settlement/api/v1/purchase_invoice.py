# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for Purchase Invoice customization (vendor email,
portal file upload, Nature of Service search).

Thin wrappers only -- the actual logic lives in
settlement/customization/purchase_invoice/utils.py and
settlement/customization/purchase_invoice/query.py.
"""

import frappe

from approval_engine.settlement.customization.purchase_invoice.query import (
	get_nature_of_service_options_for_supplier,
)
from approval_engine.settlement.customization.purchase_invoice.utils import (
	send_purchase_invoice_to_vendor,
	upload_invoice_file_from_portal,
)


@frappe.whitelist(methods=["POST"])
def send_po_to_vendor(purchase_invoice: str):
	"""
	Send a Purchase Invoice email with a PDF attachment to its supplier.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_invoice.send_po_to_vendor`
	**HTTP Method:** POST
	**Parameters:**
	        - purchase_invoice (str, required): The Purchase Invoice document name
	**Response:** `true` on success, serialized as JSON.
	"""
	return send_purchase_invoice_to_vendor(purchase_invoice)


@frappe.whitelist(methods=["POST"])
def upload_file_to_pi_from_portal(**args):
	"""
	Attach a vendor-uploaded invoice-copy file reference to a Purchase
	Order/Purchase Invoice, from the vendor portal.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_invoice.upload_file_to_pi_from_portal`
	**HTTP Method:** POST
	**Parameters:**
	        - doctype (str, required): "Purchase Order" or "Purchase Invoice"
	        - name (str, required): The document name to update
	        - fieldname (str, required): Must be `custom_supplier_invoice_copy`
	        - value (str, required): The uploaded File's file_url
	**Response:** `"success"`, serialized as JSON.
	"""
	return upload_invoice_file_from_portal(**args)


@frappe.whitelist(methods=["GET", "POST"])
@frappe.validate_and_sanitize_search_inputs
def get_nature_of_service_query(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
):
	"""
	Restrict BRN's Nature of Service (Table MultiSelect -> TDS Reference)
	to only the values selected on the linked Supplier's Nature of Services
	multiselect.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_invoice.get_nature_of_service_query`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - doctype (str, required): The Link/MultiSelect target doctype (standard search-query arg)
	        - txt (str, required): The text typed into the search box
	        - searchfield (str, required): The field being searched (standard search-query arg)
	        - start (int, required): Pagination offset (standard search-query arg, unused here)
	        - page_len (int, required): Page size (standard search-query arg, unused here)
	        - filters (dict, required): Must contain "supplier" to scope allowed services
	**Response:** List of (name, section_as_per_it_act_1961, tds_rate) tuples, serialized as JSON.
	"""
	supplier = filters.get("supplier") if filters else None
	return get_nature_of_service_options_for_supplier(txt, supplier)
