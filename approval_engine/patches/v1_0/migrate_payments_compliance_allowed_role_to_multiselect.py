# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import frappe

"""
Migrate Payments Compliance Settings.allowed_role (single Role Link) to the
new allowed_roles (Table of Payments Compliance Allowed Role).

Must run POST model-sync (see patches.txt [post_model_sync] section): the
new child doctype/table only exists after sync_all() has run. The old
allowed_role field's value survives sync_all regardless -- Payments
Compliance Settings is a Single, so its fields are rows in `tabSingles`,
and removing a field from the doctype json does not delete its orphaned
Singles row. That lets this patch read the old value here even though the
field no longer appears in the doctype's own field list.
"""


def execute():
	old_value = frappe.db.sql(
		"""
		SELECT value FROM `tabSingles`
		WHERE doctype='Payments Compliance Settings' AND field='allowed_role'
		""",
	)
	old_role = old_value[0][0] if old_value and old_value[0] else None

	if old_role:
		already_present = frappe.db.exists(
			"Payments Compliance Allowed Role",
			{"parent": "Payments Compliance Settings", "parentfield": "allowed_roles", "role": old_role},
		)
		if not already_present:
			print(
				f"Migrating Payments Compliance Settings.allowed_role={old_role!r} to allowed_roles table"
			)
			settings = frappe.get_single("Payments Compliance Settings")
			settings.append("allowed_roles", {"role": old_role})
			settings.save(ignore_permissions=True)

	# Clean up the orphaned Singles row for the removed field either way.
	frappe.db.sql(
		"""
		DELETE FROM `tabSingles`
		WHERE doctype='Payments Compliance Settings' AND field='allowed_role'
		""",
	)
	frappe.db.commit()
