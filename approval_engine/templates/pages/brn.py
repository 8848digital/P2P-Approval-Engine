# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

from urllib.parse import quote

import frappe

from approval_engine.settlement.doctype.brn.brn_portal import (
	can_make_purchase_invoice,
	check_brn_portal_access,
)


def get_context(context) -> None:
	"""
	Page controller for the /brn/<name> portal detail page: checks the user
	may see this BRN, then loads it, its public attachments, and whether the
	"Create Purchase Invoice" button should show.

	Parameters:
	        context (frappe._dict, required): The website render context.

	Returns:
	        None
	"""
	context.no_cache = 1
	context.show_sidebar = True

	brn_name = frappe.form_dict.name

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(f"/brn/{brn_name}")
		raise frappe.Redirect

	context.doc = frappe.get_doc("BRN", brn_name)
	check_brn_portal_access(context.doc)

	context.title = context.doc.name

	context.attachments = frappe.get_all(
		"File",
		fields=["name", "file_name", "file_url"],
		filters={
			"attached_to_doctype": "BRN",
			"attached_to_name": brn_name,
			"is_private": 0,
		},
	)

	context.show_make_pi_button = can_make_purchase_invoice(context.doc)
