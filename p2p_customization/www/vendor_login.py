import frappe
from frappe import _

from p2p_customization.settlement.vendor_auth_hooks import is_vendor as is_vendor_user
from p2p_customization.vendor_portal.utils import get_vendor_landing_route

no_cache = 1


def get_context(context: frappe._dict) -> frappe._dict:
	"""
	Page controller for `/vendor-login`. Redirects an already-authenticated
	vendor straight to their landing page, drops a non-vendor session and
	shows the login form again, or renders the login form itself for a
	Guest.

	Parameters:
		context (frappe._dict, required): Website render context, mutated
			in place. Reads an optional `redirect-to` from
			`frappe.form_dict`.

	Returns:
		frappe._dict: The same context, updated with login-page display
		flags (only reached when no redirect happens).
	"""
	redirect_to = sanitize_redirect(frappe.form_dict.get("redirect-to"))

	if frappe.session.user != "Guest":
		if is_vendor_user(frappe.session.user):
			# already signed in as a vendor -> skip the login form. Lands on
			# the full portal only once onboarded (has a linked Supplier),
			# otherwise straight to the bare onboarding form -- see
			# get_vendor_landing_route().
			frappe.local.flags.redirect_location = redirect_to or get_vendor_landing_route()
			# 302, not the default 301 -- the browser must re-check this once logged out
			raise frappe.Redirect(302)

		# signed in, but not a vendor -> drop that session and show the vendor login
		frappe.local.login_manager.logout()
		frappe.db.commit()

		frappe.local.flags.redirect_location = build_login_url(redirect_to)
		raise frappe.Redirect(302)

	context.title = _("Vendor Login")
	context.no_header = True
	context.no_breadcrumbs = True
	context.no_cache = 1
	context.hide_login = True
	return context


def sanitize_redirect(redirect_to: str | None) -> str | None:
	"""
	Only allow site-relative paths, so ?redirect-to= can't bounce to
	another host.

	Parameters:
		redirect_to (str, optional): Raw `redirect-to` query value.

	Returns:
		str | None: `redirect_to` unchanged if it's a safe site-relative
		path, else None.
	"""
	if not redirect_to:
		return None

	if not redirect_to.startswith("/") or redirect_to.startswith("//"):
		return None

	return redirect_to


def build_login_url(redirect_to: str | None) -> str:
	"""
	Build the `/vendor-login` URL, optionally carrying a sanitized
	`redirect-to` so the user lands back where they started after logging
	in as a vendor.

	Parameters:
		redirect_to (str, optional): Site-relative path to redirect to
			after login.

	Returns:
		str: "/vendor-login", with `?redirect-to=...` appended when
		`redirect_to` is given.
	"""
	if not redirect_to:
		return "/vendor-login"

	from urllib.parse import quote

	return f"/vendor-login?redirect-to={quote(redirect_to, safe='')}"
