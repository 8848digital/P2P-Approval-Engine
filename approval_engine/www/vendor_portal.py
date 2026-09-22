# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe

from approval_engine.vendor_portal.doctype.vendor_portal_settings.vendor_portal_settings import (
	seed_default_settings,
)
from approval_engine.vendor_portal.utils import (
	base_portal_context,
	get_docstatus_filter,
	require_vendor_portal_access,
)

no_cache = 1


def get_context(context: frappe._dict) -> None:
	"""
	Page controller for `/vendor-portal`: the vendor's dashboard, showing a
	count tile per visible portal section.

	Parameters:
		context (frappe._dict, required): Website render context, mutated
			in place.

	Returns:
		None
	"""
	suppliers = require_vendor_portal_access()
	seed_default_settings()

	context.update(base_portal_context("home"))
	context.vendor_fullname = frappe.utils.get_fullname(frappe.session.user)

	stats = []
	for row in context.portal_doctypes:
		if not row.show_in_nav:
			continue
		filters = {row.party_fieldname: ["in", suppliers]}
		# Kept in sync with vendor_portal_list.py's own filter -- the
		# dashboard count and the list it links to should always agree.
		docstatus_filter = get_docstatus_filter(row, frappe.get_meta(row.document_type))
		if docstatus_filter is not None:
			filters["docstatus"] = docstatus_filter
		count = frappe.db.count(row.document_type, filters)
		stats.append(
			{
				"label": row.label or row.document_type,
				"route": row.route,
				"icon": row.icon or "file-text",
				"count": count,
			}
		)

	context.stats = stats
