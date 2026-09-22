import frappe
from frappe.website.path_resolver import resolve_path


def resolve_website_path(path):
	"""
	Vendors get a fully custom portal under /vendor-portal, entirely
	separate from ERPNext's standard /portal and /purchase-orders style
	routes -- everyone else (Customers, other portal roles, Guests) keeps
	the default behaviour untouched.

	- Visiting "/" as a logged-in vendor redirects to /vendor-portal once
	  they've completed onboarding (have a linked Supplier), or to the bare
	  onboarding form (no portal shell) if not yet -- see
	  get_vendor_landing_route().
	- /vendor-portal is the dashboard, driven by Vendor Portal Settings.
	- /vendor-portal/<route> and /vendor-portal/<route>/<name> are the
	  generic list/detail pages for whichever Document Type is configured
	  against that route in Vendor Portal Settings.
	"""
	if not path and frappe.session.user != "Guest" and _is_vendor(frappe.session.user):
		from p2p_customization.vendor_portal.utils import get_vendor_landing_route

		frappe.flags.redirect_location = get_vendor_landing_route()
		raise frappe.Redirect(302)

	vendor_override = _resolve_vendor_portal_path(path)
	if vendor_override:
		return vendor_override

	return resolve_path(path)


def _is_vendor(user):
	from p2p_customization.settlement.vendor_auth_hooks import is_vendor

	return is_vendor(user)


def _resolve_vendor_portal_path(path):
	if not path or frappe.session.user == "Guest":
		return None

	segments = path.strip("/").split("/")
	if segments[0] != "vendor-portal":
		return None

	if not _is_vendor(frappe.session.user):
		return None

	if len(segments) == 1:
		return "vendor-portal"

	frappe.form_dict.route = segments[1]

	if len(segments) == 2:
		return "vendor-portal-list"

	frappe.form_dict.name = "/".join(segments[2:])
	return "vendor-portal-detail"
