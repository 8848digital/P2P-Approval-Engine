# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Keeps role -> user assignments in sync with the approver pools on submitted
Approval Matrix records.
"""

import frappe

from approval_engine.approval_core.workflow_config import MAX_LEVELS, pool, role_name


def reconcile_roles(document_type):
	"""
	Align `<DocType> - Approver N` role holders with the users named in submitted matrices.

	Grants the role to users newly added to a tier and revokes it from users no longer in
	any row of that tier, so cancelling or editing a matrix cannot leave stale approvers.

	Parameters:
	    document_type (str, required): Target DocType.

	Returns:
	    None
	"""
	matrices = frappe.get_all(
		"Approval Matrix",
		filters={"document_type": document_type, "docstatus": 1},
		pluck="name",
	)
	desired = {level: set() for level in range(1, MAX_LEVELS + 1)}
	for mname in matrices:
		m = frappe.get_doc("Approval Matrix", mname)
		for row in m.detail:
			for level in range(1, MAX_LEVELS + 1):
				for user in pool(row, level):
					desired[level].add(user)

	for level in range(1, MAX_LEVELS + 1):
		role = role_name(document_type, level)
		current = set(
			frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
		)
		for user in desired[level] - current:
			_grant_role(user, role)
		for user in current - desired[level]:
			_revoke_role(user, role)


def _grant_role(user, role):
	"""
	Give a user an approver role, skipping Administrator/Guest and unknown users.

	Parameters:
	    user (str, required): User ID.
	    role (str, required): Role name.

	Returns:
	    None
	"""
	if user in ("Administrator", "Guest") or not frappe.db.exists("User", user):
		return
	frappe.get_doc("User", user).add_roles(role)


def _revoke_role(user, role):
	"""
	Remove an approver role from a user, ignoring users that no longer exist.

	Parameters:
	    user (str, required): User ID.
	    role (str, required): Role name.

	Returns:
	    None
	"""
	if not frappe.db.exists("User", user):
		return
	frappe.get_doc("User", user).remove_roles(role)
