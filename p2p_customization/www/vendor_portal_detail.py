import frappe
from frappe import _

from p2p_customization.vendor_portal.doctype.portal_section_config.portal_section_config import (
	PortalSectionConfig,
)
from p2p_customization.vendor_portal.utils import (
	base_portal_context,
	get_docstatus_filter,
	get_portal_doctype_by_document_type,
	get_portal_doctype_by_route,
	require_row_access,
	require_vendor_portal_access,
	row_allowed_for_user,
	status_pill_color,
)

no_cache = 1

# Fieldtypes safe to print as plain key/value pairs on the generic detail
# grid -- Table/Table MultiSelect/Attach/etc. need their own handling and
# are skipped.
DISPLAYABLE_FIELDTYPES = {
	"Data",
	"Link",
	"Select",
	"Date",
	"Datetime",
	"Currency",
	"Int",
	"Float",
	"Percent",
	"Small Text",
	"Check",
	"Read Only",
}

ITEM_COLUMNS = [
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

	context.kv_fields = __build_kv_fields(doc, row)
	context.item_rows, context.item_columns = __build_child_table(doc, row)
	context.edit_web_form_name = row.edit_web_form
	context.linked_documents, context.linked_documents_label = __build_linked_documents(doc, row)

	context.show_attach_invoice = __show_attach_invoice(doc, row)
	# Fetched whenever the feature is on for this row, not just while the
	# upload form itself is showing -- a vendor should still see what they
	# already uploaded once a record becomes fully billed.
	context.invoice_attachments = (
		__get_invoice_attachments(row.document_type, doc.name) if row.allow_invoice_attach else []
	)


def __build_kv_fields(doc: "frappe.model.document.Document", row: PortalSectionConfig) -> list[dict]:
	"""
	Build the generic key/value grid shown on a detail page: every visible,
	displayable field on `doc` not already surfaced as a title/status/
	amount/etc, capped at 8 entries.

	Parameters:
		doc (Document, required): The document being displayed.
		row (PortalSectionConfig, required): Portal section config for
			`doc`'s DocType.

	Returns:
		list[dict]: Up to 8 `{"label": str, "value": Any}` entries.
	"""
	skip = {
		row.title_field,
		row.status_field,
		row.amount_field,
		row.currency_field,
		row.date_field,
		row.party_fieldname,
		"name",
	}

	fields = []
	for df in doc.meta.fields:
		if df.fieldname in skip or df.fieldtype not in DISPLAYABLE_FIELDTYPES:
			continue
		if df.hidden or not (df.in_list_view or df.in_standard_filter or df.bold):
			continue
		value = doc.get(df.fieldname)
		if not value:
			continue
		fields.append({"label": df.label or df.fieldname, "value": value})
		if len(fields) >= 8:
			break
	return fields


def __build_child_table(
	doc: "frappe.model.document.Document", row: PortalSectionConfig
) -> tuple[list[dict], list[tuple[str, str]]]:
	"""
	Build the item-table rows/columns shown on a detail page, from
	`row.child_table_fieldname`.

	Parameters:
		doc (Document, required): The document being displayed.
		row (PortalSectionConfig, required): Portal section config for
			`doc`'s DocType; `child_table_fieldname` names the child table
			to render.

	Returns:
		tuple[list[dict], list[tuple[str, str]]]: `(rows, columns)`, where
		`columns` is a `(fieldname, label)` list limited to the columns
		present on the child doctype, and `rows` is one dict per child row
		keyed by those fieldnames (plus `description`/`item_name`/`uom`
		when present). Both empty if there's no child table or no rows.
	"""
	if not row.child_table_fieldname:
		return [], []

	child_rows = doc.get(row.child_table_fieldname) or []
	if not child_rows:
		return [], []

	child_meta = child_rows[0].meta
	columns = [(fieldname, label) for fieldname, label in ITEM_COLUMNS if child_meta.has_field(fieldname)]
	if not columns:
		return [], []

	out_rows = []
	for child in child_rows:
		item = {}
		for fieldname, _label in columns:
			item[fieldname] = child.get(fieldname)
		item["description"] = child.get("description") if child_meta.has_field("description") else None
		item["item_name"] = child.get("item_name") if child_meta.has_field("item_name") else None
		item["uom"] = child.get("uom") if child_meta.has_field("uom") else None
		out_rows.append(item)

	return out_rows, columns


def __show_attach_invoice(doc: "frappe.model.document.Document", row: PortalSectionConfig) -> bool:
	"""
	Whether to show the "Attach Invoice Copy" upload -- row has to have it
	turned on, and the record itself has to still be under 100% billed (a
	doctype with no billed-percent field at all, or none set for this row,
	is treated as always eligible rather than silently never showing it).

	Parameters:
		doc (Document, required): The document being displayed.
		row (PortalSectionConfig, required): Portal section config for
			`doc`'s DocType.

	Returns:
		bool: True if the invoice-attach uploader should be shown.
	"""
	if not row.allow_invoice_attach:
		return False
	billed_field = row.billed_percent_fieldname or "per_billed"
	if not doc.meta.has_field(billed_field):
		return True
	return (doc.get(billed_field) or 0) < 100


def __get_invoice_attachments(document_type: str, docname: str) -> list[dict]:
	"""
	Public File attachments already uploaded against a document, newest
	first.

	Parameters:
		document_type (str, required): DocType the files are attached to.
		docname (str, required): Name of the document the files are
			attached to.

	Returns:
		list[dict]: File rows with `name`, `file_name`, `file_url`,
		`creation`.
	"""
	# ignore_permissions: same reasoning as the rest of this system's data
	# fetches -- ownership was already checked against the parent record
	# (doc.get(party_fieldname) in suppliers) before this is ever called,
	# and File's own Desk-oriented permission rules aren't configured for
	# vendor-facing roles.
	return frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": document_type,
			"attached_to_name": docname,
			"is_private": 0,
		},
		fields=["name", "file_name", "file_url", "creation"],
		order_by="creation desc",
		ignore_permissions=True,
	)


def __build_linked_documents(
	doc: "frappe.model.document.Document", row: PortalSectionConfig
) -> tuple[list[dict], str | None]:
	"""
	Documents of another configured type that link back to this one via a
	child table -- e.g. the Purchase Invoices actually raised against a
	Purchase Order, found through Purchase Invoice Item.purchase_order
	rather than any field on Purchase Invoice itself. Reuses the linked
	Document Type's OWN Portal Section Config row for its route/labels/
	status field, so display stays consistent with its own list page
	instead of duplicating that config here.

	Parameters:
		doc (Document, required): The document being displayed.
		row (PortalSectionConfig, required): Portal section config for
			`doc`'s DocType; `linked_document_type`/
			`linked_via_child_doctype`/`linked_via_fieldname` describe the
			link.

	Returns:
		tuple[list[dict], str | None]: `(linked_docs, label)`. `label` is
		None only when there's nothing configured to link.
	"""
	if not (row.linked_document_type and row.linked_via_child_doctype and row.linked_via_fieldname):
		return [], None

	linked_row = get_portal_doctype_by_document_type(row.linked_document_type)
	if not linked_row or not row_allowed_for_user(linked_row):
		return [], None

	# ignore_permissions: same reasoning as everywhere else in this system
	# -- ownership of the PARENT record (doc) was already checked before
	# this is called, and the linked records are just being read for
	# display, gated by that same ownership plus the linked row's own
	# role, not Desk-oriented DocType permissions.
	names = frappe.get_all(
		row.linked_via_child_doctype,
		filters={row.linked_via_fieldname: doc.name},
		fields=["parent"],
		distinct=True,
		pluck="parent",
		ignore_permissions=True,
	)
	if not names:
		return [], linked_row.label or row.linked_document_type

	fields = ["name"]
	for fieldname in (
		linked_row.title_field,
		linked_row.status_field,
		linked_row.amount_field,
		linked_row.currency_field,
		linked_row.date_field,
	):
		if fieldname and fieldname not in fields:
			fields.append(fieldname)

	linked_docs = frappe.get_all(
		row.linked_document_type,
		filters={"name": ["in", names]},
		fields=fields,
		order_by="creation desc",
		ignore_permissions=True,
	)

	out = []
	for d in linked_docs:
		status = d.get(linked_row.status_field) if linked_row.status_field else None
		out.append(
			{
				"name": d.name,
				"route": linked_row.route,
				"title": d.get(linked_row.title_field) if linked_row.title_field else d.name,
				"status": status,
				"pill_color": status_pill_color(status) if status else "gray",
				"amount": d.get(linked_row.amount_field) if linked_row.amount_field else None,
				"currency": d.get(linked_row.currency_field) if linked_row.currency_field else None,
				"date": d.get(linked_row.date_field) if linked_row.date_field else None,
			}
		)

	label = row.linked_documents_label or linked_row.label or row.linked_document_type
	return out, label
