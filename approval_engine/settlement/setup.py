# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""
Wired into migrate via hooks.py:

    after_migrate = [..., "approval_engine.settlement.setup.create_custom_fields"]

It can still be run manually too:

    bench --site your-site execute approval_engine.settlement.setup.create_custom_fields
"""

import json
import os

import frappe


def create_custom_fields():
	# "nature_of_service" (Table MultiSelect on Supplier, below) points at
	# this child doctype. On a from-scratch install frappe.model.sync.sync_all()
	# doesn't reliably make a brand-new child doctype visible in time for
	# this function's custom-field insert to pass check_table_multiselect_option
	# -- a targeted reload_doc does, and is safe to call every time.
	frappe.reload_doc("settlement", "doctype", "nature_of_service_reference")

	CUSTOM_FIELDS = {}
	print("Creating/Updating Settlement Custom Fields....")
	path = os.path.join(os.path.dirname(__file__), "custom_fields")
	for file in os.listdir(path):
		# `file` comes from os.listdir(path) itself, not from user input, so it can't escape `path`.
		with open(os.path.join(path, file)) as f:  # nosemgrep: frappe-security-file-traversal
			CUSTOM_FIELDS.update(json.load(f))

	CUSTOM_FIELDS = _drop_fields_for_missing_doctypes(CUSTOM_FIELDS)

	from frappe.custom.doctype.custom_field.custom_field import (
		create_custom_fields as _create_custom_fields,
	)

	_create_custom_fields(CUSTOM_FIELDS)


def _drop_fields_for_missing_doctypes(custom_fields: dict) -> dict:
	"""
	Skip custom-field entries whose target DocType isn't installed on this
	site (e.g. "JFS Settings", owned by jfs_report_customization, which
	isn't a required_apps dependency here) instead of letting the whole
	batch insert fail with LinkValidationError.

	Parameters:
	        custom_fields (dict, required): {doctype: [field_dict, ...]} as read
	                from settlement/custom_fields/*.json.

	Returns:
	        dict: Same shape, with entries for missing DocTypes removed.
	"""
	available = {}
	for doctype, fields in custom_fields.items():
		if frappe.db.exists("DocType", doctype):
			available[doctype] = fields
		else:
			print(f"Skipping custom fields for missing DocType: {doctype}")
	return available
