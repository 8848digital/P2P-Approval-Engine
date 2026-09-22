# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Vendor <-> Supplier identity lookups. Split out of vendor_portal/utils.py
to keep that file under the line-count cap. Re-exported from there (see
that file) so existing import paths targeting that module keep working.
"""

import frappe


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
