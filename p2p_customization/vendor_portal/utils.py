import frappe
from frappe import _
from frappe.model.meta import Meta

from p2p_customization.settlement.api import is_vendor
from p2p_customization.vendor_portal.doctype.portal_section_config.portal_section_config import (
	PortalSectionConfig,
)


def get_vendor_suppliers(user: str | None = None) -> list[str]:
	"""
	Every Supplier this portal user is allowed to act as, via the standard
	Portal User child table -- the same mechanism ERPNext's own
	/purchase-orders etc. pages use (see
	erpnext.controllers.website_list_for_contact.get_parents_for_user),
	so permissions stay consistent with core.

	Parameters:
		user (str, optional): User to look up. Defaults to the current
			session user.

	Returns:
		list[str]: Names of Supplier documents this user is a Portal User
		for.
	"""
	user = user or frappe.session.user
	portal_user = frappe.qb.DocType("Portal User")
	return (
		frappe.qb.from_(portal_user)
		.select(portal_user.parent)
		.where(portal_user.user == user)
		.where(portal_user.parenttype == "Supplier")
	).run(pluck="name")


def get_primary_vendor_supplier(user: str | None = None) -> str | None:
	"""
	The first Supplier this portal user is linked to -- used everywhere a
	single "current vendor" is needed rather than the full list.

	Parameters:
		user (str, optional): User to look up. Defaults to the current
			session user.

	Returns:
		str | None: The first linked Supplier's name, or None if the user
		has no linked Supplier.
	"""
	suppliers = get_vendor_suppliers(user)
	return suppliers[0] if suppliers else None


def get_primary_vendor_supplier_name(user: str | None = None) -> str | None:
	"""
	Display name of the user's primary linked Supplier.

	Parameters:
		user (str, optional): User to look up. Defaults to the current
			session user.

	Returns:
		str | None: The Supplier's `supplier_name`, falling back to its
		`name` if `supplier_name` is unset, or None if the user has no
		linked Supplier.
	"""
	supplier = get_primary_vendor_supplier(user)
	if not supplier:
		return None
	return frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier


# Pill color shown next to a document's status on the portal list/detail
# pages. Any status not in this map falls back to "gray" in
# status_pill_color() below, rather than raising.
STATUS_PILL_COLORS = {
	"Draft": "gray",
	"To Bill": "orange",
	"To Receive": "orange",
	"To Receive and Bill": "orange",
	"Completed": "green",
	"Delivered": "green",
	"Paid": "green",
	"Unpaid": "orange",
	"Partly Paid": "orange",
	"Overdue": "red",
	"Cancelled": "red",
	"Closed": "gray",
	"On Hold": "red",
	"Return": "gray",
	"Debit Note Issued": "gray",
	"Submitted": "blue",
	"Internal Transfer": "blue",
}


def status_pill_color(status: str | None) -> str:
	"""
	Map a document status to the CSS pill color used to render it.

	Parameters:
		status (str, optional): The status value to map.

	Returns:
		str: A color name from STATUS_PILL_COLORS, or "gray" for any
		unmapped/unknown status.
	"""
	return STATUS_PILL_COLORS.get(status, "gray")


def get_portal_doctypes() -> list[PortalSectionConfig]:
	"""
	Every enabled row from Vendor Portal Settings, in configured order --
	the single source of truth for what shows up in the portal, its nav
	labels, and how each Document Type is filtered/displayed. Cached
	per-request via frappe.get_cached_doc; Vendor Portal Settings is a
	Single so this is one row read, not a query.

	Parameters:
		None.

	Returns:
		list[PortalSectionConfig]: Enabled child-table rows, sorted by
		`idx_order` then `idx`.
	"""
	settings = frappe.get_cached_doc("Vendor Portal Settings")
	rows = [row for row in settings.doctypes if row.enabled]
	rows.sort(key=lambda r: (r.idx_order or 0, r.idx))
	return rows


def get_portal_doctype_by_route(route: str) -> PortalSectionConfig | None:
	"""
	Find the enabled portal section row for a given URL route segment.

	Parameters:
		route (str, required): Route value to match against each row's
			`route` field.

	Returns:
		PortalSectionConfig | None: The matching row, or None if no
		enabled row has this route.
	"""
	for row in get_portal_doctypes():
		if row.route == route:
			return row
	return None


def get_portal_doctype_by_document_type(document_type: str) -> PortalSectionConfig | None:
	"""
	Find the enabled portal section row configured for a given DocType.

	Parameters:
		document_type (str, required): DocType name to match against each
			row's `document_type` field.

	Returns:
		PortalSectionConfig | None: The matching row, or None if no
		enabled row targets this DocType.
	"""
	for row in get_portal_doctypes():
		if row.document_type == document_type:
			return row
	return None


def row_allowed_for_user(row: PortalSectionConfig, user: str | None = None) -> bool:
	"""
	A row is only visible to/accessible by vendors who hold its configured
	Role -- an unconfigured Role hides the row from everyone rather than
	defaulting it open, so a new row is invisible until an admin
	deliberately assigns it a Role.

	Parameters:
		row (PortalSectionConfig, required): The portal section row to
			check.
		user (str, optional): User to check roles for. Defaults to the
			current session user.

	Returns:
		bool: True if the row has a Role and the user holds it.
	"""
	if not row.role:
		return False
	return row.role in frappe.get_roles(user or frappe.session.user)


def get_visible_portal_doctypes(user: str | None = None) -> list[PortalSectionConfig]:
	"""
	Enabled rows this specific user is allowed to see -- what the sidebar
	and dashboard should actually render, as opposed to
	get_portal_doctypes()'s full configured set (which route lookups still
	need in full, so a role-restricted route can throw a clear permission
	error instead of a blanket 404).

	Parameters:
		user (str, optional): User to check roles for. Defaults to the
			current session user.

	Returns:
		list[PortalSectionConfig]: Enabled rows the user's roles permit.
	"""
	return [row for row in get_portal_doctypes() if row_allowed_for_user(row, user)]


def get_tab_siblings(row: PortalSectionConfig, user: str | None = None) -> list[PortalSectionConfig]:
	"""
	All visible rows sharing row's Tab Group (including row itself), in
	configured order -- e.g. Purchase Orders + Purchase Invoices under
	"orders_invoices". Used to render the tab bar on the list page. Empty
	list for a row with no Tab Group set, so callers can treat that as
	"no tabs to show" with a plain truthiness check.

	Parameters:
		row (PortalSectionConfig, required): The row whose Tab Group
			siblings are wanted.
		user (str, optional): User to filter visibility for. Defaults to
			the current session user.

	Returns:
		list[PortalSectionConfig]: Rows sharing row's Tab Group, or an
		empty list if row has no Tab Group.
	"""
	if not row or not row.tab_group:
		return []
	return [r for r in get_visible_portal_doctypes(user) if r.tab_group == row.tab_group]


def get_portal_nav_items(user: str | None = None) -> list[dict]:
	"""
	Sidebar nav entries built from get_visible_portal_doctypes(), except
	rows sharing a Tab Group collapse into ONE entry instead of one each --
	they're shown as tabs on the same list page (see get_tab_siblings)
	rather than separate sidebar links. Each item carries member_routes so
	the "active" state highlights correctly regardless of which tab within
	the group is actually open.

	Parameters:
		user (str, optional): User to build nav items for. Defaults to the
			current session user.

	Returns:
		list[dict]: One dict per nav entry with `route`, `label`, `icon`,
		and `member_routes` keys.
	"""
	items = []
	seen_groups = set()
	for row in get_visible_portal_doctypes(user):
		if not row.show_in_nav:
			continue
		if row.tab_group:
			if row.tab_group in seen_groups:
				continue
			seen_groups.add(row.tab_group)
			siblings = get_tab_siblings(row, user)
			items.append(
				{
					"route": row.route,
					"label": row.tab_group_label or row.label or row.document_type,
					"icon": row.tab_group_icon or row.icon,
					"member_routes": [r.route for r in siblings],
				}
			)
		else:
			items.append(
				{
					"route": row.route,
					"label": row.label or row.document_type,
					"icon": row.icon,
					"member_routes": [row.route],
				}
			)
	return items


def require_row_access(row: PortalSectionConfig) -> None:
	"""
	Guard for list/detail pages: throws if this specific row is
	role-restricted and the current user doesn't hold that role.

	Parameters:
		row (PortalSectionConfig, required): The portal section row being
			accessed.

	Returns:
		None

	Raises:
		frappe.PermissionError: If the current user doesn't hold the row's
			configured Role.
	"""
	if not row_allowed_for_user(row):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def get_docstatus_filter(row: PortalSectionConfig, meta: Meta) -> int | None:
	"""
	What to filter a row's own document status to, per its own configured
	Docstatus Filter -- "Submitted Only" (the default, e.g. Purchase
	Order) vs "All (Draft, Submitted, Cancelled)" (e.g. Purchase Invoice,
	where a vendor should see every stage). Returns None for a
	non-submittable doctype (nothing to filter) or when "All" is chosen,
	so callers can do `if filter is not None: filters["docstatus"] = filter`
	uniformly instead of each re-deriving this.

	Parameters:
		row (PortalSectionConfig, required): The portal section row whose
			filter is being resolved.
		meta (Meta, required): DocType meta for `row.document_type`.

	Returns:
		int | None: 1 to filter to submitted documents only, or None to
		apply no docstatus filter.
	"""
	if not meta.is_submittable:
		return None
	if (row.docstatus_filter or "Submitted Only") == "All (Draft, Submitted, Cancelled)":
		return None
	return 1


def base_portal_context(vp_active: str) -> dict:
	"""
	Common context every vendor-portal page needs for the shared sidebar:
	nav items (from Vendor Portal Settings, filtered to what this user's
	roles allow), brand name/title, and which nav item is active.

	Parameters:
		vp_active (str, required): Route/identifier of the currently active
			nav item, used to highlight it in the sidebar.

	Returns:
		dict: Context keys consumed by the shared portal sidebar template
		(`vp_active`, `vendor_supplier_name`, `portal_doctypes`,
		`portal_nav_items`, `portal_title`, `full_width`).
	"""
	settings = frappe.get_cached_doc("Vendor Portal Settings")
	return {
		"vp_active": vp_active,
		"vendor_supplier_name": get_primary_vendor_supplier_name(),
		"portal_doctypes": get_visible_portal_doctypes(),
		"portal_nav_items": get_portal_nav_items(),
		"portal_title": settings.portal_title,
		# Frappe's base web template wraps page_content in <main
		# class="container"> unless full_width is set -- Bootstrap's
		# .container is centered with its own max-width and side gutters,
		# which was leaving empty space to the left of the sidebar (and
		# right of the content) regardless of anything in the portal's own
		# CSS, since it's a wrapper outside .vp-app entirely.
		"full_width": True,
	}


def get_vendor_landing_route(user: str | None = None) -> str:
	"""
	Where a vendor lands after login -- the full portal (sidebar and all)
	once they've completed onboarding (have a linked Supplier), or
	straight to the bare onboarding form with no portal shell at all if
	they haven't. Used consistently everywhere a vendor's post-login
	destination is decided: vendor_login()'s own redirect_to, the
	already-logged-in-vendor branch on /vendor-login, and the "/" ->
	vendor redirect -- so "allowed into the portal only after onboarding"
	is one rule, not four separate hardcoded ones.

	Parameters:
		user (str, optional): User to resolve a landing route for.
			Defaults to the current session user.

	Returns:
		str: "/vendor-portal" if onboarded, else
		"/vendor-onboarding-form/new".
	"""
	user = user or frappe.session.user
	if get_vendor_suppliers(user):
		return "/vendor-portal"
	return "/vendor-onboarding-form/new"


def is_vendor_portal_enabled() -> bool:
	"""
	Master switch: JFS Settings > Vendor Portal > Enable Vendor Portal.
	Checked at the one place every portal entry point already funnels
	through (require_vendor_login, called by require_vendor_portal_access
	too) plus the login API itself, so turning this off takes the whole
	portal offline without touching any per-page logic. Defaults to
	enabled if the field is somehow unset (e.g. before the site's first
	save of JFS Settings), matching its Check field's own default.

	Parameters:
		None.

	Returns:
		bool: True if the vendor portal is enabled (or unset), else False.
	"""
	value = frappe.db.get_single_value("JFS Settings", "enable_vendor_portal")
	return True if value is None else bool(value)


def require_vendor_login() -> None:
	"""
	Lighter guard than require_vendor_portal_access(): just needs a
	logged-in vendor account, no linked Supplier required yet. For the
	handful of pages a brand-new vendor (invited by email, no Supplier
	created for them until they submit onboarding) must be able to reach
	before that link exists -- e.g. the onboarding form embed.

	Parameters:
		None.

	Returns:
		None

	Raises:
		frappe.PermissionError: If the portal is disabled, or the current
			user isn't a logged-in vendor.
	"""
	if not is_vendor_portal_enabled():
		frappe.throw(
			_("The vendor portal is currently unavailable. Please contact support."), frappe.PermissionError
		)

	user = frappe.session.user
	if user == "Guest" or not is_vendor(user):
		frappe.throw(_("You need to be logged in as a vendor to access this page"), frappe.PermissionError)


def require_vendor_portal_access() -> list[str]:
	"""
	Guard for every vendor-portal page: must be a logged-in vendor with at
	least one linked Supplier via Portal User.

	Parameters:
		None.

	Returns:
		list[str]: Names of Supplier documents the current user may act
		as.

	Raises:
		frappe.PermissionError: If the portal is disabled, the user isn't
			a logged-in vendor, or the vendor has no linked Supplier.
	"""
	require_vendor_login()

	suppliers = get_vendor_suppliers(frappe.session.user)
	if not suppliers:
		frappe.throw(
			_("Your account is not linked to a Supplier. Please contact support."),
			frappe.PermissionError,
		)
	return suppliers
