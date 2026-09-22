# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# apps/approval_engine/approval_engine/settlement/doc_events/faq_master_sync.py
"""Supplier Custom Field / vendor onboarding Web Form sync for FAQ Master.
Split out of doc_events/faq_master.py (the doc_events hook file) to keep
that file under the line-count cap - these are called from its hook
functions, never used as hook targets themselves.
"""

import frappe

FIRST_FIELD_ANCHOR = "faq_section"
TAIL_HEAD_FIELD = "coc_section"

WEBFORM_NAME = "vendor-onboarding-form"
WEBFORM_FAQ_PAGE_BREAK_LABEL = "FAQ"
WEBFORM_TAIL_FIELDNAME = "coc_section"


def question_field_dict(row, insert_after=None):
	"""Build the field dict for a FAQ Master row, shared by the Supplier
	Custom Field sync and the web form rebuild. `row` may be a FAQ Master
	Document or a frappe._dict from get_all — both support .get()."""
	fieldtype = row.get("field_type") or "Select"
	field = {
		"fieldtype": fieldtype,
		"fieldname": row.question_code,
		"label": row.question_label,
		"reqd": 1 if row.get("reqd_on_supplier") else 0,
		"description": row.get("description") or "",
	}
	field["options"] = (row.get("options") or "\nYes\nNo") if fieldtype == "Select" else ""

	depends_on_question = row.get("depends_on_question")
	if depends_on_question:
		field["depends_on"] = f"eval:doc.{depends_on_question}=='Yes'"
		field["mandatory_depends_on"] = f"eval:doc.{depends_on_question}=='Yes'"

	if insert_after is not None:
		field["insert_after"] = insert_after
		field["in_list_view"] = 0
	return field


def delete_supplier_custom_field_row(question_code) -> None:
	"""Remove the Supplier Custom Field for question_code, if one exists."""
	name = frappe.db.get_value("Custom Field", {"dt": "Supplier", "fieldname": question_code})
	if name:
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
		frappe.clear_cache(doctype="Supplier")


def get_insert_after(doc) -> str:
	"""Return the question_code this row's Custom Field should be inserted
	after: the previous active row by sort_order, or FIRST_FIELD_ANCHOR if
	doc is the first."""
	prev = frappe.get_all(
		"FAQ Master",
		filters={
			"sort_order": ["<", doc.sort_order],
			"is_active": 1,
			"name": ["!=", doc.name],
		},
		fields=["question_code"],
		order_by="sort_order desc",
		limit=1,
	)
	return prev[0].question_code if prev else FIRST_FIELD_ANCHOR


def reposition_tail_fields(exclude_name=None) -> None:
	"""Keep the Supplier form's Code of Conduct section (coc_section)
	immediately after the last active FAQ Custom Field, since new/removed
	FAQ rows shift where "last" is.

	Parameters:
	    exclude_name (str, optional): An FAQ Master name to exclude from
	        the "last active" lookup (used by the on_trash hook, which
	        fires before the row is actually removed from the DB).

	Returns:
	    None
	"""
	filters = {"is_active": 1}
	if exclude_name:
		filters["name"] = ["!=", exclude_name]

	last_faq = frappe.get_all(
		"FAQ Master",
		filters=filters,
		fields=["question_code"],
		order_by="sort_order desc",
		limit=1,
	)
	anchor = last_faq[0].question_code if last_faq else FIRST_FIELD_ANCHOR

	coc_section = frappe.db.get_value("Custom Field", {"dt": "Supplier", "fieldname": TAIL_HEAD_FIELD})
	if not coc_section:
		return  # add_vendor_faq_coc_fields patch hasn't run yet

	if frappe.db.get_value("Custom Field", coc_section, "insert_after") != anchor:
		frappe.db.set_value("Custom Field", coc_section, "insert_after", anchor)
		frappe.clear_cache(doctype="Supplier")


def rebuild_web_form_faq_fields(exclude_name=None) -> None:
	"""
	Rebuild the vendor onboarding web form's FAQ block (between the "FAQ"
	Page Break and the coc_section field) from active FAQ Master rows,
	preserving each field's existing layout dict where one already exists
	so unrelated web-form-only settings survive a resync.

	Parameters:
	    exclude_name (str, optional): An FAQ Master name to exclude (used
	        by the on_trash hook, before the row is actually removed).

	Returns:
	    None
	"""
	if not frappe.db.exists("Web Form", WEBFORM_NAME):
		return

	web_form = frappe.get_doc("Web Form", WEBFORM_NAME)
	fields = list(web_form.web_form_fields)

	start_idx = None
	end_idx = None
	for i, f in enumerate(fields):
		if (
			f.fieldtype == "Page Break"
			and (f.label or "").strip().lower() == WEBFORM_FAQ_PAGE_BREAK_LABEL.lower()
		):
			start_idx = i
		if f.fieldname == WEBFORM_TAIL_FIELDNAME:
			end_idx = i
			break

	if start_idx is None or end_idx is None:
		frappe.log_error(
			title="FAQ Master → Web Form sync skipped",
			message=f'Could not find "{WEBFORM_FAQ_PAGE_BREAK_LABEL}" Page Break or '
			f'"{WEBFORM_TAIL_FIELDNAME}" on Web Form "{WEBFORM_NAME}".',
		)
		return

	head = [f.as_dict() for f in fields[: start_idx + 1]]
	block = fields[start_idx + 1 : end_idx]
	tail = [f.as_dict() for f in fields[end_idx:]]

	existing_by_fieldname = {f.fieldname: f.as_dict() for f in block if f.fieldname}

	filters = {"is_active": 1}
	if exclude_name:
		filters["name"] = ["!=", exclude_name]

	faq_rows = frappe.get_all(
		"FAQ Master",
		filters=filters,
		fields=[
			"question_code",
			"question_label",
			"field_type",
			"options",
			"reqd_on_supplier",
			"description",
			"depends_on_question",
		],
		order_by="sort_order asc",
	)

	new_block = []
	for row in faq_rows:
		existing = existing_by_fieldname.get(row.question_code)
		if existing:
			existing.update(question_field_dict(row))
			new_block.append(existing)
		else:
			new_block.append(question_field_dict(row))

	for i, d in enumerate(head + new_block + tail):
		d["idx"] = i + 1

	web_form.set("web_form_fields", head + new_block + tail)
	web_form.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Web Form")
	try:
		from frappe.website.utils import clear_cache as clear_website_cache

		clear_website_cache()
	except Exception:
		pass
