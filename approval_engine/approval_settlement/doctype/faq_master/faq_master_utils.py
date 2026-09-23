# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import re

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from approval_engine.approval_settlement.doctype.faq_master.faq_master_sync import (
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
# The role is read from frappe.boot.jfs_faq_manager_role (see approval_engine/boot_session.py)
# rather than being baked in as a literal here, so changing JFS Settings.
# faq_manager_role takes effect on next page load without needing to rewrite
# this Custom Field's depends_on.
FAQ_SECTION_VISIBILITY_DEPENDS_ON = (
	"eval:frappe.boot.jfs_faq_section_enabled && "
	"(frappe.user.has_role(frappe.boot.jfs_faq_manager_role) || frappe.user.has_role('System Manager'))"
)

FIELDNAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate(doc, method=None):
	"""
	FAQ Master validate: auto sort order on insert, Question Code must be a
	valid fieldname, Select options/expected answer must be consistent, and
	Depends On Question can't reference itself.

	Parameters:
	        doc (Document, required): The FAQ Master being validated.
	        method (str, optional): Unused; kept for the old hook signature.

	Returns:
	        None
	"""
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
	"""
	Sync this question onto the Supplier form (Custom Field) and the vendor
	onboarding web form, or remove it when the question is inactive.

	Parameters:
	        doc (Document, required): The FAQ Master that was inserted/updated.
	        method (str, optional): Unused; kept for the old hook signature.

	Returns:
	        None
	"""
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
	"""
	Remove this question from the Supplier form and web form. Runs before
	the row is removed from the DB, so any FAQ Master query here must
	exclude doc.name itself or it'll still count as active.

	Parameters:
	        doc (Document, required): The FAQ Master being deleted.
	        method (str, optional): Unused; kept for the old hook signature.

	Returns:
	        None
	"""
	delete_supplier_custom_field_row(doc.question_code)
	reposition_tail_fields(exclude_name=doc.name)
	rebuild_web_form_faq_fields(exclude_name=doc.name)


def _parse_options(options_text) -> list:
	"""Split a Select field's newline-separated Options text into a list,
	dropping blank lines."""
	if not options_text:
		return []
	return [o for o in (options_text or "").split("\n") if o.strip()]
