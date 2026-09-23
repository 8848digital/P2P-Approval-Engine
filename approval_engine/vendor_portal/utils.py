# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Vendor portal access guards + landing-route resolution.

Identity lookups, portal-section/nav config, and status-pill/context
helpers are split into the sibling vendor_identity.py, portal_nav.py, and
portal_display.py modules (to keep this file under the line-count cap)
and re-exported below, so every existing `from
approval_engine.vendor_portal.utils import ...` across the app keeps
working unchanged.
"""

import frappe
from frappe import _

from approval_engine.settlement.vendor_auth_hooks import is_vendor
from approval_engine.vendor_portal.portal_display import (
	STATUS_PILL_COLORS,
	base_portal_context,
	get_docstatus_filter,
	status_pill_color,
)
from approval_engine.vendor_portal.portal_nav import (
	get_portal_doctype_by_document_type,
	get_portal_doctype_by_route,
	get_portal_doctypes,
	get_portal_nav_items,
	get_tab_siblings,
	get_visible_portal_doctypes,
	require_row_access,
	row_allowed_for_user,
)
from approval_engine.vendor_portal.vendor_identity import (
	get_primary_vendor_supplier,
	get_primary_vendor_supplier_name,
	get_vendor_suppliers,
)

__all__ = [
	"STATUS_PILL_COLORS",
	"base_portal_context",
	"get_docstatus_filter",
	"get_portal_doctype_by_document_type",
	"get_portal_doctype_by_route",
	"get_portal_doctypes",
	"get_portal_nav_items",
	"get_primary_vendor_supplier",
	"get_primary_vendor_supplier_name",
	"get_tab_siblings",
	"get_vendor_landing_route",
	"get_vendor_suppliers",
	"get_visible_portal_doctypes",
	"is_vendor_portal_enabled",
	"require_row_access",
	"require_vendor_login",
	"require_vendor_portal_access",
	"row_allowed_for_user",
	"status_pill_color",
]


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
	# JFS Settings is owned by jfs_report_customization, which isn't a
	# required_apps dependency here -- treated the same as the field being
	# unset (see docstring): defaults to enabled.
	if not frappe.db.exists("DocType", "JFS Settings"):
		return True
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
		frappe.throw(
			_("You need to be logged in as a vendor to access this page"), frappe.PermissionError
		)


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
