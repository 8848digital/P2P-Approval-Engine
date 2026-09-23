# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Workflow generation engine (LITERAL model).

For a target DocType, (re)build ONE standard ERPNext Workflow from all submitted
Approval Matrix records. Transitions are generated PER (company, department, band,
tier, action) with company/department/amount-band/approver-pool/no-repeat conditions
written literally into each transition. Escalate-vs-finalize is baked in at
generation time (we know which tiers are configured per row).

Roles (`<DocType> - Approver N`) are a coarse gate; the exact per-row approver pool
is embedded in each condition so only that department/band's approvers can act.
"""

import frappe

# Also re-exports the names other modules import from generator, so existing
# imports keep working after the split into workflow_*.py / role_sync.py.
from approval_engine.approval_core.role_sync import reconcile_roles  # noqa: F401
from approval_engine.approval_core.workflow_builder import (  # noqa: F401
	build_transitions,
	build_workflow,
)
from approval_engine.approval_core.workflow_config import (  # noqa: F401
	MAX_LEVELS,
	STATE_FOR_TIER,
	acting_tier,
	amount_field_for,
	band_condition,
	configured_levels,
	find_band_row,
	pool,
	resolve_amount_field,
	workflow_name,
)
from approval_engine.approval_core.workflow_setup import (  # noqa: F401
	ensure_actions,
	ensure_amount_field,
	ensure_company_read,
	ensure_department_field,
	ensure_department_read,
	ensure_role_permissions,
	ensure_roles,
	ensure_workflow_states,
	remove_legacy_history_field,
)


def setup_workflow(document_type):
	"""
	Bring everything a governed DocType needs into line (idempotent; run on matrix submit).

	Ensures masters, roles and permissions, the routing department field, then rebuilds the
	workflow from all submitted matrices and reconciles role holders.

	Parameters:
	    document_type (str, required): Target DocType.

	Returns:
	    None
	"""
	ensure_workflow_states()
	ensure_actions()
	ensure_roles(document_type)
	ensure_role_permissions(document_type)
	ensure_department_read(document_type)
	ensure_company_read(document_type)
	ensure_amount_field(document_type)
	remove_legacy_history_field(document_type)
	ensure_department_field(document_type)
	build_workflow(document_type)
	reconcile_roles(document_type)
	frappe.clear_cache(doctype=document_type)


def on_matrix_cancel(document_type):
	"""
	React to a cancelled matrix: rebuild the workflow without it, or deactivate it.

	The workflow is deactivated (never deleted) when no submitted matrix remains for the
	DocType, so in-flight documents keep their recorded state.

	Parameters:
	    document_type (str, required): Target DocType.

	Returns:
	    None
	"""
	reconcile_roles(document_type)
	remaining = frappe.db.count("Approval Matrix", {"document_type": document_type, "docstatus": 1})
	wf = frappe.db.get_value("Workflow", {"document_type": document_type}, "name")
	if wf:
		if remaining:
			build_workflow(document_type)  # rebuild without the cancelled matrix
		else:
			frappe.db.set_value("Workflow", wf, "is_active", 0)
	frappe.clear_cache(doctype=document_type)
