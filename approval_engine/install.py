# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Install hooks.

Seed the master data the generated Workflows depend on, so a freshly installed
site is ready *before* the first Approval Matrix is submitted. Everything here is
idempotent — the generator also ensures these on every matrix submit, so running
this again (e.g. on reinstall) is safe.
"""

import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Lower

from approval_engine.approval_core import generator
from approval_engine.approval_core.email_action.action_link import DEFAULT_VALIDITY_HOURS
from approval_engine.approval_settlement.setup import create_custom_fields

# Modules that came over from the retired p2p_customization app.
P2P_CUSTOMIZATION_APP = "p2p_customization"
P2P_CUSTOMIZATION_MODULES = ("settlement", "vendor portal")

# Pre-namespacing module names (lowercased) -> their current names.
RENAMED_MODULES = {
	"settlement": "Approval Settlement",
	"vendor portal": "Approval Vendor Portal",
}


def after_install():
	"""
	Seed workflow master data and the default Approval Settings values,
	create the Approval Settlement custom fields
	(install-app runs neither after_migrate nor patches, so a fresh site
	would otherwise have none -- Supplier hooks then fail), and take over
	the modules that came from p2p_customization on sites that already had
	it, renaming them to their namespaced names.

	Returns:
	    None
	"""
	generator.ensure_workflow_states()
	generator.ensure_actions()
	frappe.db.set_single_value(
		"Approval Settings", "email_link_validity_hours", DEFAULT_VALIDITY_HOURS
	)
	create_custom_fields()
	repoint_p2p_customization_module_defs()
	rename_legacy_modules()
	frappe.db.commit()


def repoint_p2p_customization_module_defs():
	"""
	Hand the Settlement and Vendor Portal Module Defs over from
	p2p_customization to approval_engine. Module Def.app_name decides what
	`bench uninstall-app` deletes: left on p2p_customization, uninstalling
	it would drop BRN and every other Settlement/Vendor Portal DocType with
	its data. Case-insensitive because p2p_customization named the module
	"settlement". No-op on sites that never had p2p_customization.

	Returns:
	    None
	"""
	module_def = DocType("Module Def")

	(
		frappe.qb.update(module_def)
		.set(module_def.app_name, "approval_engine")
		.where(module_def.app_name == P2P_CUSTOMIZATION_APP)
		.where(Lower(module_def.name).isin(P2P_CUSTOMIZATION_MODULES))
	).run()


def rename_legacy_modules():
	"""
	Move every record still on the old "Settlement"/"Vendor Portal" modules
	(DocTypes, Custom Fields, Workspaces, Pages, ...) to "Approval
	Settlement"/"Approval Vendor Portal", then delete the old Module Defs.
	Frappe locates a DocType's controller through its module, so a DocType
	left on the old name would stop loading once its folder moved. Runs
	before model sync, so it creates the new Module Defs itself. No-op on
	sites that never had the old modules.

	Returns:
	    None
	"""
	module_defs = frappe.get_all("Module Def", pluck="name")
	for old_name in module_defs:
		new_name = RENAMED_MODULES.get(old_name.lower())
		if not new_name:
			continue

		_ensure_module_def(new_name)
		for doctype in _doctypes_with_module_link():
			table = DocType(doctype)
			(
				frappe.qb.update(table)
				.set(table.module, new_name)
				.where(Lower(table.module) == old_name.lower())
			).run()

		frappe.delete_doc(
			"Module Def", old_name, force=True, ignore_missing=True, ignore_permissions=True
		)


def _ensure_module_def(module_name: str) -> None:
	"""
	Create this app's Module Def if the site doesn't have it yet.

	Parameters:
	    module_name (str, required): The Module Def name, e.g. "Approval Settlement".

	Returns:
	    None
	"""
	if frappe.db.exists("Module Def", module_name):
		return

	frappe.get_doc(
		{"doctype": "Module Def", "module_name": module_name, "app_name": "approval_engine"}
	).insert(ignore_permissions=True)


def _doctypes_with_module_link() -> list[str]:
	"""
	DocTypes that store a module name in a `module` Link field and have a
	table, so records created outside this app's files (e.g. a Workspace
	built in the UI) are covered too.

	Returns:
	    list[str]: DocType names.
	"""
	parents = frappe.get_all(
		"DocField",
		filters={"fieldname": "module", "fieldtype": "Link", "options": "Module Def"},
		pluck="parent",
		distinct=True,
	)
	return [doctype for doctype in parents if frappe.db.table_exists(doctype)]
