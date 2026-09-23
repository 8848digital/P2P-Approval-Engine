# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
import frappe
from frappe.query_builder import DocType

OLD_MODULE = "Approval Engine"
NEW_MODULE = "Approval Core"


def execute():
	"""
	Repoint every record still linked to the retired "Approval Engine" module at
	"Approval Core". The module rename shipped as a file-only change, and Frappe
	skips re-importing non-DocType fixtures (Page, Workspace, ...) whose JSON
	`modified` timestamp is unchanged, so already-migrated sites kept the old
	module name and failed with "Module Approval Engine not found".

	Returns:
	        None
	"""
	if not frappe.db.exists("Module Def", NEW_MODULE):
		return

	for doctype in __doctypes_linked_to_module():
		__repoint_module(doctype)

	frappe.delete_doc(
		"Module Def", OLD_MODULE, force=True, ignore_missing=True, ignore_permissions=True
	)


def __doctypes_linked_to_module() -> list[str]:
	"""
	Collect the DocTypes that store a module name in a `module` Link field, so the
	patch covers records created outside this app's files (e.g. a Workspace built
	in the UI) without hardcoding a list that drifts.

	Returns:
	        list[str]: DocType names that have a backing table and a `module` Link field.
	"""
	parents = frappe.get_all(
		"DocField",
		filters={"fieldname": "module", "fieldtype": "Link", "options": "Module Def"},
		pluck="parent",
		distinct=True,
	)

	return [doctype for doctype in parents if frappe.db.table_exists(doctype)]


def __repoint_module(doctype: str) -> None:
	"""
	Update every row of one DocType that still points at the old module name.

	Parameters:
	        doctype (str, required): DocType whose table holds a `module` Link field.

	Returns:
	        None
	"""
	table = DocType(doctype)

	frappe.qb.update(table).set(table.module, NEW_MODULE).where(table.module == OLD_MODULE).run()
