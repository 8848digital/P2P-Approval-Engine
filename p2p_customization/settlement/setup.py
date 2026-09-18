"""
Wired into migrate via hooks.py:

    after_migrate = [..., "p2p_customization.settlement.setup.create_custom_fields"]

It can still be run manually too:

    bench --site your-site execute p2p_customization.settlement.setup.create_custom_fields
"""

import json
import os


def create_custom_fields():
	CUSTOM_FIELDS = {}
	print("Creating/Updating Settlement Custom Fields....")
	path = os.path.join(os.path.dirname(__file__), "custom_fields")
	for file in os.listdir(path):
		# `file` comes from os.listdir(path) itself, not from user input, so it can't escape `path`.
		with open(os.path.join(path, file)) as f:  # nosemgrep: frappe-security-file-traversal
			CUSTOM_FIELDS.update(json.load(f))

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as _create_custom_fields

	_create_custom_fields(CUSTOM_FIELDS)
