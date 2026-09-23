# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import urllib.parse

import frappe
from frappe import _

from approval_engine.approval_vendor_portal.utils import (
	base_portal_context,
	get_docstatus_filter,
	get_portal_doctype_by_route,
	get_tab_siblings,
	require_row_access,
	require_vendor_portal_access,
	status_pill_color,
)

no_cache = 1


def get_context(context: frappe._dict) -> None:
	"""
	Page controller for `/vendor-portal-list`: a filterable, searchable,
	sortable list of documents for one portal section (or one tab within a
	shared Tab Group).

	Parameters:
	        context (frappe._dict, required): Website render context, mutated
	                in place. Expects `route` and reads optional `q`/`sort` from
	                `frappe.form_dict`.

	Returns:
	        None

	Raises:
	        frappe.DoesNotExistError: If `route` doesn't match a configured
	                portal section.
	        frappe.PermissionError: If the current user isn't allowed to view
	                this row.
	"""
	suppliers = require_vendor_portal_access()

	route = frappe.form_dict.get("route")
	row = get_portal_doctype_by_route(route)
	if not row:
		frappe.throw(_("Page not found"), frappe.DoesNotExistError)
	require_row_access(row)

	context.update(base_portal_context(row.route))
	context.section_label = row.label or row.document_type
	context.row_config = row

	tab_siblings = get_tab_siblings(row)
	context.tab_siblings = tab_siblings
	context.tab_group_label = (
		next((s.tab_group_label for s in tab_siblings if s.tab_group_label), None)
		if tab_siblings
		else None
	)

	fields = ["name"]
	for fieldname in (
		row.title_field,
		row.status_field,
		row.amount_field,
		row.currency_field,
		row.date_field,
	):
		if fieldname and fieldname not in fields:
			fields.append(fieldname)

	filters = {row.party_fieldname: ["in", suppliers]}
	meta = frappe.get_meta(row.document_type)
	docstatus_filter = get_docstatus_filter(row, meta)
	if docstatus_filter is not None:
		filters["docstatus"] = docstatus_filter

	# Search: OR'd among themselves, then ANDed with the filters above --
	# so it can never widen the result past this vendor's own records
	# (the party_fieldname/docstatus scoping stays a hard boundary), it
	# only narrows further within them.
	search = (frappe.form_dict.get("q") or "").strip()
	or_filters = None
	if search:
		or_filters = [["name", "like", f"%{search}%"]]
		if row.title_field and meta.has_field(row.title_field):
			or_filters.append([row.title_field, "like", f"%{search}%"])

	sort_dir = frappe.form_dict.get("sort")
	if sort_dir not in ("asc", "desc"):
		sort_dir = "desc"

	has_date_field = bool(row.date_field and meta.has_field(row.date_field))
	order_by = (
		f"{row.date_field} {sort_dir}, creation {sort_dir}" if has_date_field else f"creation {sort_dir}"
	)

	# ignore_permissions: this system's own security boundary is the
	# party_fieldname filter above plus the role gate already enforced by
	# require_row_access() -- not the Desk-oriented DocType permission
	# system, which isn't configured for vendor-facing roles on most
	# doctypes (e.g. BRN has no Supplier-role read rule at all, unlike
	# Purchase Order/Invoice where ERPNext happens to ship one already).
	rows = frappe.get_all(
		row.document_type,
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by=order_by,
		limit_page_length=0,
		ignore_permissions=True,
	)

	for r in rows:
		r.title = r.get(row.title_field) if row.title_field else r.name
		r.status = r.get(row.status_field) if row.status_field else None
		r.amount = r.get(row.amount_field) if row.amount_field else None
		r.currency = r.get(row.currency_field) if row.currency_field else None
		r.date = r.get(row.date_field) if row.date_field else None
		r.pill_color = status_pill_color(r.status) if r.status else "gray"

	context.rows = rows
	context.search_query = search
	context.sort_dir = sort_dir
	sort_dir_opposite = "asc" if sort_dir == "desc" else "desc"
	# Built server-side (not inline in the template) so the search query
	# is safely URL-encoded regardless of what characters it contains.
	toggle_params = {"sort": sort_dir_opposite}
	if search:
		toggle_params["q"] = search
	context.sort_toggle_query = urllib.parse.urlencode(toggle_params)
