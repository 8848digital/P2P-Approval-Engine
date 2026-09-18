# apps/p2p_customization/p2p_customization/settlement/doc_events/faq_master.py
import re

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from p2p_customization.settlement.doc_events.faq_master_sync import (
	delete_supplier_custom_field_row,
	get_insert_after,
	question_field_dict,
	rebuild_web_form_faq_fields,
	reposition_tail_fields,
)

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
		delete_supplier_custom_field_row(doc.question_code)
		reposition_tail_fields()
	else:
		custom_fields = {"Supplier": [question_field_dict(doc, insert_after=get_insert_after(doc))]}
		create_custom_fields(custom_fields, update=True)
		reposition_tail_fields()
		frappe.clear_cache(doctype="Supplier")

	rebuild_web_form_faq_fields()


def delete_supplier_custom_field(doc, method=None):
	"""doc_event: on_trash on FAQ Master. Runs before the row is actually
	removed from the DB, so any FAQ Master query here must exclude doc.name
	itself or it'll still count as active."""
	delete_supplier_custom_field_row(doc.question_code)
	reposition_tail_fields(exclude_name=doc.name)
	rebuild_web_form_faq_fields(exclude_name=doc.name)


def _parse_options(options_text) -> list:
	"""Split a Select field's newline-separated Options text into a list,
	dropping blank lines."""
	if not options_text:
		return []
	return [o for o in (options_text or "").split("\n") if o.strip()]
