from urllib.parse import quote, urlencode

import frappe
from frappe import _

from p2p_customization.vendor_portal.utils import (
	require_vendor_login,
	base_portal_context,
	row_allowed_for_user,
)

no_cache = 1

# form_dict keys that steer this page itself, not the embedded web form --
# everything else (e.g. email_id, reference_docname on the onboarding
# link) is passed straight through as a query string.
OWN_PARAMS = {"web_form", "name", "cmd"}


def get_context(context):
	# Lighter guard than require_vendor_portal_access(): a brand-new vendor
	# invited by email has no Supplier yet -- that's only created once they
	# submit the onboarding form, so this page can't require one already
	# existing the way every other vendor-portal page does.
	require_vendor_login()

	web_form_route = frappe.form_dict.get("web_form")
	name = frappe.form_dict.get("name")

	# Only allow embedding a Web Form that's actually configured as an
	# edit_web_form somewhere in Vendor Portal Settings, on a row this
	# user's role is actually allowed to see -- prevents both a tampered
	# ?web_form= param iframing an unrelated form, and a role-restricted
	# row's edit form being reachable by a user who can't see that row.
	settings = frappe.get_cached_doc("Vendor Portal Settings")
	matching_rows = [row for row in settings.doctypes if row.edit_web_form == web_form_route]
	if not web_form_route or not matching_rows or not any(row_allowed_for_user(row) for row in matching_rows):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	context.update(base_portal_context(""))

	# Path-based /<name> (or /new for a not-yet-created record), not
	# ?name= -- the bare route with a query string still lands in
	# read-only view mode the same way, but using the same path pattern
	# the web form's own links use keeps this consistent with how it
	# behaves outside the portal.
	actual_route = frappe.db.get_value("Web Form", web_form_route, "route") or web_form_route
	src = f"/{actual_route}"
	if name == "new":
		src += "/new"
	elif name:
		src += f"/{quote(name)}"

	extra_params = {k: v for k, v in frappe.form_dict.items() if k not in OWN_PARAMS}
	if extra_params:
		src += f"?{urlencode(extra_params)}"

	context.iframe_src = src
