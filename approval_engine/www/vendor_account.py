# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe

from approval_engine.vendor_portal.utils import base_portal_context, require_vendor_portal_access

no_cache = 1


def get_context(context: frappe._dict) -> None:
	"""
	Page controller for `/vendor-account`: the logged-in vendor's account
	settings page (password change, etc).

	Parameters:
	        context (frappe._dict, required): Website render context, mutated
	                in place.

	Returns:
	        None
	"""
	require_vendor_portal_access()

	user = frappe.get_doc("User", frappe.session.user)

	context.update(base_portal_context("account"))
	context.user_doc = user
