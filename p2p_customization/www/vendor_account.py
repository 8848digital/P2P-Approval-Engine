import frappe

from p2p_customization.vendor_portal.utils import (
	require_vendor_portal_access,
	base_portal_context,
)

no_cache = 1


def get_context(context):
	require_vendor_portal_access()

	user = frappe.get_doc("User", frappe.session.user)

	context.update(base_portal_context("account"))
	context.user_doc = user
