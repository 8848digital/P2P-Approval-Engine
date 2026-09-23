# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Section builders for the /vendor-portal-detail page controller. Split out
of www/vendor_portal_detail.py (get_context() has to stay there -- it's the
required entrypoint name for Frappe's website routing) to keep that file
under the line-count cap.
"""

import frappe

from approval_engine.vendor_portal.doctype.portal_section_config.portal_section_config import (
	PortalSectionConfig,
)

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


def build_kv_fields(doc: "frappe.model.document.Document", row: PortalSectionConfig) -> list[dict]:
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


def build_child_table(
	doc: "frappe.model.document.Document",
	row: PortalSectionConfig,
	item_columns: list[tuple[str, str]],
) -> tuple[list[dict], list[tuple[str, str]]]:
	"""
	Build the item-table rows/columns shown on a detail page, from
	`row.child_table_fieldname`.

	Parameters:
	        doc (Document, required): The document being displayed.
	        row (PortalSectionConfig, required): Portal section config for
	                `doc`'s DocType; `child_table_fieldname` names the child table
	                to render.
	        item_columns (list[tuple[str, str]], required): Candidate
	                `(fieldname, label)` columns, resolved fresh per-request by the
	                caller (translated labels can't be cached at module level).

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
	columns = [
		(fieldname, label) for fieldname, label in item_columns if child_meta.has_field(fieldname)
	]
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


def show_attach_invoice(doc: "frappe.model.document.Document", row: PortalSectionConfig) -> bool:
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


def get_invoice_attachments(document_type: str, docname: str) -> list[dict]:
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
