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
from approval_engine.settlement.setup import create_custom_fields

# Modules that came over from the retired p2p_customization app.
P2P_CUSTOMIZATION_APP = "p2p_customization"
P2P_CUSTOMIZATION_MODULES = ("settlement", "vendor portal")


def after_install():
	"""
	Seed workflow master data, create the Settlement custom fields (install-app
	runs neither after_migrate nor patches, so a fresh site would otherwise
	have none -- Supplier hooks then fail), and take over the modules that
	came from p2p_customization on sites that already had it.

	Returns:
	    None
	"""
	generator.ensure_workflow_states()
	generator.ensure_actions()
	create_custom_fields()
	repoint_p2p_customization_module_defs()
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
