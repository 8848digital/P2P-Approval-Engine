# apps/p2p_customization/p2p_customization/settlement/doc_events/faq_master.py
import re

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIRST_FIELD_ANCHOR = "faq_section"
TAIL_HEAD_FIELD = "coc_section"

WEBFORM_NAME = "vendor-onboarding-form"
WEBFORM_FAQ_PAGE_BREAK_LABEL = "FAQ"
WEBFORM_TAIL_FIELDNAME = "coc_section"

# faq_section is the Supplier form's last Tab Break (see gate_faq_section_visibility
# patch), so hiding it via depends_on hides every field in and after the Vendor
# FAQs tab - questions, Code of Conduct, and the FAQ change log - in one place.
#
# The role is read from frappe.boot.jfs_faq_manager_role (see boot.boot_session)
# rather than being baked in as a literal here, so changing JFS Settings.
# faq_manager_role takes effect on next page load without needing to rewrite
# this Custom Field's depends_on.
FAQ_SECTION_VISIBILITY_DEPENDS_ON = (
	"eval:frappe.boot.jfs_faq_section_enabled && "
	"(frappe.user.has_role(frappe.boot.jfs_faq_manager_role) || frappe.user.has_role('System Manager'))"
)

FIELDNAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate(doc, method=None):
	"""doc_event: validate on FAQ Master."""
	_auto_set_sort_order(doc)

	if not FIELDNAME_RE.match(doc.question_code or ""):
		frappe.throw(
			_(
				"Question Code must start with a lowercase letter and contain only "
				"lowercase letters, numbers, and underscores (it becomes the Supplier fieldname)."
			)
		)

	if (doc.field_type or "Select") == "Select":
		options = _parse_options(doc.options)
		if not options:
			frappe.throw(_("Answer Options must contain at least one value."))

		if doc.expected_answer and doc.expected_answer not in options:
			frappe.throw(
				_('Expected Answer "{0}" must be one of the Answer Options: {1}').format(
					doc.expected_answer, ", ".join(options)
				)
			)

	if doc.depends_on_question and doc.depends_on_question == doc.name:
		frappe.throw(_("Depends On Question cannot reference itself."))


def _auto_set_sort_order(doc) -> None:
	"""On insert only, set doc.sort_order to one past the current highest."""
	if not doc.is_new():
		return

	max_order = frappe.db.get_value(
		"FAQ Master", filters={}, fieldname="sort_order", order_by="sort_order desc"
	)
	doc.sort_order = (max_order or 0) + 1


def sync_supplier_custom_field(doc, method=None):
	"""doc_event: after_insert / on_update on FAQ Master."""
	if not doc.is_active:
		_delete_supplier_custom_field(doc.question_code)
		_reposition_tail_fields()
	else:
		custom_fields = {"Supplier": [_question_field_dict(doc, insert_after=_get_insert_after(doc))]}
		create_custom_fields(custom_fields, update=True)
		_reposition_tail_fields()
		frappe.clear_cache(doctype="Supplier")

	_rebuild_web_form_faq_fields()


def delete_supplier_custom_field(doc, method=None):
	"""doc_event: on_trash on FAQ Master. Runs before the row is actually
	removed from the DB, so any FAQ Master query here must exclude doc.name
	itself or it'll still count as active."""
	_delete_supplier_custom_field(doc.question_code)
	_reposition_tail_fields(exclude_name=doc.name)
	_rebuild_web_form_faq_fields(exclude_name=doc.name)


def _parse_options(options_text) -> list:
	"""Split a Select field's newline-separated Options text into a list,
	dropping blank lines."""
	if not options_text:
		return []
	return [o for o in (options_text or "").split("\n") if o.strip()]


def _question_field_dict(row, insert_after=None):
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


def _delete_supplier_custom_field(question_code) -> None:
	"""Remove the Supplier Custom Field for question_code, if one exists."""
	name = frappe.db.get_value("Custom Field", {"dt": "Supplier", "fieldname": question_code})
	if name:
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
		frappe.clear_cache(doctype="Supplier")


def _get_insert_after(doc) -> str:
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


def _reposition_tail_fields(exclude_name=None) -> None:
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


def _rebuild_web_form_faq_fields(exclude_name=None) -> None:
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
			existing.update(_question_field_dict(row))
			new_block.append(existing)
		else:
			new_block.append(_question_field_dict(row))

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
