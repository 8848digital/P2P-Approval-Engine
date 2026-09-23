# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Whitelisted endpoints resolving the Tax Withholding Category for a
nature of service and supplier, used by Purchase Order/Invoice item rows.

Thin wrappers only -- the logic lives in approval_settlement/doctype/tds_reference/tds_reference_utils.py.
"""

import frappe

from approval_engine.approval_settlement.doctype.tds_reference.tds_reference_utils import (
	get_tax_withholding_categories as _get_tax_withholding_categories,
)
from approval_engine.approval_settlement.doctype.tds_reference.tds_reference_utils import (
	get_tax_withholding_category as _get_tax_withholding_category,
)


@frappe.whitelist(methods=["GET", "POST"])
def get_tax_withholding_category(nature_of_service: str, supplier: str | None = None):
	"""
	Resolve the Tax Withholding Category for one nature of service, picking
	the Individual/HUF or Others category that matches the supplier's type.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.tax_withholding.get_tax_withholding_category`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - nature_of_service (str, required): The Nature Of Transaction / TDS Reference value
	        - supplier (str, optional): The Supplier, used to pick the entity-type category
	**Response:** The Tax Withholding Category name (str) or null, in the standard envelope's `data`.
	"""
	return _get_tax_withholding_category(nature_of_service, supplier)


@frappe.whitelist(methods=["GET", "POST"])
def get_tax_withholding_categories(nature_of_services: str | list, supplier: str | None = None):
	"""
	Batched version of get_tax_withholding_category: resolve every nature of
	service on a document against one supplier in a single call.

	**Endpoint:** `/api/method/approval_engine.approval_settlement.api.v1.tax_withholding.get_tax_withholding_categories`
	**HTTP Method:** GET, POST
	**Parameters:**
	        - nature_of_services (str | list, required): JSON list of nature-of-service values
	        - supplier (str, optional): The Supplier, used to pick the entity-type category
	**Response:** {nature_of_service: category_or_null} in the standard envelope's `data`.
	"""
	return _get_tax_withholding_categories(nature_of_services, supplier)
