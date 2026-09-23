# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe

from approval_engine.approval_vendor_portal.utils import (
	base_portal_context,
	get_portal_doctype_by_document_type,
	require_vendor_portal_access,
)

no_cache = 1


def get_context(context: frappe._dict) -> None:
	"""
	Page controller for `/vendor-profile`: the vendor's own Supplier
	record, read-only, with a link to its edit web form when configured.

	Parameters:
	        context (frappe._dict, required): Website render context, mutated
	                in place.

	Returns:
	        None
	"""
	suppliers = require_vendor_portal_access()
	# A vendor account is almost always linked to exactly one Supplier; if
	# somehow linked to more, show the first -- same choice the nav brand
	# name and every other vendor-portal page already make.
	supplier = suppliers[0]

	doc = frappe.get_doc("Supplier", supplier)

	context.update(base_portal_context("profile"))
	context.vendor_supplier_name = doc.supplier_name or doc.name
	context.doc = doc

	supplier_row = get_portal_doctype_by_document_type("Supplier")
	context.edit_web_form_name = supplier_row.edit_web_form if supplier_row else None
