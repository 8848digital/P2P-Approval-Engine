# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Builds the literal Workflow (states and per-row transitions) for a target
DocType from its submitted Approval Matrix records.
"""

import frappe

from approval_engine.approval_core.workflow_config import (
	ALLOW_EDIT,
	MAX_LEVELS,
	STATE_DOCSTATUS,
	STATE_FOR_TIER,
	STATE_ORDER,
	amount_field_for,
	band_condition,
	configured_levels,
	pool,
	role_name,
	workflow_name,
)


def _t(state, action, next_state, allowed, condition):
	return {
		"state": state,
		"action": action,
		"next_state": next_state,
		"allowed": allowed,
		"condition": condition,
		"allow_self_approval": 1,
	}


def build_transitions(document_type):
	amt = amount_field_for(document_type)
	transitions = []

	matrices = frappe.get_all(
		"Approval Matrix",
		filters={"document_type": document_type, "docstatus": 1},
		pluck="name",
	)
	for mname in matrices:
		m = frappe.get_doc("Approval Matrix", mname)
		for row in m.detail:
			levels = configured_levels(row)
			if not levels:
				continue
			band = band_condition(amt, row.min_amount, row.max_amount)
			gate = f"doc.company == {m.company!r} and doc.department == {row.department!r}"
			if band:
				gate = f"{gate} and {band}"

			for level in levels:
				role = role_name(document_type, level)
				# Condition = company + department + amount band + this row's tier pool.
				# The Role is still the coarse gate, but the embedded pool clause pins
				# eligibility to the specific approvers configured for THIS row/tier, so a
				# same-tier approver from another row/department can no longer act here
				# even though they hold the shared `<DocType> - Approver N` role.
				base = f"{gate} and frappe.session.user in {pool(row, level)!r}"
				src = STATE_FOR_TIER[level]
				can_hold = row.get(f"approver_{level}_can_hold")
				can_reject = row.get(f"approver_{level}_can_reject")
				hold_state = f"On Hold by Approver {level}"

				# --- Approve: escalate vs finalize decided at RUNTIME by reading the
				# matrix row live (is the NEXT approver tier configured?). Both
				# transitions are emitted; the condition selects which one fires. ---
				if level < MAX_LEVELS:
					# readable-filter form: identify the matrix row by
					# matrix + department + band (matches the client's Excel intent)
					next_configured = (
						"frappe.db.get_value('Approval Matrix Detail', "
						f"{{'parent': {m.name!r}, 'department': {row.department!r}, "
						f"'min_amount': {row.min_amount or 0}, 'max_amount': {row.max_amount or 0}}}, "
						f"'approver_{level + 1}_user_1')"
					)
					esc_cond = f"{base} and {next_configured}"  # next tier exists -> escalate
					fin_cond = f"{base} and not {next_configured}"  # next tier blank  -> finalize
					transitions.append(_t(src, "Approve", f"Approved {level}", role, esc_cond))
					transitions.append(_t(src, "Approve", "Approved", role, fin_cond))
					if can_hold:
						transitions.append(_t(hold_state, "Approve", f"Approved {level}", role, esc_cond))
						transitions.append(_t(hold_state, "Approve", "Approved", role, fin_cond))
				else:
					# top tier (4): no next approver -> always finalize
					transitions.append(_t(src, "Approve", "Approved", role, base))
					if can_hold:
						transitions.append(_t(hold_state, "Approve", "Approved", role, base))

				# --- Hold / Reject (company + dept + band + pool + no-repeat) ---
				if can_hold:
					transitions.append(_t(src, "Hold", hold_state, role, base))
					if can_reject:
						transitions.append(_t(hold_state, "Reject", "Rejected", role, base))
				if can_reject:
					transitions.append(_t(src, "Reject", "Rejected", role, base))

	return transitions


def _allow_edit(document_type, state):
	v = ALLOW_EDIT[state]
	return "All" if v == "All" else role_name(document_type, v)


def build_workflow(document_type):
	existing = frappe.db.get_value("Workflow", {"document_type": document_type}, "name")
	if existing:
		wf = frappe.get_doc("Workflow", existing)
		wf.states = []
		wf.transitions = []
	else:
		wf = frappe.new_doc("Workflow")
		wf.workflow_name = workflow_name(document_type)

	wf.document_type = document_type
	wf.is_active = 1
	wf.workflow_state_field = "workflow_state"
	wf.send_email_alert = 0
	wf.override_status = 0

	for state in STATE_ORDER:
		wf.append(
			"states",
			{
				"state": state,
				"doc_status": STATE_DOCSTATUS[state],
				"allow_edit": _allow_edit(document_type, state),
			},
		)
	for tr in build_transitions(document_type):
		wf.append("transitions", tr)

	wf.save(ignore_permissions=True)
	return wf.name
