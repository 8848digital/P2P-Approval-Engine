# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Linked-documents section builder for /vendor-portal-detail. Split out of
vendor_portal_detail_sections.py to keep that file under the line-count cap.
"""

import frappe

from approval_engine.vendor_portal.doctype.portal_section_config.portal_section_config import (
	PortalSectionConfig,
)
from approval_engine.vendor_portal.utils import (
	get_portal_doctype_by_document_type,
	row_allowed_for_user,
	status_pill_color,
)


def build_linked_documents(
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
