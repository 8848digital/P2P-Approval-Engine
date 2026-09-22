# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Portal section config lookups + sidebar nav building. Split out of
vendor_portal/utils.py to keep that file under the line-count cap.
Re-exported from there (see that file) so existing import paths targeting
that module keep working.
"""

import frappe
from frappe import _

from approval_engine.vendor_portal.doctype.portal_section_config.portal_section_config import (
	PortalSectionConfig,
)


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
