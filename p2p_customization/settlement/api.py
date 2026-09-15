
import frappe
from frappe import _
from frappe.auth import LoginManager
from frappe.utils.file_manager import save_file


@frappe.whitelist(allow_guest=True)
def vendor_login(usr: str, pwd: str):
	"""
	Custom login endpoint for the vendor portal.

	Authenticates the given credentials, then additionally checks that the
	account is actually a vendor before establishing the session. This keeps
	the vendor portal separate from the standard Frappe /login flow, so an
	arbitrary system user (or a vendor trying to use the wrong door) can't
	just log in here.
	"""
	if not usr or not pwd:
		frappe.response["http_status_code"] = 400
		return {"success": False, "error": _("Email and password are required")}

	# Local import: vendor_portal.utils imports is_vendor from this same
	# module, so a module-level import here would be circular.
	from p2p_customization.vendor_portal.utils import is_vendor_portal_enabled

	if not is_vendor_portal_enabled():
		frappe.response["http_status_code"] = 503
		return {"success": False, "error": _("The vendor portal is currently unavailable. Please contact support.")}

	try:
		login_manager = LoginManager()
		login_manager.authenticate(user=usr, pwd=pwd)
		# Lets the on_login hook (block_vendor_from_standard_login, below) know
		# this post_login() call is the legitimate vendor-portal path, so it
		# doesn't reject the very login it's meant to allow.
		frappe.flags.in_vendor_portal_login = True
		login_manager.post_login()
	except frappe.exceptions.AuthenticationError:
		frappe.local.response["http_status_code"] = 401
		frappe.clear_messages()
		return {"success": False, "error": _("Invalid email or password")}
	except frappe.exceptions.ValidationError as e:
		frappe.local.response["http_status_code"] = 401
		frappe.clear_messages()
		return {"success": False, "error": str(e)}
	finally:
		frappe.flags.in_vendor_portal_login = False

	user = frappe.session.user

	if not is_vendor(user):
		# Valid credentials, but not a vendor account -> reject and roll back session
		frappe.local.login_manager.logout()
		frappe.local.response["http_status_code"] = 403
		return {
			"success": False,
			"error": _("This account does not have vendor portal access"),
		}

	frappe.db.commit()

	# Local import: vendor_portal.utils imports is_vendor from this same
	# module, so a module-level import here would be circular.
	from p2p_customization.vendor_portal.utils import get_vendor_landing_route

	return {
		"success": True,
		"redirect_to": get_vendor_landing_route(user),
	}


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
	accounts must sign in through /vendor-login instead. vendor_login()
	(above) sets the in_vendor_portal_login flag before its own post_login()
	call, so that legitimate path isn't blocked by its own check.

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

@frappe.whitelist()
def vendor_web_logout():
	"""
	Custom logout for portal users.
	Redirects to /vendor-login if the logged-out user had vendor access,
	otherwise falls back to the standard /login page.
	"""
	user = frappe.session.user
	was_vendor = is_vendor(user)

	frappe.local.login_manager.logout()
	frappe.db.commit()

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/vendor-login" if was_vendor else "/login"


@frappe.whitelist()
def vendor_update_password(old_password: str, new_password: str):
	"""
	Password change for vendor-portal accounts.

	frappe.core.doctype.user.user.update_password() re-establishes the
	session via login_manager.login_as() once the password is saved, which
	fires the on_login hook -- that's block_vendor_from_standard_login,
	which throws for any vendor login not explicitly flagged as coming
	through vendor_login() above. A vendor changing their own password
	would otherwise always get blocked by their own account's guard, so
	this sets the same bypass flag around the call.
	"""
	if not is_vendor(frappe.session.user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from frappe.core.doctype.user.user import update_password as _update_password

	frappe.flags.in_vendor_portal_login = True
	try:
		_update_password(new_password=new_password, old_password=old_password)
	finally:
		frappe.flags.in_vendor_portal_login = False


@frappe.whitelist()
def vendor_attach_invoice_copy(route: str, docname: str):
	"""
	Lets a vendor upload their invoice copy straight from a record's own
	detail page in the portal -- for whichever Portal Section Config rows
	have Allow Attaching Invoice Copy turned on (Purchase Order, by
	default), while it isn't fully billed yet.

	Local imports: vendor_portal.utils imports is_vendor from this same
	module, so module-level imports here would be circular.
	"""
	if not is_vendor(frappe.session.user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from p2p_customization.vendor_portal.utils import (
		get_portal_doctype_by_route,
		get_vendor_suppliers,
		require_row_access,
	)

	row = get_portal_doctype_by_route(route)
	if not row or not row.allow_invoice_attach:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	require_row_access(row)

	if not docname or not frappe.db.exists(row.document_type, docname):
		frappe.throw(_("Not found"), frappe.DoesNotExistError)

	doc = frappe.get_doc(row.document_type, docname)
	if doc.get(row.party_fieldname) not in get_vendor_suppliers():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	billed_field = row.billed_percent_fieldname or "per_billed"
	if doc.meta.has_field(billed_field) and (doc.get(billed_field) or 0) >= 100:
		frappe.throw(_("This record is already fully billed"))

	uploaded_file = frappe.request.files.get("file")
	if not uploaded_file:
		frappe.throw(_("No file uploaded"))

	# Public (not private) matches this app's own existing pattern for
	# vendor-visible attachments (see templates/pages/brn.py) -- a private
	# file's URL is gated by frappe.has_permission() on the attached
	# document, which the vendor's role was never given at the Desk
	# permission level, so a private upload here would succeed but then be
	# unopenable by the very vendor who uploaded it.
	saved = save_file(
		uploaded_file.filename,
		uploaded_file.stream.read(),
		row.document_type,
		docname,
		is_private=0,
	)
	frappe.db.commit()

	return {"file_name": saved.file_name, "file_url": saved.file_url}
