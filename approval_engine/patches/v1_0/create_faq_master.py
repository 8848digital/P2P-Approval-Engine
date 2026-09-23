# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from approval_engine.patches.v1_0.create_faq_master_data import FAQ_QUESTIONS


def execute():
	"""Create FAQ Master / Supplier FAQ Answer if missing and seed the onboarding questions."""
	_create_faq_master_doctype()
	_create_supplier_faq_answer_doctype()
	_seed_faq_master_questions()


def _create_faq_master_doctype():
	"""Create FAQ Master as a custom DocType on sites that don't have it yet."""
	if frappe.db.exists("DocType", "FAQ Master"):
		return
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": "FAQ Master",
			"module": "Approval Settlement",
			"custom": 1,
			"naming_rule": "By fieldname",
			"autoname": "field:question_code",
			"fields": [
				{
					"fieldname": "question_code",
					"label": "Question Code",
					"fieldtype": "Data",
					"reqd": 1,
					"unique": 1,
					"in_list_view": 1,
					"description": "Must be a valid fieldname: lowercase letters, numbers, underscores only. Becomes the Supplier fieldname directly.",
				},
				{
					"fieldname": "question_label",
					"label": "Question",
					"fieldtype": "Data",
					"reqd": 1,
					"in_list_view": 1,
				},
				{
					"fieldname": "options",
					"label": "Answer Options",
					"fieldtype": "Small Text",
					"reqd": 1,
					"default": "\nYes\nNo",
					"description": "Newline-separated list of selectable answers, e.g.\nYes\nNo  (leading blank line = optional/unanswered state).",
				},
				{
					"fieldname": "expected_answer",
					"label": "Expected Answer",
					"fieldtype": "Data",
					"in_list_view": 1,
					"description": "Optional. If set, must exactly match one of the values in Answer Options. Leave blank if this question has no right/wrong answer (e.g. informational questions).",
				},
				{
					"fieldname": "reqd_on_supplier",
					"label": "Mandatory on Supplier Form",
					"fieldtype": "Check",
					"default": "1",
				},
				{
					"fieldname": "sort_order",
					"label": "Sort Order",
					"fieldtype": "Int",
					"default": "0",
					"in_list_view": 1,
				},
				{
					"fieldname": "is_active",
					"label": "Is Active",
					"fieldtype": "Check",
					"default": "1",
					"in_list_view": 1,
				},
				{"fieldname": "description", "label": "Description", "fieldtype": "Small Text"},
			],
			"sort_field": "sort_order",
			"sort_order": "ASC",
			"permissions": [
				{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
			],
		}
	).insert(ignore_permissions=True)


def _create_supplier_faq_answer_doctype():
	"""Create the Supplier FAQ Answer child DocType on sites that don't have it yet."""
	if frappe.db.exists("DocType", "Supplier FAQ Answer"):
		return
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": "Supplier FAQ Answer",
			"module": "Approval Settlement",
			"custom": 1,
			"istable": 1,
			"editable_grid": 1,
			"fields": [
				{
					"fieldname": "faq_question",
					"label": "Question",
					"fieldtype": "Link",
					"options": "FAQ Master",
					"reqd": 1,
					"read_only": 1,
					"in_list_view": 1,
					"columns": 4,
				},
				{
					"fieldname": "question_label",
					"label": "Question Text",
					"fieldtype": "Data",
					"fetch_from": "faq_question.question_label",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 5,
				},
				{
					"fieldname": "answer",
					"label": "Answer",
					"fieldtype": "Select",
					"options": "\nYes\nNo",
					"reqd": 1,
					"in_list_view": 1,
					"columns": 3,
				},
			],
			"permissions": [
				{"role": "System Manager", "read": 1, "write": 1, "create": 1},
			],
		}
	).insert(ignore_permissions=True)


def _seed_faq_master_questions():
	"""Seed FAQ Master with the vendor onboarding questions in
	create_faq_master_data.FAQ_QUESTIONS, skipping any that already exist."""
	for (
		question_code,
		label,
		options,
		expected,
		reqd,
		order,
		desc,
		field_type,
		depends_on_question,
	) in FAQ_QUESTIONS:
		if frappe.db.exists("FAQ Master", question_code):
			continue
		frappe.get_doc(
			{
				"doctype": "FAQ Master",
				"question_code": question_code,
				"question_label": label,
				"field_type": field_type,
				"options": options,
				"expected_answer": expected,
				"reqd_on_supplier": reqd,
				"sort_order": order,
				"is_active": 1,
				"description": desc,
				"depends_on_question": depends_on_question,
			}
		).insert(ignore_permissions=True)
