# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
import frappe

from approval_engine.approval_core.generator import (
	ensure_role_permissions,
	ensure_roles,
	ensure_workflow_states,
)


def execute():
	"""
	Backfill the per-DocType additional approver role on existing sites.

	The additional approver feature introduced a role ("<DocType> - Additional
	Approver") that generated workflow transitions reference in their `allowed`
	field. On sites whose matrices were submitted before the feature shipped, the
	role was never created — so cancelling a matrix raised LinkValidationError when
	the rebuilt workflow referenced it. (A sibling patch already backfills the
	Workflow State masters; ensure_workflow_states is repeated here idempotently so
	this patch is self-contained.)

	Creates the additional role and its DocType permissions for every DocType that
	has an Approval Matrix.

	Returns:
		None
	"""
	ensure_workflow_states()

	document_types = frappe.get_all(
		"Approval Matrix", distinct=True, pluck="document_type"
	)
	for document_type in document_types:
		ensure_roles(document_type)
		ensure_role_permissions(document_type)
