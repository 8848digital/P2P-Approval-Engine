# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints for Supplier Quotation: create a BRN from a
quotation, and create quotations from an uploaded proposal PDF.

Thin wrappers only -- the logic lives in
settlement/customization/supplier_quotation/quotation_actions.py.
"""

import frappe

from approval_engine.settlement.customization.supplier_quotation.quotation_actions import (
	create_brn as _create_brn,
)
from approval_engine.settlement.customization.supplier_quotation.quotation_actions import (
	create_supplier_quotation_from_file as _create_supplier_quotation_from_file,
)


@frappe.whitelist(methods=["POST"])
def create_brn(supplier_quotation: str):
	"""
	Create a BRN from a Supplier Quotation, or add the quotation's vendor to
	the draft BRN already raised for the same requisition (switching it to
	Multi).

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.supplier_quotation.create_brn`
	**HTTP Method:** POST
	**Parameters:**
	        - supplier_quotation (str, required): The Supplier Quotation name
	**Response:** {"name": <BRN name>, "is_new": <bool>} in the standard envelope's `data`.
	"""
	return _create_brn(supplier_quotation)


@frappe.whitelist(methods=["POST"])
def create_supplier_quotation_from_file(file_id: str):
	"""
	Extract vendors from an uploaded proposal PDF and create one Supplier
	Quotation per vendor row.

	**Endpoint:** `/api/method/approval_engine.settlement.api.v1.supplier_quotation.create_supplier_quotation_from_file`
	**HTTP Method:** POST
	**Parameters:**
	        - file_id (str, required): The File document name of the uploaded PDF
	**Response:** {"status": "success", "quotations": [...], "extracted_data": {...}} in the standard envelope's `data`.
	"""
	return _create_supplier_quotation_from_file(file_id)
