# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for Purchase Order customization (vendor email,
portal invoice creation, BRN date validation, vendor rate comparison).

Thin wrappers only -- the actual logic lives in
settlement/customization/purchase_order/utils.py,
settlement/customization/purchase_order/rate_comparison.py, and
settlement/customization/procure_to_pay/utils.py.
"""

import frappe

from approval_engine.settlement.customization.procure_to_pay.utils import (
	get_fiscal_year_and_validity as _get_fiscal_year_and_validity,
)
from approval_engine.settlement.customization.procure_to_pay.utils import (
	validate_brn_dates,
)
from approval_engine.settlement.customization.purchase_order.rate_comparison import (
	get_rate_comparison_config,
	get_rate_comparison_rows,
)
from approval_engine.settlement.customization.purchase_order.utils import (
	make_purchase_invoice,
	send_po_mail_to_vendor,
)


@frappe.whitelist(methods=["POST"])
def send_po_to_vendor(purchase_order: str):
	"""
	Send a Purchase Order email with a PDF attachment to its supplier.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_order.send_po_to_vendor`
	**HTTP Method:** POST
	**Parameters:**
	        - purchase_order (str, required): The Purchase Order document name
	**Response:** `true` on success, serialized as JSON.
	"""
	return send_po_mail_to_vendor(purchase_order)


@frappe.whitelist(methods=["POST"])
def make_purchase_invoice_from_portal(
	purchase_order_name: str,
	items: str | list | None = None,
	supplier_invoice_no: str | None = None,
	supplier_invoice_date: str | None = None,
):
	"""
	Create a Purchase Invoice from a Purchase Order, submitted from the vendor portal.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_order.make_purchase_invoice_from_portal`
	**HTTP Method:** POST
	**Parameters:**
	        - purchase_order_name (str, required): The source Purchase Order name
	        - items (str | list, optional): Items to bill, JSON-encoded or a list
	        - supplier_invoice_no (str, optional): The supplier's own invoice number
	        - supplier_invoice_date (str, optional): The supplier's own invoice date
	**Response:** The created Purchase Invoice, serialized as JSON.
	"""
	return make_purchase_invoice(
		purchase_order_name, items, supplier_invoice_no, supplier_invoice_date
	)


@frappe.whitelist(methods=["GET", "POST"])
def validate_transaction_date_with_brn_dates(brn: str, transaction_date: str):
	"""
	Validate that a transaction date falls within the linked BRN's valid date range.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_order.validate_transaction_date_with_brn_dates`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - brn (str, required): The BRN document name
	        - transaction_date (str, required): The transaction date to validate
	**Response:** Validation result, serialized as JSON (raises on failure).
	"""
	return validate_brn_dates(brn, transaction_date)


@frappe.whitelist(methods=["GET", "POST"])
def get_fiscal_year_and_validity(date: str, brn: str | None = None):
	"""
	Resolve the fiscal year for a date, and whether it's still valid against a BRN.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_order.get_fiscal_year_and_validity`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - date (str, required): The date to resolve the fiscal year for
	        - brn (str, optional): A BRN document name to validate against
	**Response:** Fiscal year + validity info, serialized as JSON.
	"""
	return _get_fiscal_year_and_validity(date, brn)


@frappe.whitelist(methods=["GET", "POST"])
def get_vendor_rate_comparison(
	supplier: str,
	nature_of_services: str,
	company: str,
	transaction_date: str,
	brn: str | None = None,
	exclude_po: str | None = None,
):
	"""
	Return the vendor's historical rate rows for the given nature of service.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_order.get_vendor_rate_comparison`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - supplier (str, required): The Supplier to compare rates for
	        - nature_of_services (str, required): The Nature of Service to filter by
	        - company (str, required): The Company context
	        - transaction_date (str, required): The reference transaction date
	        - brn (str, optional): A BRN to exclude/scope the comparison
	        - exclude_po (str, optional): A Purchase Order name to exclude from the comparison
	**Response:** List of rate comparison rows, serialized as JSON.
	"""
	return get_rate_comparison_rows(
		supplier, nature_of_services, company, transaction_date, brn, exclude_po
	)


@frappe.whitelist(methods=["GET", "POST"])
def get_vendor_rate_comparison_config():
	"""
	Return display configuration for the vendor rate comparison table.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.purchase_order.get_vendor_rate_comparison_config`
	**HTTP Method:** GET, POST
	**Parameters:** None
	**Response:** Rate comparison table configuration, serialized as JSON.
	"""
	return get_rate_comparison_config()
