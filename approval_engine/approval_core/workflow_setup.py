# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Idempotent setup the generated Workflows depend on: roles, permissions,
workflow states/actions and the fields added to target DocTypes.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from approval_engine.approval_core.workflow_config import (
	ACTIONS,
	DEFAULT_AMOUNT_FIELDS,
	MAX_LEVELS,
	STATE_ORDER,
	WORKFLOW_STATE_STYLES,
	role_name,
)


def ensure_roles(document_type):
	for level in range(1, MAX_LEVELS + 1):
		name = role_name(document_type, level)
		if not frappe.db.exists("Role", name):
			frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def ensure_role_permissions(document_type):
	"""Grant read/write/submit on the target DocType to each approver role,
	so approvers can open and act on the document."""
	from frappe.permissions import add_permission, update_permission_property

	for level in range(1, MAX_LEVELS + 1):
		role = role_name(document_type, level)
		has_perm = frappe.db.exists(
			"Custom DocPerm", {"parent": document_type, "role": role, "permlevel": 0}
		)
		if not has_perm:
			add_permission(document_type, role, 0)
		for ptype in ("read", "write", "submit"):
			update_permission_property(document_type, role, 0, ptype, 1)


def _grant_read_to_flow_roles(target_doctype, document_type):
	"""Grant read on `target_doctype` to every role that touches `document_type`'s flow: its
	approver roles, and any role that can already create the target document. A real,
	admin-visible/editable Custom DocPerm (shows up in Role Permission Manager like any other
	permission) -- deliberately NOT a permission bypass at the query/API layer, so the admin
	stays in control of it exactly like any other grant in the system.
	"""
	from frappe.permissions import add_permission, update_permission_property

	roles = {role_name(document_type, level) for level in range(1, MAX_LEVELS + 1)}
	for perm_dt in ("DocPerm", "Custom DocPerm"):
		roles.update(
			frappe.get_all(
				perm_dt, filters={"parent": document_type, "create": 1, "permlevel": 0}, pluck="role"
			)
		)

	for role in roles:
		already = frappe.db.exists(
			"Custom DocPerm", {"parent": target_doctype, "role": role, "permlevel": 0}
		) or frappe.db.exists("DocPerm", {"parent": target_doctype, "role": role, "permlevel": 0})
		if not already:
			add_permission(target_doctype, role, 0)
		update_permission_property(target_doctype, role, 0, "read", 1)


def ensure_department_read(document_type):
	"""Grant read on `Department` to everyone who touches the flow.

	`Department` is HR-restricted by default. Since the engine adds a `department`
	field to the target DocType and requires it for routing, the document's
	creators (roles that can create the target) and the approver roles must be able
	to read Department, or saving/opening the document raises
	'Insufficient Permission for Department'. (Department names aren't sensitive;
	this grants READ only.)
	"""
	_grant_read_to_flow_roles("Department", document_type)


def ensure_company_read(document_type):
	"""Grant read on `Company` to everyone who touches the flow.

	`Company` is ERPNext-restricted to specific business roles (Accounts User, Employee,
	etc.) by default, but an approver needs to see company names regardless of their
	business-role footprint -- e.g. the Finance dashboard's company selector, which any
	approver should be able to use. Same reasoning as ensure_department_read. (Company
	name/abbr/tax_id aren't sensitive; this grants READ only.)
	"""
	_grant_read_to_flow_roles("Company", document_type)


def ensure_actions():
	for action in ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{
					"doctype": "Workflow Action Master",
					"workflow_action_name": action,
				}
			).insert(ignore_permissions=True)


def ensure_workflow_states():
	for name in STATE_ORDER:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{
					"doctype": "Workflow State",
					"workflow_state_name": name,
					"style": WORKFLOW_STATE_STYLES.get(name, ""),
				}
			).insert(ignore_permissions=True)


def ensure_amount_field(document_type):
	settings = frappe.get_single("Approval Settings")
	if not any(r.document_type == document_type for r in settings.amount_fields):
		settings.append(
			"amount_fields",
			{
				"document_type": document_type,
				"amount_field": DEFAULT_AMOUNT_FIELDS.get(document_type, "grand_total"),
			},
		)
		settings.save(ignore_permissions=True)


LEGACY_HISTORY_FIELDS = ("ae_section", "custom_workflow_history")


def remove_legacy_history_field(document_type):
	"""Drop the old per-DocType `custom_workflow_history` child-table field, if present.

	History now lives centrally in `Document Workflow Log` (reference_doctype/reference_name)
	instead of a Table field added to every target DocType — no per-DocType schema needed.
	"""
	for fieldname in LEGACY_HISTORY_FIELDS:
		name = f"{document_type}-{fieldname}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)


# A routing department must belong to the document's own company: the generated conditions pair
# `doc.company == X` with `doc.department == Y`, and Approval Matrix rows are restricted the same
# way. `eval:` is resolved client-side against the open document (see link.js parse_filters).
DEPARTMENT_LINK_FILTERS = json.dumps(
	[
		["Department", "company", "=", "eval:doc.company"],
		["Department", "is_group", "=", 0],
	]
)


def ensure_department_field(document_type):
	"""Ensure the target DocType has a `department` field (routing needs it), with the picker
	scoped to the document's company."""
	if frappe.get_meta(document_type).get_field("department"):
		_backfill_department_link_filters(document_type)
		return
	create_custom_fields(
		{
			document_type: [
				{
					"fieldname": "department",
					"fieldtype": "Link",
					"label": "Department",
					"options": "Department",
					"insert_after": "company",
					"link_filters": DEPARTMENT_LINK_FILTERS,
				},
			]
		},
		ignore_validate=True,
	)


def _backfill_department_link_filters(document_type):
	"""Add the company filter to a `department` Custom Field created before the filter existed.

	Only OUR Custom Field is touched (a standard `department` field on the target DocType is left
	alone), and only when no filter is configured — so a filter someone tuned by hand survives.
	"""
	name = frappe.db.exists("Custom Field", {"dt": document_type, "fieldname": "department"})
	if not name or frappe.db.get_value("Custom Field", name, "link_filters"):
		return
	frappe.db.set_value("Custom Field", name, "link_filters", DEPARTMENT_LINK_FILTERS)
	frappe.clear_cache(doctype=document_type)
