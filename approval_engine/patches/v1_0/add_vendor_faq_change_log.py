# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

# apps/approval_engine/approval_engine/patches/v1_0/add_vendor_faq_change_log.py
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.exists("DocType", "Vendor FAQ Change Log"):
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": "Vendor FAQ Change Log",
				"module": "settlement",
				"custom": 1,
				"istable": 1,
				"editable_grid": 1,
				"fields": [
					{
						"fieldname": "question_label",
						"label": "Question",
						"fieldtype": "Data",
						"in_list_view": 1,
						"read_only": 1,
						"columns": 3,
					},
					{
						"fieldname": "old_value",
						"label": "Old Value",
						"fieldtype": "Data",
						"in_list_view": 1,
						"read_only": 1,
						"columns": 2,
					},
					{
						"fieldname": "new_value",
						"label": "New Value",
						"fieldtype": "Data",
						"in_list_view": 1,
						"read_only": 1,
						"columns": 2,
					},
					{
						"fieldname": "changed_on",
						"label": "Changed On",
						"fieldtype": "Datetime",
						"in_list_view": 1,
						"read_only": 1,
						"columns": 3,
					},
					{
						"fieldname": "changed_by",
						"label": "Changed By",
						"fieldtype": "Data",
						"in_list_view": 1,
						"read_only": 1,
						"columns": 2,
					},
				],
				"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1}],
			}
		).insert(ignore_permissions=True)

	custom_fields = {
		"Supplier": [
			{
				"fieldname": "faq_change_log",
				"label": "FAQ Change Log",
				"fieldtype": "Table",
				"options": "Vendor FAQ Change Log",
				"read_only": 1,
				"insert_after": "code_of_conduct_accepted",
			},
		]
	}
	create_custom_fields(custom_fields, update=True)
