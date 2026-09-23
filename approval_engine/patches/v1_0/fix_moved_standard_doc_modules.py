# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""
Patch: fix the "module" field on standard, user-editable documents that
moved into this app's Approval Settlement module (Web Form, Print Format,
Workspace).

Unlike DocType meta, these are treated as user-customizable records once
they exist -- Frappe's standard-doc sync only ever inserts them if
missing, it never overwrites an existing record's fields (module
included) from the on-disk JSON. So a site that already had these records
(created back when they were owned by jfs_report_customization) keeps
showing the old module in the UI even though the source file here is
already correct -- this patch is the one-time fix for that gap on
existing sites. A fresh install has no such record yet, so the JSON's own
"module": "Approval Settlement" is picked up correctly and this patch is a no-op.

Registered in patches.txt as:
    approval_engine.patches.v1_0.fix_moved_standard_doc_modules
"""

import frappe

MODULE = "Approval Settlement"

DOCS = [
	("Web Form", "vendor-onboarding-form"),
	("Print Format", "BRN"),
	("Workspace", "Payments Compliance"),
]


def execute():
	for doctype, name in DOCS:
		if not frappe.db.exists(doctype, name):
			continue
		if frappe.db.get_value(doctype, name, "module") != MODULE:
			frappe.db.set_value(doctype, name, "module", MODULE, update_modified=False)

	frappe.clear_cache()
	frappe.db.commit()
