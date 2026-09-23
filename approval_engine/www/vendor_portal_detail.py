# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe import _

from approval_engine.approval_vendor_portal.utils import (
	base_portal_context,
	get_docstatus_filter,
	get_portal_doctype_by_route,
	require_row_access,
	require_vendor_portal_access,
	status_pill_color,
)
from approval_engine.www.vendor_portal_detail_linked import build_linked_documents
from approval_engine.www.vendor_portal_detail_sections import (
	build_child_table,
	build_kv_fields,
	get_invoice_attachments,
	show_attach_invoice,
)

no_cache = 1


def _item_columns() -> list[tuple[str, str]]:
	"""Resolved fresh on every call, not cached at module level -- _() must
	run per-request (each site/request can be in a different language), and
	a module-level constant would freeze whichever language was active the
	first time this module happened to be imported in this worker process."""
	return [
		("item_code", _("Item")),
		("qty", _("Qty")),
		("rate", _("Rate")),
		("amount", _("Amount")),
	]


def get_context(context: frappe._dict) -> None:
	"""
	Page controller for `/vendor-portal-detail`: a single document's detail
	view (key/value fields, child-table items, linked documents, and the
	invoice-attach uploader when configured).

	Parameters:
	        context (frappe._dict, required): Website render context, mutated
	                in place. Expects `route` and `name` in `frappe.form_dict`.

	Returns:
	        None

	Raises:
	        frappe.DoesNotExistError: If the route or document doesn't exist,
	                or the document is filtered out by its docstatus rule.
	        frappe.PermissionError: If the current user isn't allowed to view
	                this row/document.
	"""
	suppliers = require_vendor_portal_access()

	route = frappe.form_dict.get("route")
	row = get_portal_doctype_by_route(route)
	if not row:
		frappe.throw(_("Page not found"), frappe.DoesNotExistError)
	require_row_access(row)

	name = frappe.form_dict.get("name")
	if not name or not frappe.db.exists(row.document_type, name):
		frappe.throw(_("Not found"), frappe.DoesNotExistError)

	doc = frappe.get_doc(row.document_type, name)
	if doc.get(row.party_fieldname) not in suppliers:
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# Kept in sync with vendor_portal_list.py's own filter -- a draft
	# shouldn't be reachable by its direct URL just because it's hidden
	# from the list (when this row's Docstatus Filter is "Submitted Only").
	docstatus_filter = get_docstatus_filter(row, doc.meta)
	if docstatus_filter is not None and doc.docstatus != docstatus_filter:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)

	context.update(base_portal_context(row.route))
	context.section_label = row.label or row.document_type
	context.row_config = row
	context.doc = doc

	context.title_value = doc.get(row.title_field) if row.title_field else doc.name
	context.status_value = doc.get(row.status_field) if row.status_field else None
	context.pill_color = status_pill_color(context.status_value) if context.status_value else "gray"
	context.amount_value = doc.get(row.amount_field) if row.amount_field else None
	context.currency_value = doc.get(row.currency_field) if row.currency_field else None
	context.date_value = doc.get(row.date_field) if row.date_field else None

	context.kv_fields = build_kv_fields(doc, row)
	context.item_rows, context.item_columns = build_child_table(doc, row, _item_columns())
	context.edit_web_form_name = row.edit_web_form
	context.linked_documents, context.linked_documents_label = build_linked_documents(doc, row)

	context.show_attach_invoice = show_attach_invoice(doc, row)
	# Fetched whenever the feature is on for this row, not just while the
	# upload form itself is showing -- a vendor should still see what they
	# already uploaded once a record becomes fully billed.
	context.invoice_attachments = (
		get_invoice_attachments(row.document_type, doc.name) if row.allow_invoice_attach else []
	)
