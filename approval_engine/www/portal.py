# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe.www.portal import get_context as get_core_portal_context

from approval_engine.approval_settlement.vendor_auth_hooks import is_vendor
from approval_engine.approval_vendor_portal.utils import (
	get_primary_vendor_supplier_name,
	get_vendor_landing_route,
	get_vendor_suppliers,
)

no_cache = 1


def get_context(context, **dict_params):
	is_vendor_user = frappe.session.user != "Guest" and is_vendor(frappe.session.user)

	# Vendors have their own dedicated dashboard at /vendor-portal -- don't
	# also render this parallel, hand-rolled vendor summary here. Only the
	# doctype-listing use of this page (My Account style sub-pages) stays
	# generic; a bare /portal visit for a vendor goes straight to their
	# real landing route instead.
	if is_vendor_user and not dict_params and not frappe.form_dict.get("doctype"):
		frappe.local.flags.redirect_location = get_vendor_landing_route()
		raise frappe.Redirect(302)

	context = get_core_portal_context(context, **dict_params)

	context.is_vendor = is_vendor_user
	if context.is_vendor and not context.get("doctype"):
		context.vp_active = "home"
		context.vendor_fullname = frappe.utils.get_fullname(frappe.session.user)
		context.vendor_supplier_name = get_primary_vendor_supplier_name()

		suppliers = get_vendor_suppliers()
		if suppliers:
			context.po_pending_count = frappe.db.count(
				"Purchase Order",
				{
					"supplier": ["in", suppliers],
					"docstatus": 1,
					"status": ["in", ["To Bill", "To Receive", "To Receive and Bill"]],
				},
			)
			context.pi_outstanding_count = frappe.db.count(
				"Purchase Invoice",
				{
					"supplier": ["in", suppliers],
					"docstatus": 1,
					"status": ["in", ["Unpaid", "Overdue", "Partly Paid"]],
				},
			)

	return context
