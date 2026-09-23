# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Status pill colors, docstatus filtering, and the shared portal-page
context. Split out of vendor_portal/utils.py to keep that file under the
line-count cap. Re-exported from there (see that file) so existing import
paths targeting that module keep working.
"""

import frappe
from frappe.model.meta import Meta

from approval_engine.vendor_portal.doctype.portal_section_config.portal_section_config import (
	PortalSectionConfig,
)
from approval_engine.vendor_portal.portal_nav import (
	get_portal_nav_items,
	get_visible_portal_doctypes,
)
from approval_engine.vendor_portal.vendor_identity import get_primary_vendor_supplier_name

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
