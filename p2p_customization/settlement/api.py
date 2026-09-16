import frappe
from frappe import _


def is_vendor(user: str) -> bool:
	"""Only accounts with the "Vendor" checkbox on their User record may use
	the vendor portal. The checkbox is set automatically when a user is
	created via vendor onboarding."""
	return bool(frappe.db.get_value("User", user, "vendor"))


def update_website_context(context):
	"""update_website_context hook: points the website navbar's "Home" link
	at this vendor's actual landing route, so it doesn't fall back to the
	site root. Reuses get_vendor_landing_route() rather than hardcoding
	/portal here too, so onboarded vs not-yet-onboarded vendors land on
	"Home" exactly where they'd land right after logging in. Only applies
	to logged-in vendor accounts -- every other visitor keeps the default
	Home behaviour."""
	if frappe.session.user != "Guest" and is_vendor(frappe.session.user):
		from p2p_customization.vendor_portal.utils import get_vendor_landing_route

		return {"home_page": get_vendor_landing_route(frappe.session.user)}


def block_vendor_from_standard_login(login_manager):
	"""
	Fires for every successful authentication that goes through Frappe's standard /login,
	including the desk login and any other core entry point -- vendor
	accounts must sign in through /vendor-login instead.
	settlement.vendor_portal_auth.authenticate_vendor_login() sets the
	in_vendor_portal_login flag before its own post_login() call, so that
	legitimate path isn't blocked by its own check.

	This runs before the session is created (make_session() happens later in
	post_login()), so raising here leaves the account logged out.
	"""
	if frappe.flags.in_vendor_portal_login:
		return

	if is_vendor(login_manager.user):
		frappe.throw(
			_("Vendor accounts cannot sign in here. Please use the Vendor Portal login page."),
			frappe.PermissionError,
		)
